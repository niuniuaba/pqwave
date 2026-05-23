## ADDED Requirements

### Requirement: Bode plot from AC analysis vectors
The system SHALL auto-detect magnitude and phase vectors from loaded AC analysis data and render a Bode plot with gain (dB) in one panel and phase (degrees) in a second panel, sharing the X-axis (frequency).

#### Scenario: Auto-detection of db/phase vectors
- **WHEN** user triggers Bode plot and the loaded data contains vectors matching `db(...)` / `phase(...)` naming patterns
- **THEN** the system auto-selects the first matching magnitude and phase vector pair, computes gain and phase traces, and renders them in two vertically-split panels

#### Scenario: Manual vector selection fallback
- **WHEN** auto-detection finds no matching vectors
- **THEN** the system presents a dialog allowing the user to select magnitude and phase vectors manually or enter custom expressions

#### Scenario: Frequency axis shared between panels
- **WHEN** Bode plot is rendered with two panels
- **THEN** both panels share the same X-axis (frequency), and zooming/panning in one panel synchronizes the other

### Requirement: Bode plot from real-valued trace via FFT
The system SHALL allow generating a Bode plot from a single real-valued trace by computing its FFT and extracting magnitude and phase.

#### Scenario: FFT-based Bode
- **WHEN** user triggers Bode plot on a real-valued trace (no AC vectors available)
- **THEN** the system computes the FFT of the trace and renders the magnitude (dB) and phase (degrees) vs frequency

### Requirement: Bode plot Session API
The system SHALL provide a `bode()` Session API command accepting magnitude vector name, phase vector name, and optional frequency vector name.

#### Scenario: API bode with explicit vectors
- **WHEN** user calls `bode(mag="v(out)_db", phase="v(out)_phase")`
- **THEN** the system renders the Bode plot with the specified vectors
