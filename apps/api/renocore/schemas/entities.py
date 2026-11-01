"""Core domain models shared by every module (the contracts between modules).

Coordinates are pixels in the *working image* (long side <= 2048 px), origin top-left,
x to the right, y down. Lengths are feet, areas square feet, money INR.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- labels

Label = Literal[
    "wall",
    "window",
    "door",
    "balcony",
    "pillar",
    "parapet",
    "railing",
    "gate",
    "roof_edge",
    "canopy",
    "louvers",
    "compound_wall",
]
LABELS: tuple[Label, ...] = (
    "wall",
    "window",
    "door",
    "balcony",
    "pillar",
    "parapet",
    "railing",
    "gate",
    "roof_edge",
    "canopy",
    "louvers",
    "compound_wall",
)
OPENING_LABELS: frozenset[str] = frozenset({"window", "door"})

# Pixel ownership priority when regions overlap: earlier wins.
LABEL_PRIORITY: tuple[Label, ...] = (
    "window",
    "door",
    "railing",
    "gate",
    "canopy",
    "louvers",
    "balcony",
    "pillar",
    "parapet",
    "roof_edge",
    "compound_wall",
    "wall",
)

FRIENDLY_LABELS: dict[str, str] = {
    "wall": "Main wall",
    "window": "Window",
    "door": "Door",
    "balcony": "Balcony",
    "pillar": "Pillar",
    "parapet": "Top wall edge (parapet)",
    "railing": "Railing",
    "gate": "Gate",
    "roof_edge": "Roof edge",
    "canopy": "Canopy / Chhajja",
    "louvers": "Louvers / CNC Jali",
    "compound_wall": "Compound / Boundary Wall",
}

Point = tuple[float, float]


class BoxPx(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class BoxFraction(BaseModel):
    """Box as fractions (0-1) of image width/height, as returned by Jev."""

    top: float
    bottom: float
    left: float
    right: float


# ---------------------------------------------------------------- regions

RegionSource = Literal["gemini", "jev_box", "user"]


class Region(BaseModel):
    id: str
    label: Label
    polygon: list[Point] = Field(min_length=3)
    source: RegionSource = "gemini"
    label_confidence: float | None = None
    needs_check: bool = False  # "Please check" tag (low Jev confidence)
    checked: bool = False  # user confirmed a needs_check region
    proposed: bool = False  # Jev box suggestion not yet accepted by the user


class SegmentCandidate(BaseModel):
    """A surface found by Gemini (C2) after mask -> polygon conversion."""

    label_hint: str
    polygon: list[Point] = Field(min_length=3)
    box: BoxPx


# ---------------------------------------------------------------- photo check

Severity = Literal["hard", "warn"]


class PhotoIssue(BaseModel):
    code: str  # e.g. "blurry", "too_small", "angled_view", "not_residential"
    severity: Severity
    message: str  # plain-language, user-facing


class PhotoCheckResult(BaseModel):
    """Deterministic code checks."""

    width: int
    height: int
    sharpness: float
    brightness: float
    issues: list[PhotoIssue] = []


class ChoiceResult(BaseModel):
    choice: str
    confidence: float | None = None
    probabilities: dict[str, float] = {}


class BoxResult(BaseModel):
    box: BoxFraction
    confidence: float | None = None


class WholePhotoAnswers(BaseModel):
    """Jev call C1."""

    is_residential_exterior: float
    building_type: ChoiceResult
    view_angle: ChoiceResult
    facade_obstructed: float
    usability: float  # probability-weighted level index 0..4
    door_visible: float
    main_door: BoxResult | None = None
    floors: ChoiceResult
    railing_visible: float
    railing: BoxResult | None = None
    gate_visible: float
    gate: BoxResult | None = None


PhotoVerdictStatus = Literal["pass", "warn", "reject"]


class PhotoVerdict(BaseModel):
    status: PhotoVerdictStatus
    issues: list[PhotoIssue] = []


class LabelAnswer(BaseModel):
    """Jev call C3 result for one region."""

    label: Label | Literal["not_building"]
    confidence: float
    probabilities: dict[str, float] = {}


# ---------------------------------------------------------------- scale


class ScaleMethod(StrEnum):
    user_measurement = "user_measurement"
    door = "door"
    windows = "windows"
    floors = "floors"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ReferenceLine(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    length_ft: float = Field(gt=0)


class Measurements(BaseModel):
    facade_width_ft: float | None = Field(default=None, gt=0)
    facade_height_ft: float | None = Field(default=None, gt=0)
    floors: int | None = Field(default=None, ge=1, le=10)
    reference_line: ReferenceLine | None = None


class ScaleInputs(BaseModel):
    regions: list[Region]  # approved regions
    measurements: Measurements = Measurements()
    door_visible: float | None = None  # Jev C1
    door_box_px: BoxPx | None = None  # Jev C1 main_door converted to px
    floors_answer: int | None = None  # Jev C1 floors (4 for "4 or more")
    photo_warned: bool = False  # user continued past a G1 warning


class ScaleResult(BaseModel):
    ft_per_px: float
    method: ScaleMethod
    confidence: Confidence
    facade_width_ft: float | None = None
    reference_box_px: BoxPx | None = None  # door / window used, for display
    explanation: str  # plain-language sentence for the size check screen
    needs_measurement: bool = False  # True when confidence is low


# ---------------------------------------------------------------- materials

MaterialCategory = Literal["paint", "texture", "cladding", "tiles", "panel", "railing", "gate"]
PricingUnit = Literal["litre", "kg", "piece", "sqft", "sheet", "rft"]
MeasureBasis = Literal["area", "length"]


class Companion(BaseModel):
    """Auto-added consumable, e.g. primer for paint, adhesive for tiles."""

    kind: Literal["primer", "adhesive"]
    name: str
    unit: Literal["litre", "kg"]
    quantity_per_sqft: float  # e.g. primer 1/120 L per sqft per coat
    pack_size: float
    rate: float  # INR per unit


class Material(BaseModel):
    id: str
    name: str
    category: MaterialCategory
    description: str
    applicable_labels: list[Label]
    pricing_unit: PricingUnit
    measure_basis: MeasureBasis
    coverage_sqft_per_unit: float | None = None  # paint: sqft per litre per coat; texture: sqft/kg
    coats: int = 1
    piece_area_sqft: float | None = None  # tile piece or panel sheet area
    pieces_per_box: int | None = None
    pack_size: float | None = None  # litres per can, kg per bag
    pack_sizes: list[float] = []  # other sizes also sold; the cheapest mix is bought
    wastage_pct: float
    material_rate: float  # INR per pricing unit
    labour_rate: float  # INR per measured sqft or rft
    companions: list[Companion] = []
    colorable: bool = False
    default_color: str | None = None  # hex
    swatch: str  # path relative to seed/swatches
    weather_resistance: Literal["low", "medium", "high"]
    durability: str  # plain text, e.g. "8-10 years"
    maintenance: str  # plain text


class PackCount(BaseModel):
    size: float
    count: int


class Assignment(BaseModel):
    region_id: str
    material_id: str
    color: str | None = None  # hex, for colorable materials


class RateOverride(BaseModel):
    material_id: str
    material_rate: float | None = Field(default=None, ge=0)
    labour_rate: float | None = Field(default=None, ge=0)


class Extras(BaseModel):
    scaffolding_rate_per_sqft: float = Field(default=8.0, ge=0)
    scaffolding_min_floors: int = 2
    contingency_pct: float = Field(default=5.0, ge=0)
    tax_pct: float = Field(default=18.0, ge=0)


class MaterialAdvice(BaseModel):
    """Jev call C4 result for one region."""

    region_id: str
    recommended: list[str] = []  # material ids
    not_ideal: dict[str, str] = {}  # material id -> plain-language reason
    exposed: float | None = None
    probabilities: dict[str, float] = {}


# ---------------------------------------------------------------- estimate


class EstimateInputs(BaseModel):
    regions: list[Region]  # approved regions (all labels, incl. openings)
    scale: ScaleResult
    assignments: list[Assignment]
    materials: dict[str, Material]  # catalogue by id
    overrides: list[RateOverride] = []
    extras: Extras = Extras()
    floors: int = 1
    scale_confirmed: bool = False


class SurfaceMeasure(BaseModel):
    region_id: str
    label: Label
    net_px: float
    fs: float = 1.0
    area_sqft: float
    length_ft: float | None = None


class CompanionLine(BaseModel):
    name: str
    quantity: float
    unit: str
    packs: int
    purchase_quantity: float
    rate: float
    cost: float


class LineItem(BaseModel):
    """One material applied to one surface type (regions of the same label grouped)."""

    material_id: str
    material_name: str
    category: MaterialCategory
    label: Label
    region_ids: list[str]
    measured_quantity: float
    measured_unit: Literal["sqft", "rft"]
    wastage_pct: float
    with_wastage: float
    required_quantity: float  # in purchase units before pack rounding
    purchase_quantity: float  # after pack rounding
    purchase_unit: str
    packs: int | None = None
    pack_size: float | None = None  # set when every pack is the same size
    pack_mix: list[PackCount] = []  # e.g. 1 × 4 L + 1 × 1 L, largest first
    material_rate: float
    material_cost: float
    companions: list[CompanionLine] = []
    labour_rate: float
    labour_cost: float
    total: float
    rate_overridden: bool = False
    derivation: list[str] = []  # human-readable calculation steps


class Estimate(BaseModel):
    lines: list[LineItem]
    surfaces: list[SurfaceMeasure]
    openings: list[SurfaceMeasure]
    category_subtotals: dict[str, float]
    lines_total: float
    wall_area_sqft: float
    scaffolding: float
    contingency: float
    tax: float
    grand_total: float
    range_pct: float
    range_low: float
    range_high: float
    confidence: Confidence
    provisional: bool  # scale not yet confirmed by the user
    scale: ScaleResult
    extras: Extras
    assumptions: list[str]
    fingerprint: str


# ---------------------------------------------------------------- render


class Zone(BaseModel):
    region_ids: list[str]
    material_id: str
    color_name: str  # e.g. "red"
    rgb: tuple[int, int, int]


class QAResult(BaseModel):
    """Jev call C6."""

    openings_preserved: float
    structure_preserved: float
    zones: dict[str, float]  # zone color name -> probability material is visible
    passed: bool
    failed_checks: list[str] = []  # plain-language, also fed back into the redo prompt
