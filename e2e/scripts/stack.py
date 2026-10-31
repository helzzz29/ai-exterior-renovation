"""Backend helpers for the end-to-end stack. Run from apps/api with `uv run python`.

    python ../../e2e/scripts/stack.py prepare   # create the e2e database if missing + migrate
    python ../../e2e/scripts/stack.py api       # API on E2E_API_PORT (selector loop on Windows)

Reads DATABASE_URL, E2E_API_PORT from the environment (set by e2e/run-stack.mjs).
"""

import asyncio
import os
import subprocess
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.getcwd())  # so `app` imports from apps/api


def prepare() -> None:
    import psycopg

    url = urlparse(os.environ["DATABASE_URL"].replace("+asyncpg", "").replace("+psycopg", ""))
    dbname = url.path.lstrip("/")
    admin = url._replace(path="/postgres").geturl()
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("select 1 from pg_database where datname = %s", (dbname,)).fetchone()
        if not exists:
            conn.execute(f'create database "{dbname}"')
            print(f"created database {dbname}", flush=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


def api() -> None:
    import uvicorn

    if sys.platform == "win32":  # psycopg's async mode needs a selector event loop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    port = int(os.environ.get("E2E_API_PORT", "8010"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, loop="none", log_level="warning")


if __name__ == "__main__":
    {"prepare": prepare, "api": api}[sys.argv[1]]()
