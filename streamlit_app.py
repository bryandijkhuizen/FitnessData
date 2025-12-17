from __future__ import annotations

import streamlit as st
from lib.supabase_client import get_supabase, set_session_from_state

DARK_CSS = """
<style>
.stApp{background:#0b0f14;color:#e5e7eb;}
section[data-testid="stSidebar"]{background:#0f1620;}

/* --- Hide only the WorkoutEditor link in the Streamlit nav --- */
/* We give WorkoutEditor a url_path "workout-editor" and hide that link */
section[data-testid="stSidebar"] a[href*="workout-editor"]{
  display: none !important;
}

/* Optional: tighten sidebar spacing a bit */
section[data-testid="stSidebar"] .block-container{
  padding-top: .6rem !important;
}
</style>
"""

st.set_page_config(page_title="Fitness App", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)


# ---------------------------
# Auth helpers
# ---------------------------
def is_authed() -> bool:
    return "user" in st.session_state and st.session_state["user"] is not None


def _persist_tokens_to_url(access_token: str, refresh_token: str) -> None:
    # Refresh-proof persistence
    st.query_params["at"] = access_token
    st.query_params["rt"] = refresh_token


def _clear_tokens_from_url() -> None:
    for k in ["at", "rt"]:
        if k in st.query_params:
            del st.query_params[k]


def _try_restore_session_from_url() -> None:
    """Restore Supabase session from query params after refresh."""
    if is_authed():
        return

    at = st.query_params.get("at")
    rt = st.query_params.get("rt")
    if not at or not rt:
        return

    st.session_state["access_token"] = at
    st.session_state["refresh_token"] = rt

    sb = get_supabase()
    try:
        sb.auth.set_session(at, rt)
        user_res = sb.auth.get_user()
        user = getattr(user_res, "user", None)

        if user:
            st.session_state["user"] = user
            set_session_from_state()
        else:
            for k in ["user", "access_token", "refresh_token"]:
                st.session_state.pop(k, None)
            _clear_tokens_from_url()

    except Exception:
        for k in ["user", "access_token", "refresh_token"]:
            st.session_state.pop(k, None)
        _clear_tokens_from_url()


def login(email: str, password: str) -> None:
    sb = get_supabase()
    res = sb.auth.sign_in_with_password({"email": email, "password": password})

    user = getattr(res, "user", None)
    session = getattr(res, "session", None)

    if not user or not session:
        st.error("Login failed")
        return

    st.session_state["user"] = user
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token

    _persist_tokens_to_url(session.access_token, session.refresh_token)
    set_session_from_state()

    # land on dashboard after login
    st.rerun()


def logout() -> None:
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass

    for k in ["user", "access_token", "refresh_token"]:
        st.session_state.pop(k, None)

    _clear_tokens_from_url()

    try:
        st.cache_data.clear()
    except Exception:
        pass

    st.rerun()


# ---------------------------
# Auto-restore on refresh
# ---------------------------
_try_restore_session_from_url()


# ============================================================
# ROUTES (Custom navigation) — WorkoutEditor stays hidden in nav via CSS
# ============================================================
dashboard_page = st.Page("pages/Dashboard.py", title="Dashboard", icon="🏠", url_path="dashboard")
workouts_page  = st.Page("pages/Workouts.py",  title="Workouts",  icon="📓", url_path="workouts")

# IMPORTANT: This page MUST exist in pages/ so switch_page works.
# We hide its sidebar link via CSS selector (href contains "workout-editor")
editor_page    = st.Page("pages/WorkoutEditor.py", title="Workout", icon="📝", url_path="workout-editor")


def run_login_page() -> None:
    st.title("🏋️ Fitness App")
    st.caption("Log in om naar je dashboard te gaan. Login blijft actief bij refresh.")

    box = st.container(border=True)
    with box:
        st.subheader("Login")
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Login", type="primary")

        if submitted:
            login(email.strip(), password)

    st.divider()
    st.caption("Nog geen account? Maak ‘m aan in Supabase Auth (of ik maak een Signup page voor je).")


def run_authed_app() -> None:
    # Register ALL pages here (including editor), but editor is hidden via CSS
    nav = st.navigation({"Main": [dashboard_page, workouts_page, editor_page]})

    # Sidebar account block (unique key => no duplicate widget id)
    with st.sidebar:
        st.markdown("### Account")
        try:
            st.write(st.session_state["user"].email)
        except Exception:
            st.write("—")

        if st.button("Logout", use_container_width=True, key="sidebar_logout_btn"):
            logout()
            st.stop()

    # ---- CRUCIAL: handle programmatic open-editor BEFORE nav.run() ----
    # Workouts.py sets: open_editor=True + editor_workout_id + editor_mode
    if st.session_state.get("open_editor") is True:
        st.session_state["open_editor"] = False
        st.switch_page("pages/WorkoutEditor.py")
        st.stop()

    nav.run()


# ---------------------------
# Main
# ---------------------------
if not is_authed():
    run_login_page()
else:
    run_authed_app()
