"""One test per row of the change-propagation table (user-workflow.md section 6).

Each starts from a "report-ready" design: accepted new look + finalised estimate.
"""

from tests.integration.conftest import (
    SAMPLES,
    accepted_render,
    assign_defaults,
    designing,
    regions_by_label,
    resolve_checks,
    upload,
)


async def report_ready(client, run_jobs) -> tuple[str, str]:  # noqa: ANN001
    pid, did = await designing(client, run_jobs)
    await accepted_render(client, run_jobs, did)
    fin = await client.post(f"/api/designs/{did}/estimate/finalise")
    assert fin.status_code == 200
    assert (await client.post(f"/api/designs/{did}/report")).status_code == 202
    await run_jobs()
    return pid, did


async def design(client, did: str) -> dict:  # noqa: ANN001
    pid = None
    for d in (await client.get("/api/projects")).json():
        pid = d["id"]
    designs = (await client.get(f"/api/projects/{pid}/designs")).json()
    return next(d for d in designs if d["id"] == did)


async def report_status(client, did: str) -> int:  # noqa: ANN001
    return (await client.post(f"/api/designs/{did}/report")).status_code


async def test_row_photo(client, run_jobs, provider) -> None:
    """Photo: parts detected again, suggestions redone, image + estimate stale, report locked."""
    pid, did = await report_ready(client, run_jobs)
    old_regions = {
        r["id"] for r in (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    }

    r = await upload(client, pid, (SAMPLES / "house-03.jpg").read_bytes())
    assert r.status_code == 202
    await run_jobs()
    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "regions_review"
    assert not project["regions_approved"] and not project["scale_confirmed"]
    new_regions = {
        r["id"] for r in (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    }
    assert new_regions and not (new_regions & old_regions)  # detected again
    assert provider.calls["segment"] == 2

    d = await design(client, did)
    assert d["name"] == "Design 1" and d["assignments"] == []  # name kept, choices dropped
    assert d["render"]["stale"] is True
    assert d["estimate_stale"] is True and d["estimate_finalised"] is True
    assert await report_status(client, did) == 409

    await resolve_checks(client, pid)
    await client.post(f"/api/projects/{pid}/regions/approve")
    await run_jobs()
    assert len(provider.advice_requests) == 2  # suggestions redone for the new parts
    assert set(provider.advice_requests[1]) <= new_regions


async def test_row_parts_after_confirming(client, run_jobs, provider) -> None:
    """Parts: G2 reopens, only changed parts get new suggestions, image + estimate stale."""
    pid, did = await report_ready(client, run_jobs)
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    wall = next(r for r in regions if r["label"] == "wall")
    moved = [[x, y + 20] if i == 0 else [x, y] for i, (x, y) in enumerate(wall["polygon"])]
    body = [{**r, "polygon": moved} if r["id"] == wall["id"] else r for r in regions]
    out = await client.put(f"/api/projects/{pid}/regions", json={"regions": body})
    assert out.status_code == 200 and out.json()["approved"] is False

    project = (await client.get(f"/api/projects/{pid}")).json()
    assert project["stage"] == "regions_review" and not project["regions_approved"]
    d = await design(client, did)
    assert d["render"]["stale"] and d["estimate_stale"]
    assert len(d["assignments"]) == 2  # choices on unchanged ids are kept
    assert await report_status(client, did) == 409
    assert (await client.get(f"/api/designs/{did}/estimate")).status_code == 409

    r = await client.post(f"/api/projects/{pid}/regions/approve")
    assert r.status_code == 200
    await run_jobs()
    assert provider.advice_requests[-1] == [wall["id"]]  # changed parts only
    advice = (await client.get(f"/api/projects/{pid}/material-advice")).json()
    assert advice["ready"] and wall["id"] in {a["region_id"] for a in advice["advice"]}


async def test_row_size_reference(client, run_jobs) -> None:
    """Size: image unaffected, estimate stale, report locked."""
    pid, did = await report_ready(client, run_jobs)
    before = (await client.get(f"/api/designs/{did}/estimate")).json()["estimate"]["grand_total"]
    r = await client.patch(f"/api/projects/{pid}", json={"measurements": {"facade_width_ft": 45}})
    assert r.status_code == 200
    assert r.json()["stage"] == "designing" and r.json()["scale_confirmed"]
    d = await design(client, did)
    assert d["render"]["stale"] is False
    assert d["estimate_stale"] is True
    est = (await client.get(f"/api/designs/{did}/estimate")).json()
    assert est["stale"] and est["estimate"]["grand_total"] != before
    assert est["estimate"]["confidence"] == "high"
    assert await report_status(client, did) == 409


async def test_row_materials_of_one_design(client, run_jobs) -> None:
    """Materials in design X: X image + estimate stale, report for X locked; Y untouched."""
    pid, x = await report_ready(client, run_jobs)
    y = (
        await client.post(f"/api/projects/{pid}/designs", json={"name": "Y", "copy_from": x})
    ).json()["id"]
    await accepted_render(client, run_jobs, y)
    await client.post(f"/api/designs/{y}/estimate/finalise")

    by = await regions_by_label(client, pid)
    r = await client.put(
        f"/api/designs/{x}/assignments",
        json={
            "assignments": [
                {"region_id": by["wall"][0]["id"], "material_id": "texture-roller-paint"}
            ]
        },
    )
    assert r.status_code == 200
    dx, dy = await design(client, x), await design(client, y)
    assert dx["render"]["stale"] and dx["estimate_stale"]
    assert not dy["render"]["stale"] and not dy["estimate_stale"]
    assert await report_status(client, x) == 409
    assert await report_status(client, y) == 202


async def test_row_prices(client, run_jobs) -> None:
    """Prices: image unaffected, estimate recalculated instantly, report locked until finalised."""
    pid, did = await report_ready(client, run_jobs)
    before = (await client.get(f"/api/designs/{did}/estimate")).json()["estimate"]
    r = await client.put(
        f"/api/projects/{pid}/rates",
        json={
            "overrides": [{"material_id": "cladding-natural-stone", "material_rate": 200}],
            "extras": {"contingency_pct": 10},
        },
    )
    assert r.status_code == 200
    assert r.json()["extras"]["contingency_pct"] == 10
    est = (await client.get(f"/api/designs/{did}/estimate")).json()
    assert est["stale"] and est["estimate"]["grand_total"] > before["grand_total"]
    assert any(line["rate_overridden"] for line in est["estimate"]["lines"])
    d = await design(client, did)
    assert d["render"]["stale"] is False and d["estimate_stale"] is True
    assert await report_status(client, did) == 409
    fin = (await client.post(f"/api/designs/{did}/estimate/finalise")).json()
    assert fin["version"] == 2
    assert await report_status(client, did) == 202


async def test_row_redo_of_design(client, run_jobs, provider) -> None:
    """Redo: new image to accept, estimate unaffected, report locked until accepted."""
    pid, did = await report_ready(client, run_jobs)
    r = await client.post(f"/api/designs/{did}/render", json={"note": "a warmer stone colour"})
    assert r.status_code == 202
    await run_jobs()
    assert provider.last_note == "a warmer stone colour"
    d = await design(client, did)
    assert d["render"]["status"] == "ready" and not d["render"]["stale"]
    assert d["estimate_stale"] is False and d["estimate_finalised"]
    assert await report_status(client, did) == 409
    await client.post(f"/api/renders/{d['render']['id']}/accept")
    assert await report_status(client, did) == 202


async def test_assignments_survive_unrelated_part_removal(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    await assign_defaults(client, pid, did)
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    pillar = next(r for r in regions if r["label"] == "pillar")
    body = [r for r in regions if r["id"] != pillar["id"]]
    await client.put(f"/api/projects/{pid}/regions", json={"regions": body})
    d = await design(client, did)
    assert [a["region_id"] for a in d["assignments"]] != [] and all(
        a["region_id"] != pillar["id"] for a in d["assignments"]
    )


async def test_catalogue_price_change_keeps_the_new_look(
    client, run_jobs, provider, monkeypatch
) -> None:  # noqa: ANN001
    """A new price or can size in the catalogue re-prices the estimate but never asks for a
    new (paid) picture; a new swatch does."""
    from app.services import catalogue

    pid, did = await report_ready(client, run_jobs)
    cat = dict(catalogue.get_catalogue())
    stone = cat["cladding-natural-stone"]
    cat["cladding-natural-stone"] = stone.model_copy(update={"material_rate": 999})
    monkeypatch.setattr(catalogue, "_cache", cat)
    d = await design(client, did)
    assert d["render"]["stale"] is False and d["estimate_stale"] is True

    cat["cladding-natural-stone"] = stone.model_copy(update={"swatch": "other.png"})
    d = await design(client, did)
    assert d["render"]["stale"] is True
