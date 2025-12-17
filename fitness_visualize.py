#!/usr/bin/env python3
"""
fitness_visualize.py

Reads "Fitness Tabel.xlsx" (one sheet per exercise) and visualizes WEEKLY max weight
per exercise and/or per muscle group.

Supports .env defaults (optional):
- FITNESS_EXCEL (default: "Fitness Tabel.xlsx")
- OUTPUT_DIR (default: "charts")
- WEEK_START_DAY (default: 0)         # Monday=0 ... Sunday=6
- CHART_DPI (default: 200)
- CHART_FORMAT (default: "png")
- ROTATE_X_LABELS (default: true)
- SHOW_LEGEND (default: true)
- DEBUG (default: false)

Usage examples
--------------
# 1) All exercises: create one PNG per exercise
python fitness_visualize.py --file "Fitness Tabel.xlsx" --mode exercise --outdir charts

# 2) Only one exercise
python fitness_visualize.py --mode exercise --exercise "Triceps Pushdown"

# 3) One chart per muscle group (multiple exercises as lines)
python fitness_visualize.py --mode muscle

# 4) Also export the weekly-max table to CSV
python fitness_visualize.py --mode exercise --export-csv weekly_max.csv
"""

from __future__ import annotations

import argparse
import os
from typing import Optional, List

import pandas as pd
import matplotlib.pyplot as plt

# Optional .env support
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    # If python-dotenv isn't installed, the script still works with CLI args/defaults.
    pass


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key, str(default)).strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


# .env defaults
DEFAULT_EXCEL = os.getenv("FITNESS_EXCEL", "Fitness Tabel.xlsx")
DEFAULT_OUTDIR = os.getenv("OUTPUT_DIR", "charts")
WEEK_START_DAY = int(os.getenv("WEEK_START_DAY", "0"))  # Monday=0 ... Sunday=6
CHART_DPI = int(os.getenv("CHART_DPI", "200"))
CHART_FORMAT = os.getenv("CHART_FORMAT", "png").strip().lower()
ROTATE_X_LABELS = _env_bool("ROTATE_X_LABELS", True)
SHOW_LEGEND = _env_bool("SHOW_LEGEND", True)
DEBUG = _env_bool("DEBUG", False)


def _debug(msg: str) -> None:
    if DEBUG:
        print(f"[debug] {msg}")


def _find_header_row(raw: pd.DataFrame) -> Optional[int]:
    # Find the row where any cell equals "Datum" (case-insensitive)
    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.strip().str.lower()
        if (row == "datum").any():
            return i
    return None


def load_sheet(excel_path: str, sheet_name: str) -> Optional[pd.DataFrame]:
    raw = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
    header_row = _find_header_row(raw)
    if header_row is None:
        return None

    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row)

    # Drop unnamed columns and empty rows
    df = df.loc[:, ~df.columns.astype(str).str.contains(r"^Unnamed")]
    df = df.dropna(how="all")

    # Add sheet name as metadata
    df["Sheet"] = sheet_name
    return df


def _week_start(series: pd.Series, week_start_day: int) -> pd.Series:
    """
    Return week start date for each datetime in series.

    week_start_day:
      Monday=0 ... Sunday=6
    """
    # Convert to day-of-week 0..6 (Mon..Sun)
    dow = series.dt.weekday
    delta = (dow - week_start_day) % 7
    out = (series - pd.to_timedelta(delta, unit="D")).dt.normalize()
    return out


def load_all(excel_path: str, week_start_day: int) -> pd.DataFrame:
    xl = pd.ExcelFile(excel_path)
    dfs: List[pd.DataFrame] = []
    for sh in xl.sheet_names:
        df = load_sheet(excel_path, sh)
        if df is not None and not df.empty:
            dfs.append(df)

    if not dfs:
        raise ValueError("No usable sheets found. Expected a header row containing 'Datum'.")

    data = pd.concat(dfs, ignore_index=True)

    # Types
    data["Datum"] = pd.to_datetime(data.get("Datum"), errors="coerce")
    data["Gewicht"] = pd.to_numeric(data.get("Gewicht"), errors="coerce")
    if "Reps" in data.columns:
        data["Reps"] = pd.to_numeric(data["Reps"], errors="coerce")

    # Keep only rows that matter
    required = ["Datum", "Spiergroep", "Oefening", "Gewicht"]
    for col in required:
        if col not in data.columns:
            raise ValueError(f"Missing required column '{col}'. Columns found: {list(data.columns)}")

    data = data.dropna(subset=["Datum", "Spiergroep", "Oefening", "Gewicht"])

    # Week start
    data["week_start"] = _week_start(data["Datum"], week_start_day)

    return data


def compute_weekly_max(data: pd.DataFrame) -> pd.DataFrame:
    agg = {"max_gewicht": ("Gewicht", "max")}
    if "Reps" in data.columns:
        agg["max_reps"] = ("Reps", "max")

    weekly = (
        data.groupby(["Spiergroep", "Oefening", "week_start"], as_index=False)
        .agg(**agg)
        .sort_values(["Spiergroep", "Oefening", "week_start"])
    )
    return weekly


def plot_one_exercise(weekly: pd.DataFrame, exercise: str, outpath: str) -> bool:
    d = weekly[weekly["Oefening"].astype(str).str.lower() == exercise.lower()].sort_values("week_start")
    if d.empty:
        return False

    plt.figure(dpi=CHART_DPI)
    plt.plot(d["week_start"], d["max_gewicht"], marker="o")
    plt.title(f"Weekly max weight — {exercise}")
    plt.xlabel("Week start")
    plt.ylabel("Max weight (kg)")

    if ROTATE_X_LABELS:
        plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(outpath, dpi=CHART_DPI)
    plt.close()
    return True


def plot_per_muscle_group(weekly: pd.DataFrame, spiergroep: str, outpath: str) -> bool:
    d = weekly[weekly["Spiergroep"].astype(str).str.lower() == spiergroep.lower()].sort_values("week_start")
    if d.empty:
        return False

    plt.figure(dpi=CHART_DPI)
    for ex, dd in d.groupby("Oefening"):
        plt.plot(dd["week_start"], dd["max_gewicht"], marker="o", label=str(ex))

    plt.title(f"Weekly max weight — {spiergroep}")
    plt.xlabel("Week start")
    plt.ylabel("Max weight (kg)")

    if ROTATE_X_LABELS:
        plt.xticks(rotation=45, ha="right")

    if SHOW_LEGEND:
        plt.legend()

    plt.tight_layout()
    plt.savefig(outpath, dpi=CHART_DPI)
    plt.close()
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=DEFAULT_EXCEL, help='Path to the Excel file, e.g. "Fitness Tabel.xlsx"')
    p.add_argument("--outdir", default=DEFAULT_OUTDIR, help="Output directory for charts")
    p.add_argument(
        "--mode",
        choices=["exercise", "muscle"],
        default="exercise",
        help="exercise = 1 chart per exercise; muscle = 1 chart per muscle group",
    )
    p.add_argument("--exercise", default=None, help="Only plot this exercise (only for --mode exercise)")
    p.add_argument("--spiergroep", default=None, help="Only plot this muscle group (only for --mode muscle)")
    p.add_argument("--export-csv", default=None, help="Optional: export weekly max table to CSV")
    p.add_argument(
        "--week-start-day",
        type=int,
        default=WEEK_START_DAY,
        help="Week start day: Monday=0 ... Sunday=6 (default from .env WEEK_START_DAY)",
    )

    args = p.parse_args()

    if not os.path.exists(args.file):
        raise SystemExit(f'Excel file not found: "{args.file}"')

    os.makedirs(args.outdir, exist_ok=True)

    _debug(f"Excel: {args.file}")
    _debug(f"Outdir: {args.outdir}")
    _debug(f"Week start day: {args.week_start_day}")
    _debug(f"Chart dpi: {CHART_DPI}, format: {CHART_FORMAT}")

    data = load_all(args.file, week_start_day=args.week_start_day)
    weekly = compute_weekly_max(data)

    if args.export_csv:
        weekly.to_csv(args.export_csv, index=False)
        _debug(f"Exported CSV: {args.export_csv}")

    def outpath_for(name: str) -> str:
        safe = str(name).replace(" ", "_").lower()
        return os.path.join(args.outdir, f"weekly_max_{safe}.{CHART_FORMAT}")

    if args.mode == "exercise":
        if args.exercise:
            out = outpath_for(args.exercise)
            ok = plot_one_exercise(weekly, args.exercise, out)
            if not ok:
                raise SystemExit(f"No data found for exercise: {args.exercise}")
        else:
            for ex in sorted(weekly["Oefening"].unique(), key=lambda x: str(x).lower()):
                plot_one_exercise(weekly, str(ex), outpath_for(ex))

    elif args.mode == "muscle":
        if args.spiergroep:
            out = outpath_for(args.spiergroep)
            ok = plot_per_muscle_group(weekly, args.spiergroep, out)
            if not ok:
                raise SystemExit(f"No data found for spiergroep: {args.spiergroep}")
        else:
            for sg in sorted(weekly["Spiergroep"].unique(), key=lambda x: str(x).lower()):
                plot_per_muscle_group(weekly, str(sg), outpath_for(sg))


if __name__ == "__main__":
    main()
