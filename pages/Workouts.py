from __future__ import annotations

import os
from datetime import date
from typing import Any, Optional

import pandas as pd
import streamlit as st

from lib.supabase_client import set_session_from_state

# =========================
# TABLES / COLS
# =========================
T_WORKOUTS = os.getenv("T_WORKOUTS", "workouts")
T_SETS = os.getenv("T_SETS", "workout_sets")

W_ID, W_USER, W_DATE, W_TITLE = "id", "user_id", "workout_date", "title"
W_START = os.getenv("W_START", "start_time")
W_END = os.getenv("W_END", "end_time")

S_USER = "user_id"
S_WORKOUT_ID = "workout_id"
S_EXERCISE_NAME = "exercise_name"

# =========================
# CSS
# =========================
CSS = """
<style>
.block-container { padding-top: .8rem; max-width: 1050px; }

.month-row { display:flex; justify-content:space-between; align-items:baseline; margin: 12px 0 8px 0; }
.month-row .month { font-size: 22px; font-weight: 900; }
.month-row .count { color: rgba(255,255,255,0.70); }

.workout-card{
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 22px;
  padding: 16px 16px;
  margin: 10px 0 6px 0;
  box-shadow: none !important;
}
.workout-head{ display:flex; gap: 14px; align-items:flex-start; }
.daybox{
  width: 84px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 16px;
  padding: 10px 8px;
  text-align:center;
  flex: 0 0 auto;
  box-shadow: none !important;
}
.daybox .dow{ font-size: 12px; color: rgba(255,255,255,0.65); font-weight: 800; }
.daybox .day{ font-size: 28px; font-weight: 950; margin-top: 2px; }
.workout-meta{ flex: 1 1 auto; }
.workout-title{ font-size: 24px; font-weight: 950; margin-top: 2px; }
.lines{ margin-top: 10px; line-height: 1.55; color: rgba(255,255,255,0.92); font-size: 16px; }
.lines b { font-weight: 900; }
.muted { color: rgba(255,255,255,0.65); font-size: 12px; margin-top: 4px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.title("📓 Workouts")

# =========================
# AUTH
# =========================
if "user" not in st.session_state or st.session_state["user"] is None:
    st.info("Log eerst in op de home page.")
    st.stop()

USER_ID = st.session_state["user"].id
sb = set_session_from_state()

# =========================
# Helpers
# =========================
def open_workout_editor(workout_id: str, mode: str = "edit") -> None:
    """
    Zet routing-state; streamlit_app.py ziet open_editor=True en doet st.switch_page(editor).
    """
    st.session_state["editor_workout_id"] = str(workout_id)
    st.session_state["editor_mode"] = str(mode)
    st.session_state["open_editor"] = True
    st.rerun()

def _dow_name(d: date) -> str:
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]

def _month_label(d: date) -> str:
    return pd.Timestamp(d).strftime("%B %Y")

def _fmt_time(ts: Any) -> str:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return ""
    try:
        dt = pd.to_datetime(ts, utc=True)
        return dt.strftime("%H:%M")
    except Exception:
        return ""

def _duration_minutes(start: Any, end: Any) -> Optional[int]:
    try:
        if start is None or end is None:
            return None
        s = pd.to_datetime(start, utc=True)
        e = pd.to_datetime(end, utc=True)
        if pd.isna(s) or pd.isna(e):
            return None
        mins = int((e - s).total_seconds() // 60)
        return mins if mins >= 0 else None
    except Exception:
        return None

# =========================
# Loaders
# =========================
@st.cache_data(show_spinner=False)
def load_workouts(user_id: str) -> pd.DataFrame:
    try:
        res = (
            sb.table(T_WORKOUTS)
            .select(f"{W_ID},{W_DATE},{W_TITLE},{W_START},{W_END}")
            .eq(W_USER, user_id)
            .order(W_DATE, desc=True)
            .order(W_START, desc=True)
            .execute()
        )
    except Exception:
        res = (
            sb.table(T_WORKOUTS)
            .select(f"{W_ID},{W_DATE},{W_TITLE}")
            .eq(W_USER, user_id)
            .order(W_DATE, desc=True)
            .execute()
        )

    df = pd.DataFrame(res.data or [])
    if df.empty:
        return df

    df[W_DATE] = pd.to_datetime(df[W_DATE], errors="coerce").dt.date
    df[W_TITLE] = df[W_TITLE].fillna("Workout").astype(str)

    if W_START not in df.columns:
        df[W_START] = None
    if W_END not in df.columns:
        df[W_END] = None

    return df

@st.cache_data(show_spinner=False)
def load_lines(user_id: str) -> pd.DataFrame:
    res = (
        sb.table(T_SETS)
        .select(f"{S_WORKOUT_ID},{S_EXERCISE_NAME}")
        .eq(S_USER, user_id)
        .execute()
    )
    df = pd.DataFrame(res.data or [])
    if df.empty:
        return df

    df[S_EXERCISE_NAME] = df[S_EXERCISE_NAME].fillna("").astype(str).str.strip()
    out = (
        df.groupby([S_WORKOUT_ID, S_EXERCISE_NAME], as_index=False)
        .size()
        .rename(columns={"size": "set_count"})
        .sort_values(["set_count", S_EXERCISE_NAME], ascending=[False, True])
    )
    return out

# =========================
# Mutations
# =========================
def create_workout(user_id: str, d: date, title: str) -> str:
    payload = {W_USER: user_id, W_DATE: str(d), W_TITLE: title.strip() or "Workout"}
    try:
        payload[W_START] = pd.Timestamp.utcnow().isoformat()
    except Exception:
        pass
    res = sb.table(T_WORKOUTS).insert(payload).execute()
    st.cache_data.clear()
    return str(res.data[0][W_ID])

def delete_workout(workout_id: str) -> None:
    sb.table(T_SETS).delete().eq(S_WORKOUT_ID, workout_id).execute()
    sb.table(T_WORKOUTS).delete().eq(W_ID, workout_id).execute()
    st.cache_data.clear()

# =========================
# Top actions
# =========================
top1, top2 = st.columns([0.70, 0.30])
with top1:
    st.caption("Start/Open/Edit opent dezelfde editor (Input UI) als aparte pagina. Editor staat NIET in sidebar.")
with top2:
    if st.button("▶️ Start workout", type="primary", use_container_width=True):
        wid = create_workout(USER_ID, date.today(), "Workout")
        open_workout_editor(wid, "new")

# =========================
# List
# =========================
workouts = load_workouts(USER_ID)
lines = load_lines(USER_ID)

if workouts.empty:
    st.info("Nog geen workouts.")
    st.stop()

workouts["_month"] = workouts[W_DATE].apply(_month_label)

for month, mdf in workouts.groupby("_month", sort=False):
    st.markdown(
        f"""
<div class="month-row">
  <div class="month">{month}</div>
  <div class="count">{len(mdf)} Workouts</div>
</div>
""",
        unsafe_allow_html=True,
    )

    for _, w in mdf.iterrows():
        wid = str(w[W_ID])
        wdate = w[W_DATE]
        title = str(w[W_TITLE])
        dow = _dow_name(wdate)
        daynum = wdate.day

        t1 = _fmt_time(w.get(W_START))
        t2 = _fmt_time(w.get(W_END))
        dur = _duration_minutes(w.get(W_START), w.get(W_END))
        dur_txt = f"{dur} min" if dur is not None else ""
        time_txt = f"{t1}–{t2}" if t1 and t2 else (t1 or t2 or "—")
        meta_line = f"{time_txt}" + (f" • {dur_txt}" if dur_txt else "")

        ldf = lines[lines[S_WORKOUT_ID].astype(str) == wid].copy() if not lines.empty else pd.DataFrame()
        if ldf.empty:
            lines_html = "<div class='lines'><span class='muted'>No sets</span></div>"
        else:
            ldf = ldf[ldf[S_EXERCISE_NAME].astype(str).str.len() > 0]
            ldf = ldf.sort_values(["set_count", S_EXERCISE_NAME], ascending=[False, True])
            lst = [f"<b>{int(r['set_count'])}x</b> {r[S_EXERCISE_NAME]}" for _, r in ldf.iterrows()]
            lines_html = "<div class='lines'>" + "<br/>".join(lst[:12]) + "</div>"

        st.markdown(
            f"""
<div class="workout-card">
  <div class="workout-head">
    <div class="daybox">
      <div class="dow">{dow}</div>
      <div class="day">{daynum}</div>
    </div>
    <div class="workout-meta">
      <div class="workout-title">{title}</div>
      <div class="muted">{meta_line}</div>
      {lines_html}
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        b1, b2, b3 = st.columns([0.60, 0.20, 0.20])
        with b1:
            if st.button("👁 Open", key=f"open_{wid}", type="primary", use_container_width=True):
                open_workout_editor(wid, "edit")
        with b2:
            if st.button("✏️ Edit", key=f"edit_{wid}", use_container_width=True):
                open_workout_editor(wid, "edit")
        with b3:
            if st.button("🗑 Delete", key=f"del_{wid}", use_container_width=True):
                delete_workout(wid)
                st.success("Deleted ✅")
                st.rerun()
