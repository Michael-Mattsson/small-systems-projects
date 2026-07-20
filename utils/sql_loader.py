from pathlib import Path


def load_sql(filename: str) -> str:
    """Load a SQL script from the current project directory."""

    return Path(filename).read_text(encoding="utf-8")