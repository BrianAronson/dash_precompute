"""Small Plotly styling policy used by the Place Twins report."""

# 0) Imports
from __future__ import annotations
import plotly.graph_objects as go

# 1) Visual tokens
COLORS = {
    "paper": "#222B35",
    "plot": "#222B35",
    "grid": "#3A424A",
    "text": "#F2F5F7",
    "muted_text": "#AAB4BE",
    "axis": "#56616C",
    "table_alt": "#19232D",
    "focus": "#57D6E4",
    "comparison": "#56616C",
    "context": "#7B8792",
    "connector": "#56616C",
    "attention": "#EE6772",
    "negative": "#EE6772",
    "warning": "#FAED5C",
    "missing": "#3A424A",
    "categories": [
        "#57D6E4",
        "#EE6772",
        "#FAB16C",
        "#C670E0",
        "#B0E686",
        "#FAED5C",
    ],
}
MAP_COLORS = ["#46325A", "#7E5294", "#57D6E4", "#B0E686", "#FAED5C"]
TITLE_FONT = "Inter, Arial, sans-serif"
BODY_FONT = "Inter, Arial, sans-serif"


# 2) Shared figure layout
def style_figure(
    figure: go.Figure,
    *,
    title: str | None,
    subtitle: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    height: int = 520,
    left_margin: int = 80,
    right_margin: int = 55,
    bottom_margin: int = 90,
    show_legend: bool = True,
    grid: str = "none",
) -> go.Figure:
    """Apply the dashboard's compact dark style to a Plotly figure."""

    if grid not in {"none", "x", "y", "both"}:
        raise ValueError("grid must be 'none', 'x', 'y', or 'both'")

    title_text = title
    if title and subtitle:
        title_text = (
            f"{title}<br><span style='font-size:11px;"
            f"color:{COLORS['muted_text']}'>{subtitle}</span>"
        )
    title_and_legend = bool(title and subtitle and show_legend)
    figure.update_layout(
        title=(
            {
                "text": title_text,
                "x": 0,
                "xanchor": "left",
                "font": {"family": TITLE_FONT, "size": 16},
            }
            if title_text
            else None
        ),
        height=height + 35 if title_and_legend else height,
        margin={
            "l": left_margin,
            "r": right_margin,
            "t": 135
            if title_and_legend
            else (100 if title and subtitle else (80 if title else 45)),
            "b": bottom_margin,
        },
        paper_bgcolor=COLORS["paper"],
        plot_bgcolor=COLORS["plot"],
        font={"family": BODY_FONT, "size": 11, "color": COLORS["text"]},
        hoverlabel={
            "bgcolor": COLORS["paper"],
            "bordercolor": COLORS["axis"],
            "font": {"family": BODY_FONT, "color": COLORS["text"]},
        },
        showlegend=show_legend,
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1,
            "xanchor": "left",
            "yanchor": "bottom",
            "title_text": "",
        },
    )
    axis = {
        "gridcolor": COLORS["grid"],
        "gridwidth": 0.8,
        "zeroline": False,
        "showline": True,
        "linecolor": COLORS["axis"],
        "linewidth": 1,
        "mirror": False,
        "ticks": "outside",
        "tickcolor": COLORS["axis"],
    }
    title_font = {"family": BODY_FONT, "color": COLORS["text"], "weight": 700}
    figure.update_xaxes(
        title_text=x_label,
        title_font=title_font,
        showgrid=grid in {"x", "both"},
        **axis,
    )
    figure.update_yaxes(
        title_text=y_label,
        title_font=title_font,
        showgrid=grid in {"y", "both"},
        **axis,
    )
    return figure
