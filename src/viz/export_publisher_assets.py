"""Read journal CIFs and chemical schemes from saved PMC packages; emit a small tar.

Read-only on Trillium. No publisher crawling or new paper downloads.
"""

import gzip
import hashlib
import io
import json
import pathlib
import re
import sys
import tarfile
import zipfile

pmcid = sys.argv[1]
if not re.fullmatch(r"PMC[0-9]+", pmcid):
    raise ValueError("Invalid PMCID")
base = pathlib.Path("/project/rrg-aspuru/auhcheng")
paths = [
    base / "iucr_open_access_full_2026-10-21/packages" / (pmcid + ".tar.gz"),
    base / "csd_oa_archive_2026-10-21/packages" / (pmcid + ".tar.gz"),
]
path = next((p for p in paths if p.is_file()), None)
if path is None:
    raise FileNotFoundError("No saved PMC package for " + pmcid)
outputs = {}
result = {
    "pmcid": pmcid,
    "package_path": str(path),
    "cifs": [],
    "figures": [],
    "gaps": [],
    "source": "Downloaded publisher-supplied files in the PMC OA package",
}
with tarfile.open(path) as tar:
    members = {m.name: m for m in tar if m.isfile()}
    receipt = json.load(tar.extractfile(pmcid + "/receipt.json"))
    result["doi"] = receipt.get("doi") or (receipt.get("doi_aliases") or [None])[0]
    versions = receipt.get("versions") or [
        {"version": receipt.get("version"), "files": receipt.get("files", [])}
    ]
    files = []
    for v in versions:
        for f in v.get("files", []):
            candidates = [
                pmcid + "/files/" + f["name"],
                pmcid + "/versions/" + str(v.get("version")) + "/files/" + f["name"],
            ]
            member = next((n for n in candidates if n in members), None)
            if member:
                files.append({**f, "member": member, "version": v.get("version")})
    # Prefer the latest paper version, retaining earlier files as fallback.
    files.sort(key=lambda f: str(f.get("version") or ""), reverse=True)

    def read(f):
        data = tar.extractfile(f["member"]).read()
        digest = hashlib.sha256(data).hexdigest()
        if f.get("sha256") and digest != f["sha256"]:
            raise ValueError("SHA256 mismatch: " + f["member"])
        return data, digest

    def save(f, data, asset_kind, **extra):
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", pathlib.PurePosixPath(f["name"]).name)
        name = str(len(outputs)) + "-" + safe
        if asset_kind == "cif" and not name.lower().endswith(".cif"):
            name += ".cif"
        outputs[name] = data
        return {
            "name": f["name"],
            "cache_name": name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "source_sha256": f.get("sha256"),
            "archive_member": f["member"],
            "source_url": f.get("url"),
            "version": f.get("version"),
            **extra,
        }

    for f in files:
        name = f["name"].lower()
        if name.endswith((".cif", ".cif.gz")):
            raw, _ = read(f)
            data = gzip.decompress(raw) if name.endswith(".gz") else raw
            if re.search(rb"_atom_site_(?:fract_[xyz]|Cartn_[xyz]|label)", data, re.IGNORECASE):
                result["cifs"].append(save(f, data, "cif", derived_from_gzip=name.endswith(".gz")))
    # Some journals put their structure files inside the SI ZIP.
    if not result["cifs"]:
        for f in files:
            if not f["name"].lower().endswith(".zip"):
                continue
            raw, _ = read(f)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for info in z.infolist():
                    if info.filename.lower().endswith(".cif") and info.file_size < 50000000:
                        data = z.read(info)
                        if b"_atom_site_" in data:
                            result["cifs"].append(
                                save(
                                    {**f, "name": pathlib.PurePosixPath(info.filename).name},
                                    data,
                                    "cif",
                                    zip_member=info.filename,
                                    source_zip=f["name"],
                                )
                            )
    # Only the publisher's chemical schemes are needed in this local view.
    images = [
        f
        for f in files
        if pathlib.Path(f["name"]).suffix.lower()
        in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".tif", ".tiff")
    ]
    seen = set()
    for f in images:
        if f["member"] in seen or not re.search(r"(?:scheme|sch)[_-]?\d", f["name"], re.IGNORECASE):
            continue
        data, _ = read(f)
        seen.add(f["member"])
        result["figures"].append(
            save(
                f,
                data,
                "figure",
                label="Chemical scheme",
                caption="Publisher chemical scheme supplied with the article.",
                kind="chemical_scheme",
            )
        )
    if not result["cifs"]:
        result["gaps"].append(
            "No coordinate-bearing CIF was found in the saved package; external-only or friend-held attachments are not available here."
        )
    if not result["figures"]:
        result["gaps"].append("No publisher chemical scheme was found in the saved package.")
    result["version_note"] = (
        "Files are paper-level assets; CIF data blocks are not automatically assigned to CSD refcodes."
    )
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as out:
    payload = json.dumps(result, ensure_ascii=False).encode()
    m = tarfile.TarInfo("manifest.json")
    m.size = len(payload)
    out.addfile(m, io.BytesIO(payload))
    for name, data in outputs.items():
        m = tarfile.TarInfo(name)
        m.size = len(data)
        out.addfile(m, io.BytesIO(data))
