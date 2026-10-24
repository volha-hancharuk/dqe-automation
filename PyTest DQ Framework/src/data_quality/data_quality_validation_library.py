import datetime
import decimal

import pandas as pd

MAX_REPORTED_ROWS = 20


def _date_to_text(value):
    if pd.isna(value):
        return value
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d" if value.time() == datetime.time(0) else "%Y-%m-%d %H:%M:%S")
    return value.isoformat()


class DataQualityLibrary:
    """
    Static data quality checks on pandas DataFrames.

    Each method asserts a condition and fails with a message that names the
    offending rows and column values so the HTML report explains the defect.
    """

    @staticmethod
    def _sample(df: pd.DataFrame) -> str:
        text = df.head(MAX_REPORTED_ROWS).to_string()
        extra = len(df) - MAX_REPORTED_ROWS
        return text + (f"\n... and {extra} more row(s)" if extra > 0 else "")

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Align types so equal values from Postgres and Parquet compare equal."""
        out = df.copy()
        for col in out.columns:
            series = out[col]
            non_null = series.dropna()
            if pd.api.types.is_datetime64_any_dtype(series):
                out[col] = series.map(_date_to_text)
            elif non_null.size and non_null.map(lambda v: isinstance(v, datetime.date)).all():
                out[col] = series.map(_date_to_text)
            elif non_null.size and non_null.map(lambda v: isinstance(v, decimal.Decimal)).all():
                out[col] = series.astype(float)
            if pd.api.types.is_numeric_dtype(out[col]) and not pd.api.types.is_bool_dtype(out[col]):
                out[col] = out[col].astype(float).round(6)
        return out

    @staticmethod
    def check_dataset_is_not_empty(df: pd.DataFrame):
        assert df is not None and not df.empty, "Dataset is empty: expected at least one row"

    @staticmethod
    def check_count(df1: pd.DataFrame, df2: pd.DataFrame):
        assert len(df1) == len(df2), (
            f"Row count mismatch: first dataset has {len(df1)} rows, second has {len(df2)} rows"
        )

    @staticmethod
    def check_data_completeness(source: pd.DataFrame, target: pd.DataFrame):
        """Source and target must contain exactly the same rows (order-insensitive)."""
        src_cols, tgt_cols = set(source.columns), set(target.columns)
        assert src_cols == tgt_cols, (
            f"Column mismatch: missing in target={sorted(src_cols - tgt_cols)}, "
            f"unexpected in target={sorted(tgt_cols - src_cols)}"
        )
        columns = list(source.columns)
        src = DataQualityLibrary._normalize(source[columns])
        tgt = DataQualityLibrary._normalize(target[columns])

        # Occurrence number keeps repeated rows distinct so multiplicity differences are detected
        src["_occurrence"] = src.groupby(columns, dropna=False).cumcount()
        tgt["_occurrence"] = tgt.groupby(columns, dropna=False).cumcount()
        merged = src.merge(tgt, on=columns + ["_occurrence"], how="outer", indicator=True)

        missing = merged[merged["_merge"] == "left_only"].drop(columns=["_merge", "_occurrence"])
        extra = merged[merged["_merge"] == "right_only"].drop(columns=["_merge", "_occurrence"])
        problems = []
        if not missing.empty:
            problems.append(f"{len(missing)} row(s) in source but missing in target:\n"
                            f"{DataQualityLibrary._sample(missing)}")
        if not extra.empty:
            problems.append(f"{len(extra)} row(s) in target but not in source:\n"
                            f"{DataQualityLibrary._sample(extra)}")
        assert not problems, "Data completeness check failed.\n" + "\n".join(problems)

    @staticmethod
    def check_duplicates(df: pd.DataFrame, column_names=None):
        columns = list(column_names) if column_names else list(df.columns)
        unknown = [c for c in columns if c not in df.columns]
        assert not unknown, f"Columns not found in dataset: {unknown}"
        dupes = df[df.duplicated(subset=columns, keep=False)]
        assert dupes.empty, (
            f"Found {len(dupes)} duplicated row(s) by columns {columns}:\n"
            f"{DataQualityLibrary._sample(dupes.sort_values(columns))}"
        )

    @staticmethod
    def check_not_null_values(df: pd.DataFrame, column_names=None):
        columns = list(column_names) if column_names else list(df.columns)
        unknown = [c for c in columns if c not in df.columns]
        assert not unknown, f"Columns not found in dataset: {unknown}"
        problems = []
        for col in columns:
            nulls = df[df[col].isna()]
            if not nulls.empty:
                problems.append(f"Column '{col}' has {len(nulls)} null value(s):\n"
                                f"{DataQualityLibrary._sample(nulls)}")
        assert not problems, "Not-null check failed.\n" + "\n".join(problems)
