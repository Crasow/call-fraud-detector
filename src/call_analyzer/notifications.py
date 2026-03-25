import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from call_analyzer.config import settings
from call_analyzer.models import AnalysisResult, Call

logger = logging.getLogger(__name__)


async def send_fraud_alert(call: Call, result: AnalysisResult) -> None:
    if not settings.smtp_password:
        logger.error("SMTP not configured (smtp_password is empty), cannot send fraud alert for %s", call.filename)
        return

    to_addr = settings.alert_email_to or settings.smtp_user

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_user
    msg["To"] = to_addr
    msg["Subject"] = f"Fraud detected: {call.filename}"

    categories = ", ".join(result.fraud_categories) if result.fraud_categories else "N/A"
    reasons = "\n".join(f"  - {r}" for r in result.reasons) if result.reasons else "  N/A"
    transcript = result.transcript or "N/A"

    body = (
        f"Fraud detected in call: {call.filename}\n"
        f"\n"
        f"Score: {result.fraud_score:.2f}\n"
        f"Categories: {categories}\n"
        f"\n"
        f"Reasons:\n{reasons}\n"
        f"\n"
        f"Transcript:\n{transcript}\n"
    )

    msg.attach(MIMEText(body, "plain", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        start_tls=True,
        username=settings.smtp_user,
        password=settings.smtp_password,
    )

    logger.info("Fraud alert email sent for call %s", call.filename)
