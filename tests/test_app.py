from __future__ import annotations
from itertools import pairwise
import pytest
from dash_precompute.app import create_app
from dash_precompute.catalog import ArtifactCatalog
from dash_precompute.figures import (
    COLORS,
    _separate_label_y_shifts,
    build_report_figures,
    landscape_figure,
)


@pytest.fixture
def selected_report(artifact_dir):
    catalog = ArtifactCatalog(artifact_dir)
    variant = catalog.get("AAA", "AA1")
    figures = build_report_figures(catalog.common, variant)
    return catalog, variant, figures


def _walk_components(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, list):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            yield from _walk_components(child)


def test_population_endpoint_labels_are_separated_in_screen_space() -> None:
    values = [100.0, 101.0, 175.0, 176.0]
    shifts = _separate_label_y_shifts(values, low=90.0, high=185.0)
    original_positions = [178.0 * (value - 90.0) / 95.0 for value in values]
    adjusted_positions = sorted(
        position + shift
        for position, shift in zip(original_positions, shifts, strict=True)
    )

    assert all(right - left >= 11.9 for left, right in pairwise(adjusted_positions))


def test_landscape_reconstructs_from_selected_payload(artifact_dir) -> None:
    catalog = ArtifactCatalog(artifact_dir)
    variant = catalog.get(country_code="AAA", region_code="AA1")

    landscape = landscape_figure(catalog.common, variant)

    assert len(landscape.data) == 3
    assert "Alpha North" in landscape.layout.title.text


def test_report_reconstructs_eight_views_from_one_selected_payload(
    selected_report,
) -> None:
    catalog, _variant, figures = selected_report
    assert "time_series" not in catalog.common
    assert {
        "population_history",
        "unemployment_history",
        "income_history",
        "life_expectancy_history",
        "age_structure",
        "country_density_distribution",
    } <= catalog.common.keys()
    assert list(figures) == [
        "similarity_map",
        "landscape",
        "metric_distributions",
        "population_history",
        "country_ranking",
        "income_dumbbell",
        "age_structure",
        "country_density",
    ]
    assert figures["similarity_map"].layout.meta["analytical_role"] == (
        "country_best_counterpart_map"
    )
    assert figures["country_ranking"].data[0].type == "bar"
    assert figures["metric_distributions"].data[0].type == "violin"


def test_population_history_uses_actual_population(selected_report) -> None:
    _catalog, _variant, figures = selected_report
    population_history = figures["population_history"]
    assert len(population_history.data) == 4
    assert all(trace.type == "scatter" for trace in population_history.data)
    assert all(trace.mode == "lines+markers" for trace in population_history.data)
    assert all(float(trace.y[0]) > 100_000 for trace in population_history.data)
    assert population_history.layout.yaxis.title.text == "Population"
    assert population_history.layout.meta["analytical_role"] == (
        "absolute_population_paths"
    )
    assert "Population paths" in population_history.layout.title.text


def test_age_structure_compares_and_highlights_counterparts(selected_report) -> None:
    _catalog, _variant, figures = selected_report
    age_structure = figures["age_structure"]
    assert len(age_structure.data) == 3
    assert all(trace.type == "bar" for trace in age_structure.data)
    assert len(age_structure.data[0].y) == 3
    assert age_structure.layout.meta["analytical_role"] == ("counterpart_age_structure")
    closest_age_labels = [
        annotation
        for annotation in age_structure.layout.annotations
        if annotation.font.color == COLORS["attention"]
    ]
    selected_age_labels = [
        annotation
        for annotation in age_structure.layout.annotations
        if annotation.font.color == COLORS["focus"]
    ]
    assert len(closest_age_labels) == 1
    assert len(selected_age_labels) == 1
    for region_index in range(3):
        assert (
            abs(sum(float(trace.x[region_index]) for trace in age_structure.data) - 100)
            < 1e-9
        )


def test_income_change_is_a_multiregion_dumbbell(selected_report) -> None:
    _catalog, _variant, figures = selected_report
    income = figures["income_dumbbell"]
    assert [trace.mode for trace in income.data[:-2]] == ["lines"] * 4
    assert [trace.mode for trace in income.data[-2:]] == ["markers", "markers"]
    assert len(set(income.data[-1].y)) == 4
    assert income.data[-2].marker.symbol == "circle-open"
    assert income.data[-1].marker.symbol == "circle"
    assert income.layout.meta["analytical_role"] == "income_change_dumbbell"
    assert "Real income change across counterparts" in income.layout.title.text


def test_density_curves_compare_country_grid_distributions(selected_report) -> None:
    _catalog, _variant, figures = selected_report
    country_density = figures["country_density"]
    assert [trace.type for trace in country_density.data] == ["scatter", "scatter"]
    assert all(trace.fill == "tozeroy" for trace in country_density.data)
    assert country_density.layout.xaxis.type == "log"
    assert country_density.layout.meta["analytical_role"] == (
        "population_weighted_local_density"
    )
    assert "Where people live" in country_density.layout.title.text


def test_dash_app_serves_the_precomputed_dashboard(artifact_dir) -> None:
    app = create_app(artifact_dir)
    client = app.server.test_client()
    response = client.get("/")
    version = client.get("/_place_twins/version")
    health = client.get("/health")

    assert response.status_code == 200
    assert b"Place Twins" in response.data
    assert b"place-twins-app-version" in response.data
    assert version.status_code == 200
    assert len(version.json["version"]) == 16
    assert version.headers["Cache-Control"] == "no-store"
    assert health.status_code == 200
    assert health.json == {
        "status": "ok",
        "build_id": ArtifactCatalog(artifact_dir).build_id,
    }


def test_dashboard_exposes_compact_expandable_chart_cards(artifact_dir) -> None:
    app = create_app(artifact_dir)
    components = list(_walk_components(app.layout))
    class_names = [
        getattr(component, "className", "") or "" for component in components
    ]

    assert class_names.count("dashboard-grid") == 1
    assert class_names.count("selection-card") == 1
    assert class_names.count("result-intro match-summary-card") == 1
    assert sum("expand-button" in name.split() for name in class_names) == 8
    assert sum("expandable-card" in name.split() for name in class_names) == 8
    component_ids = {getattr(component, "id", None) for component in components}
    components_by_id = {
        component.id: component
        for component in components
        if getattr(component, "id", None) is not None
    }
    assert {
        "country",
        "region",
        "reset-button",
        "match-summary-card",
        "report-heading",
        "report-title",
        "dashboard-grid",
        "population-history",
        "country-ranking",
        "income-dumbbell",
        "age-structure",
        "country-density",
    } <= component_ids
    assert components_by_id["country"].value is None
    assert components_by_id["region"].value is None
    assert components_by_id["region"].disabled is True
    assert components_by_id["report-title"].children.startswith("Select a country")
    assert components_by_id["dashboard-grid"].style == {"display": "none"}
    graph_ids = {
        "similarity-map",
        "landscape",
        "metric-distributions",
        "population-history",
        "country-ranking",
        "income-dumbbell",
        "age-structure",
        "country-density",
    }
    assert all(components_by_id[graph_id].figure == {} for graph_id in graph_ids)
    assert "comparison" not in component_ids
    assert "lens" not in component_ids
    assert "pool" not in component_ids
    assert "download-button" not in component_ids
    assert "download" not in component_ids
    assert "unemployment-heatmap" not in component_ids
    assert "life-expectancy-box" not in component_ids
