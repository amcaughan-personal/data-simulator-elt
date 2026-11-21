#!/usr/bin/env bash
# Build dist/ingest.zip: the ingest package at the zip's root. It has no dependencies
# beyond the Lambda runtime (which includes boto3).
#
# Files go in sorted, with a fixed timestamp, so unchanged code gives a byte-identical zip.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p dist

python3 - src dist/ingest.zip <<'PY'
import sys, zipfile
from pathlib import Path

src, dest = Path(sys.argv[1]), sys.argv[2]
files = sorted(p for p in (src / "ingest").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in files:
        info = zipfile.ZipInfo(str(path.relative_to(src)), date_time=(2000, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, path.read_bytes())
    print(f"built {dest}: {len(files)} files")
PY
