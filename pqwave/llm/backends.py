#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LLM backend implementations for the AI translator.

Two backends share the LLMBackend protocol:
  - LocalURLBackend: OpenAI-compatible local endpoint (Ollama, LM Studio, llama.cpp)
  - ExternalAPIBackend: remote API (OpenAI, Anthropic, anything-llm)

pqwave does not manage or bundle models. It connects to yours.

Config (multi-profile): ~/.pqwave/llm_config.json
  {
    "active": "ollama-qwen",
    "profiles": {
      "ollama-qwen": {"backend": "local_url", "endpoint": "http://localhost:11434/v1", "model": "qwen2.5:0.5b"},
      "openai": {"backend": "external_api", "endpoint": "https://api.openai.com/v1", "api_key": "sk-...", "model": "gpt-4o-mini"}
    }
  }
"""

from __future__ import annotations

import json
import os
from typing import Protocol


class LLMBackend(Protocol):
    """Protocol for LLM backends. Returns (text, metadata_dict)."""
    def chat(self, system_prompt: str, user_message: str) -> tuple[str, dict | None]: ...


class LocalURLBackend:
    """OpenAI-compatible local endpoint (Ollama, LM Studio, etc.)."""

    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    def chat(self, system_prompt: str, user_message: str) -> tuple[str, dict | None]:
        import urllib.request
        import urllib.error

        url = f"{self.endpoint}/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            meta = {}
            if usage:
                meta["prompt_tokens"] = usage.get("prompt_tokens")
                meta["completion_tokens"] = usage.get("completion_tokens")
                meta["total_tokens"] = usage.get("total_tokens")
            return text, (meta or None)
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to {url}: {e}")
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ValueError(f"Unexpected response from {url}: {e}")


class ExternalAPIBackend:
    """Remote API with API key (OpenAI, Anthropic, etc.)."""

    def __init__(self, endpoint: str, api_key: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model

    def chat(self, system_prompt: str, user_message: str) -> tuple[str, dict | None]:
        import urllib.request
        import urllib.error

        url = f"{self.endpoint}/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            meta = {}
            if usage:
                meta["prompt_tokens"] = usage.get("prompt_tokens")
                meta["completion_tokens"] = usage.get("completion_tokens")
                meta["total_tokens"] = usage.get("total_tokens")
            return text, (meta or None)
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to {url}: {e}")
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ValueError(f"Unexpected response from {url}: {e}")


# ---- Config helpers (multi-profile) ----

def _config_path() -> str:
    return os.path.expanduser("~/.pqwave/llm_config.json")


def _load_config() -> dict:
    """Load full config dict. Returns empty dict with defaults if no config."""
    path = _config_path()
    if not os.path.exists(path):
        return {"active": "default", "profiles": {
            "default": {"backend": "local_url", "endpoint": "http://localhost:11434/v1", "model": "qwen2.5:0.5b"}
        }}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "profiles" not in data or not data["profiles"]:
            data = {"active": "default", "profiles": {
                "default": {"backend": "local_url", "endpoint": "http://localhost:11434/v1", "model": "qwen2.5:0.5b"}
            }}
        if data.get("active") not in data.get("profiles", {}):
            data["active"] = next(iter(data["profiles"]))
        return data
    except (json.JSONDecodeError, OSError):
        return {"active": "default", "profiles": {
            "default": {"backend": "local_url", "endpoint": "http://localhost:11434/v1", "model": "qwen2.5:0.5b"}
        }}


def _save_config(config: dict) -> None:
    """Write config to disk with restricted permissions."""
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.chmod(path, 0o600)


def get_profiles() -> list[tuple[str, str, str]]:
    """Return [(name, backend_type, model), ...] for all profiles."""
    config = _load_config()
    profiles = config.get("profiles", {})
    return [(name, p.get("backend", ""), p.get("model", ""))
            for name, p in profiles.items()]


def get_active_profile_name() -> str | None:
    """Return the name of the currently active profile."""
    config = _load_config()
    active = config.get("active", "")
    if active in config.get("profiles", {}):
        return active
    profiles = config.get("profiles", {})
    if profiles:
        return next(iter(profiles))
    return None


def set_active_profile(name: str) -> bool:
    """Set the active profile by name. Returns True on success."""
    config = _load_config()
    if name not in config.get("profiles", {}):
        return False
    config["active"] = name
    _save_config(config)
    return True


def get_profile(name: str) -> dict | None:
    """Return a specific profile dict or None."""
    config = _load_config()
    return config.get("profiles", {}).get(name)


def save_profile(name: str, profile: dict) -> None:
    """Add or update a profile. If it's the first one, make it active."""
    config = _load_config()
    config["profiles"][name] = profile
    if config["active"] not in config["profiles"]:
        config["active"] = name
    _save_config(config)


def delete_profile(name: str) -> bool:
    """Delete a profile. Returns False if it's the last one."""
    config = _load_config()
    profiles = config.get("profiles", {})
    if name not in profiles:
        return False
    if len(profiles) <= 1:
        return False  # keep at least one
    del profiles[name]
    if config["active"] == name:
        config["active"] = next(iter(profiles))
    _save_config(config)
    return True


def create_backend_for_active() -> LLMBackend | None:
    """Create a backend instance for the active profile."""
    name = get_active_profile_name()
    if not name:
        return None
    return create_backend_for_profile(name)


def create_backend_for_profile(name: str) -> LLMBackend | None:
    """Create a backend instance for a named profile."""
    profile = get_profile(name)
    if not profile:
        return None
    return _create_backend_from_dict(profile)


def _create_backend_from_dict(profile: dict) -> LLMBackend | None:
    """Create a backend from a flat profile dict."""
    backend_type = profile.get("backend", "")
    if backend_type == "local_url":
        return LocalURLBackend(
            endpoint=profile.get("endpoint", "http://localhost:11434/v1"),
            model=profile.get("model", "qwen2.5:0.5b"),
        )
    elif backend_type == "external_api":
        api_key = profile.get("api_key", "") or os.environ.get(
            "PQWAVE_LLM_API_KEY", ""
        )
        if not api_key:
            raise ValueError("API key is required for external API backend")
        return ExternalAPIBackend(
            endpoint=profile.get("endpoint", "https://api.openai.com/v1"),
            api_key=api_key,
            model=profile.get("model", "gpt-4o-mini"),
        )
    return None


# Backwards-compat: migrate old single-backend config
def create_backend(config: dict) -> LLMBackend | None:
    """Legacy: create backend from old-style flat config. Prefer profiles."""
    return _create_backend_from_dict(config)


def save_config(config: dict) -> None:
    """Legacy: save old-style config. Converts to profile format."""
    if "profiles" in config:
        _save_config(config)
    else:
        backend_type = config.get("backend", "local_url")
        cfg = config.get(backend_type, {})
        profile = {"backend": backend_type}
        profile.update(cfg)
        _save_config({"active": "default", "profiles": {"default": profile}})
