import pytest
import pandas as pd

# Fixture to read the CSV file
@pytest.fixture
def open_csv():
    def _read(path_to_file):
        try:
            return pd.read_csv(path_to_file)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    return _read


# Fixture to validate the schema of the file
@pytest.fixture
def validate_schema():
    def _validate(actual_schema, expected_schema):
        assert actual_schema == expected_schema, (
            f"Expected schema {expected_schema}, got {actual_schema}"
        )

    return _validate


# Pytest hook to mark unmarked tests with a custom mark
def pytest_collection_modifyitems(items):
    for item in items:
        if not list(item.iter_markers()):
            item.add_marker("unmarked")