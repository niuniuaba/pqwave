## ADDED Requirements

### Requirement: Monte Carlo User Guide document

The system SHALL provide a comprehensive user's guide for the Monte Carlo analysis features, written in Markdown, located at `docs/monte_carlo/guide.md`. The guide SHALL have two parts: a compact feature reference (Part 1) with tables of all capabilities and API signatures, followed by worked tutorials (Part 2) using the files in `docs/monte_carlo/examples/`, each following the Input → Steps → Expected Output pattern.

#### Scenario: Guide covers loading modes (both parts)

- **WHEN** a user reads the guide
- **THEN** Part 1 provides a table of the three loading modes with menu paths; Part 2 walks through loading each example file with exact dialog values and expected outcomes

#### Scenario: Guide covers display modes (both parts)

- **WHEN** a user reads the guide
- **THEN** Part 1 provides a table of display modes and control bar controls; Part 2 demonstrates spaghetti, envelope, and single-run modes using real data with described outputs at specific frequency or time values

#### Scenario: Guide covers statistical analysis (both parts)

- **WHEN** a user reads the guide
- **THEN** Part 1 provides a table of analysis features with menu paths and API signatures; Part 2 provides step-by-step workflows with concrete input values and expected output numbers from the example files

#### Scenario: Guide covers correlation tools

- **WHEN** a user reads the guide
- **THEN** Part 1 describes the three-step correlation workflow and output formats in a compact table; Part 2 provides a worked correlation tutorial using the ring oscillator model file

#### Scenario: Guide covers session API / scripting

- **WHEN** a user reads the guide
- **THEN** Part 1 includes a compact API command reference table with all `mc_*` signatures; Part 2 presents API commands inline as "or via API" code blocks and concludes with a complete, copy-paste runnable scripting example
