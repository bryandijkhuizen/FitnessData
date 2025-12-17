#!/usr/bin/env python3
from __future__ import annotations

import os
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# -------------------------------------------------
# ENV
# -------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
EXCEL_PATH = os.getenv("FITNESS_EXCEL", "Fitness Tabel.xlsx").strip()

TABLE = "workout_sets"
BATCH_SIZE = 200

# ⚠️ tijdelijk: later via auth
DEFAULT_USER_ID = os.getenv(
    "DEFAULT_USER_ID",
    "5166c8c2-b53d-4295-a772-9efb22d09714"
)

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def find_header_row(raw: pd.DataFrame) -> Optional[int]:
    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.lower()
        if (row == "datum").any():
            return i
    return None


def read_sheet(path: str, sheet_name: str) -> Optional[pd.DataFrame]:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    header = find_header_row(raw)
    if header is None:
        return None

    df = pd.read_excel(path, sheet_name=sheet_name, header=header)
    df = df.loc[:, ~df.columns.astype(str).str.match("^Unnamed")]
    df = df.dropna(how="all")
    return df if not df.empty else None


def make_import_hash(row: Dict[str, Any]) -> str:
    base = (
        f"{row['user_id']}|"
        f"{row['workout_date']}|"
        f"{row['exercise_name']}|"
        f"{row.get('weight_kg')}|"
        f"{row.get('reps')}"
    )
    return hashlib.sha1(base.encode()).hexdigest()


def chunk(lst: List[Dict[str, Any]], size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# -------------------------------------------------
# Main
# -------------------------------------------------
def main() -> None:
    if not SUPABASE_URL or not SERVICE_ROLE_KEY:
        raise SystemExit("Missing Supabase credentials in .env")

    if not os.path.exists(EXCEL_PATH):
        raise SystemExit(f"Excel not found: {EXCEL_PATH}")

    print(f"Excel: {EXCEL_PATH}")

    xl = pd.ExcelFile(EXCEL_PATH)
    rows: List[Dict[str, Any]] = []

    for sheet in xl.sheet_names:
        df = read_sheet(EXCEL_PATH, sheet)
        if df is None:
            continue

        for _, r in df.iterrows():
            try:
                workout_date = pd.to_datetime(r["Datum"]).date()
            except Exception:
                continue

            row = {
                "user_id": DEFAULT_USER_ID,
                "performed_at": datetime.utcnow().isoformat(),
                "workout_date": workout_date.isoformat(),
                "exercise_name": str(r.get("Oefening", "")).strip(),
                "spiergroepen": str(r.get("Spiergroep", "")).strip(),
                "weight_kg": float(r["Gewicht"]) if not pd.isna(r["Gewicht"]) else None,
                "reps": int(r["Reps"]) if "Reps" in df.columns and not pd.isna(r["Reps"]) else None,
                "notes": None,
            }

            row["import_hash"] = make_import_hash(row)
            rows.append(row)

    if not rows:
        raise SystemExit("No rows extracted")

    # ✅ Deduplicate inside batch (CRUCIAL)
    deduped = {
        (r["user_id"], r["import_hash"]): r
        for r in rows
    }
    rows = list(deduped.values())

    print(f"Rows prepared: {len(rows)}")
    print("Uploading...")

    client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

    for batch in chunk(rows, BATCH_SIZE):
        resp = client.table(TABLE).upsert(
            batch,
            on_conflict="user_id,import_hash"
        ).execute()

        if getattr(resp, "error", None):
            raise SystemExit(resp.error)

    print("✅ Import complete")


if __name__ == "__main__":
    main()
