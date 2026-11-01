"""Production settings: invite-only accounts and the daily limits on paid AI steps."""

import pytest

from renocore.database import session_scope
from renocore.identity import ensure_seed_users, hash_password
from renocore.settings import get_settings
from tests.integration.conftest import designing, make_client, new_project, upload


async def test_closed_signup_still_lets_invited_people_sign_in(
    app, queue, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "signup_open", False)
    async with session_scope() as session:
        invited = {"Invited@Example.com": hash_password("pass-one-1")}
        assert await ensure_seed_users(session, invited)
    async with make_client(app) as c:
        stranger = {"email": "stranger@example.com", "password": "long-password"}
        r = await c.post("/api/auth/register", json=stranger)
        assert r.status_code == 403 and r.json()["code"] == "signup_closed"
        r = await c.post(
            "/api/auth/login", json={"email": "invited@example.com", "password": "pass-one-1"}
        )
        assert r.status_code == 200


async def test_seed_users_are_idempotent_and_rotate_passwords(app, queue, provider) -> None:
    first, second = hash_password("pass-one-1"), hash_password("pass-two-2")
    async with session_scope() as session:
        assert await ensure_seed_users(session, {"a@example.com": first}) == 1
        assert await ensure_seed_users(session, {"a@example.com": first}) == 0
        assert await ensure_seed_users(session, {"a@example.com": second}) == 1
    async with make_client(app) as c:
        ok = {"email": "a@example.com", "password": "pass-two-2"}
        assert (await c.post("/api/auth/login", json=ok)).status_code == 200
        old = {"email": "a@example.com", "password": "pass-one-1"}
        assert (await c.post("/api/auth/login", json=old)).status_code == 401


async def test_seed_users_refuse_plain_passwords(app) -> None:
    async with session_scope() as session:
        with pytest.raises(ValueError, match="argon2"):
            await ensure_seed_users(session, {"a@example.com": "not-a-hash"})


async def test_daily_photo_limit(client, run_jobs, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "daily_photo_limit", 1)
    first = await new_project(client, name="First")
    assert (await upload(client, first)).status_code == 202
    second = await new_project(client, name="Second")
    r = await upload(client, second)
    assert r.status_code == 429 and r.json()["code"] == "daily_limit"
    assert "today's limit of 1 photo checks" in r.json()["message"]


async def test_daily_new_look_limit(client, run_jobs, monkeypatch: pytest.MonkeyPatch) -> None:
    pid, did = await designing(client, run_jobs)
    monkeypatch.setattr(get_settings(), "daily_new_look_limit", 1)
    assert (await client.post(f"/api/designs/{did}/render", json={})).status_code == 202
    await run_jobs()
    r = await client.post(f"/api/designs/{did}/render", json={"note": "warmer colours"})
    assert r.status_code == 429 and r.json()["code"] == "daily_limit"
