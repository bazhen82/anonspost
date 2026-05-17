from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from models import upsert_recipient

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    if "email" not in df.columns:
        for alt in ("e-mail", "mail", "почта", "e_mail"):
            if alt in df.columns:
                df = df.rename(columns={alt: "email"})
                break

    if "email" not in df.columns:
        raise ValueError("В CSV нужен столбец email (или mail, e-mail)")

    if "name" not in df.columns:
        for alt in ("имя", "fio", "full_name", "фио"):
            if alt in df.columns:
                df = df.rename(columns={alt: "name"})
                break

    if "name" not in df.columns:
        df["name"] = ""

    df["email"] = df["email"].astype(str).str.strip().str.lower()
    df["name"] = df["name"].astype(str).str.strip()
    df = df[df["email"].ne("") & df["email"].ne("nan")]
    return df.drop_duplicates(subset=["email"]).reset_index(drop=True)


def import_csv_file(path: Path) -> dict[str, int]:
    df = normalize_dataframe(pd.read_csv(path))
    return import_dataframe(df)


def import_dataframe(df: pd.DataFrame) -> dict[str, int]:
    df = normalize_dataframe(df)
    stats = {"added": 0, "updated": 0, "skipped_invalid": 0, "skipped_unsubscribed": 0}

    for _, row in df.iterrows():
        email = row["email"]
        if not EMAIL_RE.match(email):
            stats["skipped_invalid"] += 1
            continue
        action, _ = upsert_recipient(email, row.get("name", ""))
        if action == "added":
            stats["added"] += 1
        elif action == "updated":
            stats["updated"] += 1
        elif action == "skipped_unsubscribed":
            stats["skipped_unsubscribed"] += 1

    return stats
