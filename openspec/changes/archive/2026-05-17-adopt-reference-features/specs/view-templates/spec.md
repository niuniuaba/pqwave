## ADDED Requirements

### Requirement: Save view template
The system SHALL allow saving the current panel's view configuration (axis ranges, log mode, trace expressions, color assignments, display settings) as a named template to `~/.pqwave/templates/<name>.json`.

#### Scenario: Save template via menu
- **WHEN** user selects "File > Save View Template" and enters a template name
- **THEN** the system writes the current panel's view configuration to a JSON file, excluding data references (file paths, raw vector names)

#### Scenario: Save template via API
- **WHEN** user calls `save_template(name="my-bode")`
- **THEN** the system saves the active panel's view configuration as "my-bode"

### Requirement: Load view template
The system SHALL allow loading a saved template onto the current panel, applying axis config, log mode, trace expressions, and display settings without requiring the original data file.

#### Scenario: Load template via menu
- **WHEN** user selects "File > Load View Template" and chooses a template
- **THEN** the system applies the template's axis ranges, log mode, and display settings to the current panel, and evaluates trace expressions against currently loaded data

#### Scenario: Missing vector on load
- **WHEN** a template's expression references a vector not in the currently loaded data
- **THEN** the system skips that trace and shows a warning in the status bar listing skipped expressions

### Requirement: List and manage templates
The system SHALL provide a Template Manager dialog for listing, previewing, deleting, and renaming saved templates.

#### Scenario: Template Manager dialog
- **WHEN** user opens the Template Manager
- **THEN** the system displays all saved templates with their names, creation dates, and a preview of stored trace expressions

### Requirement: Template Session API
The system SHALL provide `save_template()`, `load_template()`, and `list_templates()` Session API commands.

#### Scenario: API list templates
- **WHEN** user calls `list_templates()`
- **THEN** the system returns a list of all saved template names and metadata
