#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for function_registry, FunctionsCombo, FunctionsHelpDialog, and cursor-in-parens logic."""

import pytest

from pqwave.ui.function_registry import (
    FunctionInfo,
    get_all_functions,
    get_all_constants,
    lookup,
)


# --- FunctionInfo dataclass ---

def test_functioninfo_fields():
    """Verify FunctionInfo can be constructed with all fields."""
    info = FunctionInfo(
        name="sin",
        signature="sin(x)",
        description="Sine of x",
        category="Trig",
        arg_count=1,
    )
    assert info.name == "sin"
    assert info.signature == "sin(x)"
    assert info.description == "Sine of x"
    assert info.category == "Trig"
    assert info.arg_count == 1


# --- Function registry: metadata completeness ---

def test_registry_all_functions_have_metadata():
    """Every function entry has name, signature, description, category, arg_count."""
    for fn in get_all_functions():
        assert isinstance(fn.name, str) and fn.name, f"missing name: {fn}"
        assert isinstance(fn.signature, str) and fn.signature, f"missing signature: {fn}"
        assert isinstance(fn.description, str) and fn.description, f"missing description: {fn}"
        assert isinstance(fn.category, str) and fn.category, f"missing category: {fn}"
        assert isinstance(fn.arg_count, int), f"arg_count must be int: {fn}"


def test_registry_all_constants_have_metadata():
    """Every constant entry has arg_count=0."""
    for c in get_all_constants():
        assert c.arg_count == 0, f"constant {c.name} should have arg_count=0"


# --- Function registry: lookup ---

def test_registry_lookup_hit():
    """lookup('sin') returns correct FunctionInfo."""
    info = lookup("sin")
    assert info is not None
    assert info.name == "sin"
    assert info.arg_count == 1


def test_registry_lookup_miss():
    """lookup('nonexistent') returns None."""
    assert lookup("nonexistent") is None


def test_registry_lookup_constant():
    """lookup('pi') returns a constant with arg_count=0."""
    info = lookup("pi")
    assert info is not None
    assert info.arg_count == 0


# --- Function registry: counts ---

def test_registry_function_count():
    """At least 80 functions registered."""
    assert len(get_all_functions()) >= 80


def test_registry_constant_count():
    """At least 5 constants registered."""
    assert len(get_all_constants()) >= 5


# --- Cursor-in-parens logic ---

from pqwave.ui.main_window import MainWindow


def test_cursor_in_parens_basic():
    """Cursor between () of a function should be detected."""
    assert MainWindow._cursor_in_parens("sin()", 4) is True


def test_cursor_in_parens_at_close_paren():
    """Cursor right after close paren is not inside."""
    assert MainWindow._cursor_in_parens("sin()", 5) is False


def test_cursor_in_parens_not_inside():
    """Cursor between two separate function calls returns False."""
    assert MainWindow._cursor_in_parens("sin() + cos()", 6) is False


def test_cursor_in_parens_nested():
    """Cursor inside nested parens still returns True."""
    assert MainWindow._cursor_in_parens("sin(cos(x))", 4) is True


def test_cursor_in_parens_no_close():
    """Incomplete expression (no closing paren) returns True because we're inside."""
    text = "sin("
    assert MainWindow._cursor_in_parens(text, 4) is True


def test_cursor_in_parens_inside_first():
    """Cursor inside first function's parens with another function after."""
    assert MainWindow._cursor_in_parens("sin(x) + cos(y)", 4) is True


def test_cursor_in_parens_inside_second():
    """Cursor inside second function's parens."""
    assert MainWindow._cursor_in_parens("sin(x) + cos(y)", 13) is True


def test_cursor_in_parens_outside_both():
    """Cursor outside both function parens."""
    assert MainWindow._cursor_in_parens("sin(x) + cos(y)", 7) is False


def test_cursor_in_parens_empty_text():
    """Empty text returns False."""
    assert MainWindow._cursor_in_parens("", 0) is False


def test_cursor_in_parens_at_open_paren():
    """Cursor right at open paren is not yet inside."""
    assert MainWindow._cursor_in_parens("sin(x)", 3) is False
