"""Gate state machine: every allowed and forbidden transition (user-workflow.md G1-G5)."""

import pytest

from tests.integration.conftest import (
    accepted_render,
    analysed,
    approved,
    assign_defaults,
    blurry_photo,
    designing,
    new_project,
    regions_by_label,
    resolve_checks,
    upload,
)


async def stage(client, pid: str) -> str:
    return (await client.get(f"/api/projects/{pid}")).json()["stage"]


# ---------------------------------------------------------------- upload + G1


async def test_hard_photo_failure_is_immediate_and_enqueues_nothing(client, queue) -> None:
    pid = await new_project(client)
    r = await upload(client, pid, blurry_photo())
    assert r.status_code == 422
    assert r.json()["code"] == "blurry"
    assert "too blurry" in r.json()["message"]
    assert queue.jobs == {}
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "upload" and project["photo"] is None


@pytest.mark.parametrize(
    ("data", "code"),
    [(b"definitely not an image", "unsupported_format"), (b"", "empty_file")],
)
async def test_unusable_files_rejected(client, queue, data: bytes, code: str) -> None:
    pid = await new_project(client)
    r = await client.post(
        f"/api/projects/{pid}/photo", files={"file": ("x.jpg", data, "image/jpeg")}
    )
    assert r.status_code == 422
    assert r.json()["code"] == code
    assert queue.jobs == {}


async def test_too_large_upload(client, queue, monkeypatch) -> None:
    from renocore.settings import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024)
    pid = await new_project(client)
    r = await upload(client, pid)
    assert r.status_code == 422 and r.json()["code"] == "too_large"


async def test_g1_pass_goes_straight_to_parts(client, run_jobs) -> None:
    pid = await analysed(client, run_jobs)
    assert await stage(client, pid) == "regions_review"
    r = await client.post(f"/api/projects/{pid}/photo/continue")
    assert r.status_code == 409 and r.json()["code"] == "no_photo_warning"


async def test_g1_warn_then_continue(client, run_jobs, provider) -> None:
    provider.scenario = "warn"
    pid = await analysed(client, run_jobs)
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "photo_warning"
    assert project["verdict"]["status"] == "warn"
    assert any(i["code"] == "angled_view" for i in project["verdict"]["issues"])
    # parts were found speculatively, but G2 actions wait for the user's choice
    assert (await client.post(f"/api/projects/{pid}/regions/approve")).status_code == 409
    r = await client.put(f"/api/projects/{pid}/regions", json={"regions": []})
    assert r.status_code == 409
    r = await client.post(f"/api/projects/{pid}/photo/continue")
    assert r.status_code == 200
    assert r.json()["verdict_overridden"] is True
    assert r.json()["stage"] == "regions_review"
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()
    assert len(regions["regions"]) == 7
    # continuing twice is not a valid transition
    assert (await client.post(f"/api/projects/{pid}/photo/continue")).status_code == 409


async def test_g1_warn_caps_size_confidence_via_photo_warned(client, run_jobs, provider) -> None:
    provider.scenario = "warn"
    pid = await analysed(client, run_jobs)
    await client.post(f"/api/projects/{pid}/photo/continue")
    await resolve_checks(client, pid)
    await client.post(f"/api/projects/{pid}/regions/approve")
    scale = (await client.get(f"/api/projects/{pid}/scale")).json()
    assert scale["confidence"] in ("medium", "low")


async def test_g1_reject_discards_parts_and_allows_reupload(client, run_jobs, provider) -> None:
    provider.scenario = "reject"
    pid = await analysed(client, run_jobs)
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "photo_rejected"
    assert project["verdict"]["status"] == "reject"
    assert (await client.get(f"/api/projects/{pid}/regions")).json()["regions"] == []
    assert (await client.post(f"/api/projects/{pid}/photo/continue")).status_code == 409
    assert (await client.post(f"/api/projects/{pid}/regions/approve")).status_code == 409

    provider.scenario = "pass"
    r = await upload(client, pid)
    assert r.status_code == 202
    await run_jobs()
    assert await stage(client, pid) == "regions_review"


# ---------------------------------------------------------------- G2


async def test_g2_pending_checks_block_approval(client, run_jobs) -> None:
    pid = await analysed(client, run_jobs)
    r = await client.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 409
    assert r.json() == {
        "code": "checks_pending",
        "message": "Please check the 2 parts marked “Please check” before continuing.",
    }
    # answering one of two still blocks
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    body = [
        {**r, "checked": r["needs_check"] or r["checked"]}
        for r in regions  # pillar confirmed, gate proposal still undecided
    ]
    r = await client.put(f"/api/projects/{pid}/regions", json={"regions": body})
    assert r.json()["pending_checks"] == 1
    r = await client.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 409 and "1 part " in r.json()["message"]
    # "No" on the proposal removes it
    r = await client.put(
        f"/api/projects/{pid}/regions",
        json={"regions": [r for r in body if not r["proposed"]]},
    )
    assert r.json()["pending_checks"] == 0
    r = await client.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 200
    labels = {
        x["label"] for x in (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    }
    assert "gate" not in labels


async def test_g2_user_relabel_resolves_check_and_is_final(client, run_jobs) -> None:
    pid = await analysed(client, run_jobs)
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    body = []
    for r in regions:
        if r["proposed"]:
            continue
        if r["needs_check"]:  # "No, it's a ..." -> wall
            r = {**r, "label": "wall"}
        body.append(r)
    out = (await client.put(f"/api/projects/{pid}/regions", json={"regions": body})).json()
    assert out["pending_checks"] == 0
    changed = [r for r in out["regions"] if r["source"] == "user"]
    assert len(changed) == 1 and changed[0]["label"] == "wall" and changed[0]["checked"]


async def test_g2_user_drawn_part_and_validation(client, run_jobs) -> None:
    pid = await analysed(client, run_jobs)
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    body = [{**r, "checked": True, "proposed": False} for r in regions]
    body.append({"label": "roof_edge", "polygon": [[10, 10], [500, 10], [500, 40], [10, 40]]})
    out = (await client.put(f"/api/projects/{pid}/regions", json={"regions": body})).json()
    new = [r for r in out["regions"] if r["label"] == "roof_edge"]
    assert new and new[0]["source"] == "user" and not new[0]["needs_check"]

    bad_id = [*body[:1], {**body[1], "id": "nope"}]
    r = await client.put(f"/api/projects/{pid}/regions", json={"regions": bad_id})
    assert r.status_code == 422 and r.json()["code"] == "unknown_part"
    dup = [body[0], body[0]]
    r = await client.put(f"/api/projects/{pid}/regions", json={"regions": dup})
    assert r.status_code == 422 and r.json()["code"] == "duplicate_part"
    tiny = [{"label": "wall", "polygon": [[1, 1], [1, 1], [1, 1]]}]
    r = await client.put(f"/api/projects/{pid}/regions", json={"regions": tiny})
    assert r.status_code == 422 and r.json()["code"] == "invalid_shape"


async def test_g2_needs_a_wall(client, run_jobs) -> None:
    pid = await analysed(client, run_jobs)
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    openings = [r for r in regions if r["label"] in ("window", "door")]
    await client.put(f"/api/projects/{pid}/regions", json={"regions": openings})
    r = await client.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 409 and r.json()["code"] == "no_parts"


async def test_g2_not_available_before_photo(client, run_jobs) -> None:
    pid = await new_project(client)
    assert (await client.post(f"/api/projects/{pid}/regions/approve")).status_code == 409
    assert (await client.get(f"/api/projects/{pid}/scale")).status_code == 409
    r = await client.post(f"/api/projects/{pid}/scale/confirm", json={"accept": True})
    assert r.status_code == 409
    r = await client.post(f"/api/projects/{pid}/designs", json={"name": "X"})
    assert r.status_code == 409
    # while analysing
    await upload(client, pid)
    assert await stage(client, pid) == "analyzing"
    assert (await client.post(f"/api/projects/{pid}/regions/approve")).status_code == 409


async def test_g2_approve_twice_is_a_no_op(client, run_jobs, queue) -> None:
    pid = await approved(client, run_jobs)
    jobs_before = len(queue.jobs)
    r = await client.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 200 and r.json()["regions_approved"]
    assert len(queue.jobs) == jobs_before


# ---------------------------------------------------------------- G3


async def test_g3_medium_accept(client, run_jobs) -> None:
    pid = await approved(client, run_jobs)
    assert await stage(client, pid) == "scale_review"
    r = await client.post(f"/api/projects/{pid}/scale/confirm", json={})
    assert r.status_code == 422 and r.json()["code"] == "nothing_to_confirm"
    r = await client.post(f"/api/projects/{pid}/scale/confirm", json={"accept": True})
    assert r.status_code == 200 and r.json()["method"] == "door"
    assert await stage(client, pid) == "designing"


async def test_g3_low_confidence_requires_measurement(client, run_jobs, provider) -> None:
    provider.door_agrees = False  # Jev door box and approved door disagree
    provider.windows_alike = False  # and window heights differ -> floor-count fallback
    pid = await approved(client, run_jobs)
    scale = (await client.get(f"/api/projects/{pid}/scale")).json()
    assert scale["confidence"] == "low" and scale["needs_measurement"]
    r = await client.post(f"/api/projects/{pid}/scale/confirm", json={"accept": True})
    assert r.status_code == 409 and r.json()["code"] == "measurement_needed"
    assert await stage(client, pid) == "scale_review"
    r = await client.post(f"/api/projects/{pid}/scale/confirm", json={"facade_width_ft": 32})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["confidence"] == "high" and out["method"] == "user_measurement"
    assert out["confirmed"] and abs(out["facade_width_ft"] - 32) < 1
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "designing"
    assert project["measurements"]["facade_width_ft"] == 32


async def test_g3_reference_line_measurement(client, run_jobs) -> None:
    pid = await approved(client, run_jobs)
    line = {"x1": 300, "y1": 1200, "x2": 900, "y2": 1200, "length_ft": 12}
    r = await client.post(f"/api/projects/{pid}/scale/confirm", json={"reference_line": line})
    assert r.status_code == 200 and r.json()["confidence"] == "high"


async def test_g3_skipped_with_measurement_from_step_one(client, run_jobs) -> None:
    pid = await approved(client, run_jobs, facade_width_ft=30)
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "designing" and project["scale_confirmed"]
    assert [d["name"] for d in (await client.get(f"/api/projects/{pid}/designs")).json()] == [
        "Design 1"
    ]


# ---------------------------------------------------------------- G4 / G5 / report


async def test_finalise_needs_confirmed_size(client, run_jobs) -> None:
    pid = await approved(client, run_jobs)  # scale_review: provisional estimate only
    did = (await client.post(f"/api/projects/{pid}/designs", json={"name": "Try"})).json()["id"]
    await assign_defaults(client, pid, did)
    est = (await client.get(f"/api/designs/{did}/estimate")).json()
    assert est["estimate"]["provisional"] is True
    r = await client.post(f"/api/designs/{did}/estimate/finalise")
    assert r.status_code == 409 and r.json()["code"] == "size_not_confirmed"


async def test_finalise_needs_materials_and_is_versioned(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    empty = (await client.post(f"/api/projects/{pid}/designs", json={"name": "Empty"})).json()
    r = await client.post(f"/api/designs/{empty['id']}/estimate/finalise")
    assert r.status_code == 409 and r.json()["code"] == "no_materials"
    v1 = (await client.post(f"/api/designs/{did}/estimate/finalise")).json()
    again = (await client.post(f"/api/designs/{did}/estimate/finalise")).json()
    assert v1["version"] == again["version"] == 1  # unchanged inputs: same version
    await client.put(
        f"/api/projects/{pid}/rates",
        json={"overrides": [{"material_id": "paint-premium-emulsion", "material_rate": 500}]},
    )
    v2 = (await client.post(f"/api/designs/{did}/estimate/finalise")).json()
    assert v2["version"] == 2 and v2["id"] != v1["id"]


async def test_render_gate(client, run_jobs) -> None:
    pid = await approved(client, run_jobs)
    did = (await client.post(f"/api/projects/{pid}/designs", json={"name": "A"})).json()["id"]
    r = await client.post(f"/api/designs/{did}/render", json={})
    assert r.status_code == 409 and r.json()["code"] == "no_materials"
    assert (await client.get(f"/api/designs/{did}/render")).json() is None


async def test_accept_render_rules(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    started = (await client.post(f"/api/designs/{did}/render", json={})).json()
    rid = started["render"]["id"]
    assert started["render"]["status"] == "queued"
    r = await client.post(f"/api/renders/{rid}/accept")
    assert r.status_code == 409 and r.json()["code"] == "render_not_ready"
    await run_jobs()
    # a redo makes the earlier picture no longer the latest
    await client.post(f"/api/designs/{did}/render", json={"note": "warmer stone"})
    r = await client.post(f"/api/renders/{rid}/accept")
    assert r.status_code == 409 and r.json()["code"] == "not_latest"
    await run_jobs()
    latest = (await client.get(f"/api/designs/{did}/render")).json()
    assert latest["user_note"] == "warmer stone"
    r = await client.post(f"/api/renders/{latest['id']}/accept")
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert (await client.post(f"/api/renders/{latest['id']}/accept")).status_code == 200


async def test_report_requires_accepted_render_and_finalised_estimate(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    r = await client.post(f"/api/designs/{did}/report")
    assert r.status_code == 409 and r.json()["code"] == "design_not_accepted"

    await client.post(f"/api/designs/{did}/render", json={})
    await run_jobs()
    r = await client.post(f"/api/designs/{did}/report")  # ready but not accepted
    assert r.status_code == 409 and r.json()["code"] == "design_not_accepted"

    render = (await client.get(f"/api/designs/{did}/render")).json()
    await client.post(f"/api/renders/{render['id']}/accept")
    r = await client.post(f"/api/designs/{did}/report")
    assert r.status_code == 409 and r.json()["code"] == "estimate_not_finalised"

    await client.post(f"/api/designs/{did}/estimate/finalise")
    await client.put(f"/api/projects/{pid}/rates", json={"extras": {"tax_pct": 12}})
    r = await client.post(f"/api/designs/{did}/report")
    assert r.status_code == 409 and r.json()["code"] == "estimate_changed"

    await client.post(f"/api/designs/{did}/estimate/finalise")
    by = await regions_by_label(client, pid)
    await client.put(
        f"/api/designs/{did}/assignments",
        json={
            "assignments": [
                {"region_id": by["wall"][0]["id"], "material_id": "texture-roller-paint"}
            ]
        },
    )
    r = await client.post(f"/api/designs/{did}/report")
    assert r.status_code == 409 and r.json()["code"] == "design_changed"

    await accepted_render(client, run_jobs, did)
    await client.post(f"/api/designs/{did}/estimate/finalise")
    r = await client.post(f"/api/designs/{did}/report")
    assert r.status_code == 202
