You are mapping the outside of a house for a renovation plan.

Detect every visible exterior surface of the MAIN building in this photo and return one item per surface, each outlined by a polygon.

Rules:
- Include every visible exterior surface of the main building: wall faces, the parapet, the roof edge or fascia, balconies, pillars or columns, railings and the entrance gate.
- Return each separate wall face (each building block or storey face) as its own wall entry.
- Return EACH window, EACH door, EACH pillar and EACH balcony as a SEPARATE item. Never merge several windows into one item.
- Use exactly one of these labels for each item: wall, window, door, balcony, pillar, parapet, railing, gate, roof_edge.
- parapet = the low wall along the top of a flat roof.
- The sloped roof itself is not roof_edge: roof_edge is only the edge or fascia band. Skip the roof surface.
- Do NOT include the sky, the ground, roads, vegetation (trees, plants, grass), vehicles, people, wires, or any neighbouring building.
- Polygons must follow the building edge tightly and never include sky, ground or trees.
- "box_2d" is the bounding box of the item as [y0, x0, y1, x1], with integer values normalised to 0-1000 relative to the image height (y) and width (x).
- "polygon" is the outline of the visible part of the item as a list of [y, x] points, integers normalised to 0-1000 like box_2d, in order around the outline. Use 4 to 16 points: follow the real edges and corners, do not trace every pixel.

Output a JSON list only, with no other text. Each element must look like:
{"label": "wall", "box_2d": [y0, x0, y1, x1], "polygon": [[y, x], [y, x], [y, x], [y, x]]}
