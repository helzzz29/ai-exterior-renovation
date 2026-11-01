"""The PDF report renders sample data with totals, derivations and the assumptions section."""

import io
from datetime import UTC, datetime

from PIL import Image
from pypdf import PdfReader

from renocore.exports import DISCLAIMER, ReportData, ReportPart, build_report_pdf, format_inr
from renocore.schemas.entities import (
    CompanionLine,
    Confidence,
    Estimate,
    Extras,
    LineItem,
    ScaleMethod,
    ScaleResult,
    SurfaceMeasure,
)


def _jpeg(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), color).save(buf, "JPEG")
    return buf.getvalue()


def sample_estimate() -> Estimate:
    scale = ScaleResult(
        ft_per_px=0.015184,
        method=ScaleMethod.door,
        confidence=Confidence.medium,
        facade_width_ft=31,
        explanation="We used your main door as a guide (standard height 7 ft).",
    )
    paint = LineItem(
        material_id="paint",
        material_name="Exterior emulsion paint",
        category="paint",
        label="wall",
        region_ids=["w"],
        measured_quantity=254.2,
        measured_unit="sqft",
        wastage_pct=5,
        with_wastage=266.9,
        required_quantity=4.85,
        purchase_quantity=8,
        purchase_unit="L",
        packs=2,
        pack_size=4,
        material_rate=420,
        material_cost=3360,
        companions=[
            CompanionLine(
                name="Primer",
                quantity=2.22,
                unit="L",
                packs=1,
                purchase_quantity=4,
                rate=250,
                cost=1000,
            )
        ],
        labour_rate=14,
        labour_cost=3559,
        total=7919,
        rate_overridden=True,
        derivation=["Area 254.2 sqft", "With 5% wastage: 266.9 sqft", "Paint 4.85 L -> 2 x 4 L"],
    )
    stone = paint.model_copy(
        update={
            "material_id": "stone",
            "material_name": "Natural stone cladding",
            "category": "cladding",
            "label": "pillar",
            "companions": [],
            "packs": None,
            "total": 12150,
            "rate_overridden": False,
            "derivation": ["2 pillars x 10 ft x 3 faces x 1.2 ft = 72 sqft"],
        }
    )
    return Estimate(
        lines=[paint, stone],
        surfaces=[SurfaceMeasure(region_id="w", label="wall", net_px=1, area_sqft=254.2)],
        openings=[SurfaceMeasure(region_id="d", label="door", net_px=1, area_sqft=21)],
        category_subtotals={"paint": 7919, "cladding": 12150},
        lines_total=20069,
        wall_area_sqft=254.2,
        scaffolding=2034,
        contingency=1105,
        tax=4177,
        grand_total=1234567,
        range_pct=20,
        range_low=987700,
        range_high=1481500,
        confidence=Confidence.medium,
        provisional=False,
        scale=scale,
        extras=Extras(),
        assumptions=["Standard main door height of 7 ft.", "Pillars have three exposed faces."],
        fingerprint="abc",
    )


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def test_report_contains_totals_assumptions_and_disclaimer() -> None:
    data = ReportData(
        project_name="Sharma residence",
        created_at=datetime(2026, 10, 25, tzinfo=UTC),
        estimate=sample_estimate(),
        estimate_version=3,
        design_name="Stone and beige",
        parts=[
            ReportPart("Main wall", "Exterior emulsion paint", "#e8dcc4"),
            ReportPart("Pillar", "Natural stone cladding"),
        ],
        original_jpeg=_jpeg((200, 200, 200)),
        redesign_jpeg=_jpeg((150, 110, 80)),
        photo_warnings=["The photo is taken at an angle, so sizes may be less accurate."],
        render_notes=["The railing may look slightly different."],
    )
    pdf = build_report_pdf(data)
    assert pdf.startswith(b"%PDF")
    text = _text(pdf)
    for expected in (
        "Renovation plan: Sharma residence",
        "Estimate version 3",
        "25 October 2026",
        "Materials for each part",
        "Quantities and costs",
        "How the quantities were calculated",
        "Paint 4.85 L",
        "Primer",
        "Grand total",
        "Rs. 12,34,567",
        "Rs. 9,88,000",  # range rounded like the app's "About" figure
        "Rs. 14,82,000",
        "Stone cladding",
        "Scaffolding",
        "Contingency",
        "Assumptions",
        "Pillars have three exposed faces.",
        "Accuracy notes",
        "taken at an angle",
        "railing may look",
        "Price changed by you",
        "not a quotation",
    ):
        assert expected in text, expected
    assert DISCLAIMER.split(".")[0] in text.replace("\n", " ")


def test_report_without_images_or_lines() -> None:
    est = sample_estimate().model_copy(
        update={"lines": [], "category_subtotals": {}, "openings": [], "provisional": True}
    )
    pdf = build_report_pdf(
        ReportData(
            project_name="Empty",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            estimate=est,
            estimate_version=1,
            design_name="Design 1",
            parts=[],
        )
    )
    text = _text(pdf)
    assert "No materials chosen" in text and "image not available" in text
    assert "rough estimate" in text


def test_format_inr_uses_indian_grouping() -> None:
    assert format_inr(41086) == "Rs. 41,086"
    assert format_inr(999) == "Rs. 999"
    assert format_inr(1234567.4) == "Rs. 12,34,567"
    assert format_inr(123456789) == "Rs. 12,34,56,789"
    assert format_inr(-1500, "INR") == "-INR 1,500"


def test_report_groups_parts_and_replaces_rupee_glyph() -> None:
    est = sample_estimate()
    line = est.lines[0].model_copy(update={"derivation": ["Material: 25 kg × ₹38 = ₹950"]})
    data = ReportData(
        project_name="Glyph check",
        created_at=datetime(2026, 10, 25, tzinfo=UTC),
        estimate=est.model_copy(
            update={"lines": [line, *est.lines[1:]], "assumptions": ["Scaffolding ₹8 per sq ft."]}
        ),
        estimate_version=1,
        design_name="Design 1",
        parts=[ReportPart("Main wall", "Textured wall finish", "#CDBFA6")] * 11
        + [ReportPart("Pillar", "Natural stone cladding")] * 6,
        original_jpeg=None,
        redesign_jpeg=None,
    )
    text = _text(build_report_pdf(data))
    assert "Main wall (11 parts)" in text
    assert "Pillar (6 parts)" in text
    assert "Main wall\n" not in text.split("Quantities")[0]
    assert "Rs. 38" in text and "Rs. 950" in text and "Rs. 8 per sq ft" in text
    assert "₹" not in text and "■" not in text
