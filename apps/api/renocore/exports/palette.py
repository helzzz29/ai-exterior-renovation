"""Plain names for paint colours, so the report says "Warm beige" rather than "#e9dcc0".

The first eight are the swatches offered in the app (same names as apps/web COLOUR_PRESETS);
the rest fill the gaps so any picked colour gets a sensible nearest name.
"""

NAMED_COLOURS: dict[str, str] = {
    "#f5f0e6": "Off-white",
    "#e9dcc0": "Warm beige",
    "#d6e0d8": "Pale sage",
    "#cdb79e": "Sandstone",
    "#c97b5a": "Terracotta",
    "#9ca3af": "Light grey",
    "#5b6270": "Slate grey",
    "#1f2937": "Charcoal",
    "#ffffff": "White",
    "#fff8dc": "Cream",
    "#f3e5ab": "Light yellow",
    "#e1ad01": "Mustard yellow",
    "#ffcba4": "Peach",
    "#f4a6a0": "Salmon pink",
    "#e8a0b4": "Pink",
    "#a0442c": "Brick red",
    "#d32f2f": "Red",
    "#e67e22": "Orange",
    "#f1c40f": "Yellow",
    "#6c3483": "Purple",
    "#7a1f2b": "Maroon",
    "#d2b48c": "Tan",
    "#8b5a2b": "Brown",
    "#4e3524": "Dark brown",
    "#808a4a": "Olive green",
    "#4c8c4a": "Green",
    "#bfe3c8": "Mint green",
    "#2a7f7f": "Teal",
    "#a7c7e7": "Sky blue",
    "#3b6ea5": "Blue",
    "#1f3a5f": "Navy blue",
    "#c8b8db": "Lavender",
    "#c0c0c0": "Silver grey",
    "#808080": "Grey",
    "#444444": "Dark grey",
    "#111111": "Black",
}


def _rgb(hex_colour: str) -> tuple[int, int, int] | None:
    h = hex_colour.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """'Redmean' distance: cheap and close to how different two colours look."""
    rmean = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return (2 + rmean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rmean) / 256) * db * db


def colour_name(hex_colour: str) -> str | None:
    """Nearest plain name, or None for something that isn't a colour code."""
    rgb = _rgb(hex_colour)
    if rgb is None:
        return None
    return min(NAMED_COLOURS.items(), key=lambda kv: _distance(rgb, _rgb(kv[0])))[1]  # type: ignore[arg-type]


def describe_colour(hex_colour: str | None) -> str:
    """'Warm beige (E9DCC0)': a name to read, plus the code for the paint shop."""
    if not hex_colour:
        return "-"
    name = colour_name(hex_colour)
    code = hex_colour.strip().lstrip("#").upper()
    return f"{name} ({code})" if name else hex_colour
