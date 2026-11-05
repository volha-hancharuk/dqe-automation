"""Custom Robot Framework keywords for comparing an HTML report table with a Parquet dataset.

Every public function in this module becomes a keyword when the file is imported
with ``Library    helper.py`` (e.g. ``read_html_table_to_dataframe`` ->
``Read Html Table To Dataframe``).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from robot.api import logger
from robot.api.deco import keyword
from selenium.webdriver.common.by import By


def _text(element) -> str:
    """Visible text of an element; SVG <text> nodes need textContent instead of .text."""
    return " ".join((element.get_attribute("textContent") or "").split())


def _read_classic_table(table):
    """Header and rows of an HTML <table> element."""
    rows = table.find_elements(By.TAG_NAME, "tr")
    headers = [_text(th) for th in table.find_elements(By.CSS_SELECTOR, "thead th")]
    if headers:
        body = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    else:
        headers = [_text(c) for c in rows[0].find_elements(By.CSS_SELECTOR, "th, td")]
        body = rows[1:]
    data = [[_text(c) for c in r.find_elements(By.CSS_SELECTOR, "td, th")] for r in body]
    return headers, data


def _read_plotly_table(table):
    """Header and rows of a Plotly table trace.

    Plotly draws the table as SVG: one ``g.y-column`` per column, holding a header
    block and cell blocks with ``g.column-cell`` elements. Rows can be split between
    several blocks, so cells are ordered by their vertical position on the page.
    """
    headers, columns = [], []
    for column in table.find_elements(By.CSS_SELECTOR, "g.y-column"):
        header = column.find_elements(By.CSS_SELECTOR, "g.column-block#header g.column-cell")
        headers.append(_text(header[0]) if header else "")
        cells = column.find_elements(By.CSS_SELECTOR, "g.column-block:not(#header) g.column-cell")
        cells = sorted(cells, key=lambda c: c.location["y"])
        columns.append([_text(c) for c in cells])
    rows = [list(row) for row in zip(*columns)]
    if columns and len({len(c) for c in columns}) != 1:
        raise ValueError(f"Columns have different numbers of cells: {[len(c) for c in columns]}")
    return headers, rows


def _to_snake_case(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", str(name)).strip("_").lower()


@keyword("Read HTML Table To DataFrame")
def read_html_table_to_dataframe(table_element, column_mapping=None) -> pd.DataFrame:
    """Read a located table WebElement into a pandas DataFrame (all values as strings).

    ``table_element`` is a Selenium ``WebElement`` that was located in the browser
    (e.g. with SeleniumLibrary ``Get WebElement``). Both ``<table>`` elements and
    Plotly table traces are supported. Cells are read with Selenium's own element
    methods, no JavaScript is executed.

    ``column_mapping`` optionally renames the HTML headers, e.g.
    ``{"Average Time Spent": "avg_time_spent"}``. Headers that are not in the
    mapping are converted to snake_case.
    """
    if table_element.tag_name.lower() == "table":
        headers, rows = _read_classic_table(table_element)
    else:
        headers, rows = _read_plotly_table(table_element)
    if not headers:
        raise ValueError("No table header/cells were found inside the located element.")

    for i, row in enumerate(rows):
        if len(row) != len(headers):
            raise ValueError(f"Row {i} is incomplete (expected {len(headers)} cells): {row}")

    mapping = dict(column_mapping or {})
    columns = [mapping.get(h, _to_snake_case(h)) for h in headers]
    df = pd.DataFrame(rows, columns=columns)
    logger.info(f"HTML table: {len(df)} rows, columns {list(df.columns)}")
    logger.info(df.to_html(index=False), html=True)
    return df


@keyword("Read Parquet Dataset")
def read_parquet_dataset(
    folder,
    filter_date=None,
    date_column="visit_date",
    partition_column="partition_date",
    columns=None,
) -> pd.DataFrame:
    """Read a (Hive-style) partitioned Parquet dataset, optionally filtered by date.

    When ``filter_date`` (``YYYY-MM-DD``) is given, only rows where
    ``date_column >= filter_date`` are returned. If the dataset is partitioned by
    month (``partition_date=YYYY-MM``), partitions older than the filter month are
    pruned without being read. Pass an empty value / ``None`` to read everything.

    ``columns`` limits the result to the given columns (the partition column is
    dropped by default).
    """
    path = Path(folder)
    if not path.exists():
        raise FileNotFoundError(f"Parquet folder not found: {path}")

    filters = None
    if filter_date not in (None, "", "None", "${NONE}"):
        start = _parse_date(filter_date)
        filters = [(date_column, ">=", pd.Timestamp(start))]
        partition_values = {
            p.name.split("=", 1)[1]
            for p in path.iterdir()
            if p.is_dir() and p.name.startswith(f"{partition_column}=")
        }
        if partition_values:
            filters.append((partition_column, ">=", start.strftime("%Y-%m")))

    df = pd.read_parquet(path, engine="pyarrow", filters=filters)

    if columns:
        df = df[list(columns)]
    elif partition_column in df.columns:
        df = df.drop(columns=[partition_column])

    df = df.reset_index(drop=True)
    logger.info(
        f"Parquet dataset '{path}': {len(df)} rows"
        + (f" with {date_column} >= {filter_date}" if filters else " (no filter)")
    )
    return df


@keyword("Compare DataFrames")
def compare_dataframes(actual, expected, float_precision=2) -> str:
    """Compare two DataFrames for an exact match, ignoring row order.

    Values are normalised before comparing so that equivalent representations match
    (``35`` == ``35.0``, ``2026-10-02`` == ``Timestamp('2026-10-02')``); numbers are
    compared after rounding to ``float_precision`` decimals.

    Returns an empty string when the frames match, otherwise a readable description
    of every difference (column mismatches, row count, rows missing on either side).
    """
    actual = actual.copy()
    expected = expected.copy()
    problems = []

    missing_cols = [c for c in expected.columns if c not in actual.columns]
    extra_cols = [c for c in actual.columns if c not in expected.columns]
    if missing_cols or extra_cols:
        problems.append(
            f"Column mismatch: missing in HTML={missing_cols}, unexpected in HTML={extra_cols}"
        )
        return "\n".join(problems)

    actual = actual[list(expected.columns)]
    for col in expected.columns:
        expected[col] = _normalise(expected[col], float_precision)
        actual[col] = _normalise(actual[col], float_precision)

    if len(actual) != len(expected):
        problems.append(f"Row count mismatch: HTML={len(actual)}, Parquet={len(expected)}")

    cols = list(expected.columns)
    # Count duplicates explicitly so that repeated rows are compared correctly.
    a = actual.assign(_n=actual.groupby(cols).cumcount())
    e = expected.assign(_n=expected.groupby(cols).cumcount())
    merged = a.merge(e, on=cols + ["_n"], how="outer", indicator=True)
    only_html = merged[merged["_merge"] == "left_only"][cols]
    only_parquet = merged[merged["_merge"] == "right_only"][cols]

    if not only_html.empty:
        problems.append(
            f"{len(only_html)} row(s) present in HTML table but not in Parquet:\n"
            + only_html.sort_values(cols).to_string(index=False)
        )
    if not only_parquet.empty:
        problems.append(
            f"{len(only_parquet)} row(s) present in Parquet but not in HTML table:\n"
            + only_parquet.sort_values(cols).to_string(index=False)
        )

    result = "\n\n".join(problems)
    if result:
        logger.warn("DataFrames differ:\n" + result)
    else:
        logger.info(f"DataFrames match: {len(expected)} rows, columns {cols}")
    return result


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError as err:
        raise ValueError(f"FILTER_DATE must be in YYYY-MM-DD format, got '{value}'") from err


def _normalise(series: pd.Series, float_precision: int) -> pd.Series:
    """Bring a column to a canonical string form so HTML text and typed Parquet values compare."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime("%Y-%m-%d").fillna("")
    if pd.api.types.is_numeric_dtype(series):
        return series.round(float_precision).map(lambda v: "" if pd.isna(v) else repr(float(v)))

    as_str = series.astype(str).str.strip()
    numeric = pd.to_numeric(as_str, errors="coerce")
    if numeric.notna().all() and len(as_str):
        return numeric.round(float_precision).map(lambda v: repr(float(v)))
    if as_str.str.fullmatch(r"\d{4}-\d{2}-\d{2}.*").all() and len(as_str):
        parsed = pd.to_datetime(as_str, errors="coerce")
        if parsed.notna().all():
            return parsed.dt.strftime("%Y-%m-%d")
    return as_str
