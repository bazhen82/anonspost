"""
AnonsPost — панель ручных email-рассылок (портфолио).
Запуск: python app.py  →  http://127.0.0.1:5000
"""

from __future__ import annotations

import csv
import io
import uuid
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    ADMIN_LOGIN,
    ADMIN_PASSWORD,
    APP_NAME,
    APP_TAGLINE,
    DEMO_CSV,
    MAX_EMAILS_PER_CAMPAIGN,
    SMTP_FROM,
    TEST_EMAIL,
    UPLOAD_DIR,
)
from models import (
    count_active_recipients,
    count_unsubscribed,
    delivery_stats,
    get_delivery_report,
    get_latest_draft,
    init_db,
    list_recipients_preview,
    save_draft,
    unsubscribe_by_token,
)
from services.campaign import run_campaign, send_test
from services.importer import import_csv_file
from services.mailer import smtp_configured

app = Flask(__name__)
app.secret_key = __import__("config").FLASK_SECRET_KEY

def _admin_password_hash() -> str:
    """Пересчёт при каждом запуске процесса; после смены .env — перезапустите app.py."""
    return generate_password_hash(ADMIN_PASSWORD)


_admin_hash = _admin_password_hash()


def _verify_admin(login_val: str, password: str) -> bool:
    login_val = (login_val or "").strip()
    password = password or ""
    if login_val != ADMIN_LOGIN:
        return False
    return check_password_hash(_admin_hash, password)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def ensure_db():
    if not getattr(app, "_db_ready", False):
        init_db()
        app._db_ready = True


@app.context_processor
def inject_globals():
    return {
        "app_name": APP_NAME,
        "app_tagline": APP_TAGLINE,
        "max_emails": MAX_EMAILS_PER_CAMPAIGN,
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))
    if request.method == "POST":
        login_val = request.form.get("login", "")
        password = request.form.get("password", "")
        if _verify_admin(login_val, password):
            session["logged_in"] = True
            return redirect(url_for("index"))
        flash(
            "Неверный логин или пароль. Проверьте ADMIN_LOGIN и ADMIN_PASSWORD в .env "
            f"(сейчас логин «{ADMIN_LOGIN}») и перезапустите python app.py.",
            "err",
        )
    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/unsubscribe/<token>")
def unsubscribe(token: str):
    email = unsubscribe_by_token(token)
    return render_template("unsubscribe.html", success=email is not None, email=email)


@app.get("/")
@login_required
def index():
    draft = get_latest_draft()
    last_campaign_id = session.get("last_campaign_id")
    report_stats = None
    report_rows = []
    if last_campaign_id:
        report_stats = delivery_stats(last_campaign_id)
        report_rows = get_delivery_report(last_campaign_id)

    image_url = None
    image_name = None
    if draft and draft["image_path"]:
        path = Path(draft["image_path"])
        if path.is_file():
            image_name = path.name
            image_url = url_for("uploaded_image", name=path.name)

    return render_template(
        "index.html",
        draft=draft,
        active_count=count_active_recipients(),
        unsub_count=count_unsubscribed(),
        preview_rows=list_recipients_preview(15),
        smtp_ok=smtp_configured(),
        smtp_from=SMTP_FROM,
        test_email=TEST_EMAIL or SMTP_FROM or "—",
        image_url=image_url,
        image_name=image_name,
        last_campaign_id=last_campaign_id,
        report_stats=report_stats,
        report_rows=report_rows,
    )


@app.post("/import/demo")
@login_required
def import_demo():
    try:
        stats = import_csv_file(DEMO_CSV)
        flash(
            f"Импорт: +{stats['added']}, обновлено {stats['updated']}, "
            f"некорректных {stats['skipped_invalid']}, отписанных пропущено {stats['skipped_unsubscribed']}.",
            "ok",
        )
    except Exception as exc:
        flash(str(exc), "err")
    return redirect(url_for("index"))


@app.post("/import/csv")
@login_required
def import_csv():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Файл не выбран.", "err")
        return redirect(url_for("index"))
    tmp = UPLOAD_DIR / f"_import_{uuid.uuid4().hex}.csv"
    try:
        f.save(tmp)
        stats = import_csv_file(tmp)
        flash(
            f"Импорт: +{stats['added']}, обновлено {stats['updated']}, "
            f"некорректных {stats['skipped_invalid']}.",
            "ok",
        )
    except Exception as exc:
        flash(str(exc), "err")
    finally:
        tmp.unlink(missing_ok=True)
    return redirect(url_for("index"))


@app.post("/campaign/save", endpoint="save_draft")
@login_required
def save_draft_view():
    subject = request.form.get("subject", "").strip()
    body_text = request.form.get("body_text", "").strip()
    link_url = request.form.get("link_url", "").strip()

    draft = get_latest_draft()
    image_path = draft["image_path"] if draft else None

    img = request.files.get("image")
    if img and img.filename:
        ext = Path(img.filename).suffix.lower() or ".jpg"
        name = f"{uuid.uuid4().hex}{ext}"
        path = UPLOAD_DIR / name
        img.save(path)
        image_path = str(path)

    if not body_text:
        flash("Заполните текст анонса.", "err")
        return redirect(url_for("index"))

    campaign_id = save_draft(
        subject=subject or "Анонс",
        body_text=body_text,
        link_url=link_url,
        image_path=image_path,
        campaign_id=int(draft["id"]) if draft else None,
    )
    session["draft_campaign_id"] = campaign_id
    flash("Черновик сохранён.", "ok")
    return redirect(url_for("index"))


@app.post("/campaign/test", endpoint="send_test")
@login_required
def send_test_view():
    draft = get_latest_draft()
    if not draft:
        flash("Сначала сохраните черновик.", "err")
        return redirect(url_for("index"))
    email = TEST_EMAIL or SMTP_FROM
    if not email:
        flash("Укажите TEST_EMAIL или SMTP_FROM в .env", "err")
        return redirect(url_for("index"))
    ok, err = send_test(int(draft["id"]), email)
    if ok:
        flash(f"Тестовое письмо отправлено на {email}.", "ok")
    else:
        flash(f"Ошибка: {err}", "err")
    return redirect(url_for("index"))


@app.post("/campaign/send", endpoint="send_campaign")
@login_required
def send_campaign_view():
    if not smtp_configured():
        flash("Настройте SMTP в файле .env", "err")
        return redirect(url_for("index"))

    draft = get_latest_draft()
    if not draft:
        flash("Сначала сохраните черновик.", "err")
        return redirect(url_for("index"))

    active = count_active_recipients()
    if active == 0:
        flash("Нет активных получателей в базе.", "err")
        return redirect(url_for("index"))

    try:
        stats = run_campaign(int(draft["id"]))
        session["last_campaign_id"] = int(draft["id"])
        flash(
            f"Рассылка завершена: отправлено {stats['sent']}, ошибок {stats['error']} "
            f"(из {stats['total']}, лимит {MAX_EMAILS_PER_CAMPAIGN}).",
            "ok",
        )
    except Exception as exc:
        flash(str(exc), "err")
    return redirect(url_for("index"))


@app.get("/uploads/<name>")
@login_required
def uploaded_image(name: str):
    path = UPLOAD_DIR / name
    if not path.exists():
        return "Not found", 404
    return send_file(path)


@app.get("/report/<int:campaign_id>.csv")
@login_required
def download_report(campaign_id: int):
    rows = get_delivery_report(campaign_id)
    if not rows:
        flash("Отчёт пуст.", "err")
        return redirect(url_for("index"))

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=["email", "name", "status", "error_message", "sent_at"]
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "email": row["email"],
                "name": row["name"],
                "status": row["status"],
                "error_message": row["error_message"],
                "sent_at": row["sent_at"],
            }
        )

    bio = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(
        bio,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"anonspost_report_{campaign_id}.csv",
    )


if __name__ == "__main__":
    init_db()
    print(f"{APP_NAME}: http://127.0.0.1:5000")
    print(f"Логин по умолчанию: {ADMIN_LOGIN} (смените в .env)")
    app.run(debug=True, port=5000)
