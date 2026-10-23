"""Verified publisher-only media from saved PMC packages.

A paper's package (see `package`) is unpacked into the cache the first time a page asks for it.
Only manifest-allowlisted CIFs and chemical schemes have public routes; package paths, receipts,
XML and CSD files are never served by this module.
"""

import base64
import hashlib
import io
import json
import math
import os
import re
import shlex
import subprocess
import tarfile
import threading
from pathlib import Path
from urllib.parse import quote, urlsplit

import gemmi

from viz.publisher_data import DATA, package_name

CACHE = Path(os.environ.get("TEXTAL_PUBLISHER_CACHE", "data/publisher-cache")).resolve()
EXPORTER = Path(__file__).with_name("export_publisher_assets.py")
PAPERS = {}
LOCKS = {}
THUMB_LOCKS = {}
GUARD = threading.Lock()
FETCH_LIMIT = threading.Semaphore(4)
MODEL_LIMIT = threading.Semaphore(2)
ROOTS = (
    "/project/rrg-aspuru/auhcheng/iucr_open_access_full_2026-10-21/packages/",
    "/project/rrg-aspuru/auhcheng/csd_oa_archive_2026-10-21/packages/",
)


def configure(papers):
    global PAPERS
    PAPERS = {
        p["pmcid"]: p
        for p in papers.values()
        if p.get("pmcid") and p.get("provenance", {}).get("has_publisher_package", True)
    }
    CACHE.mkdir(parents=True, exist_ok=True)


def validate_manifest(data, pmcid):
    if data.get("pmcid") != pmcid or pmcid not in PAPERS:
        raise ValueError("Unknown publisher paper")
    if data.get("package_path") not in [root + pmcid + ".tar.gz" for root in ROOTS]:
        raise ValueError("Asset provenance is not an approved PMC publisher package")
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


def assets(pmcid):
    if not re.fullmatch(r"PMC[0-9]+", pmcid) or pmcid not in PAPERS:
        raise ValueError("Paper is not in the public publisher collection")
    with GUARD:
        lock = LOCKS.setdefault(pmcid, threading.Lock())
    with lock:
        folder = CACHE / pmcid
        manifest = folder / "manifest.json"
        if manifest.is_file():
            data = validate_manifest(json.loads(manifest.read_text()), pmcid)
            if all(
                (folder / f["cache_name"]).is_file()
                for kind in ("cifs", "figures")
                for f in data[kind]
            ):
                return data
        with tarfile.open(fileobj=io.BytesIO(package(pmcid))) as tar:
            data = validate_manifest(json.load(tar.extractfile("manifest.json")), pmcid)
            folder.mkdir(parents=True, exist_ok=True)
            for kind in ("cifs", "figures"):
                for f in data[kind]:
                    blob = tar.extractfile(f["cache_name"]).read()
                    if len(blob) != f["bytes"] or hashlib.sha256(blob).hexdigest() != f["sha256"]:
                        raise ValueError("Publisher file failed receipt verification")
                    path = folder / f["cache_name"]
                    temp = path.with_suffix(path.suffix + ".part")
                    temp.write_bytes(blob)
                    temp.replace(path)
            temp = manifest.with_suffix(".json.part")
            temp.write_text(json.dumps(data))
            temp.replace(manifest)
        return data


def package(pmcid):
    """The bytes of the paper's package: a tar of its manifest and publisher files.

    It is read from the dataset folder or, on the machine that builds the dataset, exported from
    the archive of PMC packages over SSH.
    """
    path = DATA / package_name(pmcid)
    if path.is_file():
        return path.read_bytes()
    if os.environ.get("TEXTAL_ASSET_SSH", "0") != "1":
        raise RuntimeError("The publisher files of this paper are not in the dataset.")
    encoded = base64.b64encode(EXPORTER.read_bytes()).decode()
    remote = (
        "python3 -c "
        + shlex.quote("import base64;exec(base64.b64decode(" + repr(encoded) + "))")
        + " "
        + shlex.quote(pmcid)
    )
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12"]
    if os.environ.get("TEXTAL_SSH_CONTROL"):
        command += ["-o", "ControlPath=" + os.environ["TEXTAL_SSH_CONTROL"]]
    command += [
        os.environ["TEXTAL_ARCHIVE_SSH"],
        "ssh -o BatchMode=yes "
        + shlex.quote(os.environ.get("TEXTAL_ARCHIVE_NODE", "tri-dm2"))
        + " "
        + shlex.quote(remote),
    ]
    try:
        with FETCH_LIMIT:
            result = subprocess.run(command, capture_output=True, timeout=100, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Publisher archive read timed out; retry the paper.") from None
    if result.returncode:
        raise RuntimeError(
            "The publisher archive connection is unavailable; cached papers remain available."
        )
    return result.stdout


def public_manifest(pmcid):
    data = assets(pmcid)
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
    data = assets(pmcid)
    asset = next(
        (f for kind in ("cifs", "figures") for f in data[kind] if f["cache_name"] == name), None
    )
    if asset is None:
        raise ValueError("File is not a public publisher asset")
    path = CACHE / pmcid / name
    raw = path.read_bytes()
    if len(raw) != asset["bytes"] or hashlib.sha256(raw).hexdigest() != asset["sha256"]:
        raise ValueError("Publisher cache checksum mismatch")
    return path, asset


def cif_models(pmcid, name):
    with MODEL_LIMIT:
        return _cif_models(pmcid, name)


def _cif_models(pmcid, name):
    data = assets(pmcid)
    asset = next((f for f in data["cifs"] if f["cache_name"] == name), None)
    if asset is None:
        raise ValueError("CIF is not listed in this paper package.")
    path, asset = asset_file(pmcid, name)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != asset["sha256"]:
        raise ValueError("Cached CIF checksum differs from its receipt.")
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
        "sha256": digest,
        "parser": "Gemmi " + gemmi.__version__,
        "blocks": blocks,
        "note": "Display-only CIF uses safe internal atom labels; original labels, elements, fractional coordinates, occupancies, cell and symmetry are retained in this response. Original CIF download is unchanged.",
    }


def thumbnail(pmcid):
    with GUARD:
        lock = THUMB_LOCKS.setdefault(pmcid, threading.Lock())
    with lock:
        return _thumbnail(pmcid)


def _thumbnail(pmcid):
    """Original main-site unit-cell drawing, generated exclusively from publisher bytes."""
    from viz.crystal import draw_cell

    data = assets(pmcid)
    if not data["cifs"]:
        raise ValueError("No publisher CIF available")
    asset = data["cifs"][0]
    asset_file(pmcid, asset["cache_name"])
    dest = CACHE / pmcid / (asset["sha256"] + "-main-preview-v5.svg")
    if not dest.exists():
        models = cif_models(pmcid, asset["cache_name"])
        with MODEL_LIMIT:
            text = draw_cell(models["blocks"][0]["text"])
        temp = dest.with_suffix(".svg.part")
        temp.write_text(text)
        temp.replace(dest)
    return dest
