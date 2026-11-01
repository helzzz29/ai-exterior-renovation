"""Background jobs: idempotency, retries, the render auto-regenerate path, progress steps."""

import asyncio

from sqlalchemy import select

from renocore.database import session_scope
from renocore.tables import JobRun
from tests.integration.conftest import designing, new_project, upload


async def test_double_upload_of_same_photo_is_one_job(client, queue, run_jobs) -> None:
    pid = await new_project(client)
    first = await upload(client, pid)
    second = await upload(client, pid)
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert len(queue.jobs) == 1
    await run_jobs()
    # once finished, uploading again is a new analysis
    third = await upload(client, pid)
    assert third.json()["job_id"] != first.json()["job_id"]


async def test_concurrent_double_click_render_is_one_job(client, queue, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    before = len(queue.jobs)
    a, b = await asyncio.gather(
        client.post(f"/api/designs/{did}/render", json={}),
        client.post(f"/api/designs/{did}/render", json={}),
    )
    assert a.status_code == b.status_code == 202
    assert a.json()["job_id"] == b.json()["job_id"]
    assert a.json()["render"]["id"] == b.json()["render"]["id"]
    assert len(queue.jobs) == before + 1
    # a different note is a different request
    c = await client.post(f"/api/designs/{did}/render", json={"note": "lighter paint"})
    assert c.json()["job_id"] != a.json()["job_id"]


async def test_double_report_is_one_job(client, queue, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    await client.post(f"/api/designs/{did}/render", json={})
    await run_jobs()
    render = (await client.get(f"/api/designs/{did}/render")).json()
    await client.post(f"/api/renders/{render['id']}/accept")
    await client.post(f"/api/designs/{did}/estimate/finalise")
    a = await client.post(f"/api/designs/{did}/report")
    b = await client.post(f"/api/designs/{did}/report")
    assert a.json()["job_id"] == b.json()["job_id"]
    await run_jobs()
    assert len((await client.get(f"/api/designs/{did}/reports")).json()) == 1


async def test_analysis_retries_after_provider_failure(client, run_jobs, provider) -> None:
    provider.fail = {"whole_photo": 1}
    pid = await new_project(client)
    job_id = (await upload(client, pid)).json()["job_id"]
    await run_jobs()
    job = (await client.get(f"/api/jobs/{job_id}")).json()
    assert job["status"] == "done" and job["error"] is None
    assert provider.calls["whole_photo"] == 2
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "regions_review"
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    assert len(regions) == 7  # the retry did not duplicate parts
    async with session_scope() as s:
        run = await s.get(JobRun, job_id)
        assert run.attempts == 2
    # the failed call is visible in the trace
    trace = (await client.get(f"/api/projects/{pid}/ai-calls")).json()
    assert sum(1 for c in trace if c["step"] == "C1") == 2


async def test_analysis_gives_up_with_plain_message(client, run_jobs, provider) -> None:
    provider.fail = {"segment": 10}
    pid = await new_project(client)
    job_id = (await upload(client, pid)).json()["job_id"]
    await run_jobs()
    job = (await client.get(f"/api/jobs/{job_id}")).json()
    assert job["status"] == "failed"
    assert job["error"] == "We couldn't finish checking your photo. Please try uploading it again."
    assert provider.calls["segment"] == 3  # JOB_MAX_ATTEMPTS
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "upload" and project["active_job"] is None


async def test_render_failure_marks_render_failed(client, run_jobs, provider) -> None:
    pid, did = await designing(client, run_jobs)
    provider.fail = {"generate_redesign": 10}
    job_id = (await client.post(f"/api/designs/{did}/render", json={})).json()["job_id"]
    await run_jobs()
    assert (await client.get(f"/api/jobs/{job_id}")).json()["status"] == "failed"
    render = (await client.get(f"/api/designs/{did}/render")).json()
    assert render["status"] == "failed" and render["image_url"] is None


async def test_render_auto_regenerates_via_render_design(client, run_jobs, provider) -> None:
    pid, did = await designing(client, run_jobs)
    provider.qa_failures = 1
    await client.post(f"/api/designs/{did}/render", json={})
    await run_jobs()
    render = (await client.get(f"/api/designs/{did}/render")).json()
    assert render["status"] == "ready"
    assert render["attempts"] == 2 and render["qa"]["passed"]
    assert provider.calls["generate_redesign"] == 2
    assert provider.last_fix_notes  # the redo is told what to fix


async def test_render_stops_after_max_regenerations(client, run_jobs, provider) -> None:
    pid, did = await designing(client, run_jobs)
    provider.qa_failures = 10
    await client.post(f"/api/designs/{did}/render", json={})
    await run_jobs()
    render = (await client.get(f"/api/designs/{did}/render")).json()
    assert render["attempts"] == 3  # first try + RENDER_MAX_AUTO_REGENERATE (2)
    assert render["qa"]["passed"] is False and render["qa"]["failed_checks"]
    # the user can still accept it at G4
    assert (await client.post(f"/api/renders/{render['id']}/accept")).status_code == 200


async def test_superseded_analysis_is_ignored(client, run_jobs, provider) -> None:
    from tests.integration.conftest import SAMPLES

    pid = await new_project(client)
    first = (await upload(client, pid)).json()["job_id"]
    second = (await upload(client, pid, (SAMPLES / "house-03.jpg").read_bytes())).json()["job_id"]
    await run_jobs()
    assert (await client.get(f"/api/jobs/{first}")).json()["status"] == "done"
    assert (await client.get(f"/api/jobs/{second}")).json()["status"] == "done"
    assert provider.calls["whole_photo"] == 1  # the stale job exited early
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    assert len(regions) == 7


async def test_step_strings_are_plain_language(client, run_jobs, monkeypatch) -> None:
    from renocore.operations import job_runner as jobs_svc

    steps: list[str] = []
    original = jobs_svc.JobCtx.set_step

    async def spy(self, step: str) -> None:  # noqa: ANN001
        steps.append(step)
        await original(self, step)

    monkeypatch.setattr(jobs_svc.JobCtx, "set_step", spy)
    pid = await new_project(client)
    await upload(client, pid)
    await run_jobs()
    assert steps == ["Checking your photo", "Finding walls, windows and balconies", "Measuring"]


async def test_job_runs_have_kinds(client, run_jobs) -> None:
    await designing(client, run_jobs)
    async with session_scope() as s:
        kinds = sorted({r.kind for r in await s.scalars(select(JobRun))})
    assert kinds == ["analyze_photo", "material_advice"]
