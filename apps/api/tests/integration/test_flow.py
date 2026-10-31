"""The whole journey: photo -> parts -> size check -> design -> new look -> estimate -> PDF."""

import io

from pypdf import PdfReader

from tests.integration.conftest import (
    accepted_render,
    designing,
    new_project,
    resolve_checks,
    upload,
)


async def test_full_journey(client, run_jobs, provider) -> None:
    pid = await new_project(client)
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "upload" and project["photo"] is None

    r = await upload(client, pid)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["project"]["stage"] == "analyzing"
    job = (await client.get(f"/api/jobs/{body['job_id']}")).json()
    assert job == {
        "id": body["job_id"],
        "kind": "analyze_photo",
        "status": "queued",
        "step": "Checking your photo",
        "error": None,
    }
    assert body["project"]["active_job"]["id"] == body["job_id"]

    await run_jobs()
    job = (await client.get(f"/api/jobs/{body['job_id']}")).json()
    assert job["status"] == "done"
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "regions_review"
    assert project["verdict"]["status"] == "pass"
    assert project["active_job"] is None
    photo = project["photo"]
    img = await client.get(photo["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

    regions = (await client.get(f"/api/projects/{pid}/regions")).json()
    labels = sorted(r["label"] for r in regions["regions"])
    assert labels == ["door", "gate", "pillar", "railing", "wall", "window", "window"]
    # unsure pillar + proposed gate
    assert regions["pending_checks"] == 2
    pillar = next(r for r in regions["regions"] if r["label"] == "pillar")
    assert pillar["needs_check"] and pillar["friendly_label"] == "Pillar"
    assert pillar["crop_url"] and (await client.get(pillar["crop_url"])).status_code == 200
    gate = next(r for r in regions["regions"] if r["label"] == "gate")
    assert gate["proposed"] and gate["source"] == "jev_box"

    out = await resolve_checks(client, pid)
    assert out["pending_checks"] == 0
    r = await client.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "scale_review"  # door-based size: medium, needs a click
    advice = (await client.get(f"/api/projects/{pid}/material-advice")).json()
    assert advice["ready"] is False
    await run_jobs()
    advice = (await client.get(f"/api/projects/{pid}/material-advice")).json()
    assert advice["ready"] is True
    assert {a["region_id"] for a in advice["advice"]} >= {pillar["id"]}

    scale = (await client.get(f"/api/projects/{pid}/scale")).json()
    assert scale["method"] == "door" and scale["confidence"] == "medium"
    assert scale["confirmed"] is False and scale["needs_measurement"] is False
    r = await client.post(f"/api/projects/{pid}/scale/confirm", json={"accept": True})
    assert r.status_code == 200 and r.json()["confirmed"] is True
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "designing" and project["scale_confirmed"]

    designs = (await client.get(f"/api/projects/{pid}/designs")).json()
    assert [d["name"] for d in designs] == ["Design 1"]

    materials = (await client.get("/api/materials")).json()
    assert len(materials) >= 10
    swatch = await client.get(materials[0]["swatch_url"])
    assert swatch.status_code == 200

    trace = (await client.get(f"/api/projects/{pid}/ai-calls")).json()
    steps = [c["step"] for c in trace]
    assert set(steps[:2]) == {"C1", "C2"} and steps[2] == "C3"  # C1 and C2 run concurrently
    assert {c["step"] for c in trace} == {"C1", "C2", "C3", "C4"}
    # plain-language trace for the "How we worked this out" panel
    by_step = {c["step"]: c for c in trace}
    assert by_step["C2"]["title"] == "Found the parts of your house"
    assert by_step["C2"]["stage"] == "photo" and by_step["C4"]["stage"] == "materials"
    assert all(c["summary"] and "C" + c["step"][1] not in c["title"] for c in trace)
    assert all(c["ok"] for c in trace)


async def test_design_to_report(client, run_jobs, provider) -> None:
    pid, did = await designing(client, run_jobs)
    estimate = (await client.get(f"/api/designs/{did}/estimate")).json()
    assert estimate["finalised"] is False and estimate["id"] is None
    total = estimate["estimate"]["grand_total"]
    assert total > 0
    assert estimate["estimate"]["provisional"] is False

    render = await accepted_render(client, run_jobs, did)
    assert render["status"] == "accepted" and render["qa"]["passed"]
    assert (await client.get(render["image_url"])).status_code == 200

    fin = (await client.post(f"/api/designs/{did}/estimate/finalise")).json()
    assert fin["finalised"] and fin["version"] == 1 and not fin["stale"]

    r = await client.post(f"/api/designs/{did}/report")
    assert r.status_code == 202, r.text
    await run_jobs()
    job = (await client.get(f"/api/jobs/{r.json()['job_id']}")).json()
    assert job["status"] == "done", job
    reports = (await client.get(f"/api/designs/{did}/reports")).json()
    assert len(reports) == 1 and reports[0]["estimate_version"] == 1
    assert reports[0]["render_id"] == render["id"]
    pdf = await client.get(reports[0]["download_url"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Grand total" in text and "Assumptions" in text
    assert "not a quotation" in text
