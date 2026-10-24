import pandas as pd
import psycopg2


class PostgresConnectorContextManager:
    """Context manager that owns a PostgreSQL connection and returns query results as DataFrames."""

    def __init__(self, db_user: str, db_password: str, db_host: str = "localhost",
                 db_name: str = "mydatabase", db_port: int = 5434):
        self.db_user = db_user
        self.db_password = db_password
        self.db_host = db_host
        self.db_name = db_name
        self.db_port = db_port
        self.connection = None

    def __enter__(self):
        self.connection = psycopg2.connect(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password,
        )
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        return False

    def get_data_sql(self, sql: str, params=None) -> pd.DataFrame:
        """Execute a read query and return the result as a pandas DataFrame."""
        if self.connection is None:
            raise RuntimeError("Connection is not open; use the connector as a context manager.")
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
        finally:
            self.connection.rollback()  # read-only usage: never keep a transaction open
        return pd.DataFrame(rows, columns=columns)
