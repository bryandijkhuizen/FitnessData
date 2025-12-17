# lib/supabase_client.py
from __future__ import annotations

import os
import streamlit as st
from supabase import create_client  # type: ignore


def _secret(path: str, default: str = "") -> str:
    """
    Lees Streamlit secrets met support voor nested keys, bijv:
      _secret("supabase.url")
    """
    try:
        cur = st.secrets
        for part in path.split("."):
            cur = cur[part]
        return str(cur).strip()
    except Exception:
        return default


def _get_supabase_url() -> str:
    # 1) flat secret keys (optioneel)
    v = _secret("SUPABASE_URL", "")
    if v:
        return v
    # 2) jouw TOML structuur
    v = _secret("supabase.url", "")
    if v:
        return v
    # 3) env var fallback
    return os.getenv("SUPABASE_URL", "").strip()


def _get_supabase_anon_key() -> str:
    v = _secret("SUPABASE_ANON_KEY", "")
    if v:
        return v
    v = _secret("supabase.anon_key", "")
    if v:
        return v
    return os.getenv("SUPABASE_ANON_KEY", "").strip()


@st.cache_resource(show_spinner=False)
def get_supabase():
    url = _get_supabase_url()
    key = _get_supabase_anon_key()
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY (secrets/env)")
    return create_client(url, key)


def set_session_from_state():
    """
    Zorgt dat de supabase client de access/refresh tokens gebruikt (RLS).
    """
    sb = get_supabase()
    at = st.session_state.get("access_token")
    rt = st.session_state.get("refresh_token")
    if at and rt:
        try:
            sb.auth.set_session(at, rt)
        except Exception:
            pass
    return sb
