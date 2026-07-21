"""
Minimal DiD Lambda stub: SQS (S3 Object Created) → read batch input → write empty
DIDOutput files + DIDComplete.

In AWS this would use boto3 against the data bucket. For the local example,
set LOCAL_S3_ROOT to a directory whose layout mirrors S3 key prefixes.
"""

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus


DID_INPUT_PREFIX = "DIDInput/"
DID_OUTPUT_PREFIX = "DIDOutput/"
DID_COMPLETE_PREFIX = "DIDComplete/"


class InfraError(Exception):
    """Raised for failures that should fail the Lambda, which will trigger an automated SQS retry / DLQ)."""


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """
    SQS event shape (S3 → EventBridge/SNS → SQS, or S3 notification → SQS):

      event["Records"][0]["body"]  → JSON string of the S3 Object Created event
      detail.bucket.name           → bucket
      detail.object.key            → e.g. DIDInput/{YYYY}/{MM}/{DD}/{uuid}
    """
    bucket, input_key = parse_sqs_s3_event(event)
    persistence_id = persistence_id_from_key(input_key)

    batch = read_json(bucket, input_key)
    files = batch.get("Files")
    if not isinstance(files, list):
        raise InfraError(f"Batch file missing Files list: s3://{bucket}/{input_key}")

    did_complete_files: list[dict[str, Any]] = []

    for entry in files:
        eicr_key = entry["eicr"]
        rr_key = entry["rr"]
        setid = entry.get("setid")
        version = entry.get("version")

        # Ensure listed refined docs are readable (real DiD would load + compare).
        _ = read_bytes(bucket, eicr_key)
        _ = read_bytes(bucket, rr_key)

        out_eicr = to_did_output_key(eicr_key)
        out_rr = to_did_output_key(rr_key)

        # Stub: empty placeholders for per-doc DiD results.
        write_bytes(bucket, out_eicr, b"")
        write_bytes(bucket, out_rr, b"")

        did_complete_files.append(
            {
                "eicr": out_eicr,
                "rr": out_rr,
                "setid": setid,
                "version": version,
            }
        )

    complete_key = f"{DID_COMPLETE_PREFIX}{persistence_id}"
    complete_body = {"Files": did_complete_files}
    write_json(bucket, complete_key, complete_body)

    return {
        "bucket": bucket,
        "input_key": input_key,
        "persistence_id": persistence_id,
        "did_complete_key": complete_key,
        "processed_count": len(did_complete_files),
    }


def parse_sqs_s3_event(event: dict[str, Any]) -> tuple[str, str]:
    records = event.get("Records") or []
    if not records:
        raise InfraError("SQS event has no Records")

    body_raw = records[0].get("body")
    if not body_raw:
        raise InfraError("SQS record missing body")

    try:
        body = json.loads(body_raw) if isinstance(body_raw, str) else body_raw
    except json.JSONDecodeError as exc:
        raise InfraError("SQS body is not valid JSON") from exc

    detail = body.get("detail") or {}
    bucket = (detail.get("bucket") or {}).get("name")
    key = (detail.get("object") or {}).get("key")
    if not bucket or not key:
        raise InfraError("S3 Object Created detail missing bucket/object.key")

    return bucket, unquote_plus(key)


def persistence_id_from_key(key: str) -> str:
    """
    Strip the first S3 key segment (prefix) to leave the persistence_id.

    AIMS form: YYYY/MM/DD/{uuid}
    Example: DIDInput/2026/07/14/19d4812b-fc1d-471a-8872-6d5edd1714ff
    → 2026/07/14/19d4812b-fc1d-471a-8872-6d5edd1714ff
    """
    parts = key.strip("/").split("/", 1)
    if len(parts) != 2 or not parts[1]:
        raise InfraError(f"S3 key has no persistence_id after prefix: {key}")
    return parts[1]


def to_did_output_key(source_key: str) -> str:
    """Replace the first S3 key segment with DIDOutput/."""
    parts = source_key.strip("/").split("/", 1)
    if len(parts) != 2 or not parts[1]:
        raise InfraError(f"S3 key has nothing after prefix: {source_key}")
    return f"{DID_OUTPUT_PREFIX}{parts[1]}"


# --- storage: local filesystem (LOCAL_S3_ROOT) or boto3 ---


def _local_root() -> Path | None:
    raw = os.environ.get("LOCAL_S3_ROOT")
    return Path(raw) if raw else None


def read_bytes(bucket: str, key: str) -> bytes:
    root = _local_root()
    if root is not None:
        path = root / bucket / key
        if not path.is_file():
            raise InfraError(f"Missing object: {path}")
        return path.read_bytes()

    import boto3

    try:
        obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except Exception as exc:  # noqa: BLE001 — surface as infra for retry/DLQ
        raise InfraError(f"S3 get_object failed s3://{bucket}/{key}: {exc}") from exc


def read_json(bucket: str, key: str) -> dict[str, Any]:
    return json.loads(read_bytes(bucket, key).decode("utf-8"))


def write_bytes(bucket: str, key: str, data: bytes) -> None:
    root = _local_root()
    if root is not None:
        path = root / bucket / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return

    import boto3

    try:
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=data)
    except Exception as exc:  # noqa: BLE001
        raise InfraError(f"S3 put_object failed s3://{bucket}/{key}: {exc}") from exc


def write_json(bucket: str, key: str, payload: dict[str, Any]) -> None:
    write_bytes(bucket, key, json.dumps(payload, indent=2).encode("utf-8"))
