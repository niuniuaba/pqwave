## ADDED Requirements

### Requirement: Trace histogram computation
The system SHALL compute and display a histogram of trace values over the visible X-range using `numpy.histogram()`, rendered as bar chart overlaid on the plot.

#### Scenario: Default histogram
- **WHEN** user triggers Histogram on a selected trace
- **THEN** the system computes a histogram with auto-determined bin count (Sturges' rule) over the visible X-range and renders it as bars in a new panel

#### Scenario: Custom bin count
- **WHEN** user specifies bin count in the histogram configuration dialog
- **THEN** the system recomputes and re-renders the histogram with the specified number of bins

#### Scenario: Custom range
- **WHEN** user specifies a min/max range for the histogram
- **THEN** the system computes the histogram only over the specified data range

### Requirement: Histogram normalization modes
The system SHALL support three normalization modes: count (absolute frequency), density (area integrates to 1), and probability (sum of bin heights equals 1).

#### Scenario: Normalization toggle
- **WHEN** user selects a normalization mode from the histogram configuration
- **THEN** the histogram re-renders with the selected normalization

### Requirement: Histogram Session API
The system SHALL provide a `histogram()` Session API command accepting trace name, bin count, range, and normalization mode.

#### Scenario: API histogram
- **WHEN** user calls `histogram(trace="v(out)", bins=100, range=[0, 5], norm="density")`
- **THEN** the system computes and renders the histogram in a new panel
