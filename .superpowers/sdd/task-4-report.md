# Task 4 Report: Vector Rename -- Session API

## Summary

Added `rename_vector(dataset_index, old_name, new_name)` command to the session API and
`Dataset.rename_variable()` method to the Dataset model.

## Files Modified

- `pqwave/models/dataset.py` -- Added `Dataset.rename_variable()` method (after `n_variables` property)
- `pqwave/session/api.py` -- Added `_cmd_rename_vector` command function with `@api_command` decorator
- `pqwave/tests/test_api_commands.py` -- Added `rename_vector` entry to `COMMAND_SPECS`

## Files Created

- `pqwave/tests/test_vector_rename.py` -- 11 tests covering Dataset unit tests and session API integration tests

## Test Results

```
11 passed in 0.71s (test_vector_rename.py)
112 passed, 1 failed (full regression: test_api_commands.py + test_models.py + test_vector_rename.py)
```

The single pre-existing failure is `TestCommandCoverage.test_all_commands_have_spec` listing 25 commands
(MC, xschem, unload, datasets) that were already missing specs before this change -- not a regression.

## Implementation Details

### Dataset.rename_variable(old_name, new_name)
- Raises `KeyError` if `old_name` not in `_var_map`
- Raises `ValueError` if `new_name` already in `_var_map`
- Updates the `Variable` object's `.name` attribute in-place
- Updates the dataset dict's variable metadata for consistency

### rename_vector session API command
- Registered via `@api_command` decorator with signature `rename_vector(dataset_index, old_name, new_name)`
- Validates `dataset_index` is in range; returns `{"status": "error", "message": "..."}` on failure
- Blocks rename if any active trace on any panel references the old name in `trace.name` or `trace.expression`
- Delegates to `Dataset.rename_variable()` for the actual rename
- On success, signals() reflects the new name; expressions using the new name work immediately

## Regressions Checked

- [x] test_api_commands.py -- 101 of 102 pass (1 pre-existing)
- [x] test_models.py -- all pass
- [x] test_vector_rename.py -- all 11 pass
- [x] No syntax errors (python compile check)
