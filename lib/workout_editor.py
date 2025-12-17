# lib/workout_editor.py
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from lib.supabase_client import set_session_from_state


# =========================
# TABLES / COLS
# =========================
T_WORKOUTS = os.getenv("T_WORKOUTS", "workouts")
T_EXERCISES = os.getenv("T_EXERCISES", "user_exercises")
T_SETS = os.getenv("T_SETS", "workout_sets")

W_ID = os.getenv("W_ID", "id")
W_USER = os.getenv("W_USER", "user_id")
W_DATE = os.getenv("W_DATE", "workout_date")
W_TITLE = os.getenv("W_TITLE", "title")
W_START = os.getenv("W_START", "start_time")
W_END = os.getenv("W_END", "end_time")

E_ID = os.getenv("E_ID", "id")
E_USER = os.getenv("E_USER", "user_id")
E_GROUP = os.getenv("E_GROUP", "spiergroep")
E_NAME = os.getenv("E_NAME", "name")
E_ARCH = os.getenv("E_ARCH", "is_archived")

S_ID = os.getenv("S_ID", "id")
S_USER = os.getenv("S_USER", "user_id")
S_WORKOUT_ID = os.getenv("S_WORKOUT_ID", "workout_id")
S_DATE = os.getenv("S_DATE", "workout_date")
S_EXERCISE_ID = os.getenv("S_EXERCISE_ID", "exercise_id")
S_EXERCISE_NAME = os.getenv("S_EXERCISE_NAME", "exercise_name")
S_GROUPS = os.getenv("S_GROUPS", "spiergroepen")
S_WEIGHT = os.getenv("S_WEIGHT", "weight_kg")
S_REPS = os.getenv("S_REPS", "reps")
S_NOTES = os.getenv("S_NOTES", "notes")

FALLBACK_GROUPS = ["Abs", "Back", "Biceps", "Cardio", "Chest", "Legs", "Shoulders", "Triceps"]


# =========================
# CSS (Input-like)
# =========================
CSS = """
<style>
.block-container { padding-top: 0.8rem; max-width: 1100px; }
hr { border: none; border-top: 1px solid rgba(255,255,255,0.12); margin: 12px 0; }
.smallmuted { color: rgba(255,255,255,0.65); font-size: 12px; }

.card {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 18px;
  padding: 16px;
  margin: 10px 0 14px 0;
  box-shadow: none !important;
}
.exercise-card {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 18px;
  padding: 14px;
  margin: 12px 0;
}
.exercise-title{ font-size: 20px; font-weight: 900; margin-bottom: 6px; }
.pillrow { display:flex; gap:10px; flex-wrap:wrap; margin: 6px 0 10px 0; }
.pill {
  display:inline-block; padding: 6px 10px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.06);
  font-size: 12px; color: rgba(255,255,255,0.85);
}
.set-head{
  display:grid;
  grid-template-columns: 44px 110px 110px 1fr 54px;
  gap: 10px;
  color: rgba(255,255,255,0.55);
  font-size: 12px;
  padding: 0 2px 6px 2px;
}
.set-row{
  display:grid;
  grid-template-columns: 44px 110px 110px 1fr 54px;
  gap: 10px;
  align-items:center;
  border-top: 1px solid rgba(255,255,255,0.10);
  padding: 10px 2px;
}
.badge{
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.18);
  display:flex;
  align-items:center;
  justify-content:center;
  font-weight: 900;
  color: rgba(255,255,255,0.95);
}
</style>
"""


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(x) -> Optional[float]:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x) -> Optional[int]:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return int(x)
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_workout_header(workout_id: str) -> Optional[Dict[str, Any]]:
    sb = set_session_from_state()
    res = sb.table(T_WORKOUTS).select(f"{W_ID},{W_DATE},{W_TITLE},{W_START},{W_END}").eq(W_ID, workout_id).execute()
    if not res.data:
        return None
    return res.data[0]


@st.cache_data(show_spinner=False)
def load_user_exercises(user_id: str) -> pd.DataFrame:
    sb = set_session_from_state()
    res = (
        sb.table(T_EXERCISES)
        .select(f"{E_ID},{E_GROUP},{E_NAME},{E_ARCH}")
        .eq(E_USER, user_id)
        .execute()
    )
    df = pd.DataFrame(res.data or [])
    if df.empty:
        return df
    df[E_GROUP] = df[E_GROUP].fillna("").astype(str).str.strip()
    df[E_NAME] = df[E_NAME].fillna("").astype(str).str.strip()
    df[E_ARCH] = df[E_ARCH].fillna(False).astype(bool)
    return df[~df[E_ARCH]].copy()


@st.cache_data(show_spinner=False)
def load_sets_for_workout(user_id: str, workout_id: str) -> pd.DataFrame:
    sb = set_session_from_state()
    res = (
        sb.table(T_SETS)
        .select(f"{S_ID},{S_EXERCISE_ID},{S_EXERCISE_NAME},{S_GROUPS},{S_WEIGHT},{S_REPS},{S_NOTES}")
        .eq(S_USER, user_id)
        .eq(S_WORKOUT_ID, workout_id)
        .order(S_ID, desc=False)
        .execute()
    )
    df = pd.DataFrame(res.data or [])
    if df.empty:
        return df
    df[S_EXERCISE_NAME] = df.get(S_EXERCISE_NAME, "").fillna("").astype(str)
    df[S_GROUPS] = df.get(S_GROUPS, "").fillna("").astype(str)
    df[S_WEIGHT] = pd.to_numeric(df.get(S_WEIGHT, None), errors="coerce")
    df[S_REPS] = pd.to_numeric(df.get(S_REPS, None), errors="coerce")
    df[S_NOTES] = df.get(S_NOTES, "").fillna("").astype(str)
    return df


def update_workout_header(workout_id: str, workout_date: date, title: str) -> None:
    sb = set_session_from_state()
    sb.table(T_WORKOUTS).update({W_DATE: str(workout_date), W_TITLE: title.strip() or "Workout"}).eq(W_ID, workout_id).execute()
    st.cache_data.clear()


def ensure_workout_started(workout_id: str) -> None:
    """If start_time is null, set it."""
    sb = set_session_from_state()
    # read
    res = sb.table(T_WORKOUTS).select(f"{W_ID},{W_START}").eq(W_ID, workout_id).execute()
    if not res.data:
        return
    if res.data[0].get(W_START) in (None, ""):
        try:
            sb.table(T_WORKOUTS).update({W_START: _now_iso_utc()}).eq(W_ID, workout_id).execute()
        except Exception:
            pass
    st.cache_data.clear()


def finish_workout(workout_id: str, title: str) -> None:
    sb = set_session_from_state()
    try:
        sb.table(T_WORKOUTS).update({W_END: _now_iso_utc(), W_TITLE: title.strip() or "Workout"}).eq(W_ID, workout_id).execute()
    except Exception:
        sb.table(T_WORKOUTS).update({W_TITLE: title.strip() or "Workout"}).eq(W_ID, workout_id).execute()
    st.cache_data.clear()


def insert_set_row(
    user_id: str,
    workout_id: str,
    workout_date: date,
    ex_id: str,
    ex_name: str,
    spiergroep: str,
    weight: Optional[float] = None,
    reps: Optional[int] = None,
    notes: str = "",
) -> str:
    sb = set_session_from_state()
    payload = {
        S_USER: user_id,
        S_WORKOUT_ID: workout_id,
        S_DATE: str(workout_date),
        S_EXERCISE_ID: ex_id,
        S_EXERCISE_NAME: ex_name,
        S_GROUPS: spiergroep,
        S_WEIGHT: weight,
        S_REPS: reps,
        S_NOTES: notes,
    }
    res = sb.table(T_SETS).insert(payload).execute()
    st.cache_data.clear()
    return str(res.data[0][S_ID])


def update_set_row(set_id: str, weight: Optional[float], reps: Optional[int], notes: str) -> None:
    sb = set_session_from_state()
    sb.table(T_SETS).update({S_WEIGHT: weight, S_REPS: reps, S_NOTES: notes}).eq(S_ID, set_id).execute()
    st.cache_data.clear()


def delete_set_row(set_id: str) -> None:
    sb = set_session_from_state()
    sb.table(T_SETS).delete().eq(S_ID, set_id).execute()
    st.cache_data.clear()


def delete_exercise_sets_in_workout(workout_id: str, exercise_id: str) -> None:
    sb = set_session_from_state()
    sb.table(T_SETS).delete().eq(S_WORKOUT_ID, workout_id).eq(S_EXERCISE_ID, exercise_id).execute()
    st.cache_data.clear()


def render_workout_editor(
    *,
    user_id: str,
    workout_id: str,
    mode: str = "edit",  # "new" or "edit"
    excel_groups: Optional[List[str]] = None,
) -> None:
    st.markdown(CSS, unsafe_allow_html=True)

    # Header row (back)
    top_l, top_r = st.columns([0.75, 0.25])
    with top_l:
        st.title("Workout")
        st.caption("Zelfde UI als Input. Adds/edits autosaven direct in Supabase.")
    with top_r:
        if st.button("⬅️ Back to Workouts", use_container_width=True):
            # clear editor context and go back
            st.session_state.pop("editor_workout_id", None)
            st.session_state.pop("editor_mode", None)
            st.switch_page("pages/Workouts.py")

    # ensure start_time exists for new
    if mode == "new":
        ensure_workout_started(workout_id)

    header = load_workout_header(workout_id)
    if not header:
        st.error("Workout niet gevonden.")
        return

    # local UI state (date/title)
    if "editor_date" not in st.session_state:
        st.session_state.editor_date = pd.to_datetime(header.get(W_DATE), errors="coerce").date() if header.get(W_DATE) else date.today()
    if "editor_title" not in st.session_state:
        st.session_state.editor_title = str(header.get(W_TITLE) or "Workout")

    # Header controls
    c1, c2, c3 = st.columns([0.35, 0.45, 0.20])
    with c1:
        st.session_state.editor_date = st.date_input("Datum", value=st.session_state.editor_date)
    with c2:
        st.session_state.editor_title = st.text_input("Titel", value=st.session_state.editor_title)
    with c3:
        if st.button("💾 Save header", type="primary", use_container_width=True):
            try:
                update_workout_header(workout_id, st.session_state.editor_date, st.session_state.editor_title)
                st.success("Header saved ✅")
            except Exception as e:
                st.error(f"Save failed: {e}")

    # Finish button
    if st.button("⏹ Finish workout", use_container_width=True):
        try:
            finish_workout(workout_id, st.session_state.editor_title)
            st.success("Workout afgerond ✅")
        except Exception as e:
            st.error(f"Finish failed: {e}")

    st.markdown("### Oefening toevoegen")

    ex_df = load_user_exercises(user_id)
    ex_df_active = ex_df.copy()

    groups: List[str] = []
    if excel_groups:
        groups.extend(excel_groups)
    if not ex_df_active.empty:
        for g in sorted(ex_df_active[E_GROUP].dropna().astype(str).unique().tolist(), key=str.lower):
            if g and g not in groups:
                groups.append(g)
    if not groups:
        groups = FALLBACK_GROUPS

    if "editor_group" not in st.session_state or st.session_state.editor_group not in groups:
        st.session_state.editor_group = groups[0]

    a1, a2, a3 = st.columns([0.35, 0.45, 0.20])
    with a1:
        st.session_state.editor_group = st.selectbox("Spiergroep", options=groups, index=groups.index(st.session_state.editor_group))
    with a2:
        search = st.text_input("Zoek", placeholder="Search exercises…", key="editor_search")

        df_g = ex_df_active.copy()
        if not df_g.empty:
            df_g = df_g[df_g[E_GROUP].astype(str) == str(st.session_state.editor_group)]
            if search.strip():
                s = search.strip().lower()
                df_g = df_g[df_g[E_NAME].astype(str).str.lower().str.contains(s)]
            df_g = df_g.sort_values(E_NAME)

        if df_g.empty:
            st.warning("Geen exercises in DB voor deze spiergroep. Voeg toe via Exercises-tab in editor (later).")
            ex_options = []
            label_map: Dict[str, str] = {}
            st.session_state.editor_ex_id = None
        else:
            ex_options = df_g[E_ID].astype(str).tolist()
            label_map = {str(r[E_ID]): str(r[E_NAME]) for _, r in df_g.iterrows()}

            def _fmt(x: str) -> str:
                return label_map.get(str(x), str(x))

            st.session_state.editor_ex_id = st.selectbox("Oefening", options=ex_options, format_func=_fmt, key="editor_ex_pick")

    with a3:
        st.write("")
        if st.button("➕ Add", use_container_width=True, disabled=st.session_state.get("editor_ex_id") is None):
            try:
                ex_id = str(st.session_state.editor_ex_id)
                ex_name = label_map.get(ex_id, "Exercise")
                sg = str(st.session_state.editor_group).strip()

                # Insert an empty set immediately (so exercise appears)
                insert_set_row(
                    user_id=user_id,
                    workout_id=workout_id,
                    workout_date=st.session_state.editor_date,
                    ex_id=ex_id,
                    ex_name=ex_name,
                    spiergroep=sg,
                    weight=None,
                    reps=None,
                    notes="",
                )
                st.success(f"Toegevoegd: {ex_name} ✅")
                st.rerun()
            except Exception as e:
                st.error(f"Add failed: {e}")

    st.markdown("### Workout (autosaved)")

    sets = load_sets_for_workout(user_id, workout_id)
    if sets.empty:
        st.caption("Nog geen sets. Voeg een oefening toe.")
        return

    for ex_id, gdf in sets.groupby(S_EXERCISE_ID, sort=False):
        ex_id = str(ex_id)
        ex_name = str(gdf.iloc[0][S_EXERCISE_NAME] or "Exercise")
        sg = str(gdf.iloc[0][S_GROUPS] or "")

        st.markdown("<div class='exercise-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='exercise-title'>{ex_name}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='pillrow'><span class='pill'>{sg}</span><span class='pill'>{st.session_state.editor_date.strftime('%d %b %Y')}</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='set-head'><div></div><div>Kg</div><div>Reps</div><div>Notes</div><div></div></div>", unsafe_allow_html=True)

        for i, r in enumerate(gdf.to_dict(orient="records"), start=1):
            sid = str(r[S_ID])

            st.markdown("<div class='set-row'>", unsafe_allow_html=True)
            c0, c1, c2, c3, c4 = st.columns([0.12, 0.22, 0.22, 0.34, 0.10])

            with c0:
                st.markdown(f"<div class='badge'>{i}</div>", unsafe_allow_html=True)
            with c1:
                kg = st.number_input("Kg", value=float(r.get(S_WEIGHT) or 0.0), min_value=0.0, step=0.5, key=f"kg_{sid}")
            with c2:
                reps = st.number_input("Reps", value=int(r.get(S_REPS) or 0), min_value=0, step=1, key=f"reps_{sid}")
            with c3:
                notes = st.text_input("Notes", value=str(r.get(S_NOTES) or ""), key=f"notes_{sid}")
            with c4:
                if st.button("🗑", key=f"del_{sid}"):
                    delete_set_row(sid)
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

            if st.button("💾 Save set", key=f"save_{sid}", use_container_width=True):
                update_set_row(sid, _safe_float(kg), _safe_int(reps), str(notes))
                st.success("Saved ✅")

        with st.expander("➕ Add set", expanded=False):
            nkg = st.number_input("Kg", min_value=0.0, step=0.5, key=f"nkg_{ex_id}")
            nreps = st.number_input("Reps", min_value=0, step=1, key=f"nreps_{ex_id}")
            nnotes = st.text_input("Notes", value="", key=f"nnotes_{ex_id}")
            if st.button("➕ Add now", key=f"addset_{ex_id}", type="primary"):
                insert_set_row(
                    user_id=user_id,
                    workout_id=workout_id,
                    workout_date=st.session_state.editor_date,
                    ex_id=ex_id,
                    ex_name=ex_name,
                    spiergroep=sg,
                    weight=_safe_float(nkg),
                    reps=_safe_int(nreps),
                    notes=str(nnotes),
                )
                st.rerun()

        if st.button("🗑 Remove exercise from workout", key=f"rmex_{ex_id}", use_container_width=True):
            delete_exercise_sets_in_workout(workout_id, ex_id)
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
