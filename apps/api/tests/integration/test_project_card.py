"""The project card says "Report ready" only while a report matches what is on screen."""

from tests.integration.conftest import accepted_render, designing


async def _card(client, pid: str) -> dict:  # noqa: ANN001
    return next(p for p in (await client.get("/api/projects")).json() if p["id"] == pid)


async def test_report_ready_follows_the_current_report(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    assert (await _card(client, pid))["report_ready"] is False

    await accepted_render(client, run_jobs, did)
    assert (await client.post(f"/api/designs/{did}/estimate/finalise")).status_code == 200
    assert (await _card(client, pid))["report_ready"] is False  # finalised, no PDF yet

    assert (await client.post(f"/api/designs/{did}/report")).status_code == 202
    await run_jobs()
    assert (await _card(client, pid))["report_ready"] is True

    # a price change makes the finalised estimate (and so the report) out of date
    rates = (await client.get(f"/api/projects/{pid}/rates")).json()
    extras = {**rates["extras"], "tax_pct": 5}
    r = await client.put(f"/api/projects/{pid}/rates", json={"overrides": [], "extras": extras})
    assert r.status_code == 200, r.text
    assert (await _card(client, pid))["report_ready"] is False
