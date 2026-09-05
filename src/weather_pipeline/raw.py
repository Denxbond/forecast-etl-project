"""Preserve raw forecast responses and retrieval metadata."""

import json
from datetime import datetime, timezone
from pathlib import Path


def save_raw_snapshot(
    raw_body: bytes,
    retrieved_at: datetime,
    city_id: str,
    endpoint: str,
    request_params: dict,
    raw_dir: Path,
) -> Path:
    """Save a retrieval in a new directory; refuse to reuse an existing one."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")

    retrieved_at = retrieved_at.astimezone(timezone.utc)
    snapshot_id = retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")

    metadata = {
        "city_id": city_id,
        "retrieved_at": retrieved_at.isoformat(),
        "endpoint": endpoint,
        "request_params": request_params,
    }
    metadata_text = json.dumps(metadata, indent=2) + "\n"

    snapshot_dir = raw_dir / city_id / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    with (snapshot_dir / "response.json").open("xb") as file:
        file.write(raw_body)

    with (snapshot_dir / "metadata.json").open("x", encoding="utf-8") as file:
        file.write(metadata_text)

    (snapshot_dir / "_SUCCESS").touch(exist_ok=False)

    return snapshot_dir