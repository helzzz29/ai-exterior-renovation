"""Auth (cookie sessions) and owner scoping: another user's resources are 404."""

from tests.integration.conftest import (
    accepted_render,
    designing,
    make_client,
    new_project,
    register,
)


async def test_register_login_logout_me(app, queue, provider) -> None:
    async with make_client(app) as c:
        assert (await c.get("/api/auth/me")).status_code == 401
        r = await c.post(
            "/api/auth/register", json={"email": "Ann@Example.com", "password": "long-password"}
        )
        assert r.status_code == 200 and r.json()["email"] == "ann@example.com"
        cookie = r.headers["set-cookie"].lower()
        assert "session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
        assert (await c.get("/api/auth/me")).json()["email"] == "ann@example.com"

        r = await c.post("/api/auth/logout")
        assert r.status_code == 204
        c.cookies.clear()
        assert (await c.get("/api/auth/me")).status_code == 401
        assert (await c.get("/api/projects")).status_code == 401

        r = await c.post(
            "/api/auth/login", json={"email": "ann@example.com", "password": "wrong-password"}
        )
        assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
        r = await c.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "long-password"}
        )
        assert r.status_code == 401
        r = await c.post(
            "/api/auth/login", json={"email": "ANN@example.com", "password": "long-password"}
        )
        assert r.status_code == 200
        assert (await c.get("/api/auth/me")).status_code == 200


async def test_duplicate_email_and_bad_tokens(app, queue, provider) -> None:
    async with make_client(app) as c:
        await register(c, "dup@example.com")
        r = await c.post(
            "/api/auth/register", json={"email": "dup@example.com", "password": "another-pass"}
        )
        assert r.status_code == 409 and r.json()["code"] == "email_taken"
        r = await c.post("/api/auth/register", json={"email": "x@example.com", "password": "short"})
        assert r.status_code == 422
    async with make_client(app) as c:
        c.cookies.set("session", "not-a-jwt")
        r = await c.get("/api/auth/me")
        assert r.status_code == 401 and r.json()["code"] == "not_signed_in"


async def test_other_user_gets_404_everywhere(client, other_client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    render = await accepted_render(client, run_jobs, did)
    await client.post(f"/api/designs/{did}/estimate/finalise")
    job_id = (await client.post(f"/api/designs/{did}/report")).json()["job_id"]
    await run_jobs()
    report = (await client.get(f"/api/designs/{did}/reports")).json()[0]
    project = (await client.get(f"/api/projects/{pid}")).json()
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]

    forbidden = [
        ("GET", f"/api/projects/{pid}", None),
        ("PATCH", f"/api/projects/{pid}", {"name": "mine now"}),
        ("DELETE", f"/api/projects/{pid}", None),
        ("POST", f"/api/projects/{pid}/photo/continue", None),
        ("GET", f"/api/projects/{pid}/regions", None),
        ("PUT", f"/api/projects/{pid}/regions", {"regions": []}),
        ("POST", f"/api/projects/{pid}/regions/approve", None),
        ("GET", f"/api/projects/{pid}/scale", None),
        ("POST", f"/api/projects/{pid}/scale/confirm", {"accept": True}),
        ("GET", f"/api/projects/{pid}/material-advice", None),
        ("GET", f"/api/projects/{pid}/designs", None),
        ("POST", f"/api/projects/{pid}/designs", {"name": "x"}),
        ("PUT", f"/api/designs/{did}/assignments", {"assignments": []}),
        ("DELETE", f"/api/designs/{did}", None),
        ("POST", f"/api/designs/{did}/render", {}),
        ("GET", f"/api/designs/{did}/render", None),
        ("POST", f"/api/renders/{render['id']}/accept", None),
        ("GET", f"/api/designs/{did}/estimate", None),
        ("POST", f"/api/designs/{did}/estimate/finalise", None),
        ("GET", f"/api/projects/{pid}/rates", None),
        ("PUT", f"/api/projects/{pid}/rates", {}),
        ("POST", f"/api/designs/{did}/report", None),
        ("GET", f"/api/designs/{did}/reports", None),
        ("GET", report["download_url"], None),
        ("GET", f"/api/jobs/{job_id}", None),
        ("GET", project["photo"]["url"], None),
        ("GET", render["image_url"], None),
        ("GET", regions[0]["crop_url"] or project["photo"]["url"], None),
        ("GET", f"/api/projects/{pid}/ai-calls", None),
    ]
    for method, url, body in forbidden:
        r = await other_client.request(method, url, json=body)
        assert r.status_code == 404, (method, url, r.status_code)
        assert r.json()["code"] == "not_found"
    r = await other_client.post(
        f"/api/projects/{pid}/photo", files={"file": ("a.jpg", b"xx", "image/jpeg")}
    )
    assert r.status_code == 404
    assert (await other_client.get("/api/projects")).json() == []
    # the owner still has everything
    assert (await client.get(f"/api/projects/{pid}")).status_code == 200


async def test_unknown_ids_are_404(client) -> None:
    for url in (
        "/api/projects/nope",
        "/api/designs/nope/render",
        "/api/jobs/nope",
        "/api/images/nope",
        "/api/reports/nope/download",
    ):
        assert (await client.get(url)).status_code == 404
    assert (await client.post("/api/renders/nope/accept")).status_code == 404


async def test_projects_crud(client) -> None:
    pid = await new_project(client, "First", floors=2)
    await new_project(client, "Second")
    listed = (await client.get("/api/projects")).json()
    assert [p["name"] for p in listed] == ["Second", "First"]
    assert listed[0]["thumbnail_url"] is None and listed[0]["stage"] == "upload"
    r = await client.patch(f"/api/projects/{pid}", json={"name": "Renamed"})
    assert r.json()["name"] == "Renamed" and r.json()["measurements"]["floors"] == 2
    assert (await client.delete(f"/api/projects/{pid}")).status_code == 204
    assert (await client.get(f"/api/projects/{pid}")).status_code == 404
