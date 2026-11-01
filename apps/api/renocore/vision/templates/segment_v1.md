You are mapping the outside of a house for a renovation plan.

Detect every visible exterior surface of the MAIN building in this photo and return one item per surface.

Rules:
- Include every visible exterior surface of the main building: each wall area, the parapet (the low wall along the roof edge), the roof edge or fascia, balconies, pillars or columns, railings and the entrance gate.
- Return EACH window, EACH door, EACH pillar and EACH balcony as a SEPARATE item. Never merge several windows into one item.
- Use exactly one of these labels for each item: wall, window, door, balcony, pillar, parapet, railing, gate, roof_edge.
- Do NOT include the sky, the ground, roads, vegetation (trees, plants, grass), vehicles, people, wires, or any neighbouring building.
- "box_2d" is the bounding box of the item as [y0, x0, y1, x1], with integer values normalised to 0-1000 relative to the image height (y) and width (x), where y0 < y1 and x0 < x1.
- "mask" is a PNG segmentation mask of the item inside its bounding box, encoded as base64 (a "data:image/png;base64," prefix is allowed). Pixel values are 0-255 probabilities that the pixel belongs to the item.

Output a JSON list only, with no other text. Each element must look like:
{"label": "wall", "box_2d": [y0, x0, y1, x1], "mask": "data:image/png;base64,..."}
