## ADDED Requirements

### Requirement: Nyquist plot from complex data
The system SHALL render a Nyquist plot (real part vs imaginary part on the X and Y axes) from complex-valued AC analysis vectors, with an equal-aspect-ratio ViewBox.

#### Scenario: Nyquist from real/imag vector pair
- **WHEN** user selects a real-part and imaginary-part vector pair for Nyquist display
- **THEN** the system renders the parametric curve (real vs imag) in a new panel with equal aspect ratio

#### Scenario: Nyquist from single complex vector
- **WHEN** user selects a single complex-valued vector (containing both real and imaginary components)
- **THEN** the system extracts real and imaginary parts and renders the Nyquist curve

#### Scenario: Equal aspect ratio
- **WHEN** the Nyquist plot is displayed
- **THEN** the ViewBox maintains a 1:1 aspect ratio so that a unit circle appears circular, with auto-range adjusting to fit the data while preserving the ratio

### Requirement: Frequency marker annotations
The system SHALL support placing frequency-annotated markers on the Nyquist curve to identify specific frequency points.

#### Scenario: Add frequency marker
- **WHEN** user clicks on the Nyquist curve with the cross-hair cursor
- **THEN** the system places a marker showing the nearest frequency value at that point on the curve

### Requirement: Nyquist plot Session API
The system SHALL provide a `nyquist()` Session API command accepting real vector name, imaginary vector name, and optional frequency vector name.

#### Scenario: API nyquist with explicit vectors
- **WHEN** user calls `nyquist(real="v(out)_real", imag="v(out)_imag")`
- **THEN** the system renders the Nyquist plot in a new panel
