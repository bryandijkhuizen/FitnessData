# pages/Dashboard.py
#!/usr/bin/env python3
from __future__ import annotations

import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# dotenv optioneel (lokaal)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from lib.supabase_client import get_supabase, set_session_from_state


# =============================
# SETTINGS (env only for non-secret things)
# =============================
WEEK_START_DAY_DEFAULT = int(os.getenv("WEEK_START_DAY", "0"))  # Mon=0..Sun=6
PR_MIN_REPS = int(os.getenv("PR_MIN_REPS", "8"))

# Table + columns (override via .env)
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "workout_sets")
COL_DATE = os.getenv("COL_DATE", "workout_date")
COL_EXERCISE = os.getenv("COL_EXERCISE", "exercise_name")
COL_MUSCLES = os.getenv("COL_MUSCLES", "spiergroepen")
COL_WEIGHT = os.getenv("COL_WEIGHT", "weight_kg")
COL_REPS = os.getenv("COL_REPS", "reps")
COL_USER = os.getenv("COL_USER", "user_id")

supabase = get_supabase()


# =============================
# Small UI helpers
# =============================
def show_table(df: pd.DataFrame, *, key: str, height: int = 320) -> None:
    st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        disabled=True,
        key=key,
        height=height,
    )


# =============================
# Auth / session
# =============================
def _is_authed() -> bool:
    return "user" in st.session_state and st.session_state["user"] is not None


# =============================
# Parsing helpers
# =============================
def _week_start(series: pd.Series, week_start_day: int) -> pd.Series:
    dow = series.dt.weekday  # Mon=0..Sun=6
    delta = (dow - week_start_day) % 7
    return (series - pd.to_timedelta(delta, unit="D")).dt.normalize()


def explode_spiergroep(data: pd.DataFrame) -> pd.DataFrame:
    """
    Support comma-separated spiergroepen:
      "Schouders, Rug" -> 2 rows
    """
    d = data.copy()
    d["Spiergroep"] = d["Spiergroep"].astype(str)

    parts = (
        d["Spiergroep"]
        .str.split(",")
        .apply(lambda xs: [x.strip() for x in xs if str(x).strip()])
    )
    d = d.assign(_Spiergroep_list=parts)
    d = d.explode("_Spiergroep_list", ignore_index=True)
    d["Spiergroep"] = d["_Spiergroep_list"].astype(str).str.strip()
    d = d.drop(columns=["_Spiergroep_list"])
    return d


# =============================
# Supabase load
# =============================
@st.cache_data(show_spinner=False)
def load_data_from_supabase(user_id: str, week_start_day: int) -> pd.DataFrame:
    set_session_from_state()

    select_cols = f"{COL_DATE},{COL_EXERCISE},{COL_MUSCLES},{COL_WEIGHT},{COL_REPS}"

    res = (
        supabase.table(SUPABASE_TABLE)
        .select(select_cols)
        .eq(COL_USER, user_id)
        .execute()
    )

    if not res.data:
        return pd.DataFrame()

    df = pd.DataFrame(res.data)

    df = df.rename(
        columns={
            COL_DATE: "Datum",
            COL_EXERCISE: "Oefening",
            COL_MUSCLES: "Spiergroep",
            COL_WEIGHT: "Gewicht",
            COL_REPS: "Reps",
        }
    )

    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
    df["Gewicht"] = pd.to_numeric(df["Gewicht"], errors="coerce")
    df["Reps"] = pd.to_numeric(df["Reps"], errors="coerce")

    df = df.dropna(subset=["Datum", "Spiergroep", "Oefening", "Gewicht"])

    df["Oefening"] = df["Oefening"].astype(str).str.strip()
    df["Spiergroep"] = df["Spiergroep"].astype(str).str.strip()

    df = explode_spiergroep(df)

    df["week_start"] = _week_start(df["Datum"], week_start_day)
    df["weekday"] = df["Datum"].dt.weekday
    return df


# =============================
# Aggregation / PR / plateau
# =============================
def compute_weekly(data: pd.DataFrame) -> pd.DataFrame:
    gcols = ["Spiergroep", "Oefening", "week_start"]

    out = data.groupby(gcols, as_index=False).agg(
        max_gewicht=("Gewicht", "max"),
        sets=("Gewicht", "size"),
        avg_gewicht=("Gewicht", "mean"),
        tonnage=("Gewicht", "sum"),
    )

    tmp = data.copy()
    tmp["volume"] = tmp["Gewicht"] * tmp["Reps"]
    vol = tmp.groupby(gcols, as_index=False).agg(
        max_reps=("Reps", "max"),
        volume=("volume", "sum"),
        reps_total=("Reps", "sum"),
    )
    out = out.merge(vol, on=gcols, how="left")
    return out.sort_values(gcols)


def add_pr_flags(weekly: pd.DataFrame, min_reps: int) -> pd.DataFrame:
    """
    PR rule:
    - PR only if max_reps >= min_reps
    - new PR only if max_gewicht strictly higher than previous best eligible
    - PR tracked per (Spiergroep, Oefening) so Chest Press can exist in multiple spiergroepen
    """
    w = weekly.copy().sort_values(["Spiergroep", "Oefening", "week_start"])

    w["pr_eligible"] = w["max_reps"].fillna(0) >= min_reps
    w["eligible_weight"] = np.where(w["pr_eligible"], w["max_gewicht"], np.nan)

    w["prev_best"] = (
        w.groupby(["Spiergroep", "Oefening"])["eligible_weight"]
        .apply(lambda s: s.cummax().shift(1))
        .reset_index(level=[0, 1], drop=True)
    )

    w["new_pr"] = w["pr_eligible"] & (w["prev_best"].isna() | (w["max_gewicht"] > w["prev_best"]))
    return w


def plateau_alerts(pr_weekly: pd.DataFrame, plateau_weeks: int = 3, include_never_pr: bool = True) -> pd.DataFrame:
    """
    Plateau = "lang geen PR" (niet: 'laatste N weken geen PR terwijl je wel traint')
    -> voorkomt dat oefeningen van maandag meteen als plateau verschijnen.

    We bepalen:
      - last_pr_week (laatste week waar new_pr=True)
      - last_seen_week (laatste week dat oefening voorkomt)
      - weeks_since_pr = (global_last_week - last_pr_week) in weken
      - plateau = weeks_since_pr >= plateau_weeks (of never PR & include_never_pr)
    """
    if pr_weekly.empty:
        return pd.DataFrame(columns=["Spiergroep", "Oefening", "spiergroep", "last_week", "last_pr_week", "weeks_since_pr", "last_max", "plateau"])

    w = pr_weekly.copy().sort_values(["Spiergroep", "Oefening", "week_start"])

    global_last_week = w["week_start"].max()

    g = (
        w.groupby(["Spiergroep", "Oefening"], as_index=False)
        .agg(
            last_week=("week_start", "max"),
            last_max=("max_gewicht", "last"),
            last_pr_week=("week_start", lambda s: pd.NaT),  # placeholder, overwritten below
        )
    )

    # last_pr_week apart (alleen weken met new_pr)
    pr_only = w[w["new_pr"]].copy()
    if not pr_only.empty:
        last_pr = (
            pr_only.groupby(["Spiergroep", "Oefening"], as_index=False)
            .agg(last_pr_week=("week_start", "max"))
        )
        g = g.drop(columns=["last_pr_week"]).merge(last_pr, on=["Spiergroep", "Oefening"], how="left")
    else:
        g["last_pr_week"] = pd.NaT

    # weeks since pr
    # als geen PR: NaN
    g["weeks_since_pr"] = (global_last_week - g["last_pr_week"]) / pd.to_timedelta(7, unit="D")
    g.loc[g["last_pr_week"].isna(), "weeks_since_pr"] = np.nan

    # plateau logic
    g["plateau"] = False
    g.loc[g["weeks_since_pr"].notna() & (g["weeks_since_pr"] >= float(plateau_weeks)), "plateau"] = True

    if include_never_pr:
        # nooit PR gehad -> actie nodig
        g.loc[g["last_pr_week"].isna(), "plateau"] = True

    # alias column for UI consistency
    g["spiergroep"] = g["Spiergroep"]

    # sort: plateau eerst, dan langst geleden PR, dan oefening
    g = g.sort_values(
        by=["plateau", "weeks_since_pr", "Oefening"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)

    return g


def split_by_weekday(data: pd.DataFrame) -> pd.DataFrame:
    df = data.copy()
    df["tonnage"] = df["Gewicht"]
    df["volume"] = df["Gewicht"] * df["Reps"]

    day = (
        df.groupby("weekday", as_index=False)
        .agg(
            sets=("Gewicht", "size"),
            tonnage=("tonnage", "sum"),
            volume=("volume", "sum"),
        )
        .sort_values("weekday")
    )
    day["day_name"] = day["weekday"].map({0: "Ma", 1: "Di", 2: "Wo", 3: "Do", 4: "Vr", 5: "Za", 6: "Zo"})
    return day


# =============================
# Chart helpers
# =============================
def metric_with_volume_fallback(df: pd.DataFrame, metric: str) -> tuple[pd.DataFrame, str]:
    d = df.copy()
    if metric == "volume":
        d["metric_plot"] = d["volume"]
        d.loc[d["metric_plot"].isna(), "metric_plot"] = d.loc[d["metric_plot"].isna(), "tonnage"]
        return d, "metric_plot"
    return d, metric


def muscle_group_weekly_agg(weekly_df: pd.DataFrame, metric: str) -> pd.DataFrame:
    d, y_col = metric_with_volume_fallback(weekly_df, metric)
    out = (
        d.groupby(["Spiergroep", "week_start"], as_index=False)
        .agg(avg_metric=(y_col, "mean"))
        .sort_values(["Spiergroep", "week_start"])
    )
    return out


def hypertrophy_score(weekly: pd.DataFrame, lookback_weeks: int = 12) -> pd.DataFrame:
    w = weekly.copy()
    w["volume_like"] = w["volume"]
    w.loc[w["volume_like"].isna(), "volume_like"] = w.loc[w["volume_like"].isna(), "tonnage"]

    mg = (
        w.groupby(["Spiergroep", "week_start"], as_index=False)
        .agg(
            volume_like=("volume_like", "sum"),
            intensity=("avg_gewicht", "mean"),
            sets=("sets", "sum"),
        )
        .sort_values(["Spiergroep", "week_start"])
    )

    if mg.empty:
        mg["hypertrophy_score"] = pd.NA
        return mg

    last_week = mg["week_start"].max()
    cutoff = last_week - pd.to_timedelta(7 * max(1, lookback_weeks), unit="D")
    win = mg[mg["week_start"] >= cutoff].copy()

    def _minmax(s: pd.Series) -> pd.Series:
        mn, mx = float(s.min()), float(s.max())
        if np.isclose(mx, mn):
            return pd.Series([50.0] * len(s), index=s.index)
        return (s - mn) / (mx - mn) * 100.0

    win["vol_norm"] = win.groupby("Spiergroep")["volume_like"].transform(_minmax)
    win["int_norm"] = win.groupby("Spiergroep")["intensity"].transform(_minmax)
    win["hypertrophy_score"] = 0.5 * win["vol_norm"] + 0.5 * win["int_norm"]

    mg = mg.merge(
        win[["Spiergroep", "week_start", "hypertrophy_score"]],
        on=["Spiergroep", "week_start"],
        how="left",
    )
    return mg


# =============================
# PAGE UI
# =============================
st.title("📊 Dashboard")
st.caption(f"PR’s alleen bij reps ≥ {PR_MIN_REPS} én gewicht > eerdere PR (per spiergroep + oefening).")

if not _is_authed():
    st.info("Je bent niet ingelogd. Ga naar de home/streamlit_app pagina om in te loggen.")
    st.stop()

USER_ID = st.session_state["user"].id

with st.sidebar:
    st.header("Instellingen")
    week_start_day = st.selectbox(
        "Week start dag",
        options=list(range(7)),
        index=WEEK_START_DAY_DEFAULT,
        format_func=lambda x: ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"][x],
    )
    metric = st.selectbox("Grafiek metric", ["max_gewicht", "volume", "avg_gewicht", "sets"])
    lookback_weeks = st.slider("Hypertrophy score lookback (weken)", 4, 24, 12, 1)

    plateau_weeks = st.slider("Plateau = weken sinds laatste PR (min)", 2, 12, 3, 1)
    include_never_pr = st.checkbox("Neem oefeningen mee die nog nooit PR hadden", value=True)

    st.divider()
    show_raw = st.checkbox("Toon raw data tabel", value=False)
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()

data = load_data_from_supabase(USER_ID, week_start_day)
if data.empty:
    st.warning("Nog geen trainingsdata gevonden voor jouw user.")
    st.stop()

weekly = compute_weekly(data)
weekly_pr = add_pr_flags(weekly, min_reps=PR_MIN_REPS)
alerts = plateau_alerts(weekly_pr, plateau_weeks=plateau_weeks, include_never_pr=include_never_pr)
mg_score = hypertrophy_score(weekly, lookback_weeks=lookback_weeks)
day_split = split_by_weekday(data)

# Top metrics
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Sets (totaal)", int(len(data)))
with c2:
    st.metric("Oefeningen", int(weekly["Oefening"].nunique()))
with c3:
    st.metric("Spiergroepen", int(weekly["Spiergroep"].nunique()))
with c4:
    st.metric("Laatste week", str(weekly["week_start"].max().date()) if not weekly.empty else "-")

tab1, tab2, tab3, tab4 = st.tabs(["📈 Progressie", "💪 Hypertrophy Score", "⚠️ Plateau Alerts", "📅 Split per Dag"])


# -----------------------------
# Tab 1
# -----------------------------
with tab1:
    spiergroepen = sorted(weekly_pr["Spiergroep"].astype(str).unique(), key=str.lower)
    oefeningen = sorted(weekly_pr["Oefening"].astype(str).unique(), key=str.lower)

    dash_a, dash_b = st.tabs(["📊 Dashboard", "🔥 PR's (duidelijke view)"])

    with dash_a:
        graph_type = st.radio(
            "Grafiek type",
            options=["Heatmap (default)", "Lijnen"],
            index=0,
            horizontal=True,
            key="graph_type",
        )

        f1, f2, f3 = st.columns([1.2, 1.2, 1.0])
        with f1:
            spiergroep_sel = st.multiselect(
                "Spiergroep(en) (leeg = alles)", options=spiergroepen, default=[], key="sg_sel"
            )
        with f2:
            oefening_sel = st.multiselect(
                "Oefening(en) (leeg = alles)", options=oefeningen, default=[], key="ex_sel"
            )
        with f3:
            show_muscle_avg = st.checkbox("Toon 1 gemiddelde lijn per spiergroep", value=True, key="show_avg")
            show_exercise_lines = st.checkbox("Toon oefening-lijnen", value=False, key="show_ex_lines")

            if graph_type == "Lijnen":
                top_k = st.slider("Max # spiergroepen (lijnen)", 3, 15, 8, 1, key="top_k")
                lookback_k = st.slider("Top-K lookback (weken)", 1, 16, 6, 1, key="topk_lb")
            else:
                top_k, lookback_k = 8, 6

        filtered = weekly_pr.copy()
        if spiergroep_sel:
            filtered = filtered[filtered["Spiergroep"].astype(str).isin(spiergroep_sel)]
        if oefening_sel:
            filtered = filtered[filtered["Oefening"].astype(str).isin(oefening_sel)]

        if filtered.empty:
            st.warning("Geen data met deze filters.")
        else:
            if graph_type.startswith("Heatmap"):
                hm_df, y_col = metric_with_volume_fallback(filtered, metric)
                hm = hm_df.groupby(["Spiergroep", "week_start"], as_index=False).agg(val=(y_col, "mean"))
                pivot = hm.pivot(index="Spiergroep", columns="week_start", values="val")

                if pivot.shape[1] > 0:
                    last_col = pivot.columns.max()
                    pivot = pivot.sort_values(by=last_col, ascending=False)

                fig = px.imshow(
                    pivot,
                    aspect="auto",
                    labels=dict(x="Week", y="Spiergroep", color=metric),
                )
                fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

            else:
                fig = go.Figure()

                if show_exercise_lines:
                    ex_df, y_ex = metric_with_volume_fallback(filtered, metric)
                    fig_ex = px.line(ex_df, x="week_start", y=y_ex, color="Oefening", markers=True)
                    for tr in fig_ex.data:
                        tr.opacity = 0.22
                        fig.add_trace(tr)

                if show_muscle_avg:
                    mg_line = muscle_group_weekly_agg(filtered, metric)

                    if not mg_line.empty:
                        mg_line = mg_line.sort_values(["Spiergroep", "week_start"])
                        last_week = mg_line["week_start"].max()
                        cutoff = last_week - pd.to_timedelta(7 * lookback_k, unit="D")

                        recent = mg_line[mg_line["week_start"] >= cutoff].dropna(subset=["avg_metric"]).copy()
                        recent = recent.sort_values(["Spiergroep", "week_start"])

                        last_vals = recent.groupby("Spiergroep")["avg_metric"].last().sort_values(ascending=False)
                        top_groups = last_vals.head(min(top_k, len(last_vals))).index.astype(str).tolist()

                        mg_line = mg_line[mg_line["Spiergroep"].astype(str).isin(top_groups)]

                    fig_avg = px.line(mg_line, x="week_start", y="avg_metric", color="Spiergroep", markers=True)
                    for tr in fig_avg.data:
                        tr.line.width = 5
                        tr.marker.size = 8
                        tr.name = f"{tr.name} (gemiddelde)"
                        fig.add_trace(tr)

                fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
                st.plotly_chart(fig, use_container_width=True)

    with dash_b:
        st.subheader(f"🔥 PR’s — reps ≥ {PR_MIN_REPS} én gewicht > eerdere PR")

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("PR’s totaal", int(weekly_pr["new_pr"].sum()))
        with k2:
            st.metric("Oefeningen met PR", int(weekly_pr.loc[weekly_pr["new_pr"], "Oefening"].nunique()))
        with k3:
            st.metric(
                "Laatste PR week",
                str(weekly_pr.loc[weekly_pr["new_pr"], "week_start"].max().date())
                if weekly_pr["new_pr"].any()
                else "-"
            )
        with k4:
            st.metric("PR-eligible weken", int(weekly_pr["pr_eligible"].sum()))

        st.divider()

        pf1, pf2 = st.columns([1.2, 1.2])
        with pf1:
            pr_spiergroepen = st.multiselect("Filter spiergroep", options=spiergroepen, default=[], key="pr_sg")
        with pf2:
            pr_ex = st.selectbox("PR timeline oefening", options=["(kies)"] + oefeningen, index=0, key="pr_ex_pick")

        pr_df = weekly_pr.copy()
        if pr_spiergroepen:
            pr_df = pr_df[pr_df["Spiergroep"].astype(str).isin(pr_spiergroepen)]

        st.markdown("### Recent PR’s")
        recent_prs = (
            pr_df[pr_df["new_pr"]]
            .sort_values("week_start", ascending=False)
            .head(50)
            .loc[:, ["week_start", "Spiergroep", "Oefening", "max_gewicht", "max_reps"]]
        )
        if recent_prs.empty:
            st.info("Nog geen PR’s volgens je regels (of filters te strak).")
        else:
            show_table(recent_prs, key="recent_prs_tbl", height=420)

        st.markdown("### PR timeline (per gekozen oefening)")
        if pr_ex != "(kies)":
            ex = weekly_pr[weekly_pr["Oefening"].astype(str) == str(pr_ex)].copy()
            ex = ex.sort_values("week_start")

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ex["week_start"], y=ex["max_gewicht"], mode="lines+markers", name="Max gewicht"))
            pr_points = ex[ex["new_pr"]]
            if not pr_points.empty:
                fig.add_trace(
                    go.Scatter(
                        x=pr_points["week_start"],
                        y=pr_points["max_gewicht"],
                        mode="markers",
                        name="PR",
                        marker=dict(size=12),
                    )
                )
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Kies een oefening om je PR-markers op de tijdlijn te zien.")


# -----------------------------
# Tab 2
# -----------------------------
with tab2:
    st.subheader("Hypertrophy score (0–100) per spiergroep per week")
    if mg_score.empty:
        st.info("Nog geen data.")
    else:
        sg = sorted(mg_score["Spiergroep"].astype(str).unique(), key=str.lower)
        sg_sel = st.multiselect("Spiergroep(en)", options=sg, default=sg[:4] if len(sg) >= 4 else sg, key="sg_score")
        m = mg_score.copy()
        if sg_sel:
            m = m[m["Spiergroep"].astype(str).isin(sg_sel)]

        fig = px.line(m, x="week_start", y="hypertrophy_score", color="Spiergroep", markers=True)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Laatste week: score overzicht")
        last_week = m["week_start"].max()
        last_tbl = (
            m[m["week_start"] == last_week]
            .sort_values("hypertrophy_score", ascending=False)
            .loc[:, ["Spiergroep", "hypertrophy_score", "sets", "volume_like", "intensity"]]
        )
        show_table(last_tbl, key="score_last_week", height=360)


# -----------------------------
# Tab 3
# -----------------------------
with tab3:
    st.subheader("⚠️ Plateau alerts (lang geen PR)")

    plateaus = alerts[alerts["plateau"]].copy()
    ok = alerts[~alerts["plateau"]].copy()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Plateau (actie nodig)")
        if plateaus.empty:
            st.success("Geen plateaus gevonden 🎉")
        else:
            cols = ["spiergroep", "Oefening", "last_pr_week", "weeks_since_pr", "last_week", "last_max"]
            view = plateaus.loc[:, cols].copy()
            view["weeks_since_pr"] = view["weeks_since_pr"].round(1)
            show_table(view, key="plateaus_tbl", height=420)
            st.caption("Tip: probeer +1 rep, +2.5kg, of extra set/week voor deze oefening.")
    with c2:
        st.markdown("### OK / recent PR")
        if ok.empty:
            st.info("Alles staat op 'plateau' volgens je instellingen (of weinig PR-data).")
        else:
            cols2 = ["spiergroep", "Oefening", "last_pr_week", "weeks_since_pr", "last_week", "last_max"]
            view2 = ok.loc[:, cols2].copy()
            view2["weeks_since_pr"] = view2["weeks_since_pr"].round(1)
            show_table(view2, key="ok_tbl", height=420)


# -----------------------------
# Tab 4
# -----------------------------
with tab4:
    st.subheader("📅 Split per trainingsdag (Ma–Zo)")
    metric_day = st.selectbox("Dag metric", ["sets", "tonnage", "volume"], index=0, key="metric_day")
    fig = px.bar(day_split, x="day_name", y=metric_day, hover_data=["sets", "tonnage", "volume"])
    st.plotly_chart(fig, use_container_width=True)
    show_table(day_split.loc[:, ["day_name", "sets", "tonnage", "volume"]], key="day_tbl", height=320)


# Raw
if show_raw:
    st.divider()
    st.subheader("Raw data (sets)")
    show_table(data.sort_values("Datum", ascending=False), key="raw_tbl", height=520)

# Download
st.divider()
st.download_button(
    "⬇️ Download weekly table (CSV)",
    data=weekly_pr.to_csv(index=False).encode("utf-8"),
    file_name="weekly_full.csv",
    mime="text/csv",
)
