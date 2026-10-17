"""CSV compatibility, immutable raw evidence, and deterministic normalized exports."""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from data.quality import Assessment, DataPolicy, assess
from data.schema import FIELDS


@dataclass(frozen=True, slots=True)
class ImportedData:
    rows: tuple[dict, ...]
    metadata: dict
    raw: bytes


def read_csv(path: str | Path) -> ImportedData:
    path = Path(path)
    raw = path.read_bytes()
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("dataset sidecar must be a JSON object")
    for field in ("symbol", "timeframe", "quote_currency", "kind", "source"):
        if not isinstance(metadata.get(field), str) or not metadata[field]:
            raise ValueError(f"dataset sidecar needs {field}")
    if metadata["kind"] not in {"historical", "synthetic"}:
        raise ValueError("dataset kind must be historical or synthetic")
    if metadata["kind"] == "historical":
        source = urlparse(metadata["source"])
        credential_keys = {"api_key", "apikey", "api_secret", "token", "access_token", "password", "signature"}
        if (source.scheme != "https" or not source.hostname or source.username or source.password
                or source.fragment or any(key.lower() in credential_keys for key, _ in parse_qsl(source.query))):
            raise ValueError("historical provenance must be a public HTTPS URL without credentials")
    if hashlib.sha256(raw).hexdigest() != metadata.get("sha256"):
        raise ValueError("dataset SHA-256 does not match its sidecar")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    header = reader.fieldnames or []
    required = set(FIELDS) - {"symbol", "timeframe"}
    if (len(header) != len(set(header)) or not required <= set(header)
            or set(header) - (set(FIELDS) | {"quote_volume"})):
        raise ValueError("invalid CSV schema; require OHLCV/timestamp and optional symbol,timeframe,quote_volume")
    rows = tuple(dict(row) for row in reader)
    return ImportedData(rows, metadata, raw)


def inspect_csv(path: str | Path, policy: DataPolicy, as_of: datetime) -> Assessment:
    imported = read_csv(path)
    return assess(imported.rows, imported.metadata, policy, as_of)


def write_dataset(path: str | Path, assessment: Assessment, metadata: dict,
                  original: bytes, raw_extension: str = "csv") -> None:
    """Never overwrite user artifacts or automatically approve a transformed dataset."""
    path = Path(path)
    if path.suffix.lower() != ".csv" or raw_extension not in {"csv", "json"}:
        raise ValueError("output must be .csv and raw evidence must be csv or json")
    sidecar = path.with_suffix(".json")
    report = path.with_suffix(".report.json")
    if any(target.exists() for target in (path, sidecar, report)):
        raise ValueError("refusing to overwrite an existing CSV, sidecar, or report")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_sha = hashlib.sha256(original).hexdigest()
    raw_path = path.parent / "raw" / f"{raw_sha}.{raw_extension}"
    raw_path.parent.mkdir(exist_ok=True)
    if raw_path.exists():
        if raw_path.read_bytes() != original:
            raise ValueError("raw evidence checksum collision or corruption")
    else:
        raw_path.write_bytes(original)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=(*FIELDS, "quote_volume"), lineterminator="\n")
    writer.writeheader()
    writer.writerows(record.row() for record in assessment.completed)
    payload = buffer.getvalue().encode("utf-8")
    values = {**metadata, "schema_version": 2, "quality_reviewed": False,
              "ingestion_eligible": assessment.report["eligible"],
              "validation_as_of": assessment.report["as_of"], "data_policy": assessment.report["policy"],
              "sha256": hashlib.sha256(payload).hexdigest(), "raw_sha256": raw_sha,
              "raw_file": str(raw_path.relative_to(path.parent)).replace("\\", "/")}
    outputs = ((path, payload),
               (sidecar, (json.dumps(values, indent=2, sort_keys=True, default=str) + "\n").encode()),
               (report, (json.dumps(assessment.report, indent=2, sort_keys=True, default=str) + "\n").encode()))
    created = []
    try:
        for target, content in outputs:
            with target.open("xb") as stream:
                created.append(target)
                stream.write(content)
    except BaseException:
        for target in created:
            target.unlink(missing_ok=True)
        raise
