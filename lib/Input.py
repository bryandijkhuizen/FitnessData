# pages/Input.py
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
W_START = os.getenv("W_START", "start_time")  # optional
W_END = os.getenv("W_END", "end_time")        # optional

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
S_NOTES = os.getenv("S_NOTES", "notes")                          # optional


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
st.markdown(CSS, unsafe_allow_html=True)


# ============================================================
# AUTH
# ============================================================
st.title("➕ Input")
st.caption("Start workout → alles autosaved (elke mutatie direct in Supabase). Spiergroepen uit Excel.")

if "user" not in st.session_state or st.session_state["user"] is None:
    st.info("Log eerst in op de home page.")
    st.stop()

USER_ID = st.session_state["user"].id
sb = set_session_from_state()


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
def load_user_exercises(user_id: str) -> pd.DataFrame:
    try:
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
    except Exception:
        return pd.DataFrame(columns=[E_ID, E_GROUP, E_NAME, E_ARCH])

@st.cache_data(show_spinner=False)
def load_sets_for_workout(user_id: str, workout_id: str) -> pd.DataFrame:
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
    df[S_EXERCISE_NAME] = df[S_EXERCISE_NAME].fillna("").astype(str)
    df[S_GROUPS] = df[S_GROUPS].fillna("").astype(str)
    df[S_WEIGHT] = pd.to_numeric(df.get(S_WEIGHT, None), errors="coerce")
    df[S_REPS] = pd.to_numeric(df.get(S_REPS, None), errors="coerce")
    df[S_NOTES] = df.get(S_NOTES, "").fillna("").astype(str)
    return df


# ============================================================
# DB mutations (autosave)
# ============================================================
def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_workout_row(user_id: str, d: date, title: str) -> str:
    payload_full = {
        W_USER: user_id,
        W_DATE: str(d),
        W_TITLE: title.strip() or "Workout",
        W_START: _now_iso_utc(),
    }
    # try with start_time
    try:
        res = sb.table(T_WORKOUTS).insert(payload_full).execute()
        wid = str(res.data[0][W_ID])
        st.cache_data.clear()
        return wid
    except Exception:
        # fallback without start_time
        payload_min = {W_USER: user_id, W_DATE: str(d), W_TITLE: title.strip() or "Workout"}
        res = sb.table(T_WORKOUTS).insert(payload_min).execute()
        wid = str(res.data[0][W_ID])
        st.cache_data.clear()
        return wid

def finish_workout_row(workout_id: str, title: str) -> None:
    # try set end_time + title
    try:
        sb.table(T_WORKOUTS).update({W_END: _now_iso_utc(), W_TITLE: title.strip() or "Workout"}).eq(W_ID, workout_id).execute()
    except Exception:
        # fallback set only title
        sb.table(T_WORKOUTS).update({W_TITLE: title.strip() or "Workout"}).eq(W_ID, workout_id).execute()
    st.cache_data.clear()

def insert_set_row(
    user_id: str,
    workout_id: str,
    d: date,
    ex_id: str,
    ex_name: str,
    spiergroep: str,
    weight: Optional[float] = None,
    reps: Optional[int] = None,
    notes: str = "",
) -> str:
    payload = {
        S_USER: user_id,
        S_WORKOUT_ID: workout_id,
        S_DATE: str(d),
        S_EXERCISE_ID: ex_id,
        S_EXERCISE_NAME: ex_name,
        S_GROUPS: spiergroep,
        S_WEIGHT: weight,
        S_REPS: reps,
        S_NOTES: notes,
    }
    res = sb.table(T_SETS).insert(payload).execute()
    sid = str(res.data[0][S_ID])
    st.cache_data.clear()
    return sid

def update_set_row(set_id: str, weight: Optional[float], reps: Optional[int], notes: str) -> None:
    sb.table(T_SETS).update({S_WEIGHT: weight, S_REPS: reps, S_NOTES: notes}).eq(S_ID, set_id).execute()
    st.cache_data.clear()

def delete_set_row(set_id: str) -> None:
    sb.table(T_SETS).delete().eq(S_ID, set_id).execute()
    st.cache_data.clear()

def delete_exercise_sets_in_workout(workout_id: str, exercise_id: str) -> None:
    sb.table(T_SETS).delete().eq(S_WORKOUT_ID, workout_id).eq(S_EXERCISE_ID, exercise_id).execute()
    st.cache_data.clear()


# ============================================================
# Session state
# ============================================================
def ensure_state() -> None:
    if "workout_date" not in st.session_state:
        st.session_state.workout_date = date.today()
    if "workout_title" not in st.session_state:
        st.session_state.workout_title = "Morning Workout"
    if "active_workout_id" not in st.session_state:
        st.session_state.active_workout_id = None
    if "selected_group" not in st.session_state:
        st.session_state.selected_group = None
    if "selected_exercise_id" not in st.session_state:
        st.session_state.selected_exercise_id = None

ensure_state()


# ============================================================
# UI
# ============================================================
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

if st.session_state.selected_group not in groups:
    st.session_state.selected_group = groups[0]


tab_workout, tab_exercises = st.tabs(["🏋️ Workout", "📚 Exercises"])


# ============================================================
# TAB: WORKOUT (autosave)
# ============================================================
with tab_workout:
    st.markdown("### Workout session")

    # Header controls
    c1, c2, c3 = st.columns([0.35, 0.40, 0.25])
    with c1:
        st.session_state.workout_date = st.date_input("Datum", value=st.session_state.workout_date)
    with c2:
        st.session_state.workout_title = st.text_input("Titel", value=st.session_state.workout_title)
    with c3:
        if st.session_state.active_workout_id is None:
            if st.button("▶️ Start Workout", type="primary", use_container_width=True):
                try:
                    wid = create_workout_row(USER_ID, st.session_state.workout_date, st.session_state.workout_title)
                    st.session_state.active_workout_id = wid
                    st.success("Workout gestart ✅ (autosave staat aan)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Start failed: {e}")
        else:
            if st.button("⏹ Finish", type="primary", use_container_width=True):
                try:
                    finish_workout_row(st.session_state.active_workout_id, st.session_state.workout_title)
                    st.success("Workout afgerond ✅")
                    st.session_state.active_workout_id = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Finish failed: {e}")

    if st.session_state.active_workout_id is None:
        st.info("Klik **Start Workout** om te beginnen. Daarna wordt elke wijziging direct opgeslagen.")
        st.stop()

    wid = str(st.session_state.active_workout_id)
    st.markdown(f"<div class='smallmuted'>Active workout_id: {wid}</div>", unsafe_allow_html=True)

    st.markdown("### Oefening toevoegen")

    a1, a2, a3 = st.columns([0.35, 0.45, 0.20])
    with a1:
        st.session_state.selected_group = st.selectbox("Spiergroep", options=groups, index=groups.index(st.session_state.selected_group))
    with a2:
        search = st.text_input("Zoek", placeholder="Search exercises…")

        df_g = ex_df_active.copy()
        if not df_g.empty:
            df_g = df_g[df_g[E_GROUP].astype(str) == str(st.session_state.selected_group)]
            if search.strip():
                s = search.strip().lower()
                df_g = df_g[df_g[E_NAME].astype(str).str.lower().str.contains(s)]
            df_g = df_g.sort_values(E_NAME)

        if df_g.empty:
            st.warning("Geen exercises in DB voor deze spiergroep. Voeg toe in tab **Exercises**.")
            ex_options = []
            label_map: Dict[str, str] = {}
            st.session_state.selected_exercise_id = None
        else:
            ex_options = df_g[E_ID].astype(str).tolist()
            label_map = {str(r[E_ID]): str(r[E_NAME]) for _, r in df_g.iterrows()}

            def _fmt(x: str) -> str:
                return label_map.get(str(x), str(x))

            st.session_state.selected_exercise_id = st.selectbox("Oefening", options=ex_options, format_func=_fmt)

    with a3:
        st.write("")
        if st.button("➕ Add", use_container_width=True, disabled=st.session_state.selected_exercise_id is None):
            try:
                ex_id = str(st.session_state.selected_exercise_id)
                ex_name = label_map.get(ex_id, "Exercise")
                sg = str(st.session_state.selected_group).strip()

                # insert first (empty) set immediately
                insert_set_row(
                    user_id=USER_ID,
                    workout_id=wid,
                    d=st.session_state.workout_date,
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

    sets = load_sets_for_workout(USER_ID, wid)
    if sets.empty:
        st.caption("Nog geen sets. Voeg een oefening toe.")
        st.stop()

    # Render per exercise
    for ex_id, gdf in sets.groupby(S_EXERCISE_ID, sort=False):
        ex_id = str(ex_id)
        ex_name = str(gdf.iloc[0][S_EXERCISE_NAME] or "Exercise")
        sg = str(gdf.iloc[0][S_GROUPS] or "")

        st.markdown("<div class='exercise-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='exercise-title'>{ex_name}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='pillrow'><span class='pill'>{sg}</span><span class='pill'>{st.session_state.workout_date.strftime('%d %b %Y')}</span></div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div class='set-head'><div></div><div>Kg</div><div>Reps</div><div>Notes</div><div></div></div>",
            unsafe_allow_html=True,
        )

        # rows (each input updates DB via Save button per row to keep Streamlit sane)
        # If you *really* want true on-change writes, we can do it too, but Streamlit reruns can get spammy.
        for i, r in enumerate(gdf.to_dict(orient="records"), start=1):
            sid = str(r[S_ID])

            st.markdown("<div class='set-row'>", unsafe_allow_html=True)
            c0, c1, c2, c3, c4 = st.columns([0.12, 0.22, 0.22, 0.34, 0.10])

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
                notes = st.text_input(
                    "Notes",
                    value=str(r.get(S_NOTES) or ""),
                    key=f"notes_{sid}",
                )
            with c4:
                if st.button("🗑", key=f"del_{sid}"):
                    try:
                        delete_set_row(sid)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")

            st.markdown("</div>", unsafe_allow_html=True)

            # Save this set (direct DB write)
            if st.button("💾 Save set", key=f"save_{sid}", use_container_width=True):
                try:
                    update_set_row(sid, float(kg), int(reps), str(notes))
                    st.success("Saved ✅")
                except Exception as e:
                    st.error(f"Save failed: {e}")

        # Add set (inserts immediately)
        with st.expander("➕ Add set", expanded=False):
            nkg = st.number_input("Kg", min_value=0.0, step=0.5, key=f"nkg_{ex_id}")
            nreps = st.number_input("Reps", min_value=0, step=1, key=f"nreps_{ex_id}")
            nnotes = st.text_input("Notes", value="", key=f"nnotes_{ex_id}")
            if st.button("➕ Add now", key=f"addset_{ex_id}", type="primary"):
                try:
                    insert_set_row(
                        user_id=USER_ID,
                        workout_id=wid,
                        d=st.session_state.workout_date,
                        ex_id=ex_id,
                        ex_name=ex_name,
                        spiergroep=sg,
                        weight=float(nkg),
                        reps=int(nreps),
                        notes=str(nnotes),
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

        # Remove exercise from workout (deletes its sets for this workout)
        if st.button("🗑 Remove exercise from workout", key=f"rmex_{ex_id}", use_container_width=True):
            try:
                delete_exercise_sets_in_workout(wid, ex_id)
                st.rerun()
            except Exception as e:
                st.error(f"Remove exercise failed: {e}")

        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# TAB: EXERCISES (per-user beheer)
# ============================================================
with tab_exercises:
    st.markdown("### Exercises (per user)")
    st.caption("Hier beheer je jouw exercises (DB). Spiergroepen komen uit Excel als baseline.")

    ex_df = load_user_exercises(USER_ID)
    ex_df_active = ex_df[~ex_df[E_ARCH]].copy() if not ex_df.empty else ex_df

    mg1, mg2 = st.columns([0.7, 0.3])
    with mg1:
        group_sel = st.selectbox("Spiergroep", options=groups, key="ex_group")
    with mg2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    in_group = (
        ex_df_active[ex_df_active[E_GROUP].astype(str) == str(group_sel)].copy()
        if not ex_df_active.empty
        else pd.DataFrame(columns=[E_ID, E_GROUP, E_NAME, E_ARCH])
    )

    st.markdown("#### Jouw oefeningen (DB)")
    if in_group.empty:
        st.info("Nog geen oefeningen in deze spiergroep.")
    else:
        st.dataframe(in_group[[E_ID, E_NAME]].rename(columns={E_ID: "ID", E_NAME: "Oefening"}), use_container_width=True, hide_index=True)

    st.markdown("#### Oefening toevoegen")
    with st.form("add_ex_form"):
        new_name = st.text_input("Naam", placeholder="Bijv. Cable Row")
        submitted = st.form_submit_button("➕ Add (autosave)")
    if submitted:
        nm = new_name.strip()
        if not nm:
            st.error("Vul een naam in.")
        else:
            try:
                sb.table(T_EXERCISES).insert({E_USER: USER_ID, E_GROUP: str(group_sel), E_NAME: nm, E_ARCH: False}).execute()
                st.cache_data.clear()
                st.success("Toegevoegd ✅")
                st.rerun()
            except Exception as e:
                st.error(f"Insert failed: {e}")

    if not in_group.empty:
        st.markdown("#### Rename / Archive")
        pick = st.selectbox("Select", options=in_group[E_ID].astype(str).tolist(), format_func=lambda x: in_group[in_group[E_ID].astype(str)==str(x)].iloc[0][E_NAME], key="pick_ex")
        row = in_group[in_group[E_ID].astype(str) == str(pick)].head(1)

        r1, r2 = st.columns([0.7, 0.3])
        with r1:
            new_nm = st.text_input("Nieuwe naam", value=str(row.iloc[0][E_NAME]), key="rename_nm")
        with r2:
            if st.button("✏️ Rename (autosave)", use_container_width=True):
                try:
                    sb.table(T_EXERCISES).update({E_NAME: new_nm.strip()}).eq(E_ID, str(pick)).execute()
                    st.cache_data.clear()
                    st.success("Hernoemd ✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Rename failed: {e}")

        if st.button("🗑 Archive (autosave)", use_container_width=True):
            try:
                sb.table(T_EXERCISES).update({E_ARCH: True}).eq(E_ID, str(pick)).execute()
                st.cache_data.clear()
                st.success("Gearchiveerd ✅")
                st.rerun()
            except Exception as e:
                st.error(f"Archive failed: {e}")
