import pytest
import re


CSV_PATH = "src/data/data.csv"


def test_file_not_empty(open_csv):
    df = open_csv(CSV_PATH)
    assert len(df.columns) > 0, "CSV is empty"
    assert not df.empty, "CSV has no data rows"


@pytest.mark.validate_csv
@pytest.mark.xfail(reason="The file is known to contain duplicate rows")
def test_duplicates(open_csv):
    df = open_csv(CSV_PATH)
    duplicates = df[df.duplicated()]
    assert duplicates.empty, f"Duplicate rows:\n{duplicates}"


@pytest.mark.validate_csv
def test_validate_schema(open_csv, validate_schema):
    df = open_csv(CSV_PATH)
    expected_schema = ["id", "name", "age", "email", "is_active"]
    validate_schema(list(df.columns), expected_schema)


@pytest.mark.validate_csv
@pytest.mark.skip(reason="Skipped as required")
def test_age_column_valid(open_csv):
    df = open_csv(CSV_PATH)
    invalid = df[~df["age"].between(0, 100)]
    assert invalid.empty, f"Invalid ages:\n{invalid}"


@pytest.mark.validate_csv
def test_email_column_valid(open_csv):
    df = open_csv(CSV_PATH)
    email_pattern = r"[\w.+-]+@[\w-]+(\.[\w-]+)+"
    invalid = [email for email in df["email"] if not re.fullmatch(email_pattern, str(email))]
    assert not invalid, f"Invalid emails: {invalid}"


@pytest.mark.parametrize("id, is_active", [(1, False), (2, True)])
def test_active_players(open_csv, id, is_active):
    df = open_csv(CSV_PATH)
    row = df[df["id"] == id]
    assert not row.empty, f"No row with id={id}"
    actual = row["is_active"].iloc[0]
    assert actual == is_active, f"Expected is_active={is_active} for id={id}, got {actual}"


def test_active_player(open_csv):
    df = open_csv(CSV_PATH)
    row = df[df["id"] == 2]
    assert not row.empty, "No row with id=2"
    actual = row["is_active"].iloc[0]
    assert actual == True, f"Expected is_active=True for id=2, got {actual}"
