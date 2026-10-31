"""ReportLab PDF: before/after, materials, quantities, costs, range, assumptions, accuracy."""

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

from app.domain.models import FRIENDLY_LABELS, Estimate, LineItem
from app.reports.colours import describe_colour


def escape(text: str) -> str:
    """XML-escape for Paragraph markup. Helvetica has no rupee glyph, so "₹" becomes "Rs. "."""
    return _xml_escape(text.replace("₹", "Rs. "))


DISCLAIMER = (
    "This is an advisory planning figure, not a quotation. Quantities are measured from a "
    "single photo and rates are indicative; please get quotes from contractors and confirm "
    "measurements on site before buying materials or starting work."
)

CATEGORY_NAMES = {
    "paint": "Paint",
    "texture": "Texture finish",
    "cladding": "Stone cladding",
    "tiles": "Tiles",
    "panel": "Panels",
    "railing": "Railings",
    "gate": "Gates",
}

CONFIDENCE_TEXT = {
    "high": "High: based on a measurement you entered.",
    "medium": "Medium: based on a standard-size reference in the photo (such as the main door).",
    "low": "Low: based on the number of floors only; enter one measurement for a better figure.",
}

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#52606d")
LINE = colors.HexColor("#d9e2ec")
SHADE = colors.HexColor("#f0f4f8")
ACCENT = colors.HexColor("#2f6f4f")


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
    """Same rounding as the app's "About ₹36,000": nearest 1,000 from 10,000 up, else 100
    (halves round up, like JavaScript's Math.round)."""
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
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13, textColor=INK)
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=20, leading=24, textColor=INK, alignment=0
        ),
        "subtitle": ParagraphStyle("subtitle", parent=body, textColor=MUTED, fontSize=10),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=13,
            leading=16,
            textColor=ACCENT,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": body,
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11),
        "cell_r": ParagraphStyle(
            "cell_r", parent=body, fontSize=8.5, leading=11, alignment=TA_RIGHT
        ),
        "total": ParagraphStyle(
            "total", parent=body, fontSize=11, leading=14, fontName="Helvetica-Bold"
        ),
    }


def _image(data: bytes | None, max_w: float, max_h: float) -> Image | Paragraph:
    if not data:
        return Paragraph("(image not available)", _styles()["small"])
    with PILImage.open(io.BytesIO(data)) as im:
        w, h = im.size
    ratio = min(max_w / w, max_h / h)
    return Image(io.BytesIO(data), width=w * ratio, height=h * ratio)


def _table(rows: list[list], widths: list[float], header: bool = True, zebra: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), SHADE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ]
    if zebra:
        for i in range(2 if header else 1, len(rows), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafcfe")))
    table.setStyle(TableStyle(style))
    return table


def _footer(canvas, doc) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "Advisory planning figure, not a quotation.")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_report_pdf(data: ReportData) -> bytes:
    s = _styles()
    est = data.estimate
    cur = data.currency
    money = lambda v: format_inr(v, cur)  # noqa: E731
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Renovation plan - {data.project_name}",
        author="Renovation Planner",
    )
    width = A4[0] - 36 * mm
    story: list = []

    # -- title
    story.append(Paragraph(f"Renovation plan: {escape(data.project_name)}", s["title"]))
    story.append(
        Paragraph(
            f"{escape(data.design_name)} &middot; Estimate version {data.estimate_version} "
            f"&middot; {data.created_at:%d %B %Y}",
            s["subtitle"],
        )
    )
    story.append(Spacer(1, 6 * mm))

    # -- before / after
    half = (width - 6 * mm) / 2
    images = Table(
        [
            [
                Paragraph("<b>Your house today</b>", s["body"]),
                Paragraph("<b>Your new look</b>", s["body"]),
            ],
            [_image(data.original_jpeg, half, 75 * mm), _image(data.redesign_jpeg, half, 75 * mm)],
        ],
        colWidths=[half + 3 * mm, half + 3 * mm],
    )
    images.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    )
    story.append(images)
    story.append(
        Paragraph(
            "The new look is an illustration. All sizes and costs are measured on the "
            "original photo.",
            s["small"],
        )
    )

    # -- materials per part
    story.append(Paragraph("Materials for each part", s["h2"]))
    rows = [["Part of the house", "Material", "Colour"]]
    grouped: dict[tuple[str, str, str | None], int] = {}
    for p in data.parts:
        key = (p.part, p.material, p.color)
        grouped[key] = grouped.get(key, 0) + 1
    for (part, material, color), count in grouped.items():
        label = part if count == 1 else f"{part} ({count} parts)"
        rows.append(
            [
                Paragraph(escape(label), s["cell"]),
                Paragraph(escape(material), s["cell"]),
                Paragraph(escape(describe_colour(color)), s["cell"]),
            ]
        )
    story.append(_table(rows, [width * 0.35, width * 0.45, width * 0.2]))

    # -- quantities and costs
    story.append(Paragraph("Quantities and costs", s["h2"]))
    rows = [["Part", "Material", "Measured", "To buy", "Material", "Labour", "Total"]]
    for line in est.lines:
        buy = buy_text(line)
        material_cost = line.material_cost + sum(c.cost for c in line.companions)
        rate_flag = " *" if line.rate_overridden else ""
        rows.append(
            [
                Paragraph(escape(FRIENDLY_LABELS.get(line.label, line.label)), s["cell"]),
                Paragraph(escape(line.material_name) + rate_flag, s["cell"]),
                f"{_qty(line.measured_quantity)} {line.measured_unit}",
                Paragraph(escape(buy), s["cell"]),
                Paragraph(money(material_cost), s["cell_r"]),
                Paragraph(money(line.labour_cost), s["cell_r"]),
                Paragraph(money(line.total), s["cell_r"]),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "No materials chosen", "", "", "", "", ""])
    story.append(
        _table(
            rows,
            [width * w for w in (0.14, 0.2, 0.12, 0.16, 0.13, 0.12, 0.13)],
        )
    )
    if any(line.rate_overridden for line in est.lines):
        story.append(Paragraph("* Price changed by you for this project.", s["small"]))

    # -- derivations
    derivations = [line for line in est.lines if line.derivation]
    if derivations:
        story.append(Paragraph("How the quantities were calculated", s["h2"]))
        for line in derivations:
            title = f"{FRIENDLY_LABELS.get(line.label, line.label)}: {line.material_name}"
            items = [
                ListItem(Paragraph(escape(step), s["small"]), leftIndent=10)
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
                        leftIndent=10,
                    )
                )
            story.append(
                KeepTogether(
                    [
                        Paragraph(f"<b>{escape(title)}</b>", s["cell"]),
                        ListFlowable(items, bulletType="bullet", start="-", leftIndent=8),
                        Spacer(1, 2 * mm),
                    ]
                )
            )

    # -- subtotals, extras, totals
    story.append(Paragraph("Cost summary", s["h2"]))
    rows = [["Category", "Subtotal"]]
    for cat, value in est.category_subtotals.items():
        rows.append([CATEGORY_NAMES.get(cat, cat.title()), Paragraph(money(value), s["cell_r"])])
    rows.append(
        [
            Paragraph("<b>Materials and labour</b>", s["cell"]),
            Paragraph(f"<b>{money(est.lines_total)}</b>", s["cell_r"]),
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
            f"Contingency ({_qty(ex.contingency_pct)}%)",
            Paragraph(money(est.contingency), s["cell_r"]),
        ]
    )
    rows.append([f"Tax / GST ({_qty(ex.tax_pct)}%)", Paragraph(money(est.tax), s["cell_r"])])
    rows.append(
        [
            Paragraph("Grand total", s["total"]),
            Paragraph(f"<b>{money(est.grand_total)}</b>", s["cell_r"]),
        ]
    )
    summary = _table(rows, [width * 0.7, width * 0.3], zebra=False)
    summary.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 1.0, INK)]))
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

    # -- assumptions and accuracy
    story.append(Paragraph("Assumptions", s["h2"]))
    assumptions = est.assumptions or ["Standard Indian low-rise construction sizes are assumed."]
    story.append(
        ListFlowable(
            [ListItem(Paragraph(escape(a), s["body"]), leftIndent=10) for a in assumptions],
            bulletType="bullet",
            start="-",
            leftIndent=8,
        )
    )
    story.append(Paragraph("Accuracy notes", s["h2"]))
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
            [ListItem(Paragraph(escape(n), s["body"]), leftIndent=10) for n in notes],
            bulletType="bullet",
            start="-",
            leftIndent=8,
        )
    )
    story.append(Spacer(1, 5 * mm))
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
