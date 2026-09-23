"""Monitor de preços de passagens aéreas.

Fluxo:
1. Lê config.yaml (rota/datas/preço-limite) e credenciais (env vars / .env local).
2. Tenta o Google Flights; se falhar, cai para o Skyscanner.
3. Registra a leitura no histórico (data/history.csv).
4. Compara com o preço-limite (e reporta se também é o menor já visto).
5. Se estiver abaixo do limite e for um preço novo mais baixo, alerta no Telegram.

Qualquer erro de scraping é logado e o script termina sem quebrar o
workflow — a próxima execução (30 min depois) tenta de novo.
"""

import logging
import os
import sys

import yaml
from dotenv import load_dotenv

import storage
from datas import calcular_datas_busca
from notify.telegram import enviar_telegram
from scrapers import google_flights, skyscanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("flight_monitor")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def carregar_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def buscar_preco_atual(cfg: dict) -> tuple[float, str, str]:
    """Tenta Google Flights primeiro; se falhar, cai para o Skyscanner.

    Retorna (preco, fonte, url_do_trajeto). Levanta RuntimeError se ambas
    as fontes falharem.
    """
    args = (cfg["origem"], cfg["destino"], cfg["data_ida"], cfg["data_volta"], cfg["moeda"])

    try:
        logger.info("Buscando preço no Google Flights...")
        preco = google_flights.buscar_menor_preco(*args)
        return preco, "google_flights", google_flights.montar_url(*args)
    except Exception as e:
        logger.warning("Google Flights falhou (%s), tentando fallback no Skyscanner", e)

    try:
        preco = skyscanner.buscar_menor_preco(*args)
        return preco, "skyscanner", skyscanner.montar_url(*args)
    except Exception as e:
        raise RuntimeError(f"Google Flights e Skyscanner falharam: {e}") from e


def montar_mensagem(cfg: dict, preco: float, fonte: str, motivo: str, url: str) -> str:
    return (
        f"✈️ Alerta de preço {cfg['origem']} → {cfg['destino']}\n"
        f"Preço atual: {cfg['moeda']} {preco:,.2f}\n"
        f"Ida: {cfg['data_ida']} | Volta: {cfg['data_volta']}\n"
        f"Motivo: {motivo}\n"
        f"Fonte: {fonte}\n"
        f"Ver trajeto: {url}"
    )


def disparar_alertas(mensagem: str) -> bool:
    """Envia o alerta pelo Telegram. Retorna True se foi de fato enviado
    (para não marcar como "alertado" um preço que não gerou notificação)."""
    return enviar_telegram(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        mensagem=mensagem,
    )


def main() -> int:
    load_dotenv()  # no-op se não houver .env (caso do GitHub Actions, que usa Secrets)
    cfg = carregar_config()

    data_ida, data_volta, e_data_alvo = calcular_datas_busca(cfg)
    cfg["data_ida"], cfg["data_volta"] = data_ida, data_volta
    if e_data_alvo:
        logger.info("Viagem alvo (%s a %s) já está dentro do horizonte de busca.", data_ida, data_volta)
    else:
        logger.info(
            "Viagem alvo (%s a %s) ainda fora do horizonte de busca (%s dias). "
            "Buscando a data máxima disponível hoje: %s a %s.",
            cfg["data_ida_alvo"],
            cfg["data_volta_alvo"],
            cfg.get("horizonte_max_dias", 330),
            data_ida,
            data_volta,
        )

    try:
        preco_atual, fonte, url = buscar_preco_atual(cfg)
    except RuntimeError as e:
        logger.error("Não foi possível obter o preço nesta execução: %s", e)
        return 0  # não quebra o workflow — tenta de novo na próxima execução

    logger.info("Preço encontrado: %s %.2f (fonte: %s)", cfg["moeda"], preco_atual, fonte)

    menor_historico = storage.lowest_historical_price(data_ida, data_volta)
    storage.append_history(
        preco=preco_atual,
        moeda=cfg["moeda"],
        fonte=fonte,
        data_ida=cfg["data_ida"],
        data_volta=cfg["data_volta"],
    )

    # O preço-limite é a condição obrigatória: nada acima dele vira alerta,
    # mesmo que seja um novo mínimo histórico (senão o bot avisaria de quedas
    # que ainda estão muito acima do valor que você toparia pagar).
    if preco_atual >= cfg["preco_limite"]:
        logger.info(
            "Preço (%.2f) está acima do limite de %.2f. Nada a fazer.",
            preco_atual,
            cfg["preco_limite"],
        )
        return 0

    motivos = [f"abaixo do preço-limite ({cfg['moeda']} {cfg['preco_limite']:,.2f})"]
    if menor_historico is not None and preco_atual < menor_historico:
        motivos.append(f"novo menor preço histórico (anterior: {cfg['moeda']} {menor_historico:,.2f})")

    estado = storage.load_alert_state()
    menor_ja_alertado = storage.lowest_alerted_price_for(
        estado, cfg["origem"], cfg["destino"], data_ida, data_volta
    )
    if menor_ja_alertado is not None and preco_atual >= menor_ja_alertado:
        logger.info(
            "Preço (%.2f) não é menor que o último já alertado (%.2f) para esta rota/data. "
            "Evitando alerta repetido.",
            preco_atual,
            menor_ja_alertado,
        )
        return 0

    mensagem = montar_mensagem(cfg, preco_atual, fonte, " e ".join(motivos), url)
    logger.info("Disparando alerta: %s", mensagem.replace("\n", " | "))

    try:
        enviado = disparar_alertas(mensagem)
    except Exception as e:
        # Falha de rede/API não deve derrubar o workflow — tenta de novo na
        # próxima execução (o preço já foi registrado no histórico acima).
        logger.error("Falha ao enviar alerta no Telegram: %s", e)
        return 0

    if not enviado:
        logger.warning(
            "Telegram não configurado (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID). "
            "Configure os GitHub Secrets — ver README."
        )
        return 0

    storage.save_alert_state(
        {
            "origem": cfg["origem"],
            "destino": cfg["destino"],
            "data_ida": data_ida,
            "data_volta": data_volta,
            "lowest_alerted_price": preco_atual,
        }
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
