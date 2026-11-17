"""Runtime configuration for AutoGuard AI.

Everything is environment-driven so the same checkout can run as a local
demo, a lab deployment, or an evaluated capstone artefact.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"
DATA_DIR = ROOT / "data"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

APP_NAME = "AutoGuard AI"
APP_VERSION = "1.0.0"
TIMEZONE_NAME = os.getenv("AUTOGUARD_TZ", "Asia/Kolkata")
TIMEZONE = ZoneInfo(TIMEZONE_NAME)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DB_PATH = Path(os.getenv("AUTOGUARD_DB", DATA_DIR / "autoguard.db"))
DEMO_ENABLED = _env_bool("AUTOGUARD_DEMO", True)
LLM_ENABLED = _env_bool("AUTOGUARD_LLM_ENABLED", True)
LLM_API_KEY = (
    os.getenv("AUTOGUARD_LLM_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
).strip()
LLM_BASE_URL = (
    os.getenv("AUTOGUARD_LLM_BASE_URL")
    or os.getenv("OPENAI_BASE_URL")
    or "https://api.openai.com/v1"
).rstrip("/")
LLM_MODEL = os.getenv("AUTOGUARD_LLM_MODEL", "gpt-4o-mini").strip()
LLM_TIMEOUT = float(os.getenv("AUTOGUARD_LLM_TIMEOUT", "90"))
OLLAMA_URL = os.getenv("AUTOGUARD_OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.getenv("AUTOGUARD_OLLAMA_MODEL", "llama3.2").strip()
MAX_UPLOAD_BYTES = int(os.getenv("AUTOGUARD_MAX_UPLOAD_MB", "12")) * 1024 * 1024


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def local_now() -> datetime:
    return datetime.now(TIMEZONE)


def to_local(value: str | datetime | None) -> datetime | None:
    """Parse an ISO timestamp (naive values are treated as UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(TIMEZONE)


def day_start_utc(days_ago: int = 0) -> str:
    """UTC ISO boundary for local midnight ``days_ago`` days back."""
    local = local_now()
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_local = start_local - timedelta(days=days_ago)
    return start_local.astimezone(timezone.utc).isoformat(timespec="seconds")


def feature_flags() -> dict:
    return {
        "demo": DEMO_ENABLED,
        "llm": LLM_ENABLED and bool(LLM_API_KEY or OLLAMA_URL),
        "llm_provider": "ollama" if OLLAMA_URL else ("openai-compatible" if LLM_API_KEY else "local"),
        "llm_model": OLLAMA_MODEL if OLLAMA_URL else (LLM_MODEL if LLM_API_KEY else ""),
    }
