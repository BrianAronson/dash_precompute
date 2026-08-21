from __future__ import annotations
import json
from pathlib import Path
import pytest
from dash_precompute import ArtifactCatalog


def test_catalog_derives_cascading_country_and_region_options(
    artifact_dir: Path,
) -> None:
    catalog = ArtifactCatalog(artifact_dir)

    assert catalog.country_options() == [
        {"label": "Alpha", "value": "AAA"},
        {"label": "Beta", "value": "BBB"},
        {"label": "Delta", "value": "DDD"},
        {"label": "Gamma", "value": "CCC"},
    ]
    assert catalog.region_options("BBB") == [{"label": "Beta East", "value": "BB1"}]
    assert catalog.contains_region("BBB", "BB1") is True
    assert catalog.contains_region("BBB", "AA1") is False


def test_catalog_rejects_unknown_keys(artifact_dir: Path) -> None:
    catalog = ArtifactCatalog(artifact_dir)
    with pytest.raises(KeyError, match="No precomputed variant"):
        catalog.get(
            country_code="AAA",
            region_code="ZZ1",
        )


def test_catalog_rejects_unreachable_key_dimensions(artifact_dir: Path) -> None:
    pointer = json.loads((artifact_dir / "current.json").read_text(encoding="utf-8"))
    manifest_path = artifact_dir / pointer["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["variants"][0]["key"]["lens"] = "hidden"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="Unexpected artifact key dimensions"):
        ArtifactCatalog(artifact_dir)


def test_catalog_checks_payload_integrity(artifact_dir: Path) -> None:
    pointer = json.loads((artifact_dir / "current.json").read_text(encoding="utf-8"))
    manifest_path = artifact_dir / pointer["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = manifest_path.parent / manifest["common_payload"]["path"]
    payload_path.write_bytes(payload_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="size differs"):
        ArtifactCatalog(artifact_dir)


def test_catalog_can_validate_every_variant_before_publication(
    artifact_dir: Path,
) -> None:
    pointer = json.loads((artifact_dir / "current.json").read_text(encoding="utf-8"))
    manifest_path = artifact_dir / pointer["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = manifest_path.parent / manifest["variants"][0]["path"]
    payload_path.write_bytes(payload_path.read_bytes() + b"tampered")

    catalog = ArtifactCatalog(artifact_dir)
    with pytest.raises(ValueError, match="size differs"):
        catalog.validate_all()
