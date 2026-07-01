# Task 16: Smith Chart Cursor Readout -- Report

## Summary

Added a three-line cursor readout overlay to the Smith chart panel that displays the reflection coefficient (Gamma), normalized impedance (z), and denormalized impedance (Z) when the cursor is moved.

## Changes Made

**File:** `pqwave/ui/main_window.py` -- `_show_smith` method

- Added a `pg.TextItem` cursor readout label anchored at top-left position `(-1.15, 1.15)` on the Smith chart panel.
- Stored `z0` (reference impedance) and `cursor_label` on the panel instance for external access.
- Connected `pw.cursor_xa_changed` to a new handler `_on_smith_cursor_xa_changed` that:
  1. Finds the nearest Gamma trace point to the cursor's X position (Re(Gamma)).
  2. Computes `|Gamma|` and `angle(Gamma)` in degrees.
  3. Converts Gamma to normalized impedance: `z = (1 + Gamma) / (1 - Gamma)`.
  4. Denormalizes to: `Z = z * Z0`.
  5. Displays a three-line readout:
     - `Gamma = |Gamma| ∠ phase deg`
     - `z = r + jx`
     - `Z = R + jX Ohm`

## Verification

- `make lint`: no new errors in modified lines (pre-existing lint issues remain).
- `make format`: black reformatting applied.
- Logic verified: Gamma-to-impedance conversion uses the standard formula `z = (1+Gamma)/(1-Gamma)`, which is the inverse of the `compute_reflection_coefficient` from `pqwave/analysis/smith.py`.
