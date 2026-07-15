"""
Configuration loader for the Narrative Intelligence Engine.

Loads YAML configuration and provides access to settings across all subsystems.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# Project root is two levels up from this file (src/utils/config.py → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class Config:
    """
    Centralized configuration manager.

    Loads settings from YAML and provides convenient access.
    Supports environment variable overrides for deployment flexibility.
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config: Dict[str, Any] = {}
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._load()
        self._load_dotenv()

    def _load(self) -> None:
        """Load configuration from YAML file."""
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            print(f"[Config] Warning: Config file not found at {self._config_path}, using defaults.")
            self._config = {}

    def _load_dotenv(self) -> None:
        """Load environment variables from .env file if it exists."""
        dotenv_path = PROJECT_ROOT / ".env"
        if dotenv_path.exists():
            try:
                with open(dotenv_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            val = parts[1].strip()
                            # Strip quotes if present
                            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                                val = val[1:-1]
                            os.environ[key] = val
            except Exception as e:
                print(f"[Config] Warning: Failed to read .env file: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a config value using dot-notation path.

        Example:
            config.get("pipeline.spacy_model")  → "en_core_web_sm"
            config.get("narrative_state.min_confidence")  → 0.3
        """
        # Check environment variable override first
        env_key = f"NARRATIVE_ENGINE_{key_path.upper().replace('.', '_')}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val

        # Walk the config dict
        keys = key_path.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def data_dir(self) -> Path:
        """Path to the data directory."""
        return PROJECT_ROOT / self.get("paths.data_dir", "data")

    @property
    def memory_dir(self) -> Path:
        """Path to the memory serialization directory."""
        return PROJECT_ROOT / self.get("paths.memory_dir", "data/memory")

    @property
    def output_dir(self) -> Path:
        """Path to the output directory."""
        return PROJECT_ROOT / self.get("paths.output_dir", "data/output")

    @property
    def cache_dir(self) -> Path:
        """Path to the pipeline cache directory."""
        return PROJECT_ROOT / self.get("paths.cache_dir", "data/cache")

    @property
    def chapters_dir(self) -> Path:
        """Path to raw chapter text files."""
        return self.data_dir / "chapters"

    @property
    def summaries_dir(self) -> Path:
        """Path to chapter summaries and baseline outlines."""
        return self.data_dir / "summaries"

    @property
    def profiles_dir(self) -> Path:
        """Path to individual character profile JSON files."""
        return self.data_dir / "profiles"

    @property
    def relationships_dir(self) -> Path:
        """Path to individual relationship states."""
        return self.data_dir / "relationships"

    @property
    def clues_dir(self) -> Path:
        """Path to physical item/clue states."""
        return self.data_dir / "clues"

    @property
    def promises_dir(self) -> Path:
        """Path to open/unresolved plot promises."""
        return self.data_dir / "promises"

    @property
    def reports_dir(self) -> Path:
        """Path to raw editorial reports."""
        return self.data_dir / "reports"

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        dirs = [
            self.data_dir,
            self.memory_dir,
            self.output_dir,
            self.cache_dir,
            self.chapters_dir,
            self.summaries_dir,
            self.profiles_dir,
            self.relationships_dir,
            self.clues_dir,
            self.promises_dir,
            self.reports_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)


# Global config instance (lazy-loaded)
_global_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """Get or create the global configuration instance."""
    global _global_config
    if _global_config is None or config_path is not None:
        _global_config = Config(config_path)
    return _global_config
