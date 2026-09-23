"""Envio de alerta via Telegram Bot API.

Passo a passo pra criar o bot e obter o chat_id está no README.
"""

import logging

import requests

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def enviar_telegram(token: str, chat_id: str, mensagem: str) -> bool:
    """Envia a mensagem e retorna True se foi de fato enviada (credenciais presentes)."""
    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados, pulando alerta do Telegram")
        return False

    resposta = requests.post(
        API_URL.format(token=token),
        json={"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"},
        timeout=15,
    )
    resposta.raise_for_status()
    return True
