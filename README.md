# SQS → Lambda batch stub for DiD

Minimal example of how DiD sees an incoming batch after Refiner, how the Lambda
parses the SQS record, and what `DIDComplete` looks like when the batch finishes.

This stub does **no** real Difference-in-Docs work: it parses the message, reads
each listed eICR/RR, writes **empty** `DIDOutput/` objects, then writes
`DIDComplete/{YYYY}/{MM}/{DD}/{uuid}`.

## Flow

```text
S3 PutObject  DIDInput/{YYYY}/{MM}/{DD}/{uuid}
    → EventBridge / S3 notification
    → SQS (ecr-dev-did-input)
    → DiD Lambda
         → parse Records[0].body → bucket + key
         → read DIDInput JSON (Files: [{eicr, rr, setId, versionNumber}, ...])
         → for each file: read refined docs, write empty DIDOutput copies
         → write DIDComplete/{YYYY}/{MM}/{DD}/{uuid}
```

## Layout

| Path | Purpose |
|------|---------|
| `lambda_function.py` | Lambda handler |
| `fixtures/sqs_event.json` | Example SQS poll / Lambda event |
| `fixtures/s3/.../DIDInput/...` | Example batch input DiD reads |
| `fixtures/expected_did_complete.json` | Expected `DIDComplete` body |
| `run_local.py` | Local dry-run (filesystem as S3) |

## Persistence ID

AIMS `persistence_id` is a **date path + UUID**: `YYYY/MM/DD/{uuid}`.

Example: `2026/07/14/19d4812b-fc1d-471a-8872-6d5edd1714ff`

The `persistence_id` is the key suffix under every pipeline prefix (`DIDInput/`, `RefinerOutputV2/`,
`DIDOutput/`, `DIDComplete/`, etc.).

## Batch input (`DIDInput/{YYYY}/{MM}/{DD}/{uuid}`)

Prototype `Files` shape from the Jul 14 eng sync (object list with setId/versionNumber):

```json
{
  "Files": [
    {
      "eicr": "RefinerOutputV2/2026/07/14/19d4812b-.../SDDH/COVID19/refined_eICR.xml",
      "rr": "RefinerOutputV2/2026/07/14/19d4812b-.../SDDH/COVID19/refined_RR.xml",
      "setId": "001",
      "versionNumber": 2
    }
  ]
}
```

## SQS body → bucket/key

`Records[0].body` is a JSON **string** of the S3 Object Created event. After
`json.loads`:

- `detail.bucket.name` → bucket (e.g. `ecr-dev-data-repository`)
- `detail.object.key` → `DIDInput/2026/07/14/19d4812b-fc1d-471a-8872-6d5edd1714ff`

## Outputs

For each input pair, empty objects under:

- `DIDOutput/2026/07/14/{uuid}/.../refined_eICR.xml`
- `DIDOutput/2026/07/14/{uuid}/.../refined_RR.xml`

Then one batch signal:

- `DIDComplete/2026/07/14/{uuid}` — `Files` lists processed paths under `DIDOutput/`
  (same setId/versionNumber). Unprocessed entries would keep `RefinerOutputV2/` paths;
  this stub processes every listed file.

## Error handling

| Situation | Behavior |
|-----------|----------|
| Batch can be processed | Write `DIDOutput/` + always write `DIDComplete/` |
| Infra failure (S3/DDB down, missing required object) | **Do not** write `DIDComplete`; raise so SQS retries / DLQ |

## Run locally

Requires Python 3.10+

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_local.py
```

Sets `LOCAL_S3_ROOT=./local_workspace`, seeds refined stubs, invokes `handler`
with `fixtures/sqs_event.json`, and prints the written `DIDComplete`.

Unset `LOCAL_S3_ROOT` and provide AWS credentials / IAM for real S3 via boto3.
