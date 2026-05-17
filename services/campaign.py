from __future__ import annotations

from datetime import datetime, timezone

from config import MAX_EMAILS_PER_CAMPAIGN
from models import (
    add_delivery_log,
    get_active_recipients,
    get_campaign,
    set_campaign_status,
)
from services.mailer import send_campaign_email


def run_campaign(campaign_id: int) -> dict[str, int]:
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError("Кампания не найдена")
    if campaign["status"] not in ("draft", "running"):
        raise ValueError("Кампания уже отправлена")

    set_campaign_status(campaign_id, "running")
    recipients = get_active_recipients(MAX_EMAILS_PER_CAMPAIGN)
    stats = {"sent": 0, "error": 0, "total": len(recipients)}

    subject = campaign["subject"] or "Анонс"
    image_path = campaign["image_path"]

    for row in recipients:
        result = send_campaign_email(
            to_email=row["email"],
            to_name=row["name"] or "",
            subject=subject,
            body_text=campaign["body_text"],
            link_url=campaign["link_url"] or "",
            unsubscribe_token=row["unsubscribe_token"],
            image_path=image_path,
        )
        if result.ok:
            stats["sent"] += 1
            add_delivery_log(
                campaign_id,
                row["id"],
                row["email"],
                row["name"] or "",
                "sent",
            )
        else:
            stats["error"] += 1
            add_delivery_log(
                campaign_id,
                row["id"],
                row["email"],
                row["name"] or "",
                "error",
                result.error,
            )

    sent_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    set_campaign_status(campaign_id, "sent", sent_at=sent_at)
    return stats


def send_test(campaign_id: int, test_email: str) -> tuple[bool, str]:
    from services.mailer import send_campaign_email

    campaign = get_campaign(campaign_id)
    if not campaign:
        return False, "Сначала сохраните черновик"

    result = send_campaign_email(
        to_email=test_email,
        to_name="Тест",
        subject="[Тест] " + (campaign["subject"] or "Анонс"),
        body_text=campaign["body_text"],
        link_url=campaign["link_url"] or "",
        unsubscribe_token="test-token-no-unsubscribe",
        image_path=campaign["image_path"],
    )
    return result.ok, result.error
