from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from dash_precompute import build_artifact_bundle


@pytest.fixture
def profile_path(tmp_path: Path) -> Path:
    records = [
        ("AA1", "Alpha North", "AAA", "Alpha", 1_000_000, 100, 2.0, 40_000),
        ("BB1", "Beta East", "BBB", "Beta", 1_050_000, 105, 2.1, 41_000),
        ("CC1", "Gamma South", "CCC", "Gamma", 5_000_000, 25, -1.0, 65_000),
        ("DD1", "Delta West", "DDD", "Delta", 800_000, 450, 6.0, 30_000),
    ]
    profile = pd.DataFrame(
        [
            {
                "year": 2023,
                "growth_start_year": 2018,
                "territorial_level": "TL2",
                "region_code": code,
                "region_name": name,
                "country_code": country_code,
                "country_name": country_name,
                "population": population,
                "population_density_per_km2": density,
                "population_change_percent": growth,
                "gdp_per_capita_usd_ppp": gdp,
                "profile_complete": True,
            }
            for (
                code,
                name,
                country_code,
                country_name,
                population,
                density,
                growth,
                gdp,
            ) in records
        ]
    )
    path = tmp_path / "regional_profile.parquet"
    profile.to_parquet(path, index=False)
    return path


@pytest.fixture
def time_series_path(tmp_path: Path, profile_path: Path) -> Path:
    profile = pd.read_parquet(profile_path)
    rows = []
    definitions = {
        "population": ("Population", "persons"),
        "unemployment_rate_percent": (
            "Unemployment rate, ages 15–64",
            "percent of labour force",
        ),
        "disposable_income_per_capita_usd_ppp": (
            "Disposable income per person, constant PPP",
            "constant US dollars per person, PPP converted",
        ),
        "life_expectancy_years": ("Life expectancy at birth", "years"),
    }
    multipliers = {
        "population": (0.94, 0.97, 1.0),
        "unemployment_rate_percent": (1.2, 2.0, 1.0),
        "disposable_income_per_capita_usd_ppp": (0.90, 0.94, 1.0),
        "life_expectancy_years": (0.99, 0.96, 1.0),
    }
    for region_index, region in profile.iterrows():
        bases = {
            "population": float(region["population"]),
            "unemployment_rate_percent": 3.5 + region_index,
            "disposable_income_per_capita_usd_ppp": 28_000 + 2_000 * region_index,
            "life_expectancy_years": 79.0 + 0.6 * region_index,
        }
        for indicator, (label, unit) in definitions.items():
            for year, multiplier in zip(
                [2018, 2020, 2023],
                multipliers[indicator],
                strict=True,
            ):
                rows.append(
                    {
                        "territorial_level": "TL2",
                        "region_code": region["region_code"],
                        "region_name": region["region_name"],
                        "country_code": region["country_code"],
                        "country_name": region["country_name"],
                        "indicator": indicator,
                        "indicator_label": label,
                        "year": year,
                        "value": bases[indicator] * multiplier,
                        "unit": unit,
                        "status": "A",
                        "status_label": "Normal value",
                    }
                )
    path = tmp_path / "regional_time_series.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture
def history_paths(tmp_path: Path, time_series_path: Path) -> dict[str, Path]:
    time_series = pd.read_parquet(time_series_path)
    filenames = {
        "population": "regional_population_history.parquet",
        "unemployment_rate_percent": "regional_unemployment_history.parquet",
        "disposable_income_per_capita_usd_ppp": "regional_income_history.parquet",
        "life_expectancy_years": "regional_life_expectancy_history.parquet",
    }
    paths = {}
    for indicator, filename in filenames.items():
        path = tmp_path / filename
        time_series.loc[time_series["indicator"].eq(indicator)].to_parquet(
            path,
            index=False,
        )
        paths[indicator] = path
    return paths


@pytest.fixture
def age_structure_path(tmp_path: Path, profile_path: Path) -> Path:
    profile = pd.read_parquet(profile_path)
    rows = []
    groups = [
        ("Y_LT15", "Under 15", 18.0),
        ("Y15T64", "15–64", 63.0),
        ("Y_GE65", "65+", 19.0),
    ]
    for region_index, region in profile.iterrows():
        shares = [
            groups[0][2] + region_index,
            groups[1][2] - region_index,
            groups[2][2],
        ]
        for (age_group, label, _), share in zip(groups, shares, strict=True):
            rows.append(
                {
                    "territorial_level": "TL2",
                    "region_code": region["region_code"],
                    "region_name": region["region_name"],
                    "country_code": region["country_code"],
                    "country_name": region["country_name"],
                    "year": 2023,
                    "age_group": age_group,
                    "age_group_label": label,
                    "population": float(region["population"]) * share / 100,
                    "share_percent": share,
                    "status": "A",
                    "status_label": "Normal value",
                }
            )
    path = tmp_path / "regional_age_structure.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture
def country_density_path(tmp_path: Path, profile_path: Path) -> Path:
    profile = pd.read_parquet(profile_path)
    edges = np.geomspace(1, 100_000, 25)
    rows = []
    for country_index, country in enumerate(
        profile[["country_code", "country_name"]]
        .drop_duplicates()
        .itertuples(index=False)
    ):
        midpoint = np.sqrt(edges[:-1] * edges[1:])
        centre = 1.7 + country_index * 0.35
        weights = np.exp(-0.5 * ((np.log10(midpoint) - centre) / 0.55) ** 2)
        weights = weights / weights.sum()
        for lower, upper, density, weight in zip(
            edges[:-1],
            edges[1:],
            midpoint,
            weights,
            strict=True,
        ):
            rows.append(
                {
                    "country_code": country.country_code,
                    "country_name": country.country_name,
                    "epoch": 2020,
                    "grid_resolution_m": 1000,
                    "density_bin_lower": lower,
                    "density_bin_upper": upper,
                    "density_bin_midpoint": density,
                    "populated_grid_cells": 10,
                    "population": weight * 1_000_000,
                    "population_share_percent": weight * 100,
                }
            )
    path = tmp_path / "country_population_density_distribution.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture
def artifact_dir(
    tmp_path: Path,
    profile_path: Path,
    history_paths: dict[str, Path],
    age_structure_path: Path,
    country_density_path: Path,
) -> Path:
    source_manifest = tmp_path / "source_manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "dataset": "synthetic_oecd_tl2_profile",
                "install_id": "source-install-1",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"
    build_artifact_bundle(
        profile_path=profile_path,
        population_history_path=history_paths["population"],
        unemployment_history_path=history_paths["unemployment_rate_percent"],
        income_history_path=history_paths["disposable_income_per_capita_usd_ppp"],
        life_expectancy_history_path=history_paths["life_expectancy_years"],
        age_structure_path=age_structure_path,
        country_density_path=country_density_path,
        source_manifest_paths=(source_manifest,),
        output_dir=output,
        match_count=2,
    )
    return output
