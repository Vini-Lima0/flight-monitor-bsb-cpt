"""Envio de alerta por e-mail via SMTP.

Padrão: Gmail com "senha de app" (ver passo a passo no README). Pra trocar
de provedor, basta ajustar SMTP_SERVER/SMTP_PORT nos Secrets — o resto do
código não muda.
"""

import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def enviar_email(
    smtp_server: str,
    smtp_port: int,
    remetente: str,
    senha_app: str,
    destinatario: str,
    assunto: str,
    corpo: str,
) -> None:
    if not remetente or not senha_app or not destinatario:
        logger.warning("Credenciais de e-mail incompletas, pulando alerta por e-mail")
        return

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = destinatario
    msg.set_content(corpo)

    with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15) as smtp:
        smtp.login(remetente, senha_app)
        smtp.send_message(msg)
