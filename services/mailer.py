from __future__ import annotations

import mimetypes
import smtplib
import ssl
import time
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import NamedTuple

from config import (
    MAIL_DELAY_SECONDS,
    PUBLIC_BASE_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_SSL,
    SMTP_USER,
)


class SendResult(NamedTuple):
    ok: bool
    error: str = ""


def _format_smtp_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "535" in text or "parol prilozheniya" in text or "application password" in text:
        return (
            "Mail.ru требует пароль для внешнего приложения (не основной пароль от почты). "
            "Создайте его: Почта Mail.ru → Настройки → Безопасность → "
            "Пароли для внешних приложений → вставьте в SMTP_PASSWORD в .env и перезапустите app.py. "
            "Справка: https://help.mail.ru/mail/security/protection/external"
        )
    return f"SMTP: {exc}"


def smtp_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD and SMTP_FROM)


def _build_bodies(
    body_text: str,
    link_url: str,
    unsubscribe_url: str,
    recipient_name: str,
) -> tuple[str, str]:
    greeting = f"Здравствуйте{', ' + recipient_name if recipient_name else ''}!\n\n"
    link_line = f"Ссылка: {link_url}\n" if link_url else ""
    footer_plain = f"\n\n---\n{link_line}Отписаться от рассылки: {unsubscribe_url}\n"

    plain = greeting + body_text.strip() + footer_plain

    link_html = ""
    if link_url:
        link_html = (
            f'<p style="margin:16px 0;">'
            f'<a href="{link_url}" style="display:inline-block;padding:12px 20px;'
            f'background:#3d6eb5;color:#fff;text-decoration:none;border-radius:6px;">'
            f"Перейти по ссылке</a></p>"
        )

    html_body = (
        f"<p>{greeting.replace(chr(10), '<br>')}</p>"
        f"<p>{body_text.strip().replace(chr(10), '<br>')}</p>"
        f"{link_html}"
        f'<p style="font-size:12px;color:#666;margin-top:24px;">'
        f'<a href="{unsubscribe_url}">Отписаться от рассылки</a></p>'
    )
    return plain, html_body


def send_campaign_email(
    *,
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    link_url: str,
    unsubscribe_token: str,
    image_path: str | None,
) -> SendResult:
    if not smtp_configured():
        return SendResult(False, "SMTP не настроен: заполните .env")

    unsubscribe_url = f"{PUBLIC_BASE_URL.rstrip('/')}/unsubscribe/{unsubscribe_token}"
    plain, html = _build_bodies(body_text, link_url, unsubscribe_url, to_name)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(plain, "plain", "utf-8"))
    alternative.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alternative)

    if image_path and Path(image_path).is_file():
        path = Path(image_path)
        mime_type, _ = mimetypes.guess_type(path.name)
        subtype = (mime_type or "image/jpeg").split("/")[-1]
        with path.open("rb") as fh:
            img = MIMEImage(fh.read(), _subtype=subtype)
        img.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(img)

    try:
        if SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        if MAIL_DELAY_SECONDS > 0:
            time.sleep(MAIL_DELAY_SECONDS)
        return SendResult(True)
    except smtplib.SMTPAuthenticationError as exc:
        return SendResult(False, _format_smtp_error(exc))
    except smtplib.SMTPException as exc:
        return SendResult(False, _format_smtp_error(exc))
    except OSError as exc:
        return SendResult(False, f"Сеть: {exc}")
