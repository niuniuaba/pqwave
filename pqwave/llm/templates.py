#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Template engine for NL → pqwave command translation.

Runs before any LLM call. If a template matches, the result is
deterministic, instant, and free. Users extend via ~/.pqwave/templates.yaml.
"""

from __future__ import annotations

import os
import re

import logging
import yaml

logger = logging.getLogger(__name__)


# ---- Built-in templates ----
_BUILTIN_TEMPLATES = [
    # show / plot (specific patterns first)
    {"match": r"(?:plot|show|display|add)\s+(?P<sig>.+?)\s+(?:to|on)\s+(?P<axis>Y[12])",
     "code": 'add("{sig}", axis="{axis}")'},

    # eye diagram (before generic show — "eyediagram" has no space)
    {"match": r"\b(?:plot|show)\s+eye\s*(?:diagram\s+)?(?:of|for)\s+(?P<sig>\S+)\s+period\s+(?P<period>\S+)",
     "code": 'eye("{sig}", period="{period}")'},
    {"match": r"\b(?:plot|show)\s+eye\s*(?:diagram\s+)?(?:of|for)\s+(?P<sig>\S+)",
     "code": 'eye("{sig}")'},

    # X vs Y: "plot v(r1) vs v(r2)" → add both
    {"match": r"\b(?:plot|show)\s+(?P<sig1>\S+)\s+(?:vs\.?|versus|against)\s+(?P<sig2>\S+)",
     "code": 'add(["{sig1}", "{sig2}"])'},

    # "set X as x axis" → change X variable
    {"match": r"\b(?:set|use|change)\s+(?P<sig>\S+)\s+(?:as|to)\s+(?:the\s+)?x\s*(?:axis|var(?:iable)?)?",
     "code": 'change_x("{sig}")'},

    # signals / info (allow words between command and target)
    {"match": r"\b(?:plot|show|display|add)\b.*\b(?:all\s+)?(?:signals|vectors|traces|waves)",
     "code": 'add_all()'},
    {"match": r"\b(?:list|get|show)\b.*\b(?:signal|vector|trace|wave)\s*names",
     "code": 'signals()'},
    # "list all vectors", "list up vectors", "list all signals", etc.
    {"match": r"\b(?:list|get|show)\b.*\b(?:all\s+)?(?:vectors|signals|traces|waves)(?!\s*\w)",
     "code": 'signals()'},
    {"match": r"\b(?:plot|show|display|add)\b.*\binfo\b",
     "code": 'info()'},

    # Wildcard: plot v(q*) → show matching
    {"match": r"\b(?:plot|show|display|add)\s+(?P<sig>\w+\([^)]*\*[^)]*\))",
     "code": 'show_matching("{sig}")'},

    # Bare wildcard: plot q* → show matching (no parens, no math context)
    {"match": r"\b(?:plot|show|display|add)\s+(?P<sig>[a-zA-Z_]\w*[*?][*\w]*)",
     "code": 'show_matching("{sig}")'},

    # comma-separated list → show([...])
    {"match": r"(?:plot|show|display|add)\s+(?P<sig>.+?,\s*.+)",
     "code": 'add([{sig}])'},

    # plot FUNC of sig → show("func(sig)") — must precede generic show
    {"match": r"\b(?:plot|show|display|add)\s+(?P<func>FUNC_RE)\s+of\s+(?P<sig>\S+)",
     "code": 'add("{func}({sig})")'},

    # generic add (sig = non-whitespace, since signal names have no spaces)
    {"match": r"\b(?:plot|show|display|add)\s+(?P<sig>\S+)",
     "code": 'add("{sig}")'},

    # hide / remove
    {"match": r"\b(?:hide|remove|delete)\s+(?P<sig>\S+)",
     "code": 'remove("{sig}")'},

    # measure with from/to (most specific first — non-greedy func captures multi-word names)
    {"match": r"measure\s+(?P<func>.+?)\s+of\s+(?P<sig>\S+)\s+(?:from|within\s+range\s+of)\s+(?P<from>.+?)\s+to\s+(?P<to>.+)",
     "code": 'measure("{func}({sig})", from_="{from}", to="{to}")'},
    {"match": r"measure\s+(?P<func>.+?)\s+of\s+(?P<sig>\S+)\s+(?:from|starting\s+at)\s+(?P<from>.+)",
     "code": 'measure("{func}({sig})", from_="{from}")'},
    {"match": r"measure\s+(?P<func>.+?)\s+of\s+(?P<sig>.+)",
     "code": 'measure("{func}({sig})")'},

    # fft (before generic "of" patterns)
    {"match": r"\bfft\s+of\s+(?P<sig>\S+)\s+with\s+(?P<window>\w+)\s+window",
     "code": 'fft("{sig}", window="{window}")'},
    {"match": r"\bfft\s+of\s+(?P<sig>\S+)",
     "code": 'fft("{sig}")'},

    # standalone: "<func> of <sig> ..." — func must be a known keyword
    {"match": r"(?P<func>FUNC_RE)\s+of\s+(?P<sig>\S+)\s+(?:from|within\s+range\s+of)\s+(?P<from>.+?)\s+to\s+(?P<to>.+)",
     "code": 'measure("{func}({sig})", from_="{from}", to="{to}")'},
    {"match": r"(?P<func>FUNC_RE)\s+of\s+(?P<sig>\S+)\s+(?:from|starting\s+at)\s+(?P<from>.+)",
     "code": 'measure("{func}({sig})", from_="{from}")'},
    {"match": r"(?P<func>FUNC_RE)\s+of\s+(?P<sig>\S+)",
     "code": 'measure("{func}({sig})")'},

    # load
    {"match": r"load\s+(?P<path>.+)",
     "code": 'load("{path}")'},

    # range (xmin/xmax must be numeric)
    {"match": r"\b(?:set\s+)?x\s*(?:axis|range)?\s+(?:from\s+)?(?P<xmin>[-+]?[\d.]+(?:\s*\w+)?)\s+(?:to|through)\s+(?P<xmax>[-+]?[\d.]+(?:\s*\w+)?)",
     "code": 'range(xmin="{xmin}", xmax="{xmax}")'},
    {"match": r"\b(?:set\s+)?y\s*(?:axis|range)?\s+(?:from\s+)?(?P<ymin>[-+]?[\d.]+(?:\s*\w+)?)\s+(?:to|through)\s+(?P<ymax>[-+]?[\d.]+(?:\s*\w+)?)",
     "code": 'range(ymin="{ymin}", ymax="{ymax}")'},

    # log toggles
    {"match": r"\b(?:enable|turn\s+on|set)\s+log\s*x(?:\s*(?:axis|mode))?",
     "code": 'log_x(True)'},
    {"match": r"\b(?:disable|turn\s+off|unset)\s+log\s*x(?:\s*(?:axis|mode))?",
     "code": 'log_x(False)'},
    {"match": r"\b(?:enable|turn\s+on|set)\s+log\s*y(?:\s*(?:axis|mode))?",
     "code": 'log_y(True)'},
    {"match": r"\b(?:disable|turn\s+off|unset)\s+log\s*y(?:\s*(?:axis|mode))?",
     "code": 'log_y(False)'},
    {"match": r"\b(?:set\s+)?x\s*(?:axis|mode)\s+to\s+log(?:\s*mode)?",
     "code": 'log_x(True)'},
    {"match": r"\b(?:set\s+)?y\s*(?:axis|mode)\s+to\s+log(?:\s*mode)?",
     "code": 'log_y(True)'},
    {"match": r"\blog\s*x\b",
     "code": 'log_x()'},
    {"match": r"\blog\s*y\b",
     "code": 'log_y()'},

    # ---- Cursor positioning ----
    {"match": r"\b(?:set|move)\s+xa\s+(?:cursor\s+)?(?:to|at|position)?\s*(?:x\s*=\s*)?(?P<value>\S+)",
     "code": 'cursor_xa("{value}")'},
    {"match": r"\b(?:set|move)\s+xb\s+(?:cursor\s+)?(?:to|at|position)?\s*(?:x\s*=\s*)?(?P<value>\S+)",
     "code": 'cursor_xb("{value}")'},
    {"match": r"\b(?:set|move)\s+ya\s+(?:cursor\s+)?(?:to|at|position)?\s*(?:y\s*=\s*)?(?P<value>\S+)",
     "code": 'cursor_ya("{value}")'},
    {"match": r"\b(?:set|move)\s+yb\s+(?:cursor\s+)?(?:to|at|position)?\s*(?:y\s*=\s*)?(?P<value>\S+)",
     "code": 'cursor_yb("{value}")'},
    {"match": r"\b(?:what|get|show)\s+(?:is\s+)?(?:the\s+)?cursor\s+(?:delta|difference|between)",
     "code": 'cursor_delta()'},
    {"match": r"\b(?:show\s+)?cursor\s+(?:state|positions|all)",
     "code": 'cursor()'},
    {"match": r"\b(?:show|hide|toggle|enable|disable|turn\s+(?:on|off))\s+xa\s+cursor",
     "code": 'cursor_xa_visible(None)'},
    {"match": r"\b(?:show|hide|toggle|enable|disable|turn\s+(?:on|off))\s+xb\s+cursor",
     "code": 'cursor_xb_visible(None)'},
    {"match": r"\b(?:show|hide|toggle|enable|disable|turn\s+(?:on|off))\s+ya\s+cursor",
     "code": 'cursor_ya_visible(None)'},
    {"match": r"\b(?:show|hide|toggle|enable|disable|turn\s+(?:on|off))\s+yb\s+cursor",
     "code": 'cursor_yb_visible(None)'},
    {"match": r"\b(?:hide|disable|turn\s+off)\s+crosshair",
     "code": 'cross_hair(False)'},

    # ---- View toggles ----
    {"match": r"\b(?:turn|set|enable|show)\s+grid\s+(on|off|true|false)",
     "code": 'grid({0})'},
    {"match": r"\b(?:turn|set|disable|hide)\s+grid",
     "code": 'grid(False)'},
    {"match": r"\bgrid\b",
     "code": 'grid()'},
    {"match": r"\b(?:turn|set|enable|show)\s+legend\s+(on|off|true|false)",
     "code": 'legend({0})'},
    {"match": r"\b(?:turn|set|disable|hide)\s+legend",
     "code": 'legend(False)'},
    {"match": r"\blegend\b",
     "code": 'legend()'},
    {"match": r"\b(?:turn|set|enable|show)\s+cross(?:\s*_?\s*|\s+)hair\s+(on|off|true|false)",
     "code": 'cross_hair({0})'},
    {"match": r"\bcross(?:\s*_?\s*|\s+)hair\b",
     "code": 'cross_hair()'},
    {"match": r"\b(?:zoom\s+)?fit\s*(?:all|view|traces)?",
     "code": 'zoom_fit()'},
    {"match": r"\bauto\s*[-_]?\s*range\s*x",
     "code": 'auto_range_x()'},
    {"match": r"\bauto\s*[-_]?\s*range\s*y",
     "code": 'auto_range_y()'},
    {"match": r"\b(?:set\s+)?title\s+(?:to\s+)?(?P<text>.+)",
     "code": 'title("{text}")'},

    # ---- Bus / Digital ----
    {"match": r"\b(?:group|create|make)\s+(?P<sig>.+?)\s+(?:as|into)\s+(?:a\s+)?bus\s*(?P<name>\w+)?",
     "code": 'bus([{sig}], name="{name}")'},
    {"match": r"\bexpand\s+(?P<name>\S+)",
     "code": 'expand("{name}")'},
    {"match": r"\bcollapse\s+(?P<name>\S+)",
     "code": 'collapse("{name}")'},
    {"match": r"\b(?:set|make|toggle)\s+(?P<sig>\S+)\s+(?:to\s+)?(?P<mode>digital|analog)",
     "code": 'digital("{sig}", on={mode})'},

    # ---- Trace properties ----
    {"match": r"\b(?:set\s+)?(?P<name>\S+)\s+height\s+(?:to\s+)?(?P<height>[\d.]+)x?",
     "code": 'set_trace("{name}", height={height})'},
    {"match": r"\b(?:set\s+)?(?P<name>\S+)\s+(?:line\s+)?width\s+(?:to\s+)?(?P<width>\d+)",
     "code": 'set_trace("{name}", width={width})'},
    {"match": r"\b(?:set\s+)?(?P<name>\S+)\s+color\s+(?:to\s+)?(?P<color>\S+)",
     "code": 'set_trace("{name}", color="{color}")'},
    {"match": r"\b(?:set\s+)?(?P<name>\S+)\s+alias\s+(?:to\s+)?(?P<alias>\S+)",
     "code": 'set_trace("{name}", alias="{alias}")'},

    # ---- FFT config ----
    {"match": r"\b(?:set\s+)?fft\s+window\s+(?:to\s+)?(?P<window>\w+)",
     "code": 'fft_config(window="{window}")'},
    {"match": r"\b(?:set\s+)?fft\s+(?:to\s+)?(?P<repr>db|linear|log)",
     "code": 'fft_config(representation="{repr}")'},

    # ---- Reload ----
    {"match": r"\b(?:reload|refresh|re-read|reread)\s*(?:file|data|simulation)?",
     "code": 'reload()'},

    # ---- Theme ----
    {"match": r"\b(?:set\s+)?theme\s+(?:to\s+)?(?P<name>dark|light)",
     "code": 'theme("{name}")'},

    # ---- Zoom ----
    {"match": r"\bzoom\s+in\b",
     "code": 'zoom_in()'},
    {"match": r"\bzoom\s+out\b",
     "code": 'zoom_out()'},

    # ---- Panel ----
    {"match": r"\bsplit\s+(?:panel\s+)?horizontal(?:ly)?",
     "code": 'split_horizontal()'},
    {"match": r"\bsplit\s+(?:panel\s+)?vertical(?:ly)?",
     "code": 'split_vertical()'},
    {"match": r"\bclose\s+(?:the\s+)?(?:active\s+)?panel",
     "code": 'close_panel()'},

    # ---- Chinese: add / plot ----
    {"match": r"(?:绘制|显示|添加|画)\s*(?P<sig>.+?)\s*(?:到|在)\s*(?P<axis>Y[12])",
     "code": 'add("{sig}", axis="{axis}")'},
    {"match": r"(?:显示\s*)?(?:所有|全部)\s*(?:信号|波形)",
     "code": 'signals()'},
    {"match": r"(?:显示\s*)?(?:信息|状态)",
     "code": 'info()'},
    {"match": r"(?:绘制|显示|添加|画)\s*(?P<sig>.+)",
     "code": 'add("{sig}")'},

    # ---- Chinese: remove / delete ----
    {"match": r"(?:隐藏|删除|移除)\s*(?P<sig>.+)",
     "code": 'remove("{sig}")'},

    # ---- Chinese: measure with from/to ----
    {"match": r"测量\s*(?P<sig>\S+)\s*的\s*(?P<func>.+?)\s*从\s*(?P<from>\S+)\s*到\s*(?P<to>\S+)",
     "code": 'measure("{func}({sig})", from_="{from}", to="{to}")'},
    {"match": r"测量\s*(?P<sig>\S+)\s*的\s*(?P<func>.+?)\s*从\s*(?P<from>\S+)",
     "code": 'measure("{func}({sig})", from_="{from}")'},
    {"match": r"测量\s*(?P<sig>\S+)\s*的\s*(?P<func>.+)",
     "code": 'measure("{func}({sig})")'},

    # ---- Chinese: FFT (before generic "<sig> 的 <func>") ----
    {"match": r"(?P<sig>\S+)\s*的\s*fft\s*(?:使用|用)?\s*(?P<window>\w+)\s*(?:窗|窗口)?",
     "code": 'fft("{sig}", window="{window}")'},
    {"match": r"(?P<sig>\S+)\s*的\s*(?:fft|频谱|傅里叶)",
     "code": 'fft("{sig}")'},

    # ---- Chinese: standalone "<sig> 的 <func>" ----
    {"match": r"(?P<sig>\S+)\s*的\s*(?P<func>.+?)\s*从\s*(?P<from>\S+)\s*到\s*(?P<to>\S+)",
     "code": 'measure("{func}({sig})", from_="{from}", to="{to}")'},
    {"match": r"(?P<sig>\S+)\s*的\s*(?P<func>.+?)\s*从\s*(?P<from>\S+)",
     "code": 'measure("{func}({sig})", from_="{from}")'},
    {"match": r"(?P<sig>\S+)\s*的\s*(?P<func>.+)",
     "code": 'measure("{func}({sig})")'},

    # ---- Chinese: load ----
    {"match": r"(?:加载|打开|读取)\s*(?P<path>.+)",
     "code": 'load("{path}")'},

    # ---- Chinese: range ----
    {"match": r"[Xx](?:轴)?\s*(?:范围|从)?\s*(?P<xmin>\S+)\s*(?:到|至|~)\s*(?P<xmax>\S+)",
     "code": 'range(xmin="{xmin}", xmax="{xmax}")'},
    {"match": r"[Yy](?:轴)?\s*(?:范围|从)?\s*(?P<ymin>\S+)\s*(?:到|至|~)\s*(?P<ymax>\S+)",
     "code": 'range(ymin="{ymin}", ymax="{ymax}")'},

    # ---- Chinese: log toggles ----
    {"match": r"(?:开启|打开|启用)\s*(?:对数|log)\s*[Xx](?:轴)?",
     "code": 'log_x(True)'},
    {"match": r"(?:关闭|禁用)\s*(?:对数|log)\s*[Xx](?:轴)?",
     "code": 'log_x(False)'},
    {"match": r"(?:开启|打开|启用)\s*(?:对数|log)\s*[Yy](?:轴)?",
     "code": 'log_y(True)'},
    {"match": r"(?:关闭|禁用)\s*(?:对数|log)\s*[Yy](?:轴)?",
     "code": 'log_y(False)'},
]

# User-friendly name → internal function name
_FUNC_MAP = {
    # English
    # English (long → short, short → self for function name lookup)
    "minimum": "min", "maximum": "max", "average": "avg", "mean": "avg",
    "min": "min", "max": "max", "avg": "avg", "rms": "rms",
    "peak to peak": "pp", "peak-to-peak": "pp", "pp": "pp",
    "integral": "integ", "integ": "integ",
    "rise time": "rise_time", "rise_time": "rise_time",
    "fall time": "fall_time", "fall_time": "fall_time",
    "duty cycle": "duty_cycle", "duty_cycle": "duty_cycle",
    "pulse width": "pulse_width", "pulse_width": "pulse_width",
    "settling time": "settling_time", "settling_time": "settling_time",
    "slew rate": "slew_rate", "slew_rate": "slew_rate",
    "overshoot": "overshoot", "undershoot": "undershoot",
    "period": "period", "frequency": "frequency",
    "thd": "thd", "snr": "snr", "sfdr": "sfdr", "sinad": "sinad",
    # Chinese
    "最小值": "min", "最小": "min",
    "最大值": "max", "最大": "max",
    "平均值": "avg", "平均": "avg", "均值": "avg",
    "均方根": "rms", "有效值": "rms",
    "峰峰值": "pp", "峰峰值": "pp",
    "积分": "integ",
    "上升时间": "rise_time", "下降时间": "fall_time",
    "周期": "period", "频率": "frequency",
    "占空比": "duty_cycle", "脉冲宽度": "pulse_width",
    "建立时间": "settling_time", "压摆率": "slew_rate",
    "过冲": "overshoot", "下冲": "undershoot",
    "总谐波失真": "thd", "谐波失真": "thd",
    "信纳比": "sinad", "信噪比": "snr",
    "无杂散动态范围": "sfdr",
}

# Common English words that are never valid signal names.
# Templates skip matches where sig matches one of these.
def _func_alternation():
    """Build regex alternation of all known function names, longest first."""
    names = sorted(_FUNC_MAP.keys(), key=len, reverse=True)
    return "(?:" + "|".join(re.escape(n) for n in names) + ")"

# Lazily cached alternation
_FUNC_RE = None


def _get_func_re():
    global _FUNC_RE
    if _FUNC_RE is None:
        _FUNC_RE = _func_alternation()
    return _FUNC_RE


_SIG_STOP_WORDS = frozenset({
    "me", "you", "the", "a", "an", "it", "is", "are", "be", "to",
    "from", "of", "in", "on", "at", "with", "and", "or", "all",
    "this", "that", "now", "please", "can", "could", "would",
    "i", "we", "they", "he", "she", "my", "your", "our", "their",
    "what", "which", "where", "when", "how", "why", "who",
    "do", "does", "did", "has", "have", "had", "will", "shall",
    "not", "no", "just", "only", "also", "very", "really",
    "show", "hide", "plot", "display", "add", "measure",
})


class TemplateEngine:
    """Deterministic NL → code translation via regex patterns."""

    def __init__(self):
        self._templates: list[dict] = []
        self._load()

    # ---- Loading ----

    def _load(self):
        func_re = _get_func_re()
        self._templates = []
        for tmpl in _BUILTIN_TEMPLATES:
            match = tmpl["match"].replace("FUNC_RE", func_re)
            self._templates.append({"match": match, "code": tmpl["code"]})
        # Project-level templates (ships with pqwave, in git)
        self._load_yaml(self._project_path(), func_re, prepend=False)
        # User-level templates (personal, ~/.pqwave/)
        self._load_yaml(self._user_path(), func_re, prepend=True)

    def _load_yaml(self, path, func_re, prepend):
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "templates" in data:
                for tmpl in data["templates"]:
                    tmpl["match"] = tmpl["match"].replace("FUNC_RE", func_re)
                    if prepend:
                        self._templates.insert(0, tmpl)
                    else:
                        self._templates.append(tmpl)
        except Exception:
            logger.warning("Failed to load templates from %s", path, exc_info=True)

    @staticmethod
    def _user_path() -> str:
        return os.path.expanduser("~/.pqwave/templates.yaml")

    @staticmethod
    def _project_path() -> str:
        import pqwave.llm
        return os.path.join(
            os.path.dirname(pqwave.llm.__file__), "templates.yaml"
        )

    def ensure_user_file(self) -> str:
        """Create ~/.pqwave/templates.yaml with defaults if missing."""
        path = self._user_path()
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "# pqwave AI templates — add your own patterns here.\n"
                    "# Built-in templates always apply; these take priority.\n"
                    "#\n"
                    "# Format:\n"
                    "#   templates:\n"
                    "#     - match: \"regex pattern\"\n"
                    "#       code: 'Python code with {group} substitution'\n"
                    "#\n"
                    "# Example:\n"
                    "#   templates:\n"
                    "#     - match: \"measure power of (?P<v>\\S+) and (?P<i>\\S+)\"\n"
                    "#       code: 'power(\"{v}\", \"{i}\")'\n"
                    "\n"
                    "templates:\n"
                    "  # Add your patterns here\n"
                )
        return path

    # ---- Matching ----

    def translate(self, text: str) -> str | None:
        """Try to match text against templates. Returns code or None.

        Uses re.search() — patterns match anywhere in the input.
        Command templates use \\b word boundaries to anchor keywords.
        """
        text = text.strip()
        for tmpl in self._templates:
            m = re.search(tmpl["match"], text, re.IGNORECASE)
            if not m:
                continue
            groups = {k: v for k, v in m.groupdict().items() if v is not None}

            # Skip matches where signal is a stop word
            if "sig" in groups:
                sig_lower = groups["sig"].strip().lower()
                if sig_lower in _SIG_STOP_WORDS:
                    continue
                # Also skip pure punctuation / common filler
                if len(sig_lower) <= 1:
                    continue

            # Normalize function name (guaranteed to match via lookup table)
            if "func" in groups:
                groups["func"] = _FUNC_MAP[groups["func"].strip().lower()]

            # Strip existing quotes from signal names
            for key in ("sig", "path"):
                if key in groups:
                    val = groups[key].strip()
                    if (val.startswith('"') and val.endswith('"')) or \
                       (val.startswith("'") and val.endswith("'")):
                        groups[key] = val[1:-1]

            # Collapse spaces in numeric/unit values: "10 ms" → "10ms"
            for key in ("from", "to", "xmin", "xmax", "ymin", "ymax"):
                if key in groups:
                    groups[key] = re.sub(r'\s+', '', groups[key].strip())

            # Split comma-separated signal lists
            if "sig" in groups and "," in groups["sig"]:
                items = [s.strip() for s in groups["sig"].split(",") if s.strip()]
                if '"{sig}"' in tmpl["code"]:
                    # Template wraps in its own quotes — rejoin as raw names
                    groups["sig"] = ", ".join(items)
                else:
                    # Template expects pre-quoted list items
                    groups["sig"] = ", ".join(f'"{it}"' for it in items)

            try:
                return tmpl["code"].format(**groups)
            except KeyError:
                continue

        return None
