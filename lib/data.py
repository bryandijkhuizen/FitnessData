import os
import numpy as np
import pandas as pd
import streamlit as st
from lib.supabase_client import set_session_from_state

SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "workout_sets")
COL_DATE = os.getenv("COL_DATE", "workout_date")
COL_EXERCISE = os.getenv("COL_EXERCISE", "exercise_name")
COL_MUSCLES = os.getenv("COL_MUSCLES", "spiergroepen")
COL_WEIGHT = os.getenv("COL_WEIGHT", "weight_kg")
COL_REPS = os.getenv("COL_REPS", "reps")
COL_USER = os.getenv("COL_USER", "user_id")

def _week_start(series: pd.Series, week_start_day: int) -> pd.Series:
    dow = series.dt.weekday
    delta = (dow - week_start_day) % 7
    return (series - pd.to_timedelta(delta, unit="D")).dt.normalize()

def explode_spiergroep(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["Spiergroep"] = d["Spiergroep"].astype(str)
    parts = d["Spiergroep"].str.split(",").apply(lambda xs: [x.strip() for x in xs if str(x).strip()])
    d = d.assign(_sg=parts).explode("_sg", ignore_index=True)
    d["Spiergroep"] = d["_sg"].astype(str).str.strip()
    return d.drop(columns=["_sg"])

@st.cache_data(show_spinner=False)
def load_data_from_supabase(user_id: str, week_start_day: int) -> pd.DataFrame:
    sb = set_session_from_state()
    select_cols = f"{COL_DATE},{COL_EXERCISE},{COL_MUSCLES},{COL_WEIGHT},{COL_REPS}"
    res = sb.table(SUPABASE_TABLE).select(select_cols).eq(COL_USER, user_id).execute()
    if not res.data:
        return pd.DataFrame()

    df = pd.DataFrame(res.data).rename(columns={
        COL_DATE: "Datum",
        COL_EXERCISE: "Oefening",
        COL_MUSCLES: "Spiergroep",
        COL_WEIGHT: "Gewicht",
        COL_REPS: "Reps",
    })

    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Gewicht"] = pd.to_numeric(df["Gewicht"], errors="coerce")
    df["Reps"] = pd.to_numeric(df["Reps"], errors="coerce")

    df = df.dropna(subset=["Datum","Spiergroep","Oefening","Gewicht"])
    df["Oefening"] = df["Oefening"].astype(str).str.strip()
    df["Spiergroep"] = df["Spiergroep"].astype(str).str.strip()

    df = explode_spiergroep(df)
    df["week_start"] = _week_start(df["Datum"], week_start_day)
    df["weekday"] = df["Datum"].dt.weekday
    return df
