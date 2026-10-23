import colorsys
import math
import re

import gemmi
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

# Covalent radii (Å) for the bonds and atom sizes of the thumbnails; the fallback covers the rest.
RADII = {
    "H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Si": 1.11, "P": 1.07,
    "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39, "Na": 1.66, "K": 2.03, "Ca": 1.76,
    "Mg": 1.41, "Zn": 1.22, "Cu": 1.32, "Fe": 1.32, "Pt": 1.36, "Li": 1.28,
}  # fmt: skip

# The Jmol colours that py3Dmol uses, for the elements the site's palette below leaves out.
JMOL_COLOURS = {
    "Li": "#CC80FF", "Be": "#C2FF00", "B": "#FFB5B5", "Na": "#AB5CF2", "Mg": "#8AFF00",
    "Al": "#BFA6A6", "Si": "#F0C8A0", "K": "#8F40D4", "Ca": "#3DFF00", "Sc": "#E6E6E6",
    "Ti": "#BFC2C7", "V": "#A6A6AB", "Cr": "#8A99C7", "Mn": "#9C7AC7", "Fe": "#E06633",
    "Co": "#F090A0", "Ni": "#50D050", "Cu": "#C88033", "Zn": "#7D80B0", "Ga": "#C28F8F",
    "Ge": "#668F8F", "As": "#BD80E3", "Se": "#FFA100", "Rb": "#702EB0", "Sr": "#00FF00",
    "Y": "#94FFFF", "Zr": "#94E0E0", "Nb": "#73C2C9", "Mo": "#54B5B5", "Tc": "#3B9E9E",
    "Ru": "#248F8F", "Rh": "#0A7D8C", "Pd": "#006985", "Ag": "#C0C0C0", "Cd": "#FFD98F",
    "In": "#A67573", "Sn": "#668080", "Sb": "#9E63B5", "Te": "#D47A00", "Xe": "#429EB0",
    "Cs": "#57178F", "Ba": "#00C900", "La": "#70D4FF", "Ce": "#FFFFC7", "Pr": "#D9FFC7",
    "Nd": "#C7FFC7", "Pm": "#A3FFC7", "Sm": "#8FFFC7", "Eu": "#61FFC7", "Gd": "#45FFC7",
    "Tb": "#30FFC7", "Dy": "#1FFFC7", "Ho": "#00FF9C", "Er": "#00E675", "Tm": "#00D452",
    "Yb": "#00BF38", "Lu": "#00AB24", "Hf": "#4DC2FF", "Ta": "#4DA6FF", "W": "#2194D6",
    "Re": "#267DAB", "Os": "#266696", "Ir": "#175487", "Pt": "#D0D0E0", "Au": "#FFD123",
    "Hg": "#B8B8D0", "Tl": "#A6544D", "Pb": "#575961", "Bi": "#9E4FB5", "Th": "#00BAFF",
    "U": "#008FFF",
}  # fmt: skip


def legible(colour: str) -> str:
    """The colour darkened to a lightness of at most 0.55, so that a flat dot shows on the light
    tiles; scaling keeps its hue and how muted it is."""
    rgb = [int(colour[i : i + 2], 16) for i in (1, 3, 5)]
    f = min(1.0, 0.55 / colorsys.rgb_to_hls(*(v / 255 for v in rgb))[1])
    return "#" + "".join(f"{round(f * v):02X}" for v in rgb)


# Element colours for the drawings: CPK hues, in the site's palette, and the Jmol hues for the rest.
ELEMENT_COLOURS = {
    **{e: legible(c) for e, c in JMOL_COLOURS.items()},
    "C": "#333333", "N": "#3B4BC9", "O": "#C8324E", "S": "#E0A400", "P": "#EB7A24",
    "F": "#34B868", "Cl": "#25A443", "Br": "#9B2235", "I": "#7A3BD0",
}  # fmt: skip
OTHER_COLOUR = "#7A7A78"

# The 3D viewer: the same hues, with lighter carbons and hydrogens so the sticks keep their depth;
# its shading keeps the light Jmol colours visible.
VIEWER_COLOURS = {
    **ELEMENT_COLOURS, **JMOL_COLOURS,
    "C": "#8C8C88", "H": "#E4E4E0", "O": "#D9405C", "S": "#F2B400",
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


def parse_structure(cif: str) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    """Reads publisher CIF atoms with Gemmi and fills the unit cell with its symmetry operators.

    Returns:
        The element symbols, the fractional coordinates (n, 3) of every atom in the cell, the
        lattice matrix (3, 3) whose rows are the lattice vectors, and the index (n,) of the
        molecule each atom belongs to.
    """
    document = gemmi.cif.read_string(cif)
    structure = next(
        (
            gemmi.make_small_structure_from_block(b)
            for b in document
            if len(b.find_values("_atom_site_fract_x"))
        ),
        None,
    )
    if structure is None or not structure.sites:
        raise ValueError("Publisher CIF has no supported fractional atom sites")
    lattice = lattice_matrix(
        structure.cell.a,
        structure.cell.b,
        structure.cell.c,
        structure.cell.alpha,
        structure.cell.beta,
        structure.cell.gamma,
    )
    elems = [site.element.name for site in structure.sites]
    frac = np.asarray([[site.fract.x, site.fract.y, site.fract.z] for site in structure.sites])
    ops = list(structure.symops)
    if not ops and structure.spacegroup:
        ops = [op.triplet() for op in structure.spacegroup.operations()]
    ops = ops or ["x,y,z"]
    if len(elems) * len(ops) > 2000:
        raise ValueError("Structure exceeds the whole-molecule preview size limit")
    images = [
        np.asarray([gemmi.Op(op).apply_to_xyz(point.tolist()) for point in frac]) for op in ops
    ]
    frac_all = np.concatenate(images) % 1.0
    elems_all = elems * len(ops)

    # Symmetry operators map atoms on special positions onto themselves: keep the first copy.
    cart = frac_all @ lattice
    dist = np.linalg.norm(cart[:, None] - cart[None], axis=-1)
    keep = ~np.triu(dist < 0.1, k=1).any(axis=0)
    elems_all = [e for e, k in zip(elems_all, keep, strict=True) if k]
    frac, mols = whole_molecules(elems_all, frac_all[keep], lattice)
    return elems_all, frac, lattice, mols


def whole_molecules(
    elems: list[str], frac: np.ndarray, lattice: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Moves atoms by lattice vectors so that bonded atoms sit next to each other.

    Wrapping every atom into the cell on its own cuts molecules at the cell faces. Here bonds are
    found under the minimum-image convention, each connected set of atoms is unwrapped along its
    bonds, and the whole set is then shifted so that its centre lies inside the cell.

    Returns:
        The moved fractional coordinates (n, 3), and the index (n,) of each atom's molecule.
    """
    diff = frac[:, None] - frac[None]
    shift = np.round(diff)
    dist = np.linalg.norm((diff - shift) @ lattice, axis=-1)
    radii = np.asarray([RADII.get(e, 1.4) for e in elems])
    bonded = (dist < 1.15 * (radii[:, None] + radii[None])) & (dist > 0.4)

    offset = np.zeros_like(frac)
    mols = np.full(len(frac), -1)
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
        mols[group] = mols.max() + 1
    return frac + offset, mols


def draw_cell(
    cif: str,
    size: int = 240,
    ink: str = "#111111",
    view: tuple[float, float] = (0.5, 0.35),
) -> str:
    """Draws the filled unit cell as a flat one-colour SVG: cell edges, bonds and heavy atoms.

    Hydrogens are left out, so the drawing stays legible at thumbnail size and reads as a specimen
    on a coloured tile. Every atom is drawn in proportion to its covalent radius, so metals and
    halogens stand out.

    Args:
        view: The yaw and pitch (radians) of the camera. The default tilts the cell so that all
            three axes read as a box.
    """
    yaw, pitch = view
    rot = np.asarray(
        [
            [math.cos(yaw), 0.0, -math.sin(yaw)],
            [math.sin(pitch) * math.sin(yaw), math.cos(pitch), math.sin(pitch) * math.cos(yaw)],
            [math.cos(pitch) * math.sin(yaw), -math.sin(pitch), math.cos(pitch) * math.cos(yaw)],
        ]
    )
    elems, frac, lattice, _ = parse_structure(cif)
    heavy = [i for i, e in enumerate(elems) if e != "H"]
    elems = [elems[i] for i in heavy]
    cart = (frac[heavy] @ lattice) @ rot.T
    corners = (UNIT_CUBE_EDGES.reshape(-1, 3) @ lattice) @ rot.T

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

    # Bonds and atoms are sized in Å, so that two drawings compare at any zoom.
    out.append(
        f'</g><g stroke="{ink}" stroke-width="{0.12 * scale:.2f}" stroke-linecap="round"'
        ' opacity="0.85">'
    )
    for a, b in zip(i, j, strict=True):
        out.append(f'<path d="M{xy[a, 0]:.1f} {xy[a, 1]:.1f}L{xy[b, 0]:.1f} {xy[b, 1]:.1f}"/>')

    # Back to front, so that nearer atoms cover farther ones.
    out.append("</g><g>")
    for k in np.argsort(cart[:, 2]):
        r = scale * 0.45 * gemmi.Element(elems[k]).covalent_r
        fill = ELEMENT_COLOURS.get(elems[k], OTHER_COLOUR)
        out.append(f'<circle cx="{xy[k, 0]:.1f}" cy="{xy[k, 1]:.1f}" r="{r:.1f}" fill="{fill}"/>')
    out.append("</g></svg>")
    return "".join(out)


def point(p) -> dict:
    return dict(zip("xyz", np.asarray(p).tolist(), strict=True))


def draw_crystal(cif: str, background: str, height: int = 560) -> str:
    """Draws a publisher CIF with py3Dmol: the filled unit cell, and the molecules around it.

    The look follows `clari.chem.draw.draw_crystal`: sticks and small spheres, the cell as thin
    cylinders, and the lattice vectors as red, green and blue arrows from the origin. Atoms come
    from `parse_structure`, so molecules are whole, as in the thumbnails. The surrounding
    molecules are those of the 26 neighbouring cells whose centre lies within half a cell of the
    unit cell, i.e. in [-0.5, 1.5] along each axis; they are a second, faint model that the page
    shows on demand (see `entry.js`).

    Returns:
        The HTML of the viewer (a div and the script that fills it), to be inlined in a page.
    """
    elems, frac, lattice, mols = parse_structure(cif)
    shifts = np.asarray([s for s in np.ndindex(3, 3, 3) if s != (1, 1, 1)]) - 1
    centres = np.stack([frac[mols == m].mean(axis=0) for m in range(mols.max() + 1)])
    near = centres[None] + shifts[:, None]
    near = ((near >= -0.5) & (near <= 1.5)).all(axis=-1)[:, mols]  # (26, n)
    shell = (frac[None] + shifts[:, None])[near]
    shell_elems = np.asarray(elems)[np.nonzero(near)[1]].tolist()

    view = py3Dmol.view(width="100%", height=height)
    view.setBackgroundColor(background)
    scheme = {"prop": "elem", "map": VIEWER_COLOURS}
    for model, (names, xyz) in enumerate([(elems, frac), (shell_elems, shell)]):
        lines = [
            f"{e} {x:.4f} {y:.4f} {z:.4f}"
            for e, (x, y, z) in zip(names, xyz @ lattice, strict=True)
        ]
        view.addModel(f"{len(lines)}\n\n" + "\n".join(lines), "xyz")
        opacity = 1.0 if (model == 0) else 0.4
        view.setStyle(
            {"model": model},
            {
                "stick": {"radius": 0.2, "colorscheme": scheme, "opacity": opacity},
                "sphere": {"scale": 0.2, "colorscheme": scheme, "opacity": opacity},
            },
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
    view.zoomTo({"model": 0})
    return view._make_html()


def viewer_geometry(cif: str) -> dict:
    """The original main-site molecule, shell and lattice geometry, from publisher CIF only."""
    elems, frac, lattice, mols = parse_structure(cif)
    shifts = np.asarray([s for s in np.ndindex(3, 3, 3) if s != (1, 1, 1)]) - 1
    centres = np.stack([frac[mols == m].mean(axis=0) for m in range(mols.max() + 1)])
    near = centres[None] + shifts[:, None]
    near = ((near >= -0.5) & (near <= 1.5)).all(axis=-1)[:, mols]
    shell = (frac[None] + shifts[:, None])[near]
    shell_elems = np.asarray(elems)[np.nonzero(near)[1]].tolist()

    def xyz(names, positions):
        lines = [
            f"{e} {x:.8f} {y:.8f} {z:.8f}"
            for e, (x, y, z) in zip(names, positions @ lattice, strict=True)
        ]
        return str(len(lines)) + "\n\n" + "\n".join(lines)

    return {
        "xyz": xyz(elems, frac),
        "shell_xyz": xyz(shell_elems, shell),
        "atoms": len(elems),
        "lattice": lattice.tolist(),
        "edges": (UNIT_CUBE_EDGES @ lattice).tolist(),
        "colours": VIEWER_COLOURS,
    }
