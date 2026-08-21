"""Build immutable, content-addressed comparison payloads before app runtime."""

# 0) Imports
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any
import numpy as np
import pandas as pd
from .config import MATCH_COUNT, MATCHING, METRICS

# 1) Artifact contract
SCHEMA_VERSION = 2
BUILDER_VERSION = "7"
_REQUIRED_PROFILE_COLUMNS = {
    "year",
    "growth_start_year",
    "territorial_level",
    "region_code",
    "region_name",
    "country_code",
    "country_name",
    "profile_complete",
    *(metric.name for metric in METRICS),
}
_REQUIRED_TIME_SERIES_COLUMNS = {
    "territorial_level",
    "region_code",
    "region_name",
    "country_code",
    "country_name",
    "indicator",
    "indicator_label",
    "year",
    "value",
    "unit",
    "status",
    "status_label",
}
_REQUIRED_AGE_STRUCTURE_COLUMNS = {
    "territorial_level",
    "region_code",
    "region_name",
    "country_code",
    "country_name",
    "year",
    "age_group",
    "age_group_label",
    "population",
    "share_percent",
    "status",
    "status_label",
}
_REQUIRED_COUNTRY_DENSITY_COLUMNS = {
    "country_code",
    "country_name",
    "epoch",
    "grid_resolution_m",
    "density_bin_lower",
    "density_bin_upper",
    "density_bin_midpoint",
    "populated_grid_cells",
    "population",
    "population_share_percent",
}
_EXPECTED_SERIES_INDICATORS = {
    "population",
    "unemployment_rate_percent",
    "disposable_income_per_capita_usd_ppp",
    "life_expectancy_years",
}
_HISTORY_PAYLOAD_KEYS = {
    "population": "population_history",
    "unemployment_rate_percent": "unemployment_history",
    "disposable_income_per_capita_usd_ppp": "income_history",
    "life_expectancy_years": "life_expectancy_history",
}


# 2) Source reading and analytical transformations
def _read_profile(path: Path) -> pd.DataFrame:
    profile = pd.read_parquet(path)
    missing = sorted(_REQUIRED_PROFILE_COLUMNS.difference(profile.columns))
    if missing:
        raise ValueError(f"OECD profile is missing required columns: {missing}")
    profile = profile.loc[profile["profile_complete"]].copy()
    if profile.empty:
        raise ValueError("OECD profile contains no complete comparison rows")
    if profile["region_code"].duplicated().any():
        raise ValueError("OECD profile contains duplicate complete region codes")
    if profile["year"].nunique() != 1 or profile["growth_start_year"].nunique() != 1:
        raise ValueError("OECD profile must contain one observation interval")
    if not profile["territorial_level"].eq("TL2").all():
        raise ValueError("OECD profile must contain only TL2 regions")
    for metric in METRICS:
        profile[metric.name] = pd.to_numeric(profile[metric.name], errors="raise")
        if not np.isfinite(profile[metric.name]).all():
            raise ValueError(f"Metric {metric.name} contains non-finite values")
        if metric.transform == "log10" and not profile[metric.name].gt(0).all():
            raise ValueError(f"Metric {metric.name} must be positive for log10")
    profile = profile.sort_values(
        ["country_name", "region_name", "region_code"],
        kind="stable",
        ignore_index=True,
    )
    return profile


def _read_time_series(
    path: Path | None,
    region_codes: set[str],
) -> pd.DataFrame:
    if path is None:
        time_series = pd.DataFrame(columns=sorted(_REQUIRED_TIME_SERIES_COLUMNS))
        return time_series
    time_series = pd.read_parquet(path)
    missing = sorted(_REQUIRED_TIME_SERIES_COLUMNS.difference(time_series.columns))
    if missing:
        raise ValueError(f"OECD time series is missing required columns: {missing}")
    time_series = time_series.loc[
        time_series["region_code"].astype(str).isin(region_codes)
        & time_series["value"].notna()
    ].copy()
    if not time_series["territorial_level"].eq("TL2").all():
        raise ValueError("OECD time series must contain only TL2 regions")
    indicators = set(time_series["indicator"].astype(str))
    missing_indicators = sorted(_EXPECTED_SERIES_INDICATORS.difference(indicators))
    if missing_indicators:
        raise ValueError(
            f"OECD time series is missing expected indicators: {missing_indicators}"
        )
    keys = ["region_code", "indicator", "year"]
    if time_series[keys].duplicated().any():
        raise ValueError("OECD time series contains duplicate region-indicator-years")
    time_series["year"] = pd.to_numeric(time_series["year"], errors="raise").astype(
        "int64"
    )
    time_series["value"] = pd.to_numeric(time_series["value"], errors="raise").astype(
        float
    )
    if not np.isfinite(time_series["value"]).all():
        raise ValueError("OECD time series contains non-finite values")
    time_series = time_series.sort_values(
        ["region_code", "indicator", "year"],
        kind="stable",
        ignore_index=True,
    )
    return time_series


def _read_history_table(
    path: Path,
    expected_indicator: str,
    region_codes: set[str],
) -> pd.DataFrame:
    history = pd.read_parquet(path)
    missing = sorted(_REQUIRED_TIME_SERIES_COLUMNS.difference(history.columns))
    if missing:
        raise ValueError(f"OECD history table is missing required columns: {missing}")
    indicators = set(history["indicator"].dropna().astype(str))
    if indicators != {expected_indicator}:
        raise ValueError(
            f"OECD history table must contain only {expected_indicator!r}; "
            f"found {sorted(indicators)}"
        )
    history = history.loc[
        history["region_code"].astype(str).isin(region_codes) & history["value"].notna()
    ].copy()
    if not history["territorial_level"].eq("TL2").all():
        raise ValueError("OECD history table must contain only TL2 regions")
    keys = ["region_code", "year"]
    if history[keys].duplicated().any():
        raise ValueError("OECD history table contains duplicate region-years")
    history["year"] = pd.to_numeric(history["year"], errors="raise").astype("int64")
    history["value"] = pd.to_numeric(history["value"], errors="raise").astype(float)
    if not np.isfinite(history["value"]).all():
        raise ValueError("OECD history table contains non-finite values")
    history = history.sort_values(keys, kind="stable", ignore_index=True)
    return history


def _read_age_structure(
    path: Path | None,
    region_codes: set[str],
) -> pd.DataFrame:
    if path is None:
        age_structure = pd.DataFrame(columns=sorted(_REQUIRED_AGE_STRUCTURE_COLUMNS))
        return age_structure
    age_structure = pd.read_parquet(path)
    missing = sorted(_REQUIRED_AGE_STRUCTURE_COLUMNS.difference(age_structure.columns))
    if missing:
        raise ValueError(f"OECD age structure is missing required columns: {missing}")
    age_structure = age_structure.loc[
        age_structure["region_code"].astype(str).isin(region_codes)
        & age_structure["share_percent"].notna()
        & age_structure["population"].notna()
    ].copy()
    if not age_structure["territorial_level"].eq("TL2").all():
        raise ValueError("OECD age structure must contain only TL2 regions")
    keys = ["region_code", "year", "age_group"]
    if age_structure[keys].duplicated().any():
        raise ValueError("OECD age structure contains duplicate region-year-age groups")
    age_structure["year"] = pd.to_numeric(age_structure["year"], errors="raise").astype(
        "int64"
    )
    for column in ["population", "share_percent"]:
        age_structure[column] = pd.to_numeric(
            age_structure[column], errors="raise"
        ).astype(float)
        if not np.isfinite(age_structure[column]).all():
            raise ValueError(f"OECD age structure contains non-finite {column}")
    if not age_structure["share_percent"].between(0, 100).all():
        raise ValueError("OECD age shares must be between 0 and 100")
    age_structure = age_structure.sort_values(keys, kind="stable", ignore_index=True)
    return age_structure


def _read_country_density(
    path: Path | None,
    country_codes: set[str],
) -> pd.DataFrame:
    if path is None:
        density = pd.DataFrame(columns=sorted(_REQUIRED_COUNTRY_DENSITY_COLUMNS))
        return density
    density = pd.read_parquet(path)
    missing = sorted(_REQUIRED_COUNTRY_DENSITY_COLUMNS.difference(density.columns))
    if missing:
        raise ValueError(f"GHSL country-density table is missing columns: {missing}")
    density = density.loc[
        density["country_code"].astype(str).isin(country_codes)
    ].copy()
    observed_codes = set(density["country_code"].astype(str))
    missing_codes = sorted(country_codes.difference(observed_codes))
    if missing_codes:
        raise ValueError(
            f"GHSL country-density table is missing countries: {missing_codes}"
        )
    keys = ["country_code", "density_bin_lower", "density_bin_upper"]
    if density[keys].duplicated().any():
        raise ValueError("GHSL country-density table contains duplicate bins")
    for column in [
        "density_bin_lower",
        "density_bin_upper",
        "density_bin_midpoint",
        "population",
        "population_share_percent",
    ]:
        density[column] = pd.to_numeric(density[column], errors="raise").astype(float)
        if not np.isfinite(density[column]).all():
            raise ValueError(f"GHSL country-density table contains non-finite {column}")
    shares = density.groupby("country_code")["population_share_percent"].sum()
    if not np.allclose(shares.to_numpy(dtype=float), 100, atol=1e-5):
        raise ValueError("GHSL country-density population shares must sum to 100")
    density = density.sort_values(keys, kind="stable", ignore_index=True)
    return density


def _history_payload(time_series: pd.DataFrame) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for region_code, group in time_series.groupby(
        "region_code",
        observed=True,
        sort=False,
    ):
        payload[str(region_code)] = {
            "label": str(group["indicator_label"].iloc[0]),
            "unit": str(group["unit"].iloc[0]),
            "observations": [
                {
                    "year": int(row.year),
                    "value": float(row.value),
                    "status": str(row.status),
                }
                for row in group.itertuples(index=False)
            ],
        }
    return payload


def _age_structure_payload(age_structure: pd.DataFrame) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for region_code, group in age_structure.groupby(
        "region_code",
        observed=True,
        sort=False,
    ):
        payload[str(region_code)] = [
            {
                "year": int(row.year),
                "age_group": str(row.age_group),
                "label": str(row.age_group_label),
                "population": float(row.population),
                "share_percent": float(row.share_percent),
                "status": str(row.status),
            }
            for row in group.itertuples(index=False)
        ]
    return payload


def _country_density_payload(density: pd.DataFrame) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for country_code, group in density.groupby(
        "country_code",
        observed=True,
        sort=False,
    ):
        payload[str(country_code)] = {
            "country_name": str(group["country_name"].iloc[0]),
            "epoch": int(group["epoch"].iloc[0]),
            "grid_resolution_m": int(group["grid_resolution_m"].iloc[0]),
            "bins": [
                {
                    "lower": float(row.density_bin_lower),
                    "upper": float(row.density_bin_upper),
                    "midpoint": float(row.density_bin_midpoint),
                    "population": float(row.population),
                    "share_percent": float(row.population_share_percent),
                }
                for row in group.itertuples(index=False)
            ],
        }
    return payload


def _transform_and_standardize(
    profile: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, float | str]]]:
    transformed = profile.copy()
    statistics: dict[str, dict[str, float | str]] = {}
    for metric in METRICS:
        values = profile[metric.name].astype(float)
        prepared = np.log10(values) if metric.transform == "log10" else values
        mean = float(prepared.mean())
        standard_deviation = float(prepared.std(ddof=0))
        if math.isclose(standard_deviation, 0):
            raise ValueError(f"Metric {metric.name} has zero variance")
        transformed[f"z_{metric.name}"] = (prepared - mean) / standard_deviation
        transformed[f"percentile_{metric.name}"] = (
            prepared.rank(method="average", pct=True) * 100
        )
        statistics[metric.name] = {
            "transform": metric.transform,
            "mean": mean,
            "standard_deviation": standard_deviation,
        }
    return transformed, statistics


def _similarity_score(distance: float) -> float:
    """Convert unbounded standardized distance to an intuitive 0–100 score."""

    score = 100.0 / (1.0 + distance)
    return score


def _region_record(row: Mapping[str, Any]) -> dict[str, Any]:
    values = {metric.name: float(row[metric.name]) for metric in METRICS}
    standardized = {metric.name: float(row[f"z_{metric.name}"]) for metric in METRICS}
    percentiles = {
        metric.name: float(row[f"percentile_{metric.name}"]) for metric in METRICS
    }
    record = {
        "region_code": str(row["region_code"]),
        "region_name": str(row["region_name"]),
        "country_code": str(row["country_code"]),
        "country_name": str(row["country_name"]),
        "values": values,
        "standardized": standardized,
        "percentiles": percentiles,
    }
    return record


def _variant_payload(
    profile: pd.DataFrame,
    focal_index: int,
    match_count: int,
) -> dict[str, Any]:
    focal = profile.loc[focal_index]
    candidate_mask = profile["country_code"].ne(focal["country_code"])
    candidates = profile.loc[candidate_mask].copy()
    if len(candidates) < match_count:
        raise ValueError(
            f"International comparison universe has only {len(candidates)} candidates"
        )

    weighted_squared = pd.DataFrame(index=candidates.index)
    for metric_name, weight in MATCHING["weights"].items():
        difference = candidates[f"z_{metric_name}"] - float(focal[f"z_{metric_name}"])
        weighted_squared[metric_name] = weight * difference.pow(2)
    weight_total = sum(MATCHING["weights"].values())
    candidates["distance"] = np.sqrt(weighted_squared.sum(axis=1) / weight_total)
    nearest = candidates.nsmallest(match_count, "distance", keep="first")

    ordered_candidates = candidates.sort_values(
        ["distance", "country_name", "region_name", "region_code"],
        kind="stable",
    )
    country_best = []
    for candidate in (
        ordered_candidates.groupby("country_code", sort=False, as_index=False)
        .first()
        .to_dict("records")
    ):
        distance = float(candidate["distance"])
        country_best.append(
            {
                "country_code": str(candidate["country_code"]),
                "country_name": str(candidate["country_name"]),
                "region_code": str(candidate["region_code"]),
                "region_name": str(candidate["region_name"]),
                "distance": distance,
                "similarity": _similarity_score(distance),
            }
        )
    country_best.sort(
        key=lambda item: (
            item["distance"],
            item["country_name"],
            item["region_name"],
        )
    )
    for country_rank, candidate in enumerate(country_best, start=1):
        candidate["country_rank"] = country_rank

    matches = []
    for rank, (index, candidate) in enumerate(nearest.iterrows(), start=1):
        squared = weighted_squared.loc[index]
        total = float(squared.sum())
        contribution = {
            metric: (float(value) / total if total > 0 else 0.0)
            for metric, value in squared.items()
        }
        matches.append(
            {
                "rank": rank,
                "distance": float(candidate["distance"]),
                "contribution": contribution,
                **_region_record(candidate),
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "focal": _region_record(focal),
        "matches": matches,
        "country_best": country_best,
    }
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    file_digest = digest.hexdigest()
    return file_digest


def _source_record(
    profile_path: Path,
    manifest_paths: Sequence[Path],
    supplemental_paths: Sequence[Path] = (),
) -> dict[str, Any]:
    source_manifests = []
    for manifest_path in sorted(manifest_paths):
        if not manifest_path.exists():
            raise FileNotFoundError(f"Source manifest does not exist: {manifest_path}")
        source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_manifests.append(
            {
                "dataset": source_manifest.get("dataset"),
                "install_id": source_manifest.get("install_id"),
                "filename": manifest_path.name,
                "sha256": _sha256_file(manifest_path),
                "source": source_manifest.get("source", {}),
            }
        )
    record: dict[str, Any] = {
        "profile_filename": profile_path.name,
        "profile_sha256": _sha256_file(profile_path),
        "profile_size_bytes": profile_path.stat().st_size,
        "source_manifests": source_manifests,
        "supplemental_files": [
            {
                "filename": path.name,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(supplemental_paths, key=lambda item: item.name)
        ],
    }
    return record


def _write_payload(payload: Mapping[str, Any], directory: Path) -> dict[str, Any]:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    destination = directory / f"{digest}.json.gz"
    if not destination.exists():
        destination.write_bytes(compressed)
    record = {
        "path": destination.relative_to(directory.parent).as_posix(),
        "sha256": digest,
        "size_bytes": len(compressed),
    }
    return record


def _digest_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return digest


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(value, temporary, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    # Published pointers and manifests must be readable by the non-root app process.
    temporary_path.chmod(0o644)
    temporary_path.replace(path)


# 3) Bundle stages
def _common_payload(
    profile: pd.DataFrame,
    transformed: pd.DataFrame,
    statistics: Mapping[str, Any],
    histories: Mapping[str, pd.DataFrame],
    age_structure: pd.DataFrame,
    country_density: pd.DataFrame,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "year": int(profile["year"].iloc[0]),
        "growth_start_year": int(profile["growth_start_year"].iloc[0]),
        "metrics": [metric.as_dict() for metric in METRICS],
        "statistics": statistics,
        "regions": [_region_record(row) for row in transformed.to_dict("records")],
        **{
            _HISTORY_PAYLOAD_KEYS[indicator]: _history_payload(history)
            for indicator, history in histories.items()
        },
        "age_structure": _age_structure_payload(age_structure),
        "country_density_distribution": _country_density_payload(country_density),
    }
    return payload


def _variant_records(
    transformed: pd.DataFrame,
    payload_dir: Path,
    match_count: int,
) -> list[dict[str, Any]]:
    variants = []
    for focal_index, focal in transformed.iterrows():
        payload = _variant_payload(
            transformed,
            focal_index=focal_index,
            match_count=match_count,
        )
        payload_record = _write_payload(payload, payload_dir)
        variants.append(
            {
                "key": {
                    "country_code": focal["country_code"],
                    "region_code": focal["region_code"],
                },
                **payload_record,
            }
        )
    return variants


def _write_bundle(
    output_dir: Path,
    bundle_dir: Path,
    build_id: str,
    source: Mapping[str, Any],
    configuration: Mapping[str, Any],
    profile: pd.DataFrame,
    transformed: pd.DataFrame,
    common: Mapping[str, Any],
    match_count: int,
) -> None:
    with TemporaryDirectory(prefix="place-twins-", dir=output_dir) as temporary:
        working = Path(temporary) / build_id
        payload_dir = working / "payloads"
        payload_dir.mkdir(parents=True)
        common_record = _write_payload(common, payload_dir)
        variants = _variant_records(transformed, payload_dir, match_count)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "build_id": build_id,
            "built_at": datetime.now(UTC).isoformat(),
            "source": source,
            "configuration": configuration,
            "region_count": len(profile),
            "country_count": int(profile["country_code"].nunique()),
            "variant_count": len(variants),
            "common_payload": common_record,
            "variants": variants,
        }
        _write_json_atomic(working / "manifest.json", manifest)
        bundle_dir.parent.mkdir(parents=True, exist_ok=True)
        working.replace(bundle_dir)


def _publish_current_bundle(output_dir: Path, manifest_path: Path) -> None:
    current = {"manifest": manifest_path.relative_to(output_dir).as_posix()}
    _write_json_atomic(output_dir / "current.json", current)


# 4) Bundle wrapper
def build_artifact_bundle(
    profile_path: Path | str,
    output_dir: Path | str,
    source_manifest_paths: Sequence[Path | str],
    time_series_path: Path | str | None = None,
    population_history_path: Path | str | None = None,
    unemployment_history_path: Path | str | None = None,
    income_history_path: Path | str | None = None,
    life_expectancy_history_path: Path | str | None = None,
    age_structure_path: Path | str | None = None,
    country_density_path: Path | str | None = None,
    match_count: int = MATCH_COUNT,
) -> Path:
    """Build and select one immutable artifact bundle, returning its manifest."""

    profile_path = Path(profile_path)
    output_dir = Path(output_dir)
    time_series_path = Path(time_series_path) if time_series_path is not None else None
    age_structure_path = (
        Path(age_structure_path) if age_structure_path is not None else None
    )
    country_density_path = (
        Path(country_density_path) if country_density_path is not None else None
    )
    history_paths = {
        "population": population_history_path,
        "unemployment_rate_percent": unemployment_history_path,
        "disposable_income_per_capita_usd_ppp": income_history_path,
        "life_expectancy_years": life_expectancy_history_path,
    }
    history_paths = {
        indicator: Path(path) if path is not None else None
        for indicator, path in history_paths.items()
    }
    supplied_histories = [path is not None for path in history_paths.values()]
    if any(supplied_histories) and not all(supplied_histories):
        raise ValueError("All four indicator-specific history tables are required")

    supplemental_paths = [
        time_series_path,
        *history_paths.values(),
        age_structure_path,
        country_density_path,
    ]
    if not profile_path.exists():
        raise FileNotFoundError(f"OECD regional profile does not exist: {profile_path}")
    for supplemental_path in supplemental_paths:
        if supplemental_path is not None and not supplemental_path.exists():
            raise FileNotFoundError(
                f"OECD supplemental artifact does not exist: {supplemental_path}"
            )
    if match_count < 1:
        raise ValueError("match_count must be positive")

    manifest_paths = tuple(Path(path) for path in source_manifest_paths)
    source = _source_record(
        profile_path,
        manifest_paths,
        supplemental_paths=[path for path in supplemental_paths if path is not None],
    )
    configuration = {
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "match_count": match_count,
        "metrics": [metric.as_dict() for metric in METRICS],
        "matching": MATCHING,
    }
    build_id = _digest_json({"source": source, "configuration": configuration})
    bundle_dir = output_dir / "bundles" / build_id
    manifest_path = bundle_dir / "manifest.json"
    if manifest_path.exists():
        _publish_current_bundle(output_dir, manifest_path)
        return manifest_path

    profile = _read_profile(profile_path)
    region_codes = set(profile["region_code"].astype(str))
    time_series = _read_time_series(time_series_path, region_codes)
    if all(supplied_histories):
        histories = {
            indicator: _read_history_table(path, indicator, region_codes)
            for indicator, path in history_paths.items()
            if path is not None
        }
    else:
        histories = {
            indicator: time_series.loc[time_series["indicator"].eq(indicator)].copy()
            for indicator in _EXPECTED_SERIES_INDICATORS
        }
    age_structure = _read_age_structure(age_structure_path, region_codes)
    country_codes = set(profile["country_code"].astype(str))
    country_density = _read_country_density(country_density_path, country_codes)
    transformed, statistics = _transform_and_standardize(profile)
    common = _common_payload(
        profile,
        transformed,
        statistics,
        histories,
        age_structure,
        country_density,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_bundle(
        output_dir,
        bundle_dir,
        build_id,
        source,
        configuration,
        profile,
        transformed,
        common,
        match_count,
    )
    _publish_current_bundle(output_dir, manifest_path)
    return manifest_path


# 5) Command line
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--time-series", type=Path)
    parser.add_argument("--population-history", type=Path)
    parser.add_argument("--unemployment-history", type=Path)
    parser.add_argument("--income-history", type=Path)
    parser.add_argument("--life-expectancy-history", type=Path)
    parser.add_argument("--age-structure", type=Path)
    parser.add_argument("--country-density", type=Path)
    parser.add_argument(
        "--source-manifest",
        dest="source_manifests",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--match-count", type=int, default=MATCH_COUNT)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = _parser().parse_args(argv)
    manifest_path = build_artifact_bundle(
        profile_path=arguments.profile,
        time_series_path=arguments.time_series,
        population_history_path=arguments.population_history,
        unemployment_history_path=arguments.unemployment_history,
        income_history_path=arguments.income_history,
        life_expectancy_history_path=arguments.life_expectancy_history,
        age_structure_path=arguments.age_structure,
        country_density_path=arguments.country_density,
        source_manifest_paths=arguments.source_manifests,
        output_dir=arguments.output,
        match_count=arguments.match_count,
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
