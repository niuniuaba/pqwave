#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Legacy shim.

All project metadata lives in ``pyproject.toml``; the version in turn comes from
``pqwave/_version.py``. This file exists only so that tooling which still calls
``setup.py`` keeps working. It deliberately does not restate any metadata, because
the previous copy here pinned ``version="0.3.3"`` and an ``entry_point`` of
``pqwave:main``, both of which silently drifted from the real package.
"""

from setuptools import setup

setup()
