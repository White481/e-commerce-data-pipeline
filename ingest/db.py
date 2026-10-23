"""Database connection helper.

Reads connection settings from environment variables (loaded from .env if present),
so no credentials are hard-coded in the source code.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is not set. "
            "Copy .env.example to .env and fill in the values."
        )
    return value


def get_engine(database: str | None = None) -> Engine:
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=_require("POSTGRES_USER"),
        password=_require("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=database or _require("POSTGRES_DB"),
    )
    return create_engine(url)
