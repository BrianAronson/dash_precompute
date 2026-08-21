"""Place Twins page structure and reusable layout components."""

# 0) Imports
from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any
from dash import dcc, html
from .catalog import ArtifactCatalog

GRAPH_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "responsive": True,
}


# 1) Components
def chart_card(
    graph_id: str,
    accessible_name: str,
    extra_class: str = "",
) -> html.Div:
    classes = " ".join(
        name
        for name in (
            "chart-card",
            "dashboard-card",
            "expandable-card",
            extra_class,
        )
        if name
    )
    card = html.Div(
        className=classes,
        children=[
            html.Button(
                "⤢",
                className="expand-button",
                type="button",
                title=f"Expand {accessible_name}",
                **{"aria-label": f"Expand {accessible_name}"},
            ),
            dcc.Graph(
                id=graph_id,
                figure={},
                config=GRAPH_CONFIG,
                responsive=True,
                className="dashboard-graph",
            ),
        ],
    )
    return card


def labeled_control(label: str, component: Any) -> html.Div:
    labeled_component = html.Div(
        className="control",
        children=[html.Label(label), component],
    )
    return labeled_component


def format_metric(value: float, format_spec: str) -> str:
    suffix = "%" if format_spec == "+.1f" else ""
    numeric_spec = format_spec.removeprefix("$")
    prefix = "$" if format_spec.startswith("$") else ""
    formatted_value = f"{prefix}{value:{numeric_spec}}{suffix}"
    return formatted_value


def ordinal(value: float) -> str:
    number = round(value)
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    formatted_ordinal = f"{number}{suffix}"
    return formatted_ordinal


def metric_cards(
    focal: Mapping[str, Any],
    metrics: Sequence[Mapping[str, Any]],
) -> list[html.Div]:
    cards = []
    for metric in metrics:
        value = focal["values"][metric["name"]]
        formatted = format_metric(value, str(metric["format"]))
        cards.append(
            html.Div(
                className="metric-card",
                children=[
                    html.Div(metric["short_label"], className="metric-label"),
                    html.Div(formatted, className="metric-value"),
                    html.Div(
                        f"{ordinal(focal['percentiles'][metric['name']])} percentile",
                        className="metric-percentile",
                    ),
                ],
            )
        )
    return cards


def page_header(catalog: ArtifactCatalog) -> html.Header:
    header = html.Header(
        className="hero",
        children=[
            html.Div(
                className="eyebrow",
                children="PRECOMPUTED REGIONAL COMPARISONS",
            ),
            html.H1("Place Twins"),
            html.P(
                "Find the large regions in other countries that most resemble "
                "the place you choose.",
                className="hero-copy",
            ),
            html.Div(
                className="source-line",
                children=[
                    html.Span("OECD TL2 regions"),
                    html.Span("•"),
                    html.Span(f"{catalog.manifest['region_count']} regions"),
                    html.Span("•"),
                    html.Span(f"{catalog.manifest['country_count']} countries"),
                ],
            ),
        ],
    )
    return header


def selection_card(catalog: ArtifactCatalog) -> html.Div:
    card = html.Div(
        className="selection-card",
        children=[
            html.Div(
                className="selection-card-heading",
                children=[
                    html.Div("USER SELECTION", className="section-label"),
                    html.Button(
                        "Reset",
                        id="reset-button",
                        className="reset-button",
                        type="button",
                    ),
                ],
            ),
            labeled_control(
                "Country",
                dcc.Dropdown(
                    id="country",
                    options=catalog.country_options(),
                    value=None,
                    clearable=False,
                    searchable=True,
                    maxHeight=360,
                    placeholder="Select a country",
                ),
            ),
            labeled_control(
                "Region",
                dcc.Dropdown(
                    id="region",
                    options=[],
                    value=None,
                    clearable=False,
                    searchable=True,
                    maxHeight=360,
                    placeholder="Select a region",
                    disabled=True,
                ),
            ),
        ],
    )
    return card


def match_summary_card() -> html.Div:
    card = html.Div(
        id="match-summary-card",
        className="result-intro match-summary-card",
        style={"display": "none"},
        children=[
            html.Div(
                className="result-heading",
                children=[
                    html.Div(id="result-kicker", className="result-kicker"),
                    html.H2(id="result-title"),
                    html.P(id="matching-note", className="result-note"),
                ],
            ),
            html.Div(
                className="metric-strip summary-metrics",
                id="metric-strip",
            ),
        ],
    )
    return card


def selection_panel(catalog: ArtifactCatalog) -> html.Section:
    panel = html.Section(
        className="control-panel",
        children=[selection_card(catalog), match_summary_card()],
    )
    return panel


def report_heading() -> html.Section:
    heading = html.Section(
        id="report-heading",
        className="report-heading",
        children=[
            html.Div("THE PRECOMPUTED REPORT", className="section-label"),
            html.H2(
                "Select a country and region to view the report",
                id="report-title",
            ),
            html.P("One precomputed artifact bundle updates every view."),
        ],
    )
    return heading


def report_grid() -> html.Section:
    grid = html.Section(
        id="dashboard-grid",
        className="dashboard-grid",
        style={"display": "none"},
        children=[
            chart_card("similarity-map", "country similarity map", "map-card"),
            chart_card("landscape", "regional landscape"),
            chart_card("metric-distributions", "metric distributions"),
            chart_card(
                "population-history",
                "population history",
                "history-card",
            ),
            chart_card("country-ranking", "strongest country counterparts"),
            chart_card("income-dumbbell", "real income dumbbell", "history-card"),
            chart_card("age-structure", "age structure comparison", "age-card"),
            chart_card(
                "country-density",
                "population-weighted local-density distribution",
                "history-card",
            ),
        ],
    )
    return grid


def source_footer(catalog: ArtifactCatalog) -> html.Footer:
    footer = html.Footer(
        children=[
            html.P(
                "Distances use standardized OECD population, density, "
                "2018–2023 population change, and GDP-per-person measures. "
                "Missing observations are excluded, not imputed."
            ),
            html.P(
                [
                    (
                        "Source: OECD Regions, Cities and Local Areas database. "
                        "Local-density distributions: European Commission JRC GHSL. "
                        "This is an independent adaptation and does not represent "
                        "the views of the OECD or its member countries."
                    ),
                    html.Br(),
                    html.Span(
                        f"Artifact build {catalog.build_id[:8]}",
                        className="build-id",
                    ),
                ]
            ),
        ]
    )
    return footer


# 2) Page wrapper
def page_layout(catalog: ArtifactCatalog) -> html.Div:
    """Build the empty selection state and eight coordinated report slots."""

    page = html.Div(
        className="page-shell",
        children=[
            page_header(catalog),
            html.Main(
                children=[
                    selection_panel(catalog),
                    report_heading(),
                    report_grid(),
                    source_footer(catalog),
                ]
            ),
        ],
    )
    return page
