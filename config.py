from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    if not value:
        return default
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


DEMO_CSV = BASE_DIR / "data" / "demo_recipients.csv"

APP_NAME = "AnonsPost"
APP_TAGLINE = "Панель ручных email-рассылок"

DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "anonspost.db")
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

FLASK_SECRET_KEY = _env("FLASK_SECRET_KEY", "change-me-in-production")
ADMIN_LOGIN = _env("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "admin")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mail.ru")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes")

TEST_EMAIL = os.getenv("TEST_EMAIL", SMTP_USER or "")
MAX_EMAILS_PER_CAMPAIGN = int(os.getenv("MAX_EMAILS_PER_CAMPAIGN", "50"))
MAIL_DELAY_SECONDS = float(os.getenv("MAIL_DELAY_SECONDS", "1.0"))

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000")
