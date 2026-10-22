import json
import math
import re

import numpy as np
import py3Dmol

UNIT_CUBE_EDGES = np.asarray(
    [
        [[0, 0, 0], [0, 0, 1]],
        [[0, 0, 0], [0, 1, 0]],
        [[0, 0, 0], [1, 0, 0]],
        [[1, 0, 0], [1, 1, 0]],
        [[1, 0, 0], [1, 0, 1]],
        [[0, 1, 0], [1, 1, 0]],
        [[0, 1, 0], [0, 1, 1]],
        [[0, 0, 1], [1, 0, 1]],
        [[0, 0, 1], [0, 1, 1]],
        [[1, 1, 1], [0, 1, 1]],
        [[1, 1, 1], [1, 0, 1]],
        [[1, 1, 1], [1, 1, 0]],
    ]
)  # (12, 2, 3)

# Covalent radii (Å) for the bonds of the thumbnails; the fallback covers the rest.
RADII = {
    "H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Si": 1.11, "P": 1.07,
    "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39, "Na": 1.66, "K": 2.03, "Ca": 1.76,
    "Mg": 1.41, "Zn": 1.22, "Cu": 1.32, "Fe": 1.32, "Pt": 1.36, "Li": 1.28,
}  # fmt: skip

# Element colours for the drawings: CPK hues, in the site's palette; the fallback is for metals.
ELEMENT_COLOURS = {
    "C": "#333333", "N": "#3B4BC9", "O": "#C8324E", "S": "#E0A400", "P": "#EB7A24",
    "F": "#34B868", "Cl": "#25A443", "Br": "#9B2235", "I": "#7A3BD0",
}  # fmt: skip
OTHER_COLOUR = "#7A7A78"

# The 3D viewer: the same hues, with lighter carbons and hydrogens so the sticks keep their depth.
VIEWER_COLOURS = {
    **ELEMENT_COLOURS, "C": "#8C8C88", "H": "#E4E4E0", "O": "#D9405C", "S": "#F2B400",
}  # fmt: skip


def lattice_matrix(a, b, c, alpha, beta, gamma) -> np.ndarray:
    """Rows are the lattice vectors, in the convention 3Dmol uses to place CIF atoms."""
    alpha, beta, gamma = (math.radians(x) for x in (alpha, beta, gamma))
    cx = c * math.cos(beta)
    cy = c * (math.cos(alpha) - math.cos(beta) * math.cos(gamma)) / math.sin(gamma)
    return np.asarray(
        [
            [a, 0.0, 0.0],
            [b * math.cos(gamma), b * math.sin(gamma), 0.0],
            [cx, cy, math.sqrt(c * c - cx * cx - cy * cy)],
        ]
    )


def cif_loop(cif: str, tag: str) -> list[list[str]]:
    """The rows of the CIF loop that holds `tag`, each row split into its fields."""
    for block in re.split(r"^loop_\s*$", cif, flags=re.MULTILINE)[1:]:
        lines = block.strip().splitlines()
        tags = []
        while lines and lines[0].startswith("_"):
            tags.append(lines.pop(0).split()[0])
        if tag not in tags:
            continue
        rows = []
        for l in lines:
            if l.startswith(("_", "#")) or not l.strip():
                break
            rows.append(l.split(None, len(tags) - 1))
        return [r for r in rows if len(r) == len(tags)]
    return []


def parse_structure(cif: str) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Reads the atoms of a CSD CIF and fills the unit cell with its symmetry operators.

    Returns:
        The element symbols, the fractional coordinates (n, 3) of every atom in the cell, and
        the lattice matrix (3, 3) whose rows are the lattice vectors.
    """
    cell = []
    for tag in ("a", "b", "c", "alpha", "beta", "gamma"):
        kind = "length" if tag in "abc" else "angle"
        m = re.search(rf"^_cell_{kind}_{tag}\s+([\d.]+)", cif, re.MULTILINE)
        cell.append(float(m.group(1)))
    lattice = lattice_matrix(*cell)

    sites = cif_loop(cif, "_atom_site_fract_x")
    elems = [s[1] for s in sites]
    frac = np.asarray([[float(re.sub(r"\(\d+\)", "", v)) for v in s[2:5]] for s in sites])
    ops = [row[-1] for row in cif_loop(cif, "_symmetry_equiv_pos_as_xyz")] or ["x,y,z"]

    x, y, z = frac.T
    images = []
    for op in ops:
        expr = op.strip("'\" ").lower().split(",")
        assert len(expr) == 3, op
        images.append(np.stack([eval(e, {"x": x, "y": y, "z": z}) for e in expr], axis=1))
    frac_all = np.concatenate(images) % 1.0
    elems_all = elems * len(ops)

    # Symmetry operators map atoms on special positions onto themselves: keep one copy.
    cart = frac_all @ lattice
    keep = []
    for i in range(len(cart)):
        if all(np.linalg.norm(cart[i] - cart[j]) > 0.1 for j in keep[-200:]):
            keep.append(i)
    elems_all = [elems_all[i] for i in keep]
    return elems_all, whole_molecules(elems_all, frac_all[keep], lattice), lattice


def whole_molecules(elems: list[str], frac: np.ndarray, lattice: np.ndarray) -> np.ndarray:
    """Moves atoms by lattice vectors so that bonded atoms sit next to each other.

    Wrapping every atom into the cell on its own cuts molecules at the cell faces. Here bonds are
    found under the minimum-image convention, each connected set of atoms is unwrapped along its
    bonds, and the whole set is then shifted so that its centre lies inside the cell.
    """
    diff = frac[:, None] - frac[None]
    shift = np.round(diff)
    dist = np.linalg.norm((diff - shift) @ lattice, axis=-1)
    radii = np.asarray([RADII.get(e, 1.4) for e in elems])
    bonded = (dist < 1.15 * (radii[:, None] + radii[None])) & (dist > 0.4)

    offset = np.zeros_like(frac)
    seen = np.zeros(len(frac), dtype=bool)
    for start in range(len(frac)):
        if seen[start]:
            continue
        seen[start] = True
        group, queue = [start], [start]
        while queue:
            i = queue.pop()
            for j in np.flatnonzero(bonded[i] & ~seen):
                seen[j] = True
                offset[j] = offset[i] + shift[i, j]
                group.append(j)
                queue.append(j)
        centre = (frac[group] + offset[group]).mean(axis=0)
        offset[group] -= np.floor(centre)
    return frac + offset


# A fixed oblique view: the cell is tilted so that all three axes read as a box.
VIEW = np.asarray(
    [
        [math.cos(0.5), 0.0, -math.sin(0.5)],
        [math.sin(0.35) * math.sin(0.5), math.cos(0.35), math.sin(0.35) * math.cos(0.5)],
        [math.cos(0.35) * math.sin(0.5), -math.sin(0.35), math.cos(0.35) * math.cos(0.5)],
    ]
)


def draw_cell(cif: str, size: int = 240, ink: str = "#111111") -> str:
    """Draws the filled unit cell as a flat one-colour SVG: cell edges, bonds and heavy atoms.

    Hydrogens are left out and carbons are small dots, so the drawing stays legible at thumbnail
    size and reads as a specimen on a coloured tile.
    """
    elems, frac, lattice = parse_structure(cif)
    heavy = [i for i, e in enumerate(elems) if e != "H"]
    elems = [elems[i] for i in heavy]
    cart = (frac[heavy] @ lattice) @ VIEW.T
    corners = (UNIT_CUBE_EDGES.reshape(-1, 3) @ lattice) @ VIEW.T

    pts = np.concatenate([cart, corners])
    lo, hi = pts[:, :2].min(0), pts[:, :2].max(0)
    scale = (size - 16) / max(hi - lo)
    offset = (size - (hi - lo) * scale) / 2 - lo * scale
    xy = cart[:, :2] * scale + offset
    cxy = corners[:, :2] * scale + offset

    radii = np.asarray([RADII.get(e, 1.4) for e in elems])
    dist = np.linalg.norm(cart[:, None] - cart[None], axis=-1)
    bonded = (dist < 1.15 * (radii[:, None] + radii[None])) & (dist > 0.4)
    i, j = np.where(np.triu(bonded))

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
        f'<g stroke="{ink}" stroke-width="0.7" fill="none" opacity="0.45">',
    ]
    for k in range(0, len(cxy), 2):
        out.append(
            f'<path d="M{cxy[k, 0]:.1f} {cxy[k, 1]:.1f}L{cxy[k + 1, 0]:.1f} {cxy[k + 1, 1]:.1f}"/>'
        )
    out.append(f'</g><g stroke="{ink}" stroke-width="1.3" stroke-linecap="round" opacity="0.85">')
    for a, b in zip(i, j, strict=True):
        out.append(f'<path d="M{xy[a, 0]:.1f} {xy[a, 1]:.1f}L{xy[b, 0]:.1f} {xy[b, 1]:.1f}"/>')
    out.append("</g><g>")
    for k in range(len(xy)):
        r = 1.6 if elems[k] == "C" else 3.2
        fill = ELEMENT_COLOURS.get(elems[k], OTHER_COLOUR)
        out.append(f'<circle cx="{xy[k, 0]:.1f}" cy="{xy[k, 1]:.1f}" r="{r}" fill="{fill}"/>')
    out.append("</g></svg>")
    return "".join(out)


def point(p) -> dict:
    return dict(zip("xyz", np.asarray(p).tolist(), strict=True))


def draw_crystal(cif: str, lattice: np.ndarray, background: str, height: int = 560) -> str:
    """Draws a CSD CIF with py3Dmol, filling the unit cell by its symmetry operators.

    The look follows `clari.chem.draw.draw_crystal`: sticks and small spheres, the cell as thin
    cylinders, and the lattice vectors as red, green and blue arrows from the origin.

    Returns:
        The HTML of the viewer (a div and the script that fills it), to be inlined in a page.
    """
    view = py3Dmol.view(width="100%", height=height)
    view.setBackgroundColor(background)
    view.addModel(
        cif, "cif", {"doAssembly": True, "duplicateAssemblyAtoms": True, "normalizeAssembly": True}
    )
    scheme = {"prop": "elem", "map": VIEWER_COLOURS}
    view.setStyle(
        {
            "stick": {"radius": 0.2, "colorscheme": scheme},
            "sphere": {"scale": 0.2, "colorscheme": scheme},
        }
    )

    origin = np.zeros(3)
    for vec, color in zip(lattice, ["red", "green", "blue"], strict=True):
        view.addArrow(
            {
                "start": point(origin),
                "end": point(vec),
                "radius": 0.2,
                "radiusRatio": 2,
                "mid": 0.92,
                "color": color,
            }
        )
    for e in UNIT_CUBE_EDGES @ lattice:
        view.addCylinder({"start": point(e[0]), "end": point(e[1]), "radius": 0.05})
    view.zoomTo()
    html = view._make_html()
    assert json.dumps(cif)[1:-1] in html, "py3Dmol did not inline the CIF as expected"
    return html
