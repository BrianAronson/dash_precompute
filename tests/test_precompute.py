from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import pytest
from dash_precompute import ArtifactCatalog, build_artifact_bundle


def test_build_artifact_bundle_is_content_addressed_and_reusable(
    tmp_path: Path,
    profile_path: Path,
) -> None:
    output = tmp_path / "artifacts"

    first = build_artifact_bundle(
        profile_path=profile_path,
        source_manifest_paths=(),
        output_dir=output,
        match_count=2,
    )
    second = build_artifact_bundle(
        profile_path=profile_path,
        source_manifest_paths=(),
        output_dir=output,
        match_count=2,
    )

    assert first == second
    manifest = json.loads(first.read_text(encoding="utf-8"))
    assert manifest["region_count"] == 4
    assert manifest["country_count"] == 4
    assert manifest["variant_count"] == 4
    assert len({item["path"] for item in manifest["variants"]}) == 4
    assert all(
        set(item["key"]) == {"country_code", "region_code"}
        for item in manifest["variants"]
    )
    assert manifest["configuration"]["matching"]["cross_country"] is True
    pointer = json.loads((output / "current.json").read_text(encoding="utf-8"))
    assert (output / pointer["manifest"]).resolve() == first.resolve()


def test_all_source_manifests_contribute_provenance_and_bundle_identity(
    tmp_path: Path,
    profile_path: Path,
) -> None:
    oecd_manifest = tmp_path / "oecd.json"
    density_manifest = tmp_path / "density.json"
    oecd_manifest.write_text(
        json.dumps(
            {
                "dataset": "oecd_profile",
                "install_id": "oecd-1",
                "source": {"attribution": "OECD test source"},
            }
        ),
        encoding="utf-8",
    )
    density_manifest.write_text(
        json.dumps(
            {
                "dataset": "ghsl_density",
                "install_id": "ghsl-1",
                "source": {"attribution": "GHSL test source"},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"

    first = build_artifact_bundle(
        profile_path=profile_path,
        source_manifest_paths=(oecd_manifest, density_manifest),
        output_dir=output,
        match_count=2,
    )
    first_record = json.loads(first.read_text(encoding="utf-8"))
    density_manifest.write_text(
        json.dumps(
            {
                "dataset": "ghsl_density",
                "install_id": "ghsl-2",
                "source": {"attribution": "GHSL test source"},
            }
        ),
        encoding="utf-8",
    )
    second = build_artifact_bundle(
        profile_path=profile_path,
        source_manifest_paths=(oecd_manifest, density_manifest),
        output_dir=output,
        match_count=2,
    )

    assert first != second
    assert [
        source["dataset"] for source in first_record["source"]["source_manifests"]
    ] == ["ghsl_density", "oecd_profile"]
    assert first_record["source"]["source_manifests"][0]["source"] == {
        "attribution": "GHSL test source"
    }


def test_precomputed_matches_follow_the_declared_policy(artifact_dir: Path) -> None:
    catalog = ArtifactCatalog(artifact_dir)

    comparison = catalog.get(country_code="AAA", region_code="AA1")

    assert comparison["matches"][0]["region_code"] == "BB1"
    assert set(comparison["matches"][0]["contribution"]) == {
        "population",
        "population_density_per_km2",
        "population_change_percent",
        "gdp_per_capita_usd_ppp",
    }
    assert comparison["matches"][0]["distance"] >= 0
    assert [item["country_code"] for item in comparison["country_best"]] == [
        "BBB",
        "DDD",
        "CCC",
    ]
    assert all(0 < item["similarity"] <= 100 for item in comparison["country_best"])
    assert [item["country_rank"] for item in comparison["country_best"]] == [1, 2, 3]


def test_build_rejects_incomplete_or_invalid_profiles(
    tmp_path: Path,
    profile_path: Path,
) -> None:
    profile = pd.read_parquet(profile_path)
    profile["profile_complete"] = False
    broken = tmp_path / "broken.parquet"
    profile.to_parquet(broken, index=False)

    with pytest.raises(ValueError, match="no complete comparison rows"):
        build_artifact_bundle(
            profile_path=broken,
            source_manifest_paths=(),
            output_dir=tmp_path / "artifacts",
        )


def test_build_requires_enough_cross_country_candidates(
    tmp_path: Path,
    profile_path: Path,
) -> None:
    with pytest.raises(ValueError, match="has only"):
        build_artifact_bundle(
            profile_path=profile_path,
            source_manifest_paths=(),
            output_dir=tmp_path / "artifacts",
            match_count=4,
        )
