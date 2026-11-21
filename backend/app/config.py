"""Runtime configuration. All secrets come from environment variables (never from code)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

# Load backend/.env (local only, git-ignored). Real environment variables win.
load_dotenv(BACKEND_DIR / ".env", override=False)


def _float_or_none(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _resolve_data_dir() -> Path:
    env_dir = os.getenv("DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    if (PROJECT_DIR / "assignment_data").exists():
        return PROJECT_DIR / "assignment_data"
    return BACKEND_DIR / "data"


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "").strip())
    openrouter_model: str = field(default_factory=lambda: os.getenv("OPENROUTER_MODEL", "openrouter/free").strip())
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    )
    llm_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "45")))
    llm_max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "2")))
    llm_temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0")))
    # Optional price assumptions (USD per 1M tokens) used ONLY for estimates when the
    # provider does not return an actual cost. They are labelled as assumptions everywhere.
    price_input_per_m: float | None = field(default_factory=lambda: _float_or_none("MODEL_PRICE_INPUT_PER_M_USD"))
    price_output_per_m: float | None = field(default_factory=lambda: _float_or_none("MODEL_PRICE_OUTPUT_PER_M_USD"))

    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'triage.db').as_posix()}")
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
        ]
    )
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(256 * 1024))))
    ai_run_cooldown_seconds: int = field(default_factory=lambda: int(os.getenv("AI_RUN_COOLDOWN_SECONDS", "30")))
    allow_live_ai: bool = field(default_factory=lambda: os.getenv("ALLOW_LIVE_AI", "true").lower() == "true")
    snapshot_time_ist: str = field(default_factory=lambda: os.getenv("SNAPSHOT_TIME_IST", "2026-11-23 09:00"))
    data_dir: Path = field(default_factory=_resolve_data_dir)
    evaluation_dir: Path = BACKEND_DIR / "evaluation"
    artifacts_dir: Path = BACKEND_DIR / "artifacts"

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key)


def get_settings() -> Settings:
    return Settings()

