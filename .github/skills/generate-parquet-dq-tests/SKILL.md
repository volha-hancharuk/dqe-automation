---
name: generate-parquet-dq-tests
description: >-
  Creates one PyTest DQ module per Parquet dataset in "PyTest DQ Framework/tests/dq checks/parquet_files/",
  deriving the expected Postgres query only from docs/parquet-aggregated-data-mapping.md and following the
  test design standard in test-automation-strategy.md (§5, §6). Invoke explicitly by name when a dataset test
  module is needed. Refuses to edit framework code, conftest.py, pytest.ini, requirements.txt or the Jenkinsfile,
  and refuses to take expected SQL from data_dev/ or the parquet loader.
disable-model-invocation: true
---

# Generate Parquet DQ tests

Complete this skill as **Step 2** of the PyTest DQ assignment. Read first:

- `PyTest DQ Framework/docs/test-automation-strategy.md` — **§5 Skill contract**, **§6 Test design standard**
- `docs/parquet-aggregated-data-mapping.md` — dataset definitions (expected SQL comes from here)

**Do not** paste expected SQL for the three named datasets into this skill.  
**Do not** instruct the agent to copy SQL from `data_dev/`.

## When this skill applies

Use this skill when the user explicitly asks to generate (or regenerate) a DQ test module for a Parquet dataset
produced by the pipeline.

The framework (Step 1) must already exist. Before writing anything, confirm these are present:

- `src/connectors/postgres/postgres_connector.py` (`PostgresConnectorContextManager.get_data_sql`)
- `src/connectors/file_system/parquet_reader.py` (`ParquetReader.process`)
- `src/data_quality/data_quality_validation_library.py` (`DataQualityLibrary`)
- `tests/conftest.py` with fixtures `db_connection`, `parquet_reader`, `data_quality_library`
- `tests/pytest.ini` with the `parquet_data`, `smoke` and dataset markers registered

If any of them is missing, stop and tell the user that Step 1 is not complete. Do not create it yourself.

**Allowed write path (the only one):**
`PyTest DQ Framework/tests/dq checks/parquet_files/test_<dataset_name>.py`

**Refuse (and explain why) when asked to:**

- change framework code, `conftest.py`, `pytest.ini`, `requirements.txt` or the `Jenkinsfile`
  (only if the user explicitly asks for it as a separate task, outside this skill);
- generate a module for a dataset that has no section in the mapping;
- put several datasets into one module;
- build expected SQL from ETL code or change expected SQL to make a failing run green.

## Inputs you must have

| Input | Where it comes from |
| --- | --- |
| Dataset name | From the user; equals the folder name under `/parquet_data/` and the mapping section heading |
| Mapping for the dataset | `docs/parquet-aggregated-data-mapping.md`, section `## <dataset_name>`: target columns, transformations, source tables/columns, comments (grouping, not null, rounding, format), filters, partitioning |
| Source schema and join keys | `docs/project-environment.md`, section "Entity-relationship model" |
| Author and requirement id | From the user, for the module header. If not given, ask once; otherwise use `TICKET-1234` and `<name>` placeholders and say so |

If the mapping file or the dataset section is missing, or a target column has no source/transformation,
**stop and ask the user**. Do not guess the mapping and do not fill gaps from other sources.

**Forbidden sources for expected SQL and expected values:**

- anything under `data_dev/` (especially `queries.py`, the parquet loader and the report generator);
- the contents of the Parquet files themselves ("make the query return what the file has");
- `tests/test_examples.py` as a source of fixture names/direction (it is a placeholder with swapped names).

## Hard rules

1. **File path and name.** One dataset per module:
   `PyTest DQ Framework/tests/dq checks/parquet_files/test_<dataset_name>.py`, where `<dataset_name>` is the exact
   snake_case Parquet folder name. Do not touch any other file.
2. **Source vs target.** `source_data` = expected result from **Postgres** via `db_connection.get_data_sql(...)`.
   `target_data` = actual result from **Parquet** via `parquet_reader.process(...)`. Never swap them.
3. **Mapping-only SQL.** The expected query is derived only from the dataset's mapping section and the ER model.
   Never read or copy SQL from `data_dev/` or the parquet loader.
4. **No invented logic.** No `UNION`, extra `WHERE`, `HAVING`, `CASE`, `COALESCE`, `ABS`, sign flips or
   deduplication unless the mapping states it. "Filters: —" means no `WHERE` clause.
5. **No dataset SQL in this skill.** `SKILL.md` stays dataset-agnostic: it explains how to derive SQL, it never
   contains the expected query for a named dataset.
6. **Names and grain.** Every output column of `source_data` is aliased to the mapping's target column name, so it
   matches the Parquet schema. The query returns only the mapped target columns: no technical or partition
   columns. Grain = the columns marked "grouping" in the mapping.
7. **Target path.** `target_path = '/parquet_data/<dataset_name>'` and `include_subfolders=True`
   (datasets are partitioned into subfolders).
8. **Library methods only.** Assertions are made only by calling `DataQualityLibrary` methods
   (`check_dataset_is_not_empty`, `check_data_completeness`, `check_count`, `check_duplicates`,
   `check_not_null_values`). No pandas logic, no bare `assert`, no `try/except` or `skip` in test bodies.
9. **All mandatory tests.** Every module contains exactly the five tests of the template: smoke (not empty),
   completeness, count, uniqueness, not-null. None may be omitted, weakened or made trivially passing
   (for example, comparing `target_data` with itself, or passing an empty column list).
10. **Markers.** Every test has `@pytest.mark.parquet_data` and `@pytest.mark.<dataset_name>`.
    `@pytest.mark.smoke` is used **only** on `test_check_dataset_is_not_empty`. If the dataset marker is not
    registered in `tests/pytest.ini`, stop and tell the user (do not edit `pytest.ini` yourself).
11. **Not-null columns** = all target columns listed in the dataset's mapping table, in mapping order.
12. **Header.** The module docstring contains Description, Requirement(s) and Author(s) as in the template.

## Workflow

1. Get the dataset name; open its section in `docs/parquet-aggregated-data-mapping.md`. If anything required is
   missing, stop (see "Inputs you must have").
2. Check the framework prerequisites and that the dataset marker is registered in `tests/pytest.ini`.
3. Build a column plan from the mapping table. For each target column write down: source table, source column(s),
   transformation, and its role — **dimension** (comment says "grouping") or **measure** (aggregate).
   Note any rounding or format rule from the Comments column, and the Filters line.
4. Derive the expected SQL using the generic rules in "SQL derivation" below. Check it against the column plan:
   every target column present and aliased, nothing extra, GROUP BY = all dimensions.
5. Create the module from the template: replace `<dataset_name>`, header fields, the query, and the not-null
   column list. Keep the test function names and order unchanged.
6. Run the "Self-check of the generated module" below and fix the module (not the rules) if any item fails.
7. Report to the user: file created, the derived query, and any mapping ambiguity you resolved and how.

## Template

Full module skeleton from TAS §6.2. Source = Postgres, target = Parquet.

```python
"""
Description: Data Quality checks for <dataset_name> dataset.
Requirement(s): TICKET-1234
Author(s): <name>
"""

import pytest


@pytest.fixture(scope='module')
def source_data(db_connection):
    source_query = """
    -- expected query derived from mapping (grain + measures + joins)
    """
    return db_connection.get_data_sql(source_query)


@pytest.fixture(scope='module')
def target_data(parquet_reader):
    target_path = '/parquet_data/<dataset_name>'
    return parquet_reader.process(target_path, include_subfolders=True)


@pytest.mark.parquet_data
@pytest.mark.smoke
@pytest.mark.<dataset_name>
def test_check_dataset_is_not_empty(target_data, data_quality_library):
    data_quality_library.check_dataset_is_not_empty(target_data)


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_data_completeness(source_data, target_data, data_quality_library):
    data_quality_library.check_data_completeness(source_data, target_data)


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_count(source_data, target_data, data_quality_library):
    data_quality_library.check_count(source_data, target_data)


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_uniqueness(target_data, data_quality_library):
    data_quality_library.check_duplicates(target_data)


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_not_null_values(target_data, data_quality_library):
    data_quality_library.check_not_null_values(target_data, ['<col_1>', '<col_2>', '<col_3>'])
```

## SQL derivation (generic)

Apply these rules to the mapping of the requested dataset. Placeholders in angle brackets are filled from the
mapping and the ER model.

**Tables and joins**

- `table.<name>` in the mapping's Source column means Postgres table `<name>`.
- Start `FROM` the table that holds the measures (the fact table), then `JOIN` each parent table that provides a
  dimension, using the PK/FK pairs from the ER model in `docs/project-environment.md`
  (`<fact>.<parent>_id = <parent>.id`). Use inner joins; join only tables the mapping references.
- Table names in the ER diagram and in the mapping may be spelled differently. If unsure, verify the real name in
  the database (`information_schema.tables`) before writing the query; never infer it from ETL code.
- Use short table aliases and qualify every column (`<alias>.<column>`).

**Dimensions (grain)**

- Every column whose comment says "grouping" goes into `SELECT` and into `GROUP BY` — nothing else goes into
  `GROUP BY`.
- If the target column is a date and the source column is a timestamp (sample shows only a date), cast it:
  `<alias>.<timestamp_col>::date AS <target_col>`. Group by the same expression.
- If the Transformation column combines several source columns, build exactly the format given in the Comments
  column (for example, `<a> || ' ' || <b>` for "separated by space"), in the stated order, and group by that
  expression.

**Measures**

- Use the aggregate function written in the Transformation column (`min`, `avg`, `sum`, …) on the stated source
  column, aliased to the target column name.
- Apply rounding only when the Comments column requires it, with the stated precision:
  `ROUND(<agg>(<alias>.<col>)::numeric, <n>)`.
- Constraints in Comments such as "can't be negative" or "not null" describe expected data quality. They are
  **not filters**: do not add `WHERE`/`HAVING` for them. A violation must surface as a failing test.

**Filters and partitioning**

- Add a `WHERE` clause only if the mapping's **Filters** line states one; "—" means none.
- **Partitioned** describes the file layout only. Do not select partition columns and do not filter by them.

**Shape check before writing the module**

- Output columns = mapping target columns, same names, nothing extra.
- `GROUP BY` = all dimension expressions.
- No `ORDER BY` needed (completeness ignores row order).
- Do not "fix" the query to match a Parquet preview, row count or sample values.

## After generation

- Do not run pytest unless the user asks. When asked, use the command from TAS §6.5 with `-m "parquet_data"`
  (credentials from the user or environment; never write them into the module).
- If tests fail, **do not change the expected SQL, the not-null list or the checks to force a green run.**
  A failure means the Parquet disagrees with the mapping until proven otherwise.
- Change the expected query only if it contradicts the mapping (a derivation mistake). Re-derive it from the
  mapping, and tell the user which mapping rule was violated.
- For each failed check, help the user record the defect per TAS §10: dataset and test name, what the mapping
  expects, what the Parquet contains (from the assert message), and the likely root cause in the transformation.

### Self-check of the generated module

- [ ] Path is `tests/dq checks/parquet_files/test_<dataset_name>.py`; no other file changed
- [ ] `source_data` uses `db_connection.get_data_sql`; `target_data` uses `parquet_reader.process('/parquet_data/<dataset_name>', include_subfolders=True)`
- [ ] Query output columns and aliases equal the mapping target columns; `GROUP BY` equals the grain
- [ ] No filter/`UNION`/`CASE`/sign logic that the mapping does not state
- [ ] Five tests present with template names; library methods only
- [ ] Markers: `parquet_data` + dataset marker on all tests, `smoke` only on the not-empty test
- [ ] Not-null list = all mapping target columns

---

## Skill review (self-check before Step 3)

Reject your own skill if any of these are true:

- [ ] Contains concrete expected SQL for `facility_name_min_time_spent_per_visit_date`, `facility_type_avg_time_spent_per_visit_date`, or `patient_sum_treatment_cost_per_facility_type`
- [ ] Tells the agent to use `data_dev/` or parquet loader SQL
- [ ] Omits completeness, count, uniqueness, or not-null
- [ ] Swaps Postgres vs Parquet fixtures or generates trivial always-pass checks
- [ ] Any section still says `TODO`
