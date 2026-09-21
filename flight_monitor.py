"""Monitor de preços de passagens aéreas.

Fluxo:
1. Lê config.yaml (rota/datas/preço-limite) e credenciais (env vars / .env local).
2. Tenta o Google Flights; se falhar, cai para o Skyscanner.
3. Registra a leitura no histórico (data/history.csv).
4. Compara com o preço-limite e com o menor preço já visto.
5. Se for um preço novo e mais baixo, dispara alerta no Telegram E por e-mail juntos.

Qualquer erro de scraping é logado e o script termina sem quebrar o
workflow — a próxima execução (30 min depois) tenta de novo.
"""

import logging
import os
import sys

import yaml
from dotenv import load_dotenv

import storage
from notify.email_notifier import enviar_email
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


def buscar_preco_atual(cfg: dict) -> tuple[float, str]:
    """Tenta Google Flights primeiro; se falhar, cai para o Skyscanner.

    Retorna (preco, fonte). Levanta RuntimeError se ambas as fontes falharem.
    """
    args = (cfg["origem"], cfg["destino"], cfg["data_ida"], cfg["data_volta"], cfg["moeda"])

    try:
        logger.info("Buscando preço no Google Flights...")
        preco = google_flights.buscar_menor_preco(*args)
        return preco, "google_flights"
    except Exception as e:
        logger.warning("Google Flights falhou (%s), tentando fallback no Skyscanner", e)

    try:
        preco = skyscanner.buscar_menor_preco(*args)
        return preco, "skyscanner"
    except Exception as e:
        raise RuntimeError(f"Google Flights e Skyscanner falharam: {e}") from e


def montar_mensagem(cfg: dict, preco: float, fonte: str, motivo: str) -> str:
    return (
        f"✈️ Alerta de preço {cfg['origem']} → {cfg['destino']}\n"
        f"Preço atual: {cfg['moeda']} {preco:,.2f}\n"
        f"Ida: {cfg['data_ida']} | Volta: {cfg['data_volta']}\n"
        f"Motivo: {motivo}\n"
        f"Fonte: {fonte}"
    )


def disparar_alertas(cfg: dict, mensagem: str) -> None:
    enviar_telegram(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        mensagem=mensagem,
    )
    enviar_email(
        # `or` (em vez de get(..., default)) porque secrets não configurados
        # no GitHub Actions chegam como string vazia, não como variável ausente.
        smtp_server=os.environ.get("SMTP_SERVER") or "smtp.gmail.com",
        smtp_port=int(os.environ.get("SMTP_PORT") or "465"),
        remetente=os.environ.get("EMAIL_SENDER", ""),
        senha_app=os.environ.get("EMAIL_APP_PASSWORD", ""),
        destinatario=cfg["destinatario_email"],
        assunto=f"Alerta de preço: {cfg['origem']} -> {cfg['destino']}",
        corpo=mensagem,
    )


def main() -> int:
    load_dotenv()  # no-op se não houver .env (caso do GitHub Actions, que usa Secrets)
    cfg = carregar_config()

    try:
        preco_atual, fonte = buscar_preco_atual(cfg)
    except RuntimeError as e:
        logger.error("Não foi possível obter o preço nesta execução: %s", e)
        return 0  # não quebra o workflow — tenta de novo na próxima execução

    logger.info("Preço encontrado: %s %.2f (fonte: %s)", cfg["moeda"], preco_atual, fonte)

    menor_historico = storage.lowest_historical_price()
    storage.append_history(
        preco=preco_atual,
        moeda=cfg["moeda"],
        fonte=fonte,
        data_ida=cfg["data_ida"],
        data_volta=cfg["data_volta"],
    )

    motivos = []
    if preco_atual < cfg["preco_limite"]:
        motivos.append(f"abaixo do preço-limite ({cfg['moeda']} {cfg['preco_limite']:,.2f})")
    if menor_historico is not None and preco_atual < menor_historico:
        motivos.append(f"novo menor preço histórico (anterior: {cfg['moeda']} {menor_historico:,.2f})")

    if not motivos:
        logger.info("Preço não é vantajoso o suficiente para alertar. Nada a fazer.")
        return 0

    estado = storage.load_alert_state()
    menor_ja_alertado = estado.get("lowest_alerted_price")
    if menor_ja_alertado is not None and preco_atual >= menor_ja_alertado:
        logger.info(
            "Preço (%.2f) não é menor que o último já alertado (%.2f). Evitando alerta repetido.",
            preco_atual,
            menor_ja_alertado,
        )
        return 0

    mensagem = montar_mensagem(cfg, preco_atual, fonte, " e ".join(motivos))
    logger.info("Disparando alertas: %s", mensagem.replace("\n", " | "))
    disparar_alertas(cfg, mensagem)

    estado["lowest_alerted_price"] = preco_atual
    storage.save_alert_state(estado)

    return 0


if __name__ == "__main__":
    sys.exit(main())
