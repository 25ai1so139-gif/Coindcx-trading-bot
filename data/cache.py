"""Expiring raw-response cache. Stale/corrupt entries are never a fallback."""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from data.schema import utc


@dataclass(frozen=True, slots=True)
class CacheEntry:
    body: bytes
    fetched_at: datetime


class ResponseCache:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def _path(self, url: str) -> Path:
        return self.directory / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def get(self, url: str, now: datetime, ttl: timedelta) -> CacheEntry | None:
        if ttl.total_seconds() < 0:
            raise ValueError("cache TTL cannot be negative")
        path = self._path(url)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = utc(value["fetched_at"])
            body = bytes.fromhex(value["body_hex"])
            if (value["url"] != url or hashlib.sha256(body).hexdigest() != value["sha256"]
                    or not timedelta(0) <= utc(now) - fetched_at < ttl):
                return None
            return CacheEntry(body, fetched_at)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, url: str, body: bytes, fetched_at: datetime) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        value = {"url": url, "fetched_at": utc(fetched_at).isoformat(),
                 "sha256": hashlib.sha256(body).hexdigest(), "body_hex": body.hex()}
        descriptor, name = tempfile.mkstemp(prefix=".response-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True)
            os.replace(name, self._path(url))
        finally:
            Path(name).unlink(missing_ok=True)
