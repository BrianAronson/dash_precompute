"""Declared comparison measures for the Place Twins demonstration."""

from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    short_label: str
    transform: str
    format: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


METRICS = (
    Metric(
        name="population",
        label="Population",
        short_label="Population",
        transform="log10",
        format=",.0f",
    ),
    Metric(
        name="population_density_per_km2",
        label="Population density",
        short_label="Density",
        transform="log10",
        format=",.1f",
    ),
    Metric(
        name="population_change_percent",
        label="Population change, 2018–2023",
        short_label="Growth",
        transform="identity",
        format="+.1f",
    ),
    Metric(
        name="gdp_per_capita_usd_ppp",
        label="GDP per capita, PPP",
        short_label="GDP / person",
        transform="log10",
        format="$,.0f",
    ),
)

MATCHING = {
    "description": (
        "Equal weight on population, density, recent growth, and GDP per person; "
        "matches must come from another country."
    ),
    "cross_country": True,
    "weights": {metric.name: 1.0 for metric in METRICS},
}
MATCH_COUNT = 8
