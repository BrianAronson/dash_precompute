"""Validated, lazy lookup over one immutable precomputed artifact bundle."""

# 0) Imports
from __future__ import annotations
import gzip
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


# 1) Manifest resolution
def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        record = json.load(source)
    return record


def _resolve_manifest(path: Path) -> Path:
    if path.is_file():
        return path
    pointer_path = path / "current.json"
    if not pointer_path.exists():
        raise FileNotFoundError(
            f"Artifact current pointer does not exist: {pointer_path}"
        )
    pointer = _read_json(pointer_path)
    root = path.resolve()
    manifest_path = (root / pointer["manifest"]).resolve()
    if not manifest_path.is_relative_to(root):
        raise ValueError("Artifact current pointer leaves its root")
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Artifact manifest does not exist: {manifest_path}"
        )
    return manifest_path


# 2) Catalog facade
class ArtifactCatalog:
    """Resolve valid selections and lazily load one immutable artifact bundle."""

    def __init__(self, manifest_path: Path | str) -> None:
        self.manifest_path = _resolve_manifest(Path(manifest_path))
        self.root = self.manifest_path.parent.resolve()
        self.manifest = _read_json(self.manifest_path)
        if self.manifest.get("schema_version") != 2:
            raise ValueError(
                f"Unsupported artifact schema: {self.manifest.get('schema_version')}"
            )
        self._index: dict[tuple[str, str], Mapping[str, Any]] = {}
        for variant in self.manifest.get("variants", []):
            key = variant.get("key", {})
            if set(key) != {"country_code", "region_code"}:
                raise ValueError(f"Unexpected artifact key dimensions: {sorted(key)}")
            identity = (
                str(key["country_code"]),
                str(key["region_code"]),
            )
            if not all(identity):
                raise ValueError("Artifact keys must contain non-empty strings")
            if identity in self._index:
                raise ValueError(f"Duplicate artifact key: {identity}")
            self._index[identity] = variant
        if not self._index:
            raise ValueError("Artifact manifest contains no variants")
        expected = self.manifest.get("variant_count")
        if expected != len(self._index):
            raise ValueError(
                f"Artifact variant count differs: {expected} != {len(self._index)}"
            )
        self._payload_cache: dict[str, dict[str, Any]] = {}
        self.common = self._load_record(self.manifest["common_payload"])
        self._regions = {
            region["region_code"]: region for region in self.common["regions"]
        }

    @property
    def build_id(self) -> str:
        build_id = str(self.manifest["build_id"])
        return build_id

    @property
    def source(self) -> Mapping[str, Any]:
        source = self.manifest["source"]
        return source

    @property
    def metrics(self) -> list[Mapping[str, Any]]:
        metrics = list(self.common["metrics"])
        return metrics

    def country_options(self) -> list[dict[str, str]]:
        countries = {
            (region["country_name"], region["country_code"])
            for region in self._regions.values()
        }
        options = [
            {"label": name, "value": code}
            for name, code in sorted(countries, key=lambda item: item[0])
        ]
        return options

    def region_options(self, country_code: str) -> list[dict[str, str]]:
        regions = [
            region
            for region in self._regions.values()
            if region["country_code"] == country_code
        ]
        options = [
            {"label": region["region_name"], "value": region["region_code"]}
            for region in sorted(regions, key=lambda item: item["region_name"])
        ]
        return options

    def get(
        self,
        country_code: str,
        region_code: str,
    ) -> dict[str, Any]:
        identity = (country_code, region_code)
        try:
            record = self._index[identity]
        except KeyError as error:
            raise KeyError(f"No precomputed variant for {identity}") from error
        payload = self._load_record(record)
        return payload

    def validate_all(self) -> None:
        """Verify every indexed payload before publishing an artifact bundle."""

        for record in self._index.values():
            self._load_record(record)

    def contains_region(self, country_code: str, region_code: str) -> bool:
        """Return whether a region belongs to the supplied country."""

        region = self._regions.get(region_code)
        return region is not None and region["country_code"] == country_code

    def _load_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        relative = str(record["path"])
        if relative in self._payload_cache:
            return self._payload_cache[relative]
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Artifact payload leaves bundle root: {relative}")
        if not path.exists():
            raise FileNotFoundError(f"Artifact payload is missing: {path}")
        data = path.read_bytes()
        if len(data) != record["size_bytes"]:
            raise ValueError(f"Artifact payload size differs: {relative}")
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError(f"Artifact payload checksum differs: {relative}")
        payload = json.loads(gzip.decompress(data))
        if payload.get("schema_version") != self.manifest["schema_version"]:
            raise ValueError(f"Artifact payload schema differs: {relative}")
        self._payload_cache[relative] = payload
        return payload
