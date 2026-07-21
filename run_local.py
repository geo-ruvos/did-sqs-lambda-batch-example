#!/usr/bin/env python3
"""Run the DiD Lambda stub against local fixture S3 layout (no AWS required)."""

import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
WORK = HERE / "local_workspace"
BUCKET = "ecr-dev-data-repository"
# AIMS persistence_id is YYYY/MM/DD/{uuid} (date prefix + uuid).
PERSISTENCE_ID = "2026/07/14/19d4812b-fc1d-471a-8872-6d5edd1714ff"

# Seed refined docs listed in the DIDInput batch file.
REFINED_KEYS = [
    f"RefinerOutputV2/{PERSISTENCE_ID}/SDDH/COVID19/refined_eICR.xml",
    f"RefinerOutputV2/{PERSISTENCE_ID}/SDDH/COVID19/refined_RR.xml",
    f"RefinerOutputV2/{PERSISTENCE_ID}/JURIS2/FLU/refined_eICR.xml",
    f"RefinerOutputV2/{PERSISTENCE_ID}/JURIS2/FLU/refined_RR.xml",
    f"RefinerOutputV2/{PERSISTENCE_ID}/SDDH/unrefined_rr/refined_eICR.xml",
    f"RefinerOutputV2/{PERSISTENCE_ID}/SDDH/unrefined_rr/refined_RR.xml",
]


def seed_workspace() -> Path:
    if WORK.exists():
        shutil.rmtree(WORK)
    bucket_root = WORK / BUCKET
    bucket_root.mkdir(parents=True)

    # Copy DIDInput batch manifest (key includes date segments)
    src_input = FIXTURES / "s3" / BUCKET / "DIDInput" / PERSISTENCE_ID
    dest_input = bucket_root / "DIDInput" / PERSISTENCE_ID
    dest_input.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_input, dest_input)

    # Placeholder refined docs DiD would read
    for key in REFINED_KEYS:
        path = bucket_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<!-- stub {key} -->\n", encoding="utf-8")

    return WORK


def main() -> int:
    root = seed_workspace()
    os.environ["LOCAL_S3_ROOT"] = str(root)

    sys.path.insert(0, str(HERE))
    from lambda_function import handler

    event = json.loads((FIXTURES / "sqs_event.json").read_text(encoding="utf-8"))
    result = handler(event, context=None)

    complete_path = root / BUCKET / result["did_complete_key"]
    print(json.dumps(result, indent=2))
    print()
    print(f"Wrote DIDComplete → {complete_path}")
    print(complete_path.read_text(encoding="utf-8"))

    expected = json.loads(
        (FIXTURES / "expected_did_complete.json").read_text(encoding="utf-8")
    )
    actual = json.loads(complete_path.read_text(encoding="utf-8"))
    if actual != expected:
        print("WARNING: DIDComplete does not match fixtures/expected_did_complete.json")
        return 1
    print("OK: DIDComplete matches expected fixture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
