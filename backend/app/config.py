"""
Application configuration using Pydantic Settings.
Loads environment variables consistently for local development and Docker.
"""
import os
import re
from pathlib import Path
from typing import List, Optional
from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parents[2]  # project root (c:\lyftrAI) or /app parent
_ROOT_ENV = _BASE_DIR / ".env"
_KEY_PATTERN = re.compile(r"^GROQ_API_KEY_(\d+)$", re.IGNORECASE)


class Settings(BaseSettings):
    """Application configuration settings."""

    # Groq API Keys (supports GROQ_API_KEY_1..N dynamically, plus LLM_API_KEYS)
    GROQ_API_KEY_1: str = ""
    GROQ_API_KEY_2: str = ""
    GROQ_API_KEY_3: str = ""
    GROQ_API_KEY_4: str = ""
    LLM_API_KEYS: str = ""

    # Model Configuration
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    MAX_TOKENS: Optional[int] = None

    # Database Configuration
    DATABASE_URL: str = "sqlite:////data/app.db"

    # CORS Configuration
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Failure Simulation
    ENABLE_FAILURE_SIMULATION: bool = False

    # Cache Configuration
    CACHE_ENABLED: bool = True
    CACHE_TYPE: str = "disk"
    CACHE_DIR: str = "/data/llm_cache"

    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def api_keys(self) -> List[str]:
        """
        Return ordered list of configured API keys.
        Combines all GROQ_API_KEY_1..N (sorted numerically) and comma-separated
        LLM_API_KEYS without duplicates while preserving order.
        """
        numbered_keys: dict[int, str] = {}

        # 1. Read from .env files first (lower priority than os.environ)
        for env_path in (_ROOT_ENV, Path(".env")):
            if env_path.is_file():
                for k, v in dotenv_values(env_path).items():
                    match = _KEY_PATTERN.match(k)
                    if match and v and v.strip():
                        numbered_keys[int(match.group(1))] = v.strip()

        # 2. Explicit fields on Settings (captures env overrides for 1..4)
        for idx, val in enumerate(
            [self.GROQ_API_KEY_1, self.GROQ_API_KEY_2, self.GROQ_API_KEY_3, self.GROQ_API_KEY_4],
            start=1,
        ):
            if val and val.strip():
                numbered_keys[idx] = val.strip()

        # 3. Any additional GROQ_API_KEY_<N> from process environment
        for k, v in os.environ.items():
            match = _KEY_PATTERN.match(k)
            if match and v and v.strip():
                numbered_keys[int(match.group(1))] = v.strip()

        keys: List[str] = []
        for idx in sorted(numbered_keys):
            candidate = numbered_keys[idx]
            if candidate not in keys:
                keys.append(candidate)

        if self.LLM_API_KEYS:
            for item in self.LLM_API_KEYS.split(","):
                cleaned = item.strip()
                if cleaned and cleaned not in keys:
                    keys.append(cleaned)

        return keys

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        if not self.ALLOWED_ORIGINS:
            return ["http://localhost:3000"]
        origins = [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]
        return origins or ["http://localhost:3000"]


settings = Settings()
