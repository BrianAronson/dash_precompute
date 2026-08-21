"""Demo-specific Plotly reconstruction from precomputed regional payloads."""

# 0) Imports
from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .visual_policy import COLORS, MAP_COLORS, style_figure


# 2) Figure subfunctions
def _series_values(
    common: Mapping[str, Any],
    region_code: str,
    indicator: str,
) -> dict[int, float]:
    payload_keys = {
        "population": "population_history",
        "unemployment_rate_percent": "unemployment_history",
        "disposable_income_per_capita_usd_ppp": "income_history",
        "life_expectancy_years": "life_expectancy_history",
    }
    series = (
        common.get(payload_keys[indicator], {})
        .get(str(region_code), {})
        .get("observations", [])
    )
    values = {
        int(observation["year"]): float(observation["value"])
        for observation in series
    }
    return values


def _counterpart_cohort(
    variant: Mapping[str, Any],
    max_regions: int,
) -> list[Mapping[str, Any]]:
    """Return the focal region followed by unique, strongest counterparts."""

    country_best = sorted(
        variant["country_best"],
        key=lambda region: int(region["country_rank"]),
    )
    candidates = [variant["focal"], variant["matches"][0], *country_best]
    cohort = []
    seen = set()
    for region in candidates:
        code = str(region["region_code"])
        if code in seen:
            continue
        seen.add(code)
        cohort.append(region)
        if len(cohort) == max_regions:
            break
    return cohort


def _short_label(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    shortened = f"{value[: limit - 1].rstrip()}…"
    return shortened


def _separate_label_y_shifts(
    values: Sequence[float],
    low: float,
    high: float,
    plot_height: float = 178.0,
    minimum_gap: float = 12.0,
) -> list[float]:
    """Return small pixel shifts that keep endpoint labels from colliding."""

    if not values or high <= low:
        return [0.0] * len(values)
    positions = [plot_height * (value - low) / (high - low) for value in values]
    order = sorted(range(len(values)), key=positions.__getitem__)
    adjusted = [positions[index] for index in order]
    for index in range(1, len(adjusted)):
        adjusted[index] = max(adjusted[index], adjusted[index - 1] + minimum_gap)
    overflow = max(0.0, adjusted[-1] - plot_height)
    if overflow:
        adjusted = [position - overflow for position in adjusted]
    for index in range(len(adjusted) - 2, -1, -1):
        adjusted[index] = min(adjusted[index], adjusted[index + 1] - minimum_gap)
    underflow = max(0.0, -adjusted[0])
    if underflow:
        adjusted = [position + underflow for position in adjusted]
    shifts = [0.0] * len(values)
    for sorted_index, original_index in enumerate(order):
        shifts[original_index] = round(
            adjusted[sorted_index] - positions[original_index], 1
        )
    return shifts


def _rgba(color: str, opacity: float) -> str:
    value = color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"Expected a six-digit hex color; received {color!r}")
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    rgba = f"rgba({red}, {green}, {blue}, {opacity})"
    return rgba


def _age_values(
    common: Mapping[str, Any],
    region_code: str,
) -> dict[int, dict[str, Mapping[str, Any]]]:
    expected = {"Y_LT15", "Y15T64", "Y_GE65"}
    by_year: dict[int, dict[str, Mapping[str, Any]]] = {}
    for record in common.get("age_structure", {}).get(str(region_code), []):
        by_year.setdefault(int(record["year"]), {})[str(record["age_group"])] = record
    complete_years = {
        year: records for year, records in by_year.items() if set(records) == expected
    }
    return complete_years


def _empty_figure(title: str, message: str, height: int = 300) -> go.Figure:
    figure = go.Figure()
    style_figure(
        figure,
        title=title,
        height=height,
        left_margin=24,
        right_margin=24,
        bottom_margin=24,
        grid="none",
    )
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        align="center",
        font={"color": COLORS["muted_text"], "size": 11},
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return figure


def _format_metric_value(value: float, format_spec: str) -> str:
    suffix = "%" if format_spec == "+.1f" else ""
    prefix = "$" if format_spec.startswith("$") else ""
    numeric_spec = format_spec.removeprefix("$")
    formatted_value = f"{prefix}{value:{numeric_spec}}{suffix}"
    return formatted_value


# 3) Figure operations
def landscape_figure(
    common: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> go.Figure:
    """Place the focal region and its matches in density/GDP space."""

    regions = common["regions"]
    focal = variant["focal"]
    matches = variant["matches"]
    match_codes = {match["region_code"] for match in matches}
    background = [
        region
        for region in regions
        if region["region_code"] != focal["region_code"]
        and region["region_code"] not in match_codes
    ]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[r["values"]["population_density_per_km2"] for r in background],
            y=[r["values"]["gdp_per_capita_usd_ppp"] for r in background],
            mode="markers",
            marker={"size": 7, "color": COLORS["context"], "opacity": 0.56},
            customdata=[
                [
                    r["region_name"],
                    r["country_name"],
                    r["values"]["population"],
                    r["values"]["population_change_percent"],
                ]
                for r in background
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                "Density: %{x:,.1f} / km²<br>GDP / person: %{y:$,.0f}<br>"
                "Population: %{customdata[2]:,.0f}<br>"
                "2018–23 change: %{customdata[3]:+.1f}%<extra></extra>"
            ),
            name="Other regions",
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[m["values"]["population_density_per_km2"] for m in matches],
            y=[m["values"]["gdp_per_capita_usd_ppp"] for m in matches],
            mode="markers+text",
            marker={
                "size": [14 if m["rank"] == 1 else 10 for m in matches],
                "color": COLORS["attention"],
                "line": {"color": COLORS["paper"], "width": 1.5},
            },
            text=[m["region_name"] if m["rank"] == 1 else "" for m in matches],
            textposition=[
                "top right" if m["rank"] == 1 else "top center" for m in matches
            ],
            customdata=[
                [
                    m["rank"],
                    m["region_name"],
                    m["country_name"],
                    m["values"]["population"],
                    m["values"]["population_change_percent"],
                ]
                for m in matches
            ],
            hovertemplate=(
                "<b>#%{customdata[0]} %{customdata[1]}</b><br>%{customdata[2]}<br>"
                "Density: %{x:,.1f} / km²<br>GDP / person: %{y:$,.0f}<br>"
                "Population: %{customdata[3]:,.0f}<br>"
                "2018–23 change: %{customdata[4]:+.1f}%<extra></extra>"
            ),
            name="Closest matches",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[focal["values"]["population_density_per_km2"]],
            y=[focal["values"]["gdp_per_capita_usd_ppp"]],
            mode="markers+text",
            marker={
                "size": 18,
                "color": COLORS["focus"],
                "symbol": "diamond",
                "line": {"color": COLORS["paper"], "width": 2},
            },
            text=[focal["region_name"]],
            textposition="bottom left",
            hovertemplate=(
                f"<b>{focal['region_name']}</b><br>{focal['country_name']}<br>"
                "Density: %{x:,.1f} / km²<br>GDP / person: %{y:$,.0f}<extra></extra>"
            ),
            name="Selected region",
        )
    )
    style_figure(
        figure,
        title=f"Regional landscape: {focal['region_name']}",
        subtitle=f"{len(regions):,} OECD TL2 profiles · log axes",
        x_label="Population density (people per km²)",
        y_label="GDP per person (PPP USD)",
        height=320,
        left_margin=58,
        right_margin=14,
        bottom_margin=44,
        grid="both",
    )
    figure.update_xaxes(
        type="log",
        dtick=1,
    )
    figure.update_yaxes(
        type="log",
        dtick=1,
        tickprefix="$",
        tickformat="~s",
    )
    figure.update_layout(
        margin={"l": 58, "r": 14, "t": 94, "b": 44},
        legend={
            "orientation": "h",
            "x": 1,
            "y": 1.02,
            "xanchor": "right",
            "yanchor": "bottom",
            "font": {"size": 9},
        },
    )
    return figure


def similarity_map_figure(variant: Mapping[str, Any]) -> go.Figure:
    """Map each country's closest precomputed regional counterpart."""

    focal = variant["focal"]
    country_best = pd.DataFrame(variant["country_best"])
    country_best["map_label"] = (
        country_best["country_name"]
        + "<br>Best regional match: "
        + country_best["region_name"]
    )
    score_range = (
        float(country_best["similarity"].min()),
        float(country_best["similarity"].max()),
    )
    if score_range[0] >= score_range[1]:
        score_range = (score_range[0] - 1.0, score_range[1] + 1.0)
    colorscale = [
        [index / (len(MAP_COLORS) - 1), color]
        for index, color in enumerate(MAP_COLORS)
    ]
    figure = go.Figure(
        go.Choropleth(
            locations=country_best["country_code"],
            z=country_best["similarity"],
            locationmode="ISO-3",
            text=country_best["map_label"],
            zmin=score_range[0],
            zmax=score_range[1],
            colorscale=colorscale,
            marker={"line": {"color": COLORS["axis"], "width": 0.7}},
            colorbar={"title": {"text": "Similarity"}, "thickness": 13},
            hovertemplate=(
                "%{text}<br>Similarity: %{z:.0f} / 100<extra></extra>"
            ),
        )
    )
    style_figure(
        figure,
        title="Best regional counterpart by country",
        subtitle=(
            f"Closest TL2 region to {focal['region_name']} per country · "
            "full-range sequential scale"
        ),
        height=310,
        left_margin=6,
        right_margin=54,
        bottom_margin=10,
        show_legend=False,
    )
    figure.update_layout(
        margin={"l": 6, "r": 54, "t": 66, "b": 10},
        meta={"analytical_role": "country_best_counterpart_map"},
    )
    figure.update_geos(
        bgcolor=COLORS["paper"],
        projection={"type": "natural earth"},
        showframe=False,
        showcoastlines=False,
        showland=True,
        landcolor=COLORS["missing"],
        showocean=True,
        oceancolor=COLORS["paper"],
        lakecolor=COLORS["paper"],
    )
    return figure


def population_history_figure(
    common: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> go.Figure:
    """Show actual population paths for the selected region and top counterparts."""

    focal = variant["focal"]
    cohort = []
    for region in _counterpart_cohort(variant, max_regions=4):
        series = _series_values(common, region["region_code"], "population")
        if len(series) >= 2:
            cohort.append((region, series))
    if len(cohort) < 2:
        figure = _empty_figure(
            title="Population paths",
            message="Too few annual population histories are available for comparison.",
        )
        return figure

    figure = go.Figure()
    all_values: list[float] = []
    endpoints: list[tuple[int, float, str, str]] = []
    line_styles = [
        (COLORS["focus"], "diamond", "solid", 2.8),
        (COLORS["attention"], "circle", "solid", 2.6),
        (COLORS["context"], "square", "dash", 1.8),
        (COLORS["context"], "triangle-up", "dot", 1.8),
    ]
    for (region, series), (color, symbol, dash, width) in zip(
        cohort,
        line_styles,
        strict=True,
    ):
        years = sorted(series)
        values = [series[year] for year in years]
        all_values.extend(values)
        figure.add_trace(
            go.Scatter(
                x=years,
                y=values,
                mode="lines+markers",
                line={"color": color, "width": width, "dash": dash},
                marker={"color": color, "size": 5, "symbol": symbol},
                hovertemplate=(
                    f"<b>{region['region_name']}</b><br>"
                    "%{x}: %{y:,.0f} people<extra></extra>"
                ),
                name=str(region["region_name"]),
                showlegend=False,
            )
        )
        endpoints.append((years[-1], values[-1], str(region["region_name"]), color))
    low, high = min(all_values), max(all_values)
    padding = max(1.0, (high - low) * 0.10)
    y_min = max(0, low - padding)
    y_max = high + padding
    label_shifts = _separate_label_y_shifts(
        [value for _, value, _, _ in endpoints],
        low=y_min,
        high=y_max,
    )
    for (end_year, value, label, color), yshift in zip(
        endpoints,
        label_shifts,
        strict=True,
    ):
        figure.add_annotation(
            x=end_year,
            y=value,
            text=_short_label(label, limit=17),
            showarrow=False,
            xanchor="left",
            xshift=6,
            yshift=yshift,
            font={"color": color, "size": 9},
        )
    first_year = min(min(series) for _, series in cohort)
    last_year = max(max(series) for _, series in cohort)
    style_figure(
        figure,
        title="Population paths",
        subtitle=f"Actual population · {focal['region_name']} plus strongest counterparts",
        x_label="Year",
        y_label="Population",
        height=300,
        left_margin=62,
        right_margin=86,
        bottom_margin=44,
        grid="both",
    )
    figure.update_xaxes(
        tickmode="array",
        tickvals=list(range(first_year, last_year + 1))[
            :: max(1, (last_year - first_year + 1) // 5)
        ],
        tickformat="d",
        range=[first_year, last_year + max(1, (last_year - first_year) * 0.16)],
    )
    figure.update_yaxes(
        range=[y_min, y_max],
        tickformat="~s",
    )
    figure.update_layout(
        margin={"l": 62, "r": 92, "t": 66, "b": 44},
        meta={
            **(figure.layout.meta or {}),
            "analytical_role": "absolute_population_paths",
        },
    )
    return figure


def age_structure_figure(
    common: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> go.Figure:
    """Compare broad age composition across the closest regional matches."""

    focal = variant["focal"]
    cohort: list[tuple[Mapping[str, Any], dict[int, dict[str, Mapping[str, Any]]]]] = []
    common_years: set[int] | None = None
    for region in [focal, *variant["matches"]]:
        values = _age_values(common, region["region_code"])
        if not values:
            continue
        candidate_years = set(values)
        overlap = (
            candidate_years if common_years is None else common_years & candidate_years
        )
        if not overlap:
            continue
        cohort.append((region, values))
        common_years = overlap
        if len(cohort) == 6:
            break
    if len(cohort) < 2 or common_years is None:
        figure = _empty_figure(
            title="Age structure across counterparts",
            message="Too few matches share a broad-age profile in one year.",
        )
        return figure

    year = max(common_years)
    regions = [region for region, _ in cohort]
    labels = [str(region["region_name"]) for region in regions]
    group_order = ["Y_LT15", "Y15T64", "Y_GE65"]
    group_colors = [COLORS["focus"], "#FAB16C", "#C670E0"]
    figure = go.Figure()
    for age_group, color in zip(group_order, group_colors, strict=True):
        records = [values[year][age_group] for _, values in cohort]
        shares = [float(record["share_percent"]) for record in records]
        populations = [float(record["population"]) for record in records]
        figure.add_trace(
            go.Bar(
                x=shares,
                y=labels,
                orientation="h",
                marker={"color": color, "line": {"width": 0}},
                text=[f"{share:.0f}%" if share >= 8 else "" for share in shares],
                textposition="inside",
                insidetextanchor="middle",
                customdata=populations,
                hovertemplate=(
                    f"<b>{records[0]['label']}</b><br>"
                    "%{y}: %{x:.1f}%<br>"
                    "%{customdata:,.0f} people<extra></extra>"
                ),
                name=str(records[0]["label"]),
            )
        )
    style_figure(
        figure,
        title="Age structure across counterparts",
        subtitle=(
            f"Selected region plus {len(cohort) - 1} closest matches · "
            f"latest common year {year}"
        ),
        x_label="Share of population",
        height=300,
        left_margin=112,
        right_margin=14,
        bottom_margin=42,
        grid="x",
    )
    figure.update_xaxes(range=[0, 100], ticksuffix="%", dtick=25)
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=list(reversed(labels)),
        showticklabels=False,
    )
    focal_code = str(focal["region_code"])
    closest_code = str(variant["matches"][0]["region_code"])
    for region, label in zip(regions, labels, strict=True):
        region_code = str(region["region_code"])
        highlighted = region_code in {focal_code, closest_code}
        label_color = (
            COLORS["focus"]
            if region_code == focal_code
            else (
                COLORS["attention"]
                if region_code == closest_code
                else COLORS["muted_text"]
            )
        )
        figure.add_annotation(
            x=-0.025,
            y=label,
            xref="paper",
            yref="y",
            text=(
                f"<b>{_short_label(label, limit=18)}</b>"
                if highlighted
                else _short_label(label, limit=18)
            ),
            showarrow=False,
            xanchor="right",
            align="right",
            font={
                "color": label_color,
                "size": 9,
            },
        )
    figure.update_layout(
        barmode="stack",
        bargap=0.22,
        margin={"l": 112, "r": 14, "t": 94, "b": 42},
        legend={
            "orientation": "h",
            "x": 1,
            "y": 1.02,
            "xanchor": "right",
            "yanchor": "bottom",
            "font": {"size": 9},
            "traceorder": "normal",
        },
        uniformtext={"mode": "hide", "minsize": 9},
        meta={"analytical_role": "counterpart_age_structure"},
    )
    return figure


def country_density_figure(
    common: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> go.Figure:
    """Compare where residents live along the local-density spectrum."""

    focal = variant["focal"]
    comparison = variant["matches"][0]
    distributions = common.get("country_density_distribution", {})
    focal_distribution = distributions.get(str(focal["country_code"]))
    comparison_distribution = distributions.get(str(comparison["country_code"]))
    if not focal_distribution or not comparison_distribution:
        figure = _empty_figure(
            title="Where people live by local density",
            message="No gridded population-density distribution is available for this pair.",
        )
        return figure

    log_grid = np.linspace(-1, 5.3, 240)
    bandwidth = 0.18
    figure = go.Figure()
    for region, payload, color, opacity, width in [
        (comparison, comparison_distribution, COLORS["attention"], 0.30, 2.2),
        (focal, focal_distribution, COLORS["focus"], 0.38, 2.6),
    ]:
        bins = [item for item in payload["bins"] if float(item["population"]) > 0]
        log_density = np.log10(
            np.asarray([item["midpoint"] for item in bins], dtype=float)
        )
        population = np.asarray(
            [item["population"] for item in bins],
            dtype=float,
        )
        weights = population / population.sum()
        differences = (log_grid[:, None] - log_density[None, :]) / bandwidth
        density = (
            np.exp(-0.5 * differences**2) @ weights / (bandwidth * np.sqrt(2 * np.pi))
        )
        country_name = str(region["country_name"])
        figure.add_trace(
            go.Scatter(
                x=np.power(10.0, log_grid),
                y=density,
                mode="lines",
                line={"color": color, "width": width},
                fill="tozeroy",
                fillcolor=_rgba(color, opacity),
                name=country_name,
                hovertemplate=(
                    f"<b>{country_name}</b><br>"
                    "Local density: %{x:,.0f} people / km²<extra></extra>"
                ),
            )
        )
    epoch = int(focal_distribution["epoch"])
    style_figure(
        figure,
        title="Where people live by local density",
        subtitle=(f"Residents across 1 km grid cells · {epoch} GHSL population grid"),
        x_label="Local population density (people per km²)",
        y_label="Resident-weighted density",
        height=300,
        left_margin=52,
        right_margin=16,
        bottom_margin=44,
        grid="x",
    )
    figure.update_xaxes(
        type="log",
        range=[-1, 5.3],
        tickvals=[1, 10, 100, 1_000, 10_000, 100_000],
        ticktext=["1", "10", "100", "1k", "10k", "100k"],
    )
    figure.update_yaxes(
        rangemode="tozero",
        showticklabels=False,
        title_text=None,
        showgrid=False,
    )
    figure.update_layout(
        margin={"l": 26, "r": 16, "t": 94, "b": 44},
        legend={
            "orientation": "h",
            "x": 1,
            "y": 1.02,
            "xanchor": "right",
            "yanchor": "bottom",
            "font": {"size": 9},
        },
        meta={
            "analytical_role": "population_weighted_local_density",
            "bandwidth_log10": bandwidth,
            "unit_of_observation": "resident weighted by 1 km grid-cell population",
        },
    )
    return figure


def income_dumbbell_figure(
    common: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> go.Figure:
    """Compare real-income change across a cohort of top counterparts."""

    cohort: list[tuple[Mapping[str, Any], dict[int, float]]] = []
    common_years: set[int] | None = None
    for region in _counterpart_cohort(variant, max_regions=10):
        series = _series_values(
            common,
            region["region_code"],
            "disposable_income_per_capita_usd_ppp",
        )
        if len(series) < 2:
            continue
        candidate_years = set(series)
        overlap = (
            candidate_years if common_years is None else common_years & candidate_years
        )
        if len(overlap) < 2:
            continue
        cohort.append((region, series))
        common_years = overlap
        if len(cohort) == 6:
            break
    if len(cohort) < 3 or common_years is None:
        figure = _empty_figure(
            title="Real income change across counterparts",
            message="Too few regions share a comparable real-income interval.",
        )
        return figure

    start_year, end_year = min(common_years), max(common_years)
    regions = [region for region, _ in cohort]
    starts = [series[start_year] for _, series in cohort]
    ends = [series[end_year] for _, series in cohort]
    labels = [str(region["region_name"]) for region in regions]
    colors = [
        COLORS["focus"],
        COLORS["attention"],
        *([COLORS["context"]] * max(0, len(regions) - 2)),
    ]
    figure = go.Figure()
    for label, start, end, color in zip(
        labels,
        starts,
        ends,
        colors,
        strict=True,
    ):
        figure.add_trace(
            go.Scatter(
                x=[start, end],
                y=[label, label],
                mode="lines",
                line={"color": color, "width": 3},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    changes = [end - start for start, end in zip(starts, ends, strict=True)]
    change_percent = [
        100 * (end / start - 1) for start, end in zip(starts, ends, strict=True)
    ]
    figure.add_trace(
        go.Scatter(
            x=starts,
            y=labels,
            mode="markers",
            marker={
                "color": colors,
                "size": 11,
                "symbol": "circle-open",
                "line": {"width": 2},
            },
            customdata=[
                [end, change, percent]
                for end, change, percent in zip(
                    ends,
                    changes,
                    change_percent,
                    strict=True,
                )
            ],
            hovertemplate=(
                f"<b>%{{y}}</b><br>{start_year}: $%{{x:,.0f}}<br>"
                f"{end_year}: $%{{customdata[0]:,.0f}}<br>"
                "Change: $%{customdata[1]:+,.0f} (%{customdata[2]:+.1f}%)"
                "<extra></extra>"
            ),
            name=str(start_year),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=ends,
            y=labels,
            mode="markers",
            marker={"color": colors, "size": 11, "symbol": "circle"},
            customdata=[
                [start, change, percent]
                for start, change, percent in zip(
                    starts,
                    changes,
                    change_percent,
                    strict=True,
                )
            ],
            hovertemplate=(
                f"<b>%{{y}}</b><br>{start_year}: $%{{customdata[0]:,.0f}}<br>"
                f"{end_year}: $%{{x:,.0f}}<br>"
                "Change: $%{customdata[1]:+,.0f} (%{customdata[2]:+.1f}%)"
                "<extra></extra>"
            ),
            name=str(end_year),
        )
    )
    low, high = min([*starts, *ends]), max([*starts, *ends])
    padding = max(2500, (high - low) * 0.18)
    style_figure(
        figure,
        title="Real income change across counterparts",
        subtitle=f"{start_year} to {end_year} · selected region plus strongest counterparts",
        x_label="Income per person (PPP USD)",
        height=300,
        left_margin=112,
        right_margin=18,
        bottom_margin=44,
        grid="x",
    )
    figure.update_xaxes(
        range=[low - padding, high + padding],
        tickprefix="$",
        tickformat="~s",
    )
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=list(reversed(labels)),
    )
    figure.update_layout(
        margin={"l": 112, "r": 18, "t": 94, "b": 44},
        legend={
            "orientation": "h",
            "x": 1,
            "y": 1.02,
            "xanchor": "right",
            "yanchor": "bottom",
            "font": {"size": 9},
        },
        meta={"analytical_role": "income_change_dumbbell"},
    )
    return figure


def country_ranking_figure(variant: Mapping[str, Any]) -> go.Figure:
    """Rank the strongest country-level regional counterparts."""

    country_best = pd.DataFrame(variant["country_best"])
    country_best["counterpart"] = (
        country_best["country_name"] + " · " + country_best["region_name"]
    )
    top = country_best.nsmallest(10, "country_rank", keep="first")
    best_label = str(top.iloc[0]["counterpart"])
    categories = top["counterpart"].astype(str).tolist()
    colors = [
        COLORS["attention"] if label == best_label else COLORS["focus"]
        for label in categories
    ]
    figure = go.Figure(
        go.Bar(
            x=top["similarity"],
            y=categories,
            orientation="h",
            marker={"color": colors},
            text=[f"{value:.0f}" for value in top["similarity"]],
            textposition="outside",
            textfont={"color": COLORS["text"]},
            cliponaxis=False,
            customdata=top[["country_name", "region_name"]],
            hovertemplate=(
                "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                "Similarity: %{x:.0f} / 100<extra></extra>"
            ),
        )
    )
    style_figure(
        figure,
        title="Strongest country counterparts",
        subtitle="Each country contributes only its single closest TL2 region",
        x_label="Similarity score (0–100)",
        height=310,
        left_margin=132,
        right_margin=26,
        bottom_margin=42,
        show_legend=False,
        grid="x",
    )
    figure.update_xaxes(range=[0, 100], tickvals=[0, 25, 50, 75, 100])
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=categories,
        autorange="reversed",
    )
    figure.add_annotation(
        x=1,
        y=1.035,
        xref="paper",
        yref="paper",
        text="Similarity score",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font={"size": 12, "color": COLORS["muted_text"]},
    )
    figure.update_layout(
        margin={"l": 132, "r": 26, "t": 66, "b": 42},
        meta={"analytical_role": "country_counterpart_ranking"},
    )
    return figure


def metric_distributions_figure(
    common: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> go.Figure:
    """Place a selected pair over all-region distributions for every measure."""

    focal = variant["focal"]
    comparison = variant["matches"][0]
    metrics = common["metrics"]
    labels = [str(metric["short_label"]) for metric in metrics]
    figure = go.Figure()

    for metric in metrics:
        metric_name = str(metric["name"])
        label = str(metric["short_label"])
        values = [
            float(region["standardized"][metric_name]) for region in common["regions"]
        ]
        figure.add_trace(
            go.Violin(
                x=values,
                y=[label] * len(values),
                orientation="h",
                width=0.72,
                spanmode="hard",
                points=False,
                line={"color": COLORS["context"], "width": 1.2},
                fillcolor=COLORS["comparison"],
                opacity=0.52,
                hoverinfo="skip",
                showlegend=False,
                name=label,
            )
        )

    focal_values = [float(focal["standardized"][metric["name"]]) for metric in metrics]
    comparison_values = [
        float(comparison["standardized"][metric["name"]]) for metric in metrics
    ]
    figure.add_trace(
        go.Scatter(
            x=focal_values,
            y=labels,
            mode="markers",
            marker={
                "size": 14,
                "color": COLORS["focus"],
                "symbol": "diamond",
                "line": {"color": COLORS["paper"], "width": 1.5},
            },
            customdata=[
                _format_metric_value(focal["values"][metric["name"]], metric["format"])
                for metric in metrics
            ],
            hovertemplate="%{y}<br>%{customdata}<extra></extra>",
            name=focal["region_name"],
        )
    )
    figure.add_trace(
        go.Scatter(
            x=comparison_values,
            y=labels,
            mode="markers",
            marker={
                "size": 12,
                "color": COLORS["attention"],
                "line": {"color": COLORS["paper"], "width": 1.5},
            },
            customdata=[
                _format_metric_value(
                    comparison["values"][metric["name"]], metric["format"]
                )
                for metric in metrics
            ],
            hovertemplate="%{y}<br>%{customdata}<extra></extra>",
            name=comparison["region_name"],
        )
    )
    visible_values = [*focal_values, *comparison_values]
    x_limit = min(4.5, max(3.0, max(abs(value) for value in visible_values) + 0.4))
    style_figure(
        figure,
        title="The four-metric fingerprint",
        subtitle=(
            f"{len(common['regions']):,} TL2 distributions · dots mark the selected pair"
        ),
        x_label="Standardized position across OECD regions",
        height=300,
        left_margin=78,
        right_margin=14,
        bottom_margin=42,
        grid="x",
    )
    figure.update_xaxes(
        range=[-x_limit, x_limit],
        tickvals=[-2, 0, 2],
        ticktext=["Lower", "Average", "Higher"],
    )
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=labels,
        autorange="reversed",
    )
    figure.update_layout(
        violinmode="overlay",
        margin={"l": 78, "r": 14, "t": 94, "b": 42},
        legend={
            "orientation": "h",
            "x": 1,
            "y": 1.02,
            "xanchor": "right",
            "yanchor": "bottom",
            "font": {"size": 9},
        },
    )
    return figure


# 4) Report wrapper
def build_report_figures(
    common: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> dict[str, go.Figure]:
    """Reconstruct the eight coordinated views for one precomputed selection."""

    figures = {
        "similarity_map": similarity_map_figure(variant),
        "landscape": landscape_figure(common, variant),
        "metric_distributions": metric_distributions_figure(common, variant),
        "population_history": population_history_figure(common, variant),
        "country_ranking": country_ranking_figure(variant),
        "income_dumbbell": income_dumbbell_figure(common, variant),
        "age_structure": age_structure_figure(common, variant),
        "country_density": country_density_figure(common, variant),
    }
    return figures
