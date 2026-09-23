"""Monitor de preços de passagens aéreas, com datas flexíveis no mês.

Fluxo:
1. Lê config.yaml (rota, mês alvo, duração, preço-limite) e o token do
   Telegram (variáveis de ambiente / .env local).
2. Abre o calendário de preços do Google Flights em algumas datas semente
   que, juntas, cobrem o mês inteiro, e coleta todas as combinações de
   ida/volta com a duração pedida.
3. Fica com a combinação mais barata e registra a leitura no histórico.
4. Só considera alertar se esse preço estiver abaixo do preço-limite.
5. Se for um preço novo mais baixo, alerta no Telegram com as datas
   vencedoras e o link do trajeto.

Erros de scraping são logados e o script termina sem quebrar o workflow —
a próxima execução tenta de novo.
"""

import logging
import os
import sys
from datetime import date

import yaml
from dotenv import load_dotenv

import storage
from datas import combinacao_valida, datas_semente
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


def buscar_melhor_combinacao(cfg: dict) -> tuple[float, date, date, str]:
    """Varre o mês alvo e devolve (preco, ida, volta, fonte) mais barato.

    Levanta RuntimeError se nenhuma fonte devolver combinação utilizável.
    """
    sementes, dentro_do_mes = datas_semente(cfg)
    if not dentro_do_mes:
        logger.info(
            "Mês alvo %s ainda está além do horizonte de busca (%s dias). "
            "Buscando a data máxima alcançável hoje: %s.",
            cfg["mes_alvo"],
            cfg.get("horizonte_max_dias", 330),
            sementes[0][0],
        )

    candidatas: list[tuple[float, date, date]] = []
    for data_ida, data_volta in sementes:
        try:
            combinacoes = google_flights.buscar_combinacoes(
                cfg["origem"], cfg["destino"], data_ida, data_volta, cfg["moeda"]
            )
        except Exception as e:
            logger.warning("Calendário falhou para a semente %s (%s)", data_ida, e)
            continue

        if dentro_do_mes:
            validas = [c for c in combinacoes if combinacao_valida(cfg, c[1], c[2])]
        else:
            # Fora do mês alvo só interessa manter a duração pedida.
            validas = [c for c in combinacoes if (c[2] - c[1]).days == int(cfg["duracao_dias"])]

        logger.info(
            "Semente %s: %d combinações lidas, %d utilizáveis%s",
            data_ida,
            len(combinacoes),
            len(validas),
            f" (menor: {min(c[0] for c in validas):,.2f})" if validas else "",
        )
        candidatas.extend(validas)

    if candidatas:
        preco, ida, volta = min(candidatas, key=lambda c: c[0])
        return preco, ida, volta, "google_flights"

    # Fallback: par de datas fixo na primeira semente.
    data_ida, data_volta = sementes[0]
    try:
        preco = skyscanner.buscar_menor_preco(
            cfg["origem"], cfg["destino"], data_ida, data_volta, cfg["moeda"]
        )
        return preco, date.fromisoformat(data_ida), date.fromisoformat(data_volta), "skyscanner"
    except Exception as e:
        raise RuntimeError(f"Google Flights e Skyscanner falharam: {e}") from e


def montar_mensagem(cfg: dict, preco: float, ida: date, volta: date, fonte: str, motivo: str, url: str) -> str:
    return (
        f"✈️ Alerta de preço {cfg['origem']} → {cfg['destino']}\n"
        f"Preço: {cfg['moeda']} {preco:,.2f}\n"
        f"Melhores datas: {ida.strftime('%d/%m/%Y')} → {volta.strftime('%d/%m/%Y')} "
        f"({(volta - ida).days} dias)\n"
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

    logger.info(
        "Buscando %s → %s | mês %s | %s dias de viagem | datas flexíveis",
        cfg["origem"],
        cfg["destino"],
        cfg["mes_alvo"],
        cfg["duracao_dias"],
    )

    try:
        preco_atual, ida, volta, fonte = buscar_melhor_combinacao(cfg)
    except RuntimeError as e:
        logger.error("Não foi possível obter o preço nesta execução: %s", e)
        return 0  # não quebra o workflow — tenta de novo na próxima execução

    logger.info(
        "Melhor combinação: %s %.2f em %s → %s (fonte: %s)",
        cfg["moeda"],
        preco_atual,
        ida,
        volta,
        fonte,
    )

    menor_historico = storage.lowest_historical_price(
        cfg["mes_alvo"], int(cfg["duracao_dias"])
    )
    storage.append_history(
        preco=preco_atual,
        moeda=cfg["moeda"],
        fonte=fonte,
        data_ida=ida.isoformat(),
        data_volta=volta.isoformat(),
    )

    # O preço-limite é a condição obrigatória: nada acima dele vira alerta,
    # mesmo que seja um novo mínimo histórico.
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
        estado, cfg["origem"], cfg["destino"], cfg["mes_alvo"], int(cfg["duracao_dias"])
    )
    if menor_ja_alertado is not None and preco_atual >= menor_ja_alertado:
        logger.info(
            "Preço (%.2f) não é menor que o último já alertado (%.2f) para esta rota/mês. "
            "Evitando alerta repetido.",
            preco_atual,
            menor_ja_alertado,
        )
        return 0

    url = google_flights.montar_url(
        cfg["origem"], cfg["destino"], ida.isoformat(), volta.isoformat(), cfg["moeda"]
    )
    mensagem = montar_mensagem(cfg, preco_atual, ida, volta, fonte, " e ".join(motivos), url)
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
            "mes_alvo": cfg["mes_alvo"],
            "duracao_dias": int(cfg["duracao_dias"]),
            "data_ida": ida.isoformat(),
            "data_volta": volta.isoformat(),
            "lowest_alerted_price": preco_atual,
        }
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
