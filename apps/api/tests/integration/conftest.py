"""API integration test harness.

- Real Postgres test database (port 5434): schema rebuilt once per session with Alembic,
  every table truncated before each test.
- Procrastinate runs on an InMemoryConnector; `run_jobs()` drains the queue inline.
- Imaging, estimation and the AI rules + render loop are real; only the
  provider (the model calls) is replaced by the configurable FakeProvider in fakes.py.
"""

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://reno:reno@localhost:5434/reno_test"
)
_STORAGE = tempfile.mkdtemp(prefix="reno-test-storage-")
os.environ.update(
    {
        "ENV": "test",
        "DATABASE_URL": TEST_DB,
        "AI_PROVIDER": "fake",
        "STORAGE_ROOT": _STORAGE,
        "JOB_RETRY_BASE_SECONDS": "0",
        "JOB_MAX_ATTEMPTS": "3",
        "LOG_LEVEL": "WARNING",
        "JWT_SECRET": "test-secret-test-secret-test-secret",
    }
)

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from procrastinate.testing import InMemoryConnector  # noqa: E402

from app import ai  # noqa: E402
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import app.jobs.tasks  # noqa: E402,F401  (registers tasks)
from app import db  # noqa: E402
from app import storage as storage_mod  # noqa: E402
from app.jobs.queue import queue_app  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import ALL_TABLES  # noqa: E402
from app.services import catalogue  # noqa: E402
from tests.integration import fakes  # noqa: E402

API_DIR = Path(__file__).resolve().parents[2]
SAMPLES = API_DIR.parents[1] / "samples"

pytestmark = pytest.mark.db


def _raw_dsn() -> str:
    return TEST_DB.replace("postgresql+asyncpg://", "postgresql://")


async def _reset_schema() -> None:
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


def alembic_config(url: str = TEST_DB) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "app" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session")
def database() -> str:
    asyncio.run(_reset_schema())
    command.upgrade(alembic_config(), "head")
    return TEST_DB


@pytest.fixture(autouse=True)
async def _clean_state(database: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute(f"TRUNCATE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    await db.dispose_engine()
    storage_mod.set_storage(None)
    catalogue.reset_catalogue()
    yield
    await db.dispose_engine()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> fakes.FakeProvider:
    """The one fake provider every job in this test gets (with the real DB recorder)."""
    fake = fakes.FakeProvider()

    def factory(settings, recorder=None):  # noqa: ANN001, ANN202
        fake.recorder = recorder
        return fake

    monkeypatch.setattr(ai, "get_provider", factory)
    return fake


@pytest.fixture
async def queue() -> AsyncIterator[InMemoryConnector]:
    connector = InMemoryConnector()
    with queue_app.replace_connector(connector):
        yield connector


@pytest.fixture
def run_jobs(queue: InMemoryConnector) -> Callable[[], Awaitable[None]]:
    async def _run() -> None:
        await queue_app.run_worker_async(
            wait=False, install_signal_handlers=False, listen_notify=False
        )

    return _run


@pytest.fixture
def app():  # noqa: ANN201
    return create_app()


def make_client(app) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(app, queue, provider) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    async with make_client(app) as c:
        await register(c, "owner@example.com")
        yield c


@pytest.fixture
async def other_client(app, queue, provider) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    async with make_client(app) as c:
        await register(c, "someone-else@example.com")
        yield c


# ---------------------------------------------------------------- helpers

_PHOTO: bytes | None = None


def house_photo() -> bytes:
    global _PHOTO
    if _PHOTO is None:
        _PHOTO = (SAMPLES / "house-02.jpg").read_bytes()
    return _PHOTO


def blurry_photo() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), (120, 120, 120)).save(buf, "JPEG")
    return buf.getvalue()


async def register(c: httpx.AsyncClient, email: str) -> dict:
    r = await c.post("/api/auth/register", json={"email": email, "password": "correct-horse-1"})
    assert r.status_code == 200, r.text
    return r.json()


async def new_project(c: httpx.AsyncClient, name: str = "Our house", **measurements) -> str:
    r = await c.post("/api/projects", json={"name": name, "measurements": measurements})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def upload(c: httpx.AsyncClient, pid: str, data: bytes | None = None) -> httpx.Response:
    return await c.post(
        f"/api/projects/{pid}/photo",
        files={"file": ("my house.jpg", data or house_photo(), "image/jpeg")},
    )


async def analysed(c: httpx.AsyncClient, run_jobs, **measurements) -> str:  # noqa: ANN001
    pid = await new_project(c, **measurements)
    r = await upload(c, pid)
    assert r.status_code == 202, r.text
    await run_jobs()
    return pid


async def resolve_checks(c: httpx.AsyncClient, pid: str, keep_proposals: bool = True) -> dict:
    regions = (await c.get(f"/api/projects/{pid}/regions")).json()["regions"]
    body = []
    for r in regions:
        if r["proposed"] and not keep_proposals:
            continue
        body.append(
            {
                "id": r["id"],
                "label": r["label"],
                "polygon": r["polygon"],
                "checked": True if r["needs_check"] else r["checked"],
                "proposed": False,
            }
        )
    r = await c.put(f"/api/projects/{pid}/regions", json={"regions": body})
    assert r.status_code == 200, r.text
    return r.json()


async def approved(c: httpx.AsyncClient, run_jobs, **measurements) -> str:  # noqa: ANN001
    pid = await analysed(c, run_jobs, **measurements)
    await resolve_checks(c, pid)
    r = await c.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 200, r.text
    await run_jobs()
    return pid


async def designing(c: httpx.AsyncClient, run_jobs) -> tuple[str, str]:  # noqa: ANN001
    """Project in the designing stage with Design 1 painted (wall) + stone pillar."""
    pid = await approved(c, run_jobs)
    r = await c.post(f"/api/projects/{pid}/scale/confirm", json={"accept": True})
    assert r.status_code == 200, r.text
    designs = (await c.get(f"/api/projects/{pid}/designs")).json()
    did = designs[0]["id"]
    await assign_defaults(c, pid, did)
    return pid, did


async def regions_by_label(c: httpx.AsyncClient, pid: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in (await c.get(f"/api/projects/{pid}/regions")).json()["regions"]:
        out.setdefault(r["label"], []).append(r)
    return out


async def assign_defaults(c: httpx.AsyncClient, pid: str, did: str) -> dict:
    by = await regions_by_label(c, pid)
    body = {
        "assignments": [
            {
                "region_id": by["wall"][0]["id"],
                "material_id": "paint-premium-emulsion",
                "color": "#e8dcc4",
            },
            {"region_id": by["pillar"][0]["id"], "material_id": "cladding-natural-stone"},
        ]
    }
    r = await c.put(f"/api/designs/{did}/assignments", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def accepted_render(c: httpx.AsyncClient, run_jobs, did: str) -> dict:  # noqa: ANN001
    r = await c.post(f"/api/designs/{did}/render", json={})
    assert r.status_code == 202, r.text
    await run_jobs()
    render = (await c.get(f"/api/designs/{did}/render")).json()
    r = await c.post(f"/api/renders/{render['id']}/accept")
    assert r.status_code == 200, r.text
    return r.json()
