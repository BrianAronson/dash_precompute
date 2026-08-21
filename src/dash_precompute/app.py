"""Dash application for exploring precomputed international region matches."""

# 0) Imports
from __future__ import annotations
import argparse
import hashlib
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate
from .catalog import ArtifactCatalog
from .figures import build_report_figures
from .layout import metric_cards, page_layout


# 1) Sub functions
def _application_version(assets_folder: Path) -> str:
    """Fingerprint the browser/server contract and static presentation assets."""

    digest = hashlib.sha256()
    package_dir = Path(__file__).parent
    paths = [Path(__file__), package_dir / "figures.py", package_dir / "layout.py"]
    paths.extend(sorted(assets_folder.glob("*.css")))
    paths.extend(sorted(assets_folder.glob("*.js")))
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    version = digest.hexdigest()[:16]
    return version


def _index_template(app_version: str) -> str:
    template = """<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <meta name="place-twins-app-version" content="__APP_VERSION__">
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>""".replace("__APP_VERSION__", app_version)
    return template


def _selection_is_valid(
    catalog: ArtifactCatalog,
    country_code: str | None,
    region_code: str | None,
) -> bool:
    is_valid = (
        country_code is not None
        and region_code is not None
        and catalog.contains_region(country_code, region_code)
    )
    return is_valid


def _register_callbacks(app: Dash, catalog: ArtifactCatalog) -> None:
    matching = catalog.manifest["configuration"]["matching"]

    @app.callback(
        output={
            "options": Output("region", "options"),
            "value": Output("region", "value"),
            "disabled": Output("region", "disabled"),
        },
        inputs={
            "country_code": Input("country", "value"),
            "current_region": State("region", "value"),
        },
    )
    def update_regions(
        country_code: str | None,
        current_region: str | None,
    ) -> dict[str, Any]:
        if country_code is None:
            empty_region_state = {"options": [], "value": None, "disabled": True}
            return empty_region_state

        options = catalog.region_options(country_code)
        values = [option["value"] for option in options]
        selected_region = current_region if current_region in values else None
        region_state = {
            "options": options,
            "value": selected_region,
            "disabled": not options,
        }
        return region_state

    @app.callback(
        Output("country", "value"),
        Input("reset-button", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_selection(_n_clicks: int | None) -> None:
        return None

    @app.callback(
        output={
            "kicker": Output("result-kicker", "children"),
            "title": Output("result-title", "children"),
            "note": Output("matching-note", "children"),
            "metrics": Output("metric-strip", "children"),
            "summary_style": Output("match-summary-card", "style"),
            "report_title": Output("report-title", "children"),
            "grid_style": Output("dashboard-grid", "style"),
        },
        inputs={
            "country_code": Input("country", "value"),
            "region_code": Input("region", "value"),
        },
    )
    def update_report_summary(
        country_code: str | None,
        region_code: str | None,
    ) -> dict[str, Any]:
        if not _selection_is_valid(catalog, country_code, region_code):
            empty_summary = {
                "kicker": "",
                "title": "",
                "note": "",
                "metrics": [],
                "summary_style": {"display": "none"},
                "report_title": "Select a country and region to view the report",
                "grid_style": {"display": "none"},
            }
            return empty_summary

        variant = catalog.get(country_code, region_code)
        focal = variant["focal"]
        closest = variant["matches"][0]
        summary = {
            "kicker": "CLOSEST INTERNATIONAL MATCH",
            "title": f"{closest['region_name']}, {closest['country_name']}",
            "note": f"For {focal['region_name']}: {matching['description']}",
            "metrics": metric_cards(focal, catalog.metrics),
            "summary_style": {},
            "report_title": "One selection, many analytical views",
            "grid_style": {},
        }
        return summary

    @app.callback(
        output={
            "similarity_map": Output("similarity-map", "figure"),
            "landscape": Output("landscape", "figure"),
            "metric_distributions": Output("metric-distributions", "figure"),
            "population_history": Output("population-history", "figure"),
            "country_ranking": Output("country-ranking", "figure"),
            "income_dumbbell": Output("income-dumbbell", "figure"),
            "age_structure": Output("age-structure", "figure"),
            "country_density": Output("country-density", "figure"),
        },
        inputs={
            "country_code": Input("country", "value"),
            "region_code": Input("region", "value"),
        },
    )
    def update_report_figures(
        country_code: str | None,
        region_code: str | None,
    ) -> dict[str, Any]:
        if not _selection_is_valid(catalog, country_code, region_code):
            raise PreventUpdate

        variant = catalog.get(country_code, region_code)
        figures = build_report_figures(catalog.common, variant)
        return figures


# 2) Application wrapper
def create_app(artifacts: Path | str = Path("artifacts")) -> Dash:
    """Create the application around one selected immutable artifact bundle."""

    catalog = ArtifactCatalog(artifacts)
    assets_folder = Path(__file__).parent / "assets"
    app = Dash(__name__, title="Place Twins", assets_folder=str(assets_folder))
    app_version = _application_version(assets_folder)
    app.index_string = _index_template(app_version)

    @app.server.get("/_place_twins/version")
    def application_version():
        return {"version": app_version}, {"Cache-Control": "no-store"}

    @app.server.get("/health")
    def health():
        return {"status": "ok", "build_id": catalog.build_id}

    app.layout = page_layout(catalog)
    _register_callbacks(app, catalog)
    return app


# 3) Command line
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path(os.environ.get("DASH_PRECOMPUTE_ARTIFACTS", "artifacts")),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = _parser().parse_args(argv)
    app = create_app(arguments.artifacts)
    app.run(host=arguments.host, port=arguments.port, debug=arguments.debug)


if __name__ == "__main__":
    main()
