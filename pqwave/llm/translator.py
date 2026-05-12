#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Translator — converts natural language to pqwave Session API Python code.

Uses a configurable LLM backend with a system prompt that includes
the current session state and command registry.
"""

from __future__ import annotations


def _build_system_prompt(session) -> str:
    """Build the system prompt with command registry and session context."""
    from pqwave.session.api import get_command_registry

    command_lines = []
    for name, entry in sorted(get_command_registry().items()):
        command_lines.append(f"  {entry['signature']} — {entry['help']}")

    signal_text = ""
    try:
        sigs = session.signals()
        if sigs:
            signal_text = "Available signals: " + ", ".join(sigs[:30])
    except Exception:
        pass

    return f"""You are a pqwave code generator. Output exactly one line of Python code per request.
No explanation, no markdown, no backticks. Just the code.

Commands:
{chr(10).join(command_lines)}

{signal_text}

EXAMPLES — these show the correct calling convention:

User: plot vout
Code: show("vout")

User: plot vout to Y2
Code: show("vout", axis="Y2")

User: measure rise time of vout
Code: measure("rise_time(vout)")

User: measure avg of vout from 1ms to 10ms
Code: measure("avg(vout)", from_="1m", to="10m")

User: measure minimum of vout from 10ms to 20ms
Code: measure("min(vout)", from_="10m", to="20m")

User: measure peak to peak of i(r1)
Code: measure("pp(i(r1))")

User: fft of vout with hann window
Code: fft("vout", window="hann")

User: show me all signals
Code: signals()

User: add vout and vin
Code: show(["vout", "vin"])

User: remove vout
Code: hide("vout")

RULES:
- from_= and to= are Python kwargs, NOT inside the expression string
  WRONG: measure("avg(vout), from=1m, to=10m")
  RIGHT: measure("avg(vout)", from_="1m", to="10m")
- Signal names are strings: show("vout") NOT show(vout)
- "plot" = show, "minimum" = min(), "peak to peak" = pp(), "average" = avg()
- Time/freq values keep SPICE suffixes as strings: "1m", "10u", "1k"
- NEVER use undefined variable names like v(r1) without quotes"""


class AITranslator:
    """Translates natural language to executable Python code.

    Backends (independently toggleable):
      1. Template engine (deterministic, instant, free).
      2. LLM (local model or cloud API).
    """

    def __init__(self, session=None):
        from pqwave.session.api import SessionAPI
        from pqwave.llm.backends import create_backend_for_active
        from pqwave.llm.templates import TemplateEngine

        self._session = session or SessionAPI()
        self._backend = create_backend_for_active()
        self._templates = TemplateEngine()
        self.template_enabled: bool = True
        self.llm_enabled: bool = True
        self._learn_log: list[dict] = []

    @property
    def is_configured(self) -> bool:
        return self._backend is not None

    @property
    def model_name(self) -> str:
        """Return the model name of the active backend, or 'llm'."""
        if self._backend is not None:
            return getattr(self._backend, 'model', 'llm')
        from pqwave.llm.backends import get_active_profile_name
        name = get_active_profile_name()
        return name or 'llm'

    def reload_config(self) -> bool:
        from pqwave.llm.backends import create_backend_for_active

        self._backend = create_backend_for_active()
        return self._backend is not None

    @property
    def last_timing(self) -> dict | None:
        """Timing info from the last translate() call, or None."""
        return getattr(self, "_last_timing", None)

    def translate(self, text: str) -> str:
        import time

        # 1. Template engine
        if self.template_enabled:
            t0 = time.monotonic()
            code = self._templates.translate(text)
            if code is not None:
                self._last_timing = {
                    "backend": "template",
                    "elapsed_ms": (time.monotonic() - t0) * 1000,
                }
                return code

        # 2. LLM backend
        if not self.llm_enabled:
            raise RuntimeError(
                "All backends disabled. Use /backend template on "
                "or /backend llm on to enable one."
            )

        if not self._backend:
            raise RuntimeError(
                "No AI backend configured. Run pqwave --setup-llm "
                "or click the gear icon."
            )

        system_prompt = _build_system_prompt(self._session)
        t0 = time.monotonic()
        response, meta = self._backend.chat(system_prompt, text)
        elapsed = (time.monotonic() - t0) * 1000

        self._last_timing = {"backend": "llm", "elapsed_ms": elapsed}
        if meta:
            self._last_timing.update(meta)

        code = response.strip()
        for prefix in ("Code:", "code:", "Python:", "python:", "Command:", "command:"):
            if code.startswith(prefix):
                code = code[len(prefix):].strip()
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines).strip()

        self._learn_log.append({"query": text, "code": code, "ms": elapsed})
        return code

    # ---- /remember ----

    def _generalize_one(self, query: str, code: str) -> dict | None:
        """Turn one (query, code) pair into a template pattern.

        Returns {match, code} or None if already covered or not generalizable.
        """
        import re
        # If already covered by existing templates, skip
        if self._templates.translate(query) is not None:
            return None

        vars_in_code = re.findall(r'"([^"]*)"', code)
        if not vars_in_code:
            # No variables — exact match template
            return {"match": "^" + re.escape(query) + "$", "code": code}

        match = re.escape(query)
        code_tmpl = code
        for i, val in enumerate(vars_in_code):
            name = f"arg{i+1}" if len(vars_in_code) > 1 else "sig"
            match = match.replace(re.escape(val), f"(?P<{name}>\\\\S+)", 1)
            code_tmpl = code_tmpl.replace(f'"{val}"', f'"{{{name}}}"', 1)

        return {"match": match, "code": code_tmpl}

    def remember_all(self) -> list[dict]:
        """Generalize all logged LLM translations into templates."""
        results = []
        for entry in list(self._learn_log):
            tmpl = self._generalize_one(entry["query"], entry["code"])
            if tmpl:
                results.append(tmpl)
        self._learn_log.clear()
        return results

    def remember_last(self) -> dict | None:
        """Generalize only the most recent LLM translation."""
        if not self._learn_log:
            return None
        entry = self._learn_log.pop()
        return self._generalize_one(entry["query"], entry["code"])

    def log_count(self) -> int:
        return len(self._learn_log)

    def test_llm(self) -> str:
        """Test the LLM connection. Returns response or raises."""
        if not self._backend:
            raise RuntimeError("No LLM backend configured.")
        resp, _ = self._backend.chat("Reply with exactly: OK", "ping")
        return resp
