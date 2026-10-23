"""Verified publisher-only media from the paper packages of the dataset folder.

Only manifest-allowlisted CIFs and chemical schemes have public routes; package paths, receipts,
XML and CSD files are never served by this module.
"""

import functools
import hashlib
import json
import math
import re
import tarfile
import threading
from urllib.parse import quote, urlsplit

import gemmi

from viz.publisher_data import DATA, package_name

PAPERS = {}
MODEL_LIMIT = threading.Semaphore(2)
THUMB_VERSION = 8


def configure(papers):
    global PAPERS
    PAPERS = {
        p["pmcid"]: p
        for p in papers.values()
        if p.get("pmcid") and p.get("provenance", {}).get("has_publisher_package", True)
    }
    package.cache_clear()
    thumbnail.cache_clear()


def validate_manifest(data, pmcid):
    if data.get("pmcid") != pmcid or pmcid not in PAPERS:
        raise ValueError("Unknown publisher paper")
    doi = data.get("doi") or data.get("index_doi")
    if not doi or doi.lower() != PAPERS[pmcid]["doi"].lower():
        raise ValueError("Publisher DOI does not match the paper")
    out = dict(data)
    out["figures"] = [f for f in data.get("figures", []) if f.get("kind") == "chemical_scheme"]
    out["cifs"] = data.get("cifs", [])
    for kind in ("cifs", "figures"):
        for f in out[kind]:
            name = f["cache_name"]
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
                raise ValueError("Invalid publisher asset filename")
            if not re.fullmatch(r"[a-f0-9]{64}", f["sha256"]):
                raise ValueError("Missing publisher checksum")
            if not f.get("archive_member", "").startswith(pmcid + "/"):
                raise ValueError("Invalid publisher package member")
            url = urlsplit(f.get("source_url") or "")
            if url.scheme != "https" or url.hostname != "pmc-oa-opendata.s3.amazonaws.com":
                raise ValueError("Asset must originate from PMC OA publisher storage")
            allowed = (
                (".cif",)
                if kind == "cifs"
                else (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".tif", ".tiff")
            )
            if not name.lower().endswith(allowed):
                raise ValueError("Unsupported publisher asset type")
            f["local_url"] = "/paper-assets/" + pmcid + "/" + quote(name)
    return out


# Most packages are about 100 kB, so recently opened papers are kept in memory.
@functools.lru_cache(maxsize=64)
def package(pmcid):
    """The paper's manifest and the bytes of its listed files, checked against their checksums."""
    if not re.fullmatch(r"PMC[0-9]+", pmcid) or pmcid not in PAPERS:
        raise ValueError("Paper is not in the public publisher collection")
    with tarfile.open(DATA / package_name(pmcid)) as tar:
        data = validate_manifest(json.load(tar.extractfile("manifest.json")), pmcid)
        blobs = {}
        for f in data["cifs"] + data["figures"]:
            blob = tar.extractfile(f["cache_name"]).read()
            if len(blob) != f["bytes"] or hashlib.sha256(blob).hexdigest() != f["sha256"]:
                raise ValueError("Publisher file failed receipt verification")
            blobs[f["cache_name"]] = blob
    return data, blobs


def public_manifest(pmcid):
    data, _ = package(pmcid)
    out = {"pmcid": pmcid, "doi": PAPERS[pmcid]["doi"], "cifs": [], "figures": []}
    for kind in ("cifs", "figures"):
        for f in data[kind]:
            out[kind].append(
                {
                    key: f.get(key)
                    for key in (
                        "name",
                        "cache_name",
                        "bytes",
                        "sha256",
                        "source_url",
                        "local_url",
                        "kind",
                    )
                }
            )
    return out


def asset_file(pmcid, name):
    data, blobs = package(pmcid)
    asset = next(
        (f for kind in ("cifs", "figures") for f in data[kind] if f["cache_name"] == name), None
    )
    if asset is None:
        raise ValueError("File is not a public publisher asset")
    return blobs[name], asset


def cif_models(pmcid, name):
    with MODEL_LIMIT:
        return _cif_models(pmcid, name)


def _cif_models(pmcid, name):
    data, blobs = package(pmcid)
    asset = next((f for f in data["cifs"] if f["cache_name"] == name), None)
    if asset is None:
        raise ValueError("CIF is not listed in this paper package.")
    raw = blobs[name]
    parsed = gemmi.cif.read_string(raw.decode("utf-8", errors="replace"))
    blocks = []
    for block in parsed:
        structure = gemmi.make_small_structure_from_block(block)
        if not structure.sites:
            continue
        cell = [
            structure.cell.a,
            structure.cell.b,
            structure.cell.c,
            structure.cell.alpha,
            structure.cell.beta,
            structure.cell.gamma,
        ]
        if not all(math.isfinite(v) and v > 0 for v in cell):
            raise ValueError("Invalid unit cell in data_" + block.name)
        ops = list(structure.symops)
        op_source = "explicit CIF operators"
        if not ops and structure.spacegroup:
            ops = [op.triplet() for op in structure.spacegroup.operations()]
            op_source = "CIF space-group record"
        if not ops:
            ops = ["x,y,z"]
            op_source = "identity only; no symmetry information"
        ops = [gemmi.Op(op).triplet() for op in ops]
        lines = ["data_model"]
        for tag, v in zip(
            ["length_a", "length_b", "length_c", "angle_alpha", "angle_beta", "angle_gamma"], cell
        ):
            lines.append("_cell_" + tag + " " + format(v, ".17g"))
        lines += ["loop_", "_symmetry_equiv_pos_as_xyz"] + ["'" + op + "'" for op in ops]
        lines += [
            "loop_",
            "_atom_site_label",
            "_atom_site_type_symbol",
            "_atom_site_fract_x",
            "_atom_site_fract_y",
            "_atom_site_fract_z",
            "_atom_site_occupancy",
        ]
        sites = []
        for i, site in enumerate(structure.sites):
            coords = [site.fract.x, site.fract.y, site.fract.z]
            if not all(math.isfinite(v) for v in coords):
                raise ValueError("Non-finite coordinates: " + site.label)
            if not site.element.atomic_number:
                raise ValueError("Unknown element: " + site.label)
            element = site.element.name
            lines.append(
                "A"
                + str(i)
                + " "
                + element
                + " "
                + " ".join(format(v, ".17g") for v in coords)
                + " "
                + format(site.occ, ".17g")
            )
            sites.append(
                {
                    "label": site.label,
                    "element": element,
                    "fractional": coords,
                    "occupancy": site.occ,
                }
            )
        from viz.crystal import viewer_geometry

        geometry = viewer_geometry("\n".join(lines) + "\n")
        blocks.append(
            {
                "viewer": geometry,
                "name": block.name,
                "text": "\n".join(lines) + "\n",
                "cell": cell,
                "space_group": structure.spacegroup_hm,
                "symmetry_operations": ops,
                "symmetry_source": op_source,
                "asymmetric_atoms": len(sites),
                "sites": sites,
            }
        )
    if not blocks:
        raise ValueError("No supported atom-coordinate blocks found in this CIF.")
    return {
        "pmcid": pmcid,
        "original_url": asset["local_url"],
        "name": asset["name"],
        "bytes": asset["bytes"],
        "sha256": asset["sha256"],
        "parser": "Gemmi " + gemmi.__version__,
        "blocks": blocks,
        "note": "Display-only CIF uses safe internal atom labels; original labels, elements, fractional coordinates, occupancies, cell and symmetry are retained in this response. Original CIF download is unchanged.",
    }


@functools.lru_cache(maxsize=4096)
def thumbnail(pmcid):
    """Original main-site unit-cell drawing, generated exclusively from publisher bytes."""
    from viz.crystal import draw_cell

    data, _ = package(pmcid)
    if not data["cifs"]:
        raise ValueError("No publisher CIF available")
    models = cif_models(pmcid, data["cifs"][0]["cache_name"])
    with MODEL_LIMIT:
        return draw_cell(models["blocks"][0]["text"])
