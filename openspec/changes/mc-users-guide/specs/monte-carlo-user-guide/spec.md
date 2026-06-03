## ADDED Requirements

### Requirement: Monte Carlo User Guide document

The system SHALL provide a comprehensive user's guide for the Monte Carlo analysis features, written in Markdown, located at `docs/monte_carlo/guide.md`.

#### Scenario: Guide covers loading workflow

- **WHEN** a user reads the guide
- **THEN** the guide explains all three MC loading modes (stepped, multi-file, pattern-based) with examples

#### Scenario: Guide covers display modes

- **WHEN** a user reads the guide
- **THEN** the guide documents spaghetti, envelope, and single-run display modes with the control bar UI

#### Scenario: Guide covers statistical analysis

- **WHEN** a user reads the guide
- **THEN** the guide explains cross-run statistics, yield analysis, worst-case ranking, sensitivity analysis, histogram, and scatter plot features

#### Scenario: Guide covers correlation tools

- **WHEN** a user reads the guide
- **THEN** the guide documents the three-step correlation workflow: loading model files, editing correlation matrices, and generating output in all supported formats (CSV, TSV, ngspice .control, .param)

#### Scenario: Guide covers session API / scripting

- **WHEN** a user reads the guide
- **THEN** the guide documents all 17 `mc_*` session API commands (mc_load, mc_info, mc_style, mc_nominal, mc_filter, mc_param, mc_group, mc_ungroup, mc_stats, mc_histogram, mc_yield, mc_scatter, mc_worst, mc_sensitivity, mc_correlation_load, mc_correlation_show, mc_correlation_edit, mc_generate) with parameter descriptions, return value examples, and a complete scripting example

### Requirement: Help menu access to MC Guide

The system SHALL provide a "Monte Carlo Guide" action in the Help menu that opens the guide document.

#### Scenario: Help menu entry exists

- **WHEN** the user opens the Help menu
- **THEN** a "Monte Carlo Guide" action is visible

#### Scenario: Opening the guide

- **WHEN** the user clicks "Monte Carlo Guide"
- **THEN** a dialog window opens displaying `docs/monte_carlo/guide.md` rendered as Markdown in a read-only text viewer
