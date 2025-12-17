#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List, Set, Dict, Any

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client


# ---------- Hard env loading (fix: wrong working dir) ----------
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip().strip('"').strip("'")
SERVICE_ROLE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip().strip('"').strip("'")
EXCEL_PATH = (os.getenv("FITNESS_EXCEL") or "Fitness Tabel.xlsx").strip()

TABLE = "exercises"
BATCH_SIZE = 200


def _find_header_row(raw: pd.DataFrame) -> Optional[int]:
    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.strip().str.lower()
        if (row == "datum").any():
            return i
    return None


def _read_sheet(excel_path: str, sheet_name: str) -> Optional[pd.DataFrame]:
    raw = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
    header_row = _find_header_row(raw)
    if header_row is None:
        return None

    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row)

    # drop unnamed columns safely (mask aligned to df.columns Index)
    mask = ~df.columns.astype(str).str.match(r"^Unnamed")
    df = df.loc[:, mask]

    df = df.dropna(how="all")
    return df if not df.empty else None


def _extract_exercises(excel_path: str) -> List[str]:
    xl = pd.ExcelFile(excel_path)
    found: Set[str] = set()

    for sh in xl.sheet_names:
        df = _read_sheet(excel_path, sh)
        if df is None:
            continue

        if "Oefening" in df.columns:
            series = df["Oefening"]
            if isinstance(series, pd.DataFrame):  # duplicate column name edge case
                series = series.iloc[:, 0]

            vals = (
                series.dropna()
                .astype(str)
                .map(lambda s: s.strip())
                .tolist()
            )

            for v in vals:
                if v and v.lower() != "nan":
                    found.add(v)
        else:
            name = str(sh).strip()
            if name:
                found.add(name)

    return sorted(found, key=str.lower)


def _chunk(lst: List[Dict[str, Any]], n: int) -> List[List[Dict[str, Any]]]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def _validate_env() -> None:
    if not ENV_PATH.exists():
        raise SystemExit(f".env not found next to script: {ENV_PATH}")

    if not SUPABASE_URL or not SERVICE_ROLE_KEY:
        raise SystemExit(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env.\n"
            f"Loaded .env from: {ENV_PATH}\n"
            f"SUPABASE_URL='{SUPABASE_URL}'\n"
            f"SERVICE_ROLE_KEY set? {'yes' if bool(SERVICE_ROLE_KEY) else 'no'}"
        )

    # Supabase client expects HTTP project URL
    if not (SUPABASE_URL.startswith("https://") or SUPABASE_URL.startswith("http://")):
        raise SystemExit(
            "SUPABASE_URL must be the *Project URL* (https://<ref>.supabase.co), not a Postgres URL.\n"
            f"Got: {SUPABASE_URL}"
        )

    if "postgresql://" in SUPABASE_URL or ":5432" in SUPABASE_URL or SUPABASE_URL.startswith("db."):
        raise SystemExit(
            "SUPABASE_URL looks like a database connection string. Use Project Settings → API → Project URL.\n"
            f"Got: {SUPABASE_URL}"
        )


def main() -> None:
    _validate_env()

    if not os.path.exists(EXCEL_PATH):
        raise SystemExit(f'Excel not found: "{EXCEL_PATH}" (set FITNESS_EXCEL in .env). Current dir: {os.getcwd()}')

    exercises = _extract_exercises(EXCEL_PATH)
    if not exercises:
        raise SystemExit("No exercises found in Excel.")

    print(f"Loaded .env from: {ENV_PATH}")
    print(f"SUPABASE_URL: {SUPABASE_URL}")
    print(f"Excel: {EXCEL_PATH}")
    print(f"Found {len(exercises)} unique exercises")

    client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

    rows = [{"name": name} for name in exercises]

    total_sent = 0
    for batch in _chunk(rows, BATCH_SIZE):
        resp = client.table(TABLE).upsert(batch, on_conflict="name").execute()

        # supabase-py versions differ: sometimes resp.error, sometimes resp.data only.
        err = getattr(resp, "error", None)
        if err:
            raise SystemExit(f"Supabase error: {err}")

        total_sent += len(batch)

    print(f"Done. Sent {total_sent} rows to Supabase.")
    print("Check Supabase Table Editor → exercises.")


if __name__ == "__main__":
    main()
