from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

_REQUIRED = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
)

_missing = [key for key in _REQUIRED if not os.getenv(key)]
if _missing:
    raise RuntimeError(
        "Missing required database settings in .env: "
        + ", ".join(_missing)
    )

# Defaults match docker-compose.yml, which publishes the container on a
# non-standard port to avoid colliding with other local PostgreSQL servers.
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5434"))

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=POSTGRES_HOST,
    port=POSTGRES_PORT,
    database=os.environ["POSTGRES_DB"],
)
