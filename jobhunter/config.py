"""Loads config.yaml (what to search) and profile.yaml (who is searching)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .filtering import SearchProfile

_ENV_REF = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand_env(value):
    """Expand ${VAR} and ${VAR:-default} inside string values."""
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


def load_yaml(path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("%s: top level must be a mapping" % path)
    return _expand_env(data)


@dataclass
class Settings:
    config: Dict[str, Any]
    profile: Dict[str, Any]
    root: Path

    @classmethod
    def load(cls, config_path="config.yaml", profile_path="profile.yaml") -> "Settings":
        config = load_yaml(config_path)
        profile = load_yaml(profile_path) if Path(profile_path).exists() else {}
        if not config.get("search_profiles"):
            raise ValueError("config.yaml: 'search_profiles' must define at least one profile")
        settings = cls(config, profile, Path(config_path).resolve().parent)
        settings.search_profiles  # validate early
        return settings

    def section(self, name: str) -> Dict[str, Any]:
        return self.config.get(name) or {}

    @property
    def run(self) -> Dict[str, Any]:
        return self.section("run")

    @property
    def sources(self) -> Dict[str, Any]:
        return self.section("sources")

    @property
    def search_profiles(self) -> List[SearchProfile]:
        return [SearchProfile.from_dict(p) for p in self.config["search_profiles"] if p.get("enabled", True)]

    def _dir(self, env_var: str, key: str, default: str) -> Path:
        path = Path(os.environ.get(env_var) or self.run.get(key) or default)
        return path if path.is_absolute() else self.root / path

    @property
    def state_dir(self) -> Path:
        return self._dir("STATE_DIR", "state_dir", "state")

    @property
    def output_dir(self) -> Path:
        return self._dir("OUTPUT_DIR", "output_dir", "output")
