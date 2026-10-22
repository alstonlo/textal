"""Import the completed Luna run, leaving the running extraction untouched.

Exit 3 means not ready. With --progress-only this also supplies a read-only health
check to the completion heartbeat. Assets are published only after all refcodes
are terminal and the complete Parquet has been verified locally.
"""

import argparse
import hashlib
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

import polars as pl
from build_publisher_assets import build

DEFAULT_RUN = "/project/rrg-aspuru/auhcheng/acta_e_schema_2026-10-22/anchored-v1"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sections", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("src/viz/assets"))
    p.add_argument("--ssh", default="auhcheng@trillium.alliancecan.ca")
    p.add_argument("--control", default=str(Path.home() / ".ssh/trillium-%C"))
    p.add_argument("--node", default="tri-dm2")
    p.add_argument("--remote-run", default=DEFAULT_RUN)
    p.add_argument("--progress-only", action="store_true")
    p.add_argument("--texts", type=Path, default=Path("data/publisher-texts"))
    args = p.parse_args()

    def remote(code, timeout=120):
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=12",
            "-o",
            "ControlPath=" + args.control,
            args.ssh,
            "ssh -o BatchMode=yes "
            + shlex.quote(args.node)
            + " "
            + shlex.quote("python3 -c " + shlex.quote(code)),
        ]
        r = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        if r.returncode:
            raise RuntimeError(
                "Archive SSH connection unavailable; the remote extraction is independent of this connection."
            )
        return r.stdout

    progress = json.loads(
        remote(
            "from pathlib import Path;print((Path("
            + repr(args.remote_run)
            + ")/'progress.json').read_text())"
        )
    )
    print(json.dumps(progress, indent=2))
    if args.progress_only:
        return 0
    if (
        progress.get("phase") != "complete"
        or progress["refcodes_finished"] != progress["refcodes_total"]
    ):
        return 3
    code = (
        "from pathlib import Path;import hashlib,json;p=Path("
        + repr(args.remote_run)
        + ")/'extractions.parquet';b=p.read_bytes();print(json.dumps({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}))"
    )
    receipt = json.loads(remote(code))
    blob = remote(
        "from pathlib import Path;import sys;sys.stdout.buffer.write((Path("
        + repr(args.remote_run)
        + ")/'extractions.parquet').read_bytes())",
        timeout=300,
    )
    if len(blob) != receipt["bytes"] or hashlib.sha256(blob).hexdigest() != receipt["sha256"]:
        raise ValueError("Completed extraction snapshot checksum mismatch")
    with tempfile.TemporaryDirectory() as tmp:
        parquet = Path(tmp) / "extractions.parquet"
        parquet.write_bytes(blob)
        table = pl.read_parquet(parquet)
        if table["identifier"].n_unique() != progress["refcodes_total"]:
            raise ValueError(
                "Completed Parquet is missing refcodes; refusing a partial final import"
            )
        result = build(
            args.sections, parquet, args.output, texts=args.texts, preserve_existing=True
        )
    receipt.update(
        imported_at=result["built_at"],
        remote_run=args.remote_run,
        refcodes=result["refcodes"],
        papers=result["papers"],
    )
    (args.output / "completed-luna-import.json").write_text(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
