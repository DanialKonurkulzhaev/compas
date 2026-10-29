"""Отправка письма для сброса пароля."""

import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode

from fastapi import HTTPException
from src.config import settings
from src.services.auth import serializer


def send_email_to_recover_password(email: str):
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise HTTPException(503, "Почтовая отправка не настроена")
    token = serializer.dumps(email)
    message = EmailMessage()
    message["Subject"] = "Compas: восстановление пароля"
    message["From"] = settings.SMTP_FROM
    message["To"] = email
    separator = "&" if "?" in settings.PASSWORD_RESET_URL else "?"
    message.set_content(
        settings.PASSWORD_RESET_URL + separator + urlencode({"token": token})
    )
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as connection:
        connection.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER:
            connection.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        connection.send_message(message)
