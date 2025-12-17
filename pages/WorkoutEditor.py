from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from lib.supabase_client import set_session_from_state

# ============================================================
# ENV (tables)
# ============================================================
DEFAULT_EXCEL = os.getenv("FITNESS_EXCEL", "Fitness Tabel.xlsx")

T_WORKOUTS = os.getenv("T_WORKOUTS", "workouts")
T_EXERCISES = os.getenv("T_EXERCISES", "user_exercises")
T_SETS = os.getenv("T_SETS", "workout_sets")

# workouts columns
W_ID = os.getenv("W_ID", "id")
W_USER = os.getenv("W_USER", "user_id")
W_DATE = os.getenv("W_DATE", "workout_date")
W_TITLE = os.getenv("W_TITLE", "title")
W_START = os.getenv("W_START", "start_time")
W_END = os.getenv("W_END", "end_time")

# user_exercises columns
E_ID = os.getenv("E_ID", "id")
E_USER = os.getenv("E_USER", "user_id")
E_GROUP = os.getenv("E_GROUP", "spiergroep")
E_NAME = os.getenv("E_NAME", "name")
E_ARCH = os.getenv("E_ARCH", "is_archived")

# workout_sets columns
S_ID = os.getenv("S_ID", "id")
S_USER = os.getenv("S_USER", "user_id")
S_WORKOUT_ID = os.getenv("S_WORKOUT_ID", "workout_id")
S_DATE = os.getenv("S_DATE", "workout_date")
S_EXERCISE_ID = os.getenv("S_EXERCISE_ID", "exercise_id")
S_EXERCISE_NAME = os.getenv("S_EXERCISE_NAME", "exercise_name")  # snapshot
S_GROUPS = os.getenv("S_GROUPS", "spiergroepen")                 # snapshot
S_WEIGHT = os.getenv("S_WEIGHT", "weight_kg")
S_REPS = os.getenv("S_REPS", "reps")
S_NOTES = os.getenv("S_NOTES", "notes")

FALLBACK_GROUPS = ["Abs", "Back", "Biceps", "Cardio", "Chest", "Legs", "Shoulders", "Triceps"]

# ============================================================
# CSS
# ============================================================
CSS = """
<style>
.block-container { padding-top: 1.0rem; max-width: 1100px; }
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
  grid-template-columns: 44px 110px 110px 1fr 110px 54px;
  gap: 10px;
  color: rgba(255,255,255,0.55);
  font-size: 12px;
  padding: 0 2px 6px 2px;
}
.set-row{
  display:grid;
  grid-template-columns: 44px 110px 110px 1fr 110px 54px;
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
st.markdown(CSS, unsafe_allow_html=True)

# ============================================================
# AUTH
# ============================================================
if "user" not in st.session_state or st.session_state["user"] is None:
    st.info("Log eerst in op de home page.")
    st.stop()

USER_ID = st.session_state["user"].id
sb = set_session_from_state()

# ============================================================
# Routing state (from Workouts)
# ============================================================
workout_id = str(st.session_state.get("editor_workout_id") or "").strip()
mode = str(st.session_state.get("editor_mode") or "edit").strip().lower()

if not workout_id:
    st.error("Geen workout geselecteerd. Ga terug naar Workouts.")
    if st.button("← Back to Workouts", key="we_back_noid", use_container_width=True):
        st.session_state["go_workouts"] = True
        st.rerun()
    st.stop()

# ============================================================
# Helpers
# ============================================================
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

# ============================================================
# Excel parsing (spiergroepen)
# ============================================================
def _find_header_row(raw: pd.DataFrame) -> Optional[int]:
    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.strip().str.lower()
        if (row == "datum").any():
            return i
    return None

def _dedupe_columns(cols: List[str]) -> List[str]:
    seen: dict[str, int] = {}
    out: List[str] = []
    for c in cols:
        c = str(c)
        if c not in seen:
            seen[c] = 0
            out.append(c)
        else:
            seen[c] += 1
            out.append(f"{c}__{seen[c]}")
    return out

def _pick_col(df: pd.DataFrame, base: str) -> Optional[str]:
    if base in df.columns:
        return base
    matches = [c for c in df.columns if str(c).startswith(base + "__")]
    return matches[0] if matches else None

@st.cache_data(show_spinner=False)
def load_excel_groups(excel_path: str) -> List[str]:
    if not excel_path or not os.path.exists(excel_path):
        return []
    try:
        xl = pd.ExcelFile(excel_path)
    except Exception:
        return []
    out: set[str] = set()
    for sh in xl.sheet_names:
        try:
            raw = pd.read_excel(excel_path, sheet_name=sh, header=None)
        except Exception:
            continue
        header_row = _find_header_row(raw)
        if header_row is None:
            continue
        try:
            df = pd.read_excel(excel_path, sheet_name=sh, header=header_row)
        except Exception:
            continue
        df.columns = _dedupe_columns(list(df.columns))
        c_sg = _pick_col(df, "Spiergroep")
        if not c_sg:
            continue
        sg = df[c_sg].dropna().astype(str)
        for x in sg:
            for part in str(x).split(","):
                part = part.strip()
                if part:
                    out.add(part)
    return sorted(out, key=str.lower)

# ============================================================
# DB loaders
# ============================================================
@st.cache_data(show_spinner=False)
def load_workout(user_id: str, wid: str) -> Optional[dict]:
    res = (
        sb.table(T_WORKOUTS)
        .select(f"{W_ID},{W_USER},{W_DATE},{W_TITLE},{W_START},{W_END}")
        .eq(W_ID, wid)
        .eq(W_USER, user_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None

@st.cache_data(show_spinner=False)
def load_user_exercises(user_id: str) -> pd.DataFrame:
    res = (
        sb.table(T_EXERCISES)
        .select(f"{E_ID},{E_GROUP},{E_NAME},{E_ARCH}")
        .eq(E_USER, user_id)
        .execute()
    )
    df = pd.DataFrame(res.data or [])
    if df.empty:
        return pd.DataFrame(columns=[E_ID, E_GROUP, E_NAME, E_ARCH])
    df[E_GROUP] = df[E_GROUP].fillna("").astype(str).str.strip()
    df[E_NAME] = df[E_NAME].fillna("").astype(str).str.strip()
    df[E_ARCH] = df[E_ARCH].fillna(False).astype(bool)
    return df

@st.cache_data(show_spinner=False)
def load_sets_for_workout(user_id: str, wid: str) -> pd.DataFrame:
    res = (
        sb.table(T_SETS)
        .select(f"{S_ID},{S_EXERCISE_ID},{S_EXERCISE_NAME},{S_GROUPS},{S_WEIGHT},{S_REPS},{S_NOTES}")
        .eq(S_USER, user_id)
        .eq(S_WORKOUT_ID, wid)
        .order(S_ID, desc=False)
        .execute()
    )
    df = pd.DataFrame(res.data or [])
    if df.empty:
        return df
    df[S_EXERCISE_NAME] = df[S_EXERCISE_NAME].fillna("").astype(str)
    df[S_GROUPS] = df[S_GROUPS].fillna("").astype(str)
    df[S_WEIGHT] = pd.to_numeric(df.get(S_WEIGHT, None), errors="coerce")
    df[S_REPS] = pd.to_numeric(df.get(S_REPS, None), errors="coerce")
    df[S_NOTES] = df.get(S_NOTES, "").fillna("").astype(str)
    return df

# ============================================================
# DB mutations
# ============================================================
def ensure_start_time(wid: str) -> None:
    w0 = load_workout(USER_ID, wid)
    if not w0:
        return
    if w0.get(W_START):
        return
    try:
        sb.table(T_WORKOUTS).update({W_START: _now_iso_utc()}).eq(W_ID, wid).eq(W_USER, USER_ID).execute()
        st.cache_data.clear()
    except Exception:
        pass

def update_workout_meta(wid: str, d: date, title: str) -> None:
    sb.table(T_WORKOUTS).update({W_DATE: str(d), W_TITLE: title.strip() or "Workout"}).eq(W_ID, wid).eq(W_USER, USER_ID).execute()
    st.cache_data.clear()

def finish_workout(wid: str, title: str) -> None:
    sb.table(T_WORKOUTS).update({W_END: _now_iso_utc(), W_TITLE: title.strip() or "Workout"}).eq(W_ID, wid).eq(W_USER, USER_ID).execute()
    st.cache_data.clear()

def insert_set_row(
    user_id: str,
    wid: str,
    d: date,
    ex_id: str,
    ex_name: str,
    spiergroep: str,
    weight: float,
    reps: int,
    notes: str = "",
) -> Optional[str]:
    payload = {
        S_USER: user_id,
        S_WORKOUT_ID: wid,
        S_DATE: str(d),
        S_EXERCISE_ID: ex_id,
        S_EXERCISE_NAME: ex_name,
        S_GROUPS: spiergroep,
        S_WEIGHT: float(weight),
        S_REPS: int(reps),
        S_NOTES: notes,
    }

    res = sb.table(T_SETS).insert(payload).execute()

    # supabase-py: errors zitten vaak in res.error, niet als exception
    err = getattr(res, "error", None)
    if err:
        st.error(f"Insert error: {err}")
        st.code(payload)
        return None

    data = getattr(res, "data", None) or []
    if not data:
        st.error("Insert returned no data (check RLS/permissions/returning).")
        st.code(payload)
        return None

    st.cache_data.clear()
    return str(data[0][S_ID])


def update_set_row(set_id: str, weight: float, reps: int, notes: str) -> None:
    sb.table(T_SETS).update({S_WEIGHT: float(weight), S_REPS: int(reps), S_NOTES: notes}).eq(S_ID, set_id).execute()
    st.cache_data.clear()

def delete_set_row(set_id: str) -> None:
    sb.table(T_SETS).delete().eq(S_ID, set_id).execute()
    st.cache_data.clear()

def delete_exercise_sets_in_workout(wid: str, exercise_id: str) -> None:
    sb.table(T_SETS).delete().eq(S_WORKOUT_ID, wid).eq(S_EXERCISE_ID, exercise_id).execute()
    st.cache_data.clear()

# ============================================================
# Init
# ============================================================
ensure_start_time(workout_id)

w = load_workout(USER_ID, workout_id)
if not w:
    st.error("Workout niet gevonden (of niet van jou).")
    if st.button("← Back to Workouts", key="we_back_notfound", use_container_width=True):
        st.session_state["go_workouts"] = True
        st.rerun()
    st.stop()

db_date = pd.to_datetime(w.get(W_DATE), errors="coerce").date() if w.get(W_DATE) else date.today()
db_title = str(w.get(W_TITLE) or "Workout")

# ============================================================
# UI
# ============================================================
label = "🆕 New workout" if mode == "new" else "✏️ Edit workout"
st.title("📝 Workout")
st.caption(f"{label} • Zelfde UI als Input. Alles autosaved in Supabase.")

card = st.container(border=True)
with card:
    c1, c2, c3, c4 = st.columns([0.30, 0.40, 0.15, 0.15])

    with c1:
        workout_date = st.date_input("Datum", value=db_date, key="we_date")
    with c2:
        workout_title = st.text_input("Titel", value=db_title, key="we_title")
    with c3:
        if st.button("💾 Save", key="we_save_workout", type="primary", use_container_width=True):
            try:
                update_workout_meta(workout_id, workout_date, workout_title)
                st.success("Saved ✅")
            except Exception as e:
                st.error(f"Save failed: {e}")
    with c4:
        if st.button("⏹ Finish", key="we_finish_workout", type="primary", use_container_width=True):
            try:
                finish_workout(workout_id, workout_title)
                st.success("Finished ✅")
                st.session_state["go_workouts"] = True
                st.rerun()
            except Exception as e:
                st.error(f"Finish failed: {e}")

    st.markdown(f"<div class='smallmuted'>workout_id: {workout_id}</div>", unsafe_allow_html=True)

# ------------------------------------------------------------
# Oefening toevoegen (met Kg/Reps direct naast Add)
# ------------------------------------------------------------
st.markdown("## Oefening toevoegen")

excel_groups = load_excel_groups(DEFAULT_EXCEL)
ex_df = load_user_exercises(USER_ID)
ex_df_active = ex_df[~ex_df[E_ARCH]].copy() if not ex_df.empty else ex_df

groups: List[str] = []
if excel_groups:
    groups.extend(excel_groups)
if not ex_df_active.empty:
    for g in sorted(ex_df_active[E_GROUP].dropna().astype(str).unique().tolist(), key=str.lower):
        if g and g not in groups:
            groups.append(g)
if not groups:
    groups = FALLBACK_GROUPS

if "we_group" not in st.session_state or st.session_state["we_group"] not in groups:
    st.session_state["we_group"] = groups[0]
if "we_ex_id" not in st.session_state:
    st.session_state["we_ex_id"] = None
if "we_add_kg" not in st.session_state:
    st.session_state["we_add_kg"] = 0.0
if "we_add_reps" not in st.session_state:
    st.session_state["we_add_reps"] = 0

a1, a2, a3 = st.columns([0.38, 0.44, 0.18])

with a1:
    st.session_state["we_group"] = st.selectbox(
        "Spiergroep",
        options=groups,
        index=groups.index(st.session_state["we_group"]),
        key="we_group_select",
    )

with a2:
    search = st.text_input("Zoek", placeholder="Search exercises…", key="we_search")

    df_g = ex_df_active.copy()
    if not df_g.empty:
        df_g = df_g[df_g[E_GROUP].astype(str) == str(st.session_state["we_group"])]
        if search.strip():
            s = search.strip().lower()
            df_g = df_g[df_g[E_NAME].astype(str).str.lower().str.contains(s)]
        df_g = df_g.sort_values(E_NAME)

    label_map: Dict[str, str] = {}

    if df_g.empty:
        st.warning("Geen exercises in DB voor deze spiergroep.")
        st.session_state["we_ex_id"] = None
        st.selectbox("Oefening", options=[], disabled=True, key="we_exercise_empty")
    else:
        ex_options = df_g[E_ID].astype(str).tolist()
        label_map = {str(r[E_ID]): str(r[E_NAME]) for _, r in df_g.iterrows()}

        def _fmt(x: str) -> str:
            return label_map.get(str(x), str(x))

        st.session_state["we_ex_id"] = st.selectbox(
            "Oefening",
            options=ex_options,
            format_func=_fmt,
            key="we_exercise_select",
        )

with a3:
    st.number_input("Kg", min_value=0.0, step=0.5, key="we_add_kg")
    st.number_input("Reps", min_value=0, step=1, key="we_add_reps")
    st.write("")
    if st.button("➕ Add", key="we_add_btn", use_container_width=True, disabled=st.session_state["we_ex_id"] is None):
        try:
            ex_id = str(st.session_state["we_ex_id"])
            ex_name = label_map.get(ex_id, "Exercise")
            sg = str(st.session_state["we_group"]).strip()

            kg_val = _safe_float(st.session_state.get("we_add_kg")) or 0.0
            reps_val = _safe_int(st.session_state.get("we_add_reps")) or 0

            insert_set_row(
                user_id=USER_ID,
                wid=workout_id,
                d=workout_date,
                ex_id=ex_id,
                ex_name=ex_name,
                spiergroep=sg,
                weight=kg_val,
                reps=reps_val,
                notes="",
            )
            st.success(f"Toegevoegd: {ex_name} ✅")
            st.rerun()
        except Exception as e:
            st.error(f"Add failed: {e}")

# ------------------------------------------------------------
# Workout sets
# ------------------------------------------------------------
st.markdown("## Workout (autosaved)")

sets = load_sets_for_workout(USER_ID, workout_id)
if sets.empty:
    st.caption("Nog geen sets. Voeg een oefening toe.")
else:
    for ex_id, gdf in sets.groupby(S_EXERCISE_ID, sort=False):
        ex_id = str(ex_id)
        ex_name = str(gdf.iloc[0][S_EXERCISE_NAME] or "Exercise")
        sg = str(gdf.iloc[0][S_GROUPS] or "")

        st.markdown("<div class='exercise-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='exercise-title'>{ex_name}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='pillrow'><span class='pill'>{sg}</span><span class='pill'>{workout_date.strftime('%d %b %Y')}</span></div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div class='set-head'><div></div><div>Kg</div><div>Reps</div><div>Notes</div><div></div><div></div></div>",
            unsafe_allow_html=True,
        )

        for i, r in enumerate(gdf.to_dict(orient="records"), start=1):
            sid = str(r[S_ID])

            st.markdown("<div class='set-row'>", unsafe_allow_html=True)
            c0, c1, c2, c3, c5, c6 = st.columns([0.12, 0.20, 0.20, 0.32, 0.20, 0.10])

            with c0:
                st.markdown(f"<div class='badge'>{i}</div>", unsafe_allow_html=True)
            with c1:
                kg = st.number_input(
                    "Kg",
                    value=float(r.get(S_WEIGHT) or 0.0),
                    min_value=0.0,
                    step=0.5,
                    key=f"kg_{sid}",
                )
            with c2:
                reps = st.number_input(
                    "Reps",
                    value=int(r.get(S_REPS) or 0),
                    min_value=0,
                    step=1,
                    key=f"reps_{sid}",
                )
            with c3:
                notes = st.text_input("Notes", value=str(r.get(S_NOTES) or ""), key=f"notes_{sid}")
            with c5:
                if st.button("💾 Save set", key=f"save_{sid}", use_container_width=True):
                    try:
                        update_set_row(sid, float(kg), int(reps), str(notes))
                        st.success("Saved ✅")
                    except Exception as e:
                        st.error(f"Save failed: {e}")
            with c6:
                if st.button("🗑", key=f"del_{sid}"):
                    try:
                        delete_set_row(sid)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")

            st.markdown("</div>", unsafe_allow_html=True)

        with st.expander("➕ Add set", expanded=False):
            nkg = st.number_input("Kg", min_value=0.0, step=0.5, key=f"nkg_{ex_id}")
            nreps = st.number_input("Reps", min_value=0, step=1, key=f"nreps_{ex_id}")
            nnotes = st.text_input("Notes", value="", key=f"nnotes_{ex_id}")
            if st.button("➕ Add now", key=f"addset_{ex_id}", type="primary"):
                try:
                    insert_set_row(
                        user_id=USER_ID,
                        wid=workout_id,
                        d=workout_date,
                        ex_id=ex_id,
                        ex_name=ex_name,
                        spiergroep=sg,
                        weight=_safe_float(nkg) or 0.0,
                        reps=_safe_int(nreps) or 0,
                        notes=str(nnotes),
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

        if st.button("🗑 Remove exercise from workout", key=f"rmex_{ex_id}", use_container_width=True):
            try:
                delete_exercise_sets_in_workout(workout_id, ex_id)
                st.rerun()
            except Exception as e:
                st.error(f"Remove exercise failed: {e}")

        st.markdown("</div>", unsafe_allow_html=True)

st.divider()

if st.button("← Back to Workouts", key="we_back_bottom", use_container_width=True):
    st.session_state["go_workouts"] = True
    st.rerun()
