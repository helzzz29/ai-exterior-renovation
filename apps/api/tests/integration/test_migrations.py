"""Alembic head on an empty database matches the ORM models (no autogenerate diff)."""

import asyncio

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from renocore.revisions.filters import include_object
from renocore.tables import Base
from tests.integration.conftest import TEST_DB, alembic_config

SCRATCH_DB = "reno_migration_check"


def _admin_dsn() -> str:
    return TEST_DB.replace("postgresql+asyncpg://", "postgresql://")


async def _recreate(name: str) -> None:
    conn = await asyncpg.connect(_admin_dsn())
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop(name: str) -> None:
    conn = await asyncpg.connect(_admin_dsn())
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


async def _diff(url: str) -> list:
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as conn:

        def compare(sync_conn):  # noqa: ANN001, ANN202
            ctx = MigrationContext.configure(
                sync_conn, opts={"include_object": include_object, "compare_type": True}
            )
            return compare_metadata(ctx, Base.metadata)

        diff = await conn.run_sync(compare)
    await engine.dispose()
    return diff


@pytest.fixture
def scratch_url():  # noqa: ANN201
    asyncio.run(_recreate(SCRATCH_DB))
    yield TEST_DB.rsplit("/", 1)[0] + f"/{SCRATCH_DB}"
    asyncio.run(_drop(SCRATCH_DB))


def test_upgrade_head_matches_models_and_downgrades(scratch_url: str) -> None:
    cfg = alembic_config(scratch_url)
    command.upgrade(cfg, "head")
    assert asyncio.run(_diff(scratch_url)) == []

    async def tables() -> set[str]:
        conn = await asyncpg.connect(scratch_url.replace("+asyncpg", ""))
        try:
            rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        finally:
            await conn.close()
        return {r["tablename"] for r in rows}

    names = asyncio.run(tables())
    assert {"users", "projects", "job_runs", "procrastinate_jobs"} <= names
    command.downgrade(cfg, "base")
    assert asyncio.run(tables()) == {"alembic_version"}
