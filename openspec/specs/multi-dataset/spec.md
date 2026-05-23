## ADDED Requirements

### Requirement: Load multiple datasets

The system SHALL allow users to load multiple simulation files in a single session without clearing previously loaded data. Each loaded file becomes a dataset appended to the dataset list. The system SHALL switch the variable browser to the most recently loaded dataset.

#### Scenario: Open second file appends dataset
- **WHEN** a user opens a second raw file via `File > Open File` while a dataset is already loaded
- **THEN** the new dataset is appended to the dataset list, the dataset combo shows both datasets, and traces from the first dataset remain visible on all panels

#### Scenario: Open file without existing data
- **WHEN** a user opens a raw file with no datasets loaded
- **THEN** the system creates the first dataset and populates the variable browser

### Requirement: Switch active dataset

The system SHALL provide a dataset combo box that lists all loaded datasets by filename. Selecting a dataset switches the variable browser to show that dataset's signals. Switching datasets SHALL NOT remove or hide existing traces on any panel.

#### Scenario: Switch dataset updates variable list
- **WHEN** a user selects dataset index 1 from the dataset combo
- **THEN** the variable browser shows signals from dataset 1, and traces from dataset 0 remain on the plot unchanged

#### Scenario: Adding a trace uses active dataset
- **WHEN** a user adds a trace to a panel while dataset 1 is active
- **THEN** the trace is evaluated against dataset 1's data

### Requirement: Remove a dataset

The system SHALL allow users to remove a dataset from the session. Removing a dataset SHALL also remove all traces sourced from that dataset. If the removed dataset was the active one, the system SHALL switch to the first remaining dataset.

#### Scenario: Close dataset removes its traces
- **WHEN** a user closes dataset 0 via `File > Close Dataset` while two datasets are loaded and traces from dataset 0 are displayed
- **THEN** all traces from dataset 0 are removed from all panels, dataset 0 is removed from the dataset list, and the remaining dataset becomes active

### Requirement: REPL commands for multi-dataset management

The system SHALL provide `load` (append mode), `unload`, `datasets`, and `dataset` REPL commands for managing multiple datasets from the API.

#### Scenario: Load command appends in REPL
- **WHEN** a user executes `load("second_file.raw")` in the REPL with data already loaded
- **THEN** the new file is loaded as an additional dataset without removing existing datasets

#### Scenario: Datasets command lists all
- **WHEN** a user executes `datasets()` in the REPL
- **THEN** the system returns a list of all loaded datasets with their indices, filenames, and trace counts

#### Scenario: Dataset command switches active
- **WHEN** a user executes `dataset(1)` in the REPL
- **THEN** the active dataset switches to index 1 and the variable browser updates accordingly
