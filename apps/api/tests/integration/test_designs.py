"""Designs, assignments validation, rates and material advice."""

from tests.integration.conftest import designing, regions_by_label


async def test_create_duplicate_delete(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    copy = await client.post(
        f"/api/projects/{pid}/designs", json={"name": "Stone version", "copy_from": did}
    )
    assert copy.status_code == 201
    original = next(
        d for d in (await client.get(f"/api/projects/{pid}/designs")).json() if d["id"] == did
    )
    assert copy.json()["assignments"] == original["assignments"]
    assert copy.json()["render"] is None and not copy.json()["estimate_finalised"]

    r = await client.post(
        f"/api/projects/{pid}/designs", json={"name": "Bad", "copy_from": "missing"}
    )
    assert r.status_code == 404
    assert (await client.delete(f"/api/designs/{copy.json()['id']}")).status_code == 204
    names = [d["name"] for d in (await client.get(f"/api/projects/{pid}/designs")).json()]
    assert names == ["Design 1"]


async def test_rename_design(client, other_client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    r = await client.patch(f"/api/designs/{did}", json={"name": "Stone front"})
    assert r.status_code == 200
    assert r.json()["name"] == "Stone front" and r.json()["id"] == did
    assert len(r.json()["assignments"]) == 2  # choices untouched
    names = [d["name"] for d in (await client.get(f"/api/projects/{pid}/designs")).json()]
    assert names == ["Stone front"]
    assert (await client.patch(f"/api/designs/{did}", json={"name": ""})).status_code == 422
    assert (await client.patch(f"/api/designs/{did}", json={"name": "x" * 81})).status_code == 422
    r = await other_client.patch(f"/api/designs/{did}", json={"name": "Mine"})
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert (await client.patch("/api/designs/nope", json={"name": "A"})).status_code == 404


async def test_assignment_validation(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    by = await regions_by_label(client, pid)
    wall, door, railing = by["wall"][0]["id"], by["door"][0]["id"], by["railing"][0]["id"]

    async def put(assignments: list[dict]) -> tuple[int, dict]:
        r = await client.put(f"/api/designs/{did}/assignments", json={"assignments": assignments})
        return r.status_code, r.json()

    status, body = await put([{"region_id": wall, "material_id": "railing-toughened-glass"}])
    assert status == 422 and body["code"] == "material_not_applicable"
    assert "can't be used" in body["message"]
    status, body = await put([{"region_id": door, "material_id": "paint-premium-emulsion"}])
    assert status == 422 and body["code"] == "opening"
    status, body = await put([{"region_id": wall, "material_id": "unobtainium"}])
    assert status == 422 and body["code"] == "unknown_material"
    status, body = await put([{"region_id": "gone", "material_id": "paint-premium-emulsion"}])
    assert status == 422 and body["code"] == "unknown_part"
    status, body = await put(
        [{"region_id": wall, "material_id": "paint-premium-emulsion", "color": "beige"}]
    )
    assert status == 422 and body["code"] == "invalid_color"
    status, body = await put(
        [
            {"region_id": wall, "material_id": "paint-premium-emulsion"},
            {"region_id": wall, "material_id": "texture-roller-paint"},
        ]
    )
    assert status == 422 and body["code"] == "duplicate_part"

    status, body = await put(
        [
            {"region_id": wall, "material_id": "texture-roller-paint", "color": "#aabbcc"},
            {"region_id": railing, "material_id": "railing-toughened-glass"},
        ]
    )
    assert status == 200
    assert {a["material_id"] for a in body["assignments"]} == {
        "texture-roller-paint",
        "railing-toughened-glass",
    }
    est = (await client.get(f"/api/designs/{did}/estimate")).json()["estimate"]
    assert {line["category"] for line in est["lines"]} == {"texture", "railing"}


async def test_relabel_drops_choices_that_no_longer_fit(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)  # pillar has stone cladding
    regions = (await client.get(f"/api/projects/{pid}/regions")).json()["regions"]
    body = [{**r, "label": "railing"} if r["label"] == "pillar" else r for r in regions]
    await client.put(f"/api/projects/{pid}/regions", json={"regions": body})
    designs = (await client.get(f"/api/projects/{pid}/designs")).json()
    assert [a["material_id"] for a in designs[0]["assignments"]] == ["paint-premium-emulsion"]


async def test_rates_roundtrip_and_validation(client, run_jobs) -> None:
    pid, did = await designing(client, run_jobs)
    rates = (await client.get(f"/api/projects/{pid}/rates")).json()
    assert rates["overrides"] == [] and rates["extras"]["tax_pct"] == 18
    r = await client.put(
        f"/api/projects/{pid}/rates",
        json={
            "overrides": [
                {"material_id": "paint-premium-emulsion", "labour_rate": 20},
                {"material_id": "cladding-natural-stone"},  # nothing set: ignored
            ],
            "extras": {"tax_pct": 12, "scaffolding_rate_per_sqft": 0},
        },
    )
    assert r.status_code == 200
    assert r.json()["overrides"] == [
        {"material_id": "paint-premium-emulsion", "material_rate": None, "labour_rate": 20}
    ]
    assert (await client.get(f"/api/projects/{pid}/rates")).json() == r.json()
    est = (await client.get(f"/api/designs/{did}/estimate")).json()["estimate"]
    assert est["extras"]["tax_pct"] == 12 and est["scaffolding"] == 0

    bad = await client.put(
        f"/api/projects/{pid}/rates",
        json={"overrides": [{"material_id": "nope", "labour_rate": 1}]},
    )
    assert bad.status_code == 422 and bad.json()["code"] == "unknown_material"
    dup = await client.put(
        f"/api/projects/{pid}/rates",
        json={
            "overrides": [
                {"material_id": "paint-premium-emulsion", "labour_rate": 1},
                {"material_id": "paint-premium-emulsion", "labour_rate": 2},
            ]
        },
    )
    assert dup.status_code == 422
    neg = await client.put(
        f"/api/projects/{pid}/rates",
        json={"overrides": [{"material_id": "paint-premium-emulsion", "labour_rate": -1}]},
    )
    assert neg.status_code == 422


async def test_material_advice_tags(client, run_jobs) -> None:
    pid, _ = await designing(client, run_jobs)
    advice = (await client.get(f"/api/projects/{pid}/material-advice")).json()
    assert advice["ready"]
    by = await regions_by_label(client, pid)
    ids = {a["region_id"] for a in advice["advice"]}
    assert by["wall"][0]["id"] in ids
    assert by["door"][0]["id"] not in ids  # openings get no suggestions
    wall = next(a for a in advice["advice"] if a["region_id"] == by["wall"][0]["id"])
    assert len(wall["recommended"]) == 2


async def test_materials_catalogue(client) -> None:
    materials = (await client.get("/api/materials")).json()
    ids = {m["id"] for m in materials}
    assert {"paint-premium-emulsion", "railing-toughened-glass"} <= ids
    assert all(m["swatch_url"].startswith("/api/swatches/") for m in materials)
