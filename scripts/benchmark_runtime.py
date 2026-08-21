"""Measure the interactive path over an existing Place Twins artifact bundle."""

# 0) Imports
from __future__ import annotations
import argparse
import statistics
import time
from pathlib import Path
import plotly.io as pio
from dash_precompute.catalog import ArtifactCatalog
from dash_precompute.figures import build_report_figures


# 1) Command line
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--country", default="CAN")
    parser.add_argument("--region", default="CA59")
    parser.add_argument("--repeats", type=int, default=7)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    if arguments.repeats < 1:
        raise ValueError("repeats must be positive")

    started = time.perf_counter()
    catalog = ArtifactCatalog(arguments.artifacts)
    catalog_ms = 1000 * (time.perf_counter() - started)
    started = time.perf_counter()
    variant = catalog.get(arguments.country, arguments.region)
    cold_variant_ms = 1000 * (time.perf_counter() - started)

    build_times = []
    serialization_times = []
    serialized_sizes = []
    for _repeat in range(arguments.repeats):
        started = time.perf_counter()
        figures = build_report_figures(catalog.common, variant)
        build_times.append(1000 * (time.perf_counter() - started))

        started = time.perf_counter()
        serialized = [pio.to_json(figure, pretty=False) for figure in figures.values()]
        serialization_times.append(1000 * (time.perf_counter() - started))
        serialized_sizes.append(sum(len(payload.encode()) for payload in serialized))

    focal = variant["focal"]
    print(f"Selection: {focal['region_name']}, {focal['country_name']}")
    print(f"Catalog initialization: {catalog_ms:.1f} ms")
    print(f"Cold variant resolution: {cold_variant_ms:.1f} ms")
    print(
        "Eight-figure reconstruction, median: "
        f"{statistics.median(build_times):.1f} ms"
    )
    print(
        "Eight-figure JSON serialization, median: "
        f"{statistics.median(serialization_times):.1f} ms"
    )
    print(
        "Eight-figure JSON size, median: "
        f"{statistics.median(serialized_sizes) / 1024:.1f} KiB"
    )


if __name__ == "__main__":
    main()
