"""ReportLab PDF: before/after, materials, quantities, costs, range, assumptions, accuracy.

Contractor-grade BOQ and architectural report with high-clarity typography,
aligned tables, metric tiles, and clean visual structure.
"""

import io
import math
from dataclasses import dataclass, field
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from renocore.exports.palette import describe_colour
from renocore.schemas.entities import FRIENDLY_LABELS, Estimate, LineItem


def escape(text: str) -> str:
    """XML-escape for Paragraph markup. Helvetica has no rupee glyph, so "₹" becomes "Rs. "."""
    return _xml_escape(text.replace("₹", "Rs. "))


DISCLAIMER = (
    "This is an advisory planning figure, not a quotation. Quantities are measured from a "
    "single photo and rates are indicative; please get quotes from contractors and confirm "
    "measurements on site before buying materials or starting work."
)

CATEGORY_NAMES = {
    "paint": "Paint & Primer",
    "texture": "Texture finish",
    "cladding": "Stone cladding",
    "tiles": "Tiles & Panels",
    "panel": "Architectural Panels",
    "railing": "Railings & Glass",
    "gate": "Gates & Metalwork",
}

CONFIDENCE_TEXT = {
    "high": "High: based on a verified on-site measurement you entered.",
    "medium": "Medium: calibrated using a standard architectural reference (such as the main door).",
    "low": "Low: calibrated from floor count only; confirm one measurement for greater precision.",
}

# Architectural Executive Palette (Royal Blue, Slate, Crisp Whites)
PRIMARY = colors.HexColor("#1d4ed8")       # Royal architectural blue
ACCENT = colors.HexColor("#2563eb")        # Sapphire blue accent
ACCENT_LIGHT = colors.HexColor("#eff6ff")  # Sky/ice blue tint
INK = colors.HexColor("#0f172a")           # Slate 900
MUTED = colors.HexColor("#64748b")         # Slate 500
LINE = colors.HexColor("#e2e8f0")          # Slate 200 border
SHADE = colors.HexColor("#f8fafc")         # Slate 50 background
SHADE_ALT = colors.HexColor("#f1f5f9")     # Slate 100 zebra
BAND = colors.HexColor("#1e3a8a")          # Deep navy/royal blue top banner


@dataclass
class ReportPart:
    part: str  # plain-language name of the part, e.g. "Main wall"
    material: str
    color: str | None = None


@dataclass
class ReportData:
    project_name: str
    created_at: datetime
    estimate: Estimate
    estimate_version: int
    design_name: str
    parts: list[ReportPart]
    original_jpeg: bytes | None = None
    redesign_jpeg: bytes | None = None
    photo_warnings: list[str] = field(default_factory=list)
    render_notes: list[str] = field(default_factory=list)  # design checks that didn't pass
    currency: str = "Rs."


def format_inr(amount: float, prefix: str = "Rs.") -> str:
    """Indian digit grouping: 1,23,45,678."""
    negative = amount < 0
    whole = str(int(round(abs(amount))))
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{'-' if negative else ''}{prefix} {whole}"


def round_friendly(value: float) -> float:
    """Same rounding as the app's 'About ₹36,000': nearest 1,000 from 10,000 up, else 100."""
    step = 1000 if abs(value) >= 10000 else 100
    return math.floor(value / step + 0.5) * step


def buy_text(line: LineItem) -> str:
    """'10 L (1 x 10)' or, for a mix of sizes, '5 L (1 x 4 + 1 x 1)'."""
    buy = f"{_qty(line.purchase_quantity)} {line.purchase_unit}"
    if len(line.pack_mix) > 1:
        buy += " (" + " + ".join(f"{p.count} x {_qty(p.size)}" for p in line.pack_mix) + ")"
    elif line.packs:
        buy += f" ({line.packs} x {_qty(line.pack_size or 0)})"
    return buy


def _qty(value: float) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=9, leading=13, textColor=INK)
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=18, leading=22, textColor=INK, alignment=0
        ),
        "subtitle": ParagraphStyle("subtitle", parent=body, textColor=MUTED, fontSize=9.5),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=11.5,
            leading=15,
            textColor=PRIMARY,
            fontName="Helvetica-Bold",
            spaceBefore=8,
            spaceAfter=3,
        ),
        "band_brand": ParagraphStyle(
            "band_brand",
            parent=base["Title"],
            fontSize=12,
            leading=14,
            textColor=colors.HexColor("#a7f3d0"),
            fontName="Helvetica-Bold",
        ),
        "band_title": ParagraphStyle(
            "band_title",
            parent=base["Title"],
            fontSize=16,
            leading=20,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=0,
        ),
        "band_meta": ParagraphStyle(
            "band_meta",
            parent=body,
            textColor=colors.HexColor("#ecfdf5"),
            fontSize=8.5,
            leading=12,
            alignment=TA_RIGHT,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            parent=body,
            textColor=MUTED,
            fontSize=7.5,
            leading=9.5,
            fontName="Helvetica-Bold",
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=PRIMARY,
        ),
        "kpi_sub": ParagraphStyle(
            "kpi_sub",
            parent=body,
            textColor=MUTED,
            fontSize=7,
            leading=9,
        ),
        "body": body,
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=11, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=10.5),
        "cell_bold": ParagraphStyle(
            "cell_bold", parent=body, fontSize=8, leading=10.5, fontName="Helvetica-Bold"
        ),
        "cell_r": ParagraphStyle(
            "cell_r", parent=body, fontSize=8, leading=10.5, alignment=TA_RIGHT
        ),
        "cell_r_bold": ParagraphStyle(
            "cell_r_bold",
            parent=body,
            fontSize=8,
            leading=10.5,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "total": ParagraphStyle(
            "total", parent=body, fontSize=10, leading=13, fontName="Helvetica-Bold", textColor=PRIMARY
        ),
        "img_label": ParagraphStyle(
            "img_label",
            parent=body,
            fontSize=8.5,
            leading=11,
            fontName="Helvetica-Bold",
            textColor=PRIMARY,
        ),
    }


def _image(data: bytes | None, max_w: float, max_h: float) -> Image | Paragraph:
    if not data:
        return Paragraph("(image not available)", _styles()["small"])
    with PILImage.open(io.BytesIO(data)) as im:
        w, h = im.size
    ratio = min(max_w / w, max_h / h)
    return Image(io.BytesIO(data), width=w * ratio, height=h * ratio)


def _table(
    rows: list[list],
    widths: list[float],
    header: bool = True,
    zebra: bool = True,
    header_bg: colors.Color | None = None,
) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        bg = header_bg or PRIMARY
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), bg),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ]
    if zebra:
        for i in range(2 if header else 1, len(rows), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), SHADE))
    table.setStyle(TableStyle(style))
    return table


def _footer(canvas, doc) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "Advisory planning figure, not a quotation. Generated by Renova AI.")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _heading(text: str, number: int, width: float, s: dict[str, ParagraphStyle]) -> Table:
    """Section heading: an emerald number badge, clean title, and subtle bottom rule."""
    num_badge = Table(
        [[Paragraph(f"<b>{number}</b>", ParagraphStyle("badge", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, alignment=1))]],
        colWidths=[5.5 * mm],
    )
    num_badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    t = Table(
        [[num_badge, Paragraph(escape(text), s["h2"])]],
        colWidths=[7 * mm, width - 7 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return t


def _hex_or_none(color: str | None) -> colors.Color | None:
    try:
        return colors.HexColor(color) if color else None
    except (ValueError, TypeError):
        return None


def build_report_pdf(data: ReportData) -> bytes:
    s = _styles()
    est = data.estimate
    cur = data.currency
    money = lambda v: format_inr(v, cur)  # noqa: E731
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"Renovation plan - {data.project_name}",
        author="Renova AI",
    )
    width = A4[0] - 32 * mm
    story: list = []

    # -- 1. Executive Architectural Title Band
    band = Table(
        [
            [
                Paragraph(
                    f"<b>RENOVA AI</b> &middot; <font size=8.5 color='#bfdbfe'>EXTERIOR DESIGN &amp; BOQ REPORT</font><br/>"
                    f"<font size=14 color='white'><b>Renovation plan: {escape(data.project_name)}</b></font>",
                    s["band_title"],
                ),
                Paragraph(
                    f"<b>Design:</b> {escape(data.design_name)}<br/>"
                    f"<b>Estimate version {data.estimate_version}</b><br/>"
                    f"{data.created_at:%d %B %Y}",
                    s["band_meta"],
                ),
            ]
        ],
        colWidths=[width * 0.65, width * 0.35],
    )
    band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BAND),
                ("LINEBELOW", (0, -1), (-1, -1), 2.5, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(band)
    story.append(Spacer(1, 3.5 * mm))

    # -- 2. Key Metrics Summary (3 Highlight Tiles)
    def kpi(label: str, value: str, sub: str = "") -> list:
        items = [Paragraph(label, s["kpi_label"]), Paragraph(value, s["kpi_value"])]
        if sub:
            items.append(Paragraph(sub, s["kpi_sub"]))
        return items

    cards = [
        kpi("TOTAL BUDGET", money(est.grand_total), "Materials, labour, scaffolding & tax"),
        kpi(
            "LIKELY RANGE",
            f"{money(round_friendly(est.range_low))} - {money(round_friendly(est.range_high))}",
            f"Expected ±{_qty(est.range_pct)}% contractor range",
        ),
        kpi("AREA MEASURED", f"{_qty(est.wall_area_sqft)} sqft", "Net exterior facade surface"),
    ]
    glance = Table([cards], colWidths=[width * 0.35, width * 0.38, width * 0.27])
    glance.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SHADE),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LINEAFTER", (0, 0), (1, 0), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(glance)
    story.append(Spacer(1, 3.5 * mm))

    # -- 3. Visual Before & After Elevation Showcase
    half = (width - 4 * mm) / 2
    images = Table(
        [
            [
                Paragraph("<b>BEFORE: Existing House Exterior</b>", s["img_label"]),
                Paragraph("<b>AFTER TRANSITION: Proposed Architectural Transformation</b>", s["img_label"]),
            ],
            [_image(data.original_jpeg, half, 72 * mm), _image(data.redesign_jpeg, half, 72 * mm)],
        ],
        colWidths=[half + 2 * mm, half + 2 * mm],
    )
    images.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ]
        )
    )
    story.append(images)
    story.append(
        Paragraph(
            "The new look is an illustration. All sizes and costs are measured on the original photo.",
            s["small"],
        )
    )

    # -- 4. Material Schedule for Each Part
    story.append(_heading("Materials for each part", 1, width, s))
    mat_header = [
        "",
        Paragraph("<b>Part of the house</b>", ParagraphStyle("th1", parent=s["cell_bold"], textColor=colors.white)),
        Paragraph("<b>Material</b>", ParagraphStyle("th2", parent=s["cell_bold"], textColor=colors.white)),
        Paragraph("<b>Colour</b>", ParagraphStyle("th3", parent=s["cell_bold"], textColor=colors.white)),
    ]
    rows = [mat_header]
    chips: list[tuple[int, colors.Color]] = []
    grouped: dict[tuple[str, str, str | None], int] = {}
    for p in data.parts:
        key = (p.part, p.material, p.color)
        grouped[key] = grouped.get(key, 0) + 1
    for (part, material, color), count in grouped.items():
        label = part if count == 1 else f"{part} ({count} parts)"
        chip = _hex_or_none(color)
        if chip is not None:
            chips.append((len(rows), chip))
        rows.append(
            [
                "",
                Paragraph(escape(label), s["cell_bold"]),
                Paragraph(escape(material), s["cell"]),
                Paragraph(escape(describe_colour(color)), s["cell"]),
            ]
        )
    materials = _table(rows, [width * 0.05, width * 0.33, width * 0.42, width * 0.2])
    chip_style = [("BACKGROUND", (0, i), (0, i), c) for i, c in chips] + [
        ("BOX", (0, i), (0, i), 0.5, colors.HexColor("#94a3b8")) for i, _ in chips
    ]
    if chip_style:
        materials.setStyle(TableStyle(chip_style))
    story.append(materials)

    # -- 5. Contractor Bill of Quantities (Quantities and Costs)
    story.append(_heading("Quantities and costs", 2, width, s))
    boq_header = [
        Paragraph("<b>Part</b>", ParagraphStyle("h_part", parent=s["cell_bold"], textColor=colors.white)),
        Paragraph("<b>Material</b>", ParagraphStyle("h_mat", parent=s["cell_bold"], textColor=colors.white)),
        Paragraph("<b>Measured</b>", ParagraphStyle("h_meas", parent=s["cell_bold"], textColor=colors.white)),
        Paragraph("<b>To buy</b>", ParagraphStyle("h_buy", parent=s["cell_bold"], textColor=colors.white)),
        Paragraph("<b>Material</b>", ParagraphStyle("h_mcost", parent=s["cell_r_bold"], textColor=colors.white)),
        Paragraph("<b>Labour</b>", ParagraphStyle("h_lcost", parent=s["cell_r_bold"], textColor=colors.white)),
        Paragraph("<b>Total</b>", ParagraphStyle("h_tot", parent=s["cell_r_bold"], textColor=colors.white)),
    ]
    rows = [boq_header]
    for line in est.lines:
        buy = buy_text(line)
        material_cost = line.material_cost + sum(c.cost for c in line.companions)
        rate_flag = " *" if line.rate_overridden else ""
        rows.append(
            [
                Paragraph(escape(FRIENDLY_LABELS.get(line.label, line.label)), s["cell_bold"]),
                Paragraph(escape(line.material_name) + rate_flag, s["cell"]),
                Paragraph(f"{_qty(line.measured_quantity)} {line.measured_unit}", s["cell"]),
                Paragraph(escape(buy), s["cell"]),
                Paragraph(money(material_cost), s["cell_r"]),
                Paragraph(money(line.labour_cost), s["cell_r"]),
                Paragraph(money(line.total), s["cell_r_bold"]),
            ]
        )
    if len(rows) == 1:
        rows.append([
            Paragraph("-", s["cell"]),
            Paragraph("No materials chosen", s["cell"]),
            Paragraph("", s["cell"]),
            Paragraph("", s["cell"]),
            Paragraph("", s["cell_r"]),
            Paragraph("", s["cell_r"]),
            Paragraph("", s["cell_r"]),
        ])
    story.append(
        _table(
            rows,
            [width * w for w in (0.15, 0.23, 0.12, 0.16, 0.11, 0.11, 0.12)],
        )
    )
    if any(line.rate_overridden for line in est.lines):
        story.append(Paragraph("* Price changed by you for this project.", s["small"]))

    # -- 6. Step-by-Step Quantity Derivations
    derivations = [line for line in est.lines if line.derivation]
    if derivations:
        story.append(_heading("How the quantities were calculated", 3, width, s))
        for line in derivations:
            title = f"{FRIENDLY_LABELS.get(line.label, line.label)}: {line.material_name}"
            items = [
                ListItem(Paragraph(escape(step), s["small"]), leftIndent=8)
                for step in line.derivation
            ]
            for c in line.companions:
                items.append(
                    ListItem(
                        Paragraph(
                            escape(
                                f"{c.name}: {_qty(c.quantity)} {c.unit} needed, buy "
                                f"{_qty(c.purchase_quantity)} {c.unit} = {money(c.cost)}"
                            ),
                            s["small"],
                        ),
                        leftIndent=8,
                    )
                )
            calc_box = Table(
                [
                    [Paragraph(f"<b>{escape(title)}</b>", s["cell_bold"])],
                    [ListFlowable(items, bulletType="bullet", start="-", leftIndent=6)],
                ],
                colWidths=[width],
            )
            calc_box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), SHADE),
                        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(KeepTogether([calc_box, Spacer(1, 1.5 * mm)]))

    # -- 7. Cost Summary & Totals
    story.append(_heading("Cost summary", 4, width, s))
    summary_header = [
        Paragraph("<b>Category</b>", ParagraphStyle("h_cat", parent=s["cell_bold"], textColor=colors.white)),
        Paragraph("<b>Subtotal</b>", ParagraphStyle("h_sub", parent=s["cell_r_bold"], textColor=colors.white)),
    ]
    rows = [summary_header]
    for cat, value in est.category_subtotals.items():
        rows.append([
            Paragraph(escape(CATEGORY_NAMES.get(cat, cat.title())), s["cell"]),
            Paragraph(money(value), s["cell_r"]),
        ])
    rows.append(
        [
            Paragraph("<b>Materials and labour</b>", s["cell_bold"]),
            Paragraph(f"<b>{money(est.lines_total)}</b>", s["cell_r_bold"]),
        ]
    )
    ex = est.extras
    rows.append(
        [
            Paragraph(
                f"Scaffolding ({money(ex.scaffolding_rate_per_sqft)} per sqft of wall, "
                f"{ex.scaffolding_min_floors}+ floors)",
                s["cell"],
            ),
            Paragraph(money(est.scaffolding), s["cell_r"]),
        ]
    )
    rows.append(
        [
            Paragraph(f"Contingency ({_qty(ex.contingency_pct)}%)", s["cell"]),
            Paragraph(money(est.contingency), s["cell_r"]),
        ]
    )
    rows.append([
        Paragraph(f"Tax / GST ({_qty(ex.tax_pct)}%)", s["cell"]),
        Paragraph(money(est.tax), s["cell_r"]),
    ])
    rows.append(
        [
            Paragraph("<b>Grand total</b>", s["total"]),
            Paragraph(f"<b>{money(est.grand_total)}</b>", s["total"]),
        ]
    )
    summary = _table(rows, [width * 0.7, width * 0.3], zebra=False)
    summary.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -1), (-1, -1), 1.2, PRIMARY),
                ("BACKGROUND", (0, -1), (-1, -1), ACCENT_LIGHT),
                ("TOPPADDING", (0, -1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ]
        )
    )
    story.append(summary)
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            f"Likely range: <b>{money(round_friendly(est.range_low))}</b> to "
            f"<b>{money(round_friendly(est.range_high))}</b> "
            f"(plus or minus {_qty(est.range_pct)}%).",
            s["body"],
        )
    )
    if est.provisional:
        story.append(
            Paragraph("This is a rough estimate: the size has not been confirmed.", s["body"])
        )

    # -- 8. Assumptions & Accuracy Notes
    story.append(_heading("Assumptions", 5, width, s))
    assumptions = est.assumptions or ["Standard Indian low-rise construction sizes are assumed."]
    story.append(
        ListFlowable(
            [ListItem(Paragraph(escape(a), s["body"]), leftIndent=8) for a in assumptions],
            bulletType="bullet",
            start="-",
            leftIndent=6,
        )
    )

    story.append(_heading("Accuracy notes", 6, width, s))
    notes = [
        f"Size reference: {est.scale.explanation}",
        f"Confidence: {CONFIDENCE_TEXT.get(str(est.confidence), str(est.confidence))}",
        f"Wall area measured: {_qty(est.wall_area_sqft)} sqft.",
    ]
    notes += [f"Photo: {w}" for w in data.photo_warnings]
    notes += [f"New look: {n}" for n in data.render_notes]
    if est.openings:
        area = sum(o.area_sqft for o in est.openings)
        notes.append(
            f"Windows and doors ({_qty(area)} sqft) are not painted or clad and are not priced."
        )
    story.append(
        ListFlowable(
            [ListItem(Paragraph(escape(n), s["body"]), leftIndent=8) for n in notes],
            bulletType="bullet",
            start="-",
            leftIndent=6,
        )
    )
    story.append(Spacer(1, 3.5 * mm))

    # -- 9. Official Advisory Disclaimer Callout
    disclaimer = Table(
        [[Paragraph(f"<b>Please note.</b> {escape(DISCLAIMER)}", s["body"])]], colWidths=[width]
    )
    disclaimer.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SHADE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(disclaimer)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
