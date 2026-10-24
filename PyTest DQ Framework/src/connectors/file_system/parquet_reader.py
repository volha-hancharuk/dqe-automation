import os
from typing import List

import pandas as pd


class ParquetReader:
    """Reads a Parquet file or a directory of Parquet files into a single DataFrame."""

    @staticmethod
    def _collect_files(path: str, include_subfolders: bool) -> List[str]:
        files = []
        if include_subfolders:
            for root, _, names in os.walk(path):
                files.extend(os.path.join(root, n) for n in names if n.endswith(".parquet"))
        else:
            files.extend(os.path.join(path, n) for n in os.listdir(path) if n.endswith(".parquet"))
        return sorted(files)

    def process(self, path: str, include_subfolders: bool = False) -> pd.DataFrame:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Parquet path does not exist: {path}")
        if os.path.isfile(path):
            return pd.read_parquet(path)

        files = self._collect_files(path, include_subfolders)
        if not files:
            raise FileNotFoundError(f"No .parquet files found in {path} (include_subfolders={include_subfolders})")
        return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
