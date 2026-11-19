"""Analysis of Nigeria's growth, prices, labour market and economic
structure, read from the warehouse.

Every figure in the report is produced here, from SQL against the
warehouse rather than from a local spreadsheet, so the whole analysis is
reproducible from the database and re-runnable after any re-import.

Interpretive caution, carried through deliberately: the labour-market
series are ILO modelled estimates (stored with observation_status
'estimated'), not Nigeria's own survey results. They are internally
consistent over time, which makes them usable for trends, but their
levels should not be read as NBS published figures.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from .config import PROJECT_ROOT
from .database import engine

FIGURE_DIR = PROJECT_ROOT / "reports" / "figures"

# Emphasis palette: one hue carries the subject, gray carries context.
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
RED = "#d03b3b"

SERIES_QUERY = """
SELECT i.indicator_code AS code,
       EXTRACT(YEAR FROM o.period_start)::int AS year,
       o.value::float AS value
FROM indicator_observations AS o
JOIN indicators AS i
  ON i.indicator_id = o.indicator_id
JOIN geographies AS g
  ON g.geography_id = o.geography_id
WHERE g.geo_code = 'NGA'
  AND i.frequency = 'annual'
ORDER BY code, year
"""


def load_indicators() -> pd.DataFrame:
    """Return annual Nigeria indicators as a year-by-indicator frame."""
    long_form = pd.read_sql(text(SERIES_QUERY), engine)

    if long_form.empty:
        raise RuntimeError(
            "No annual Nigeria observations found. Load data first with "
            "python -m nigeria_economic_intelligence.sources.worldbank "
            "--ingest"
        )

    return long_form.pivot(index="year", columns="code", values="value")


def growth_findings(data: pd.DataFrame) -> dict:
    """GDP per capita relative to its historical peak."""
    per_capita = data["NGA_GDP_PER_CAPITA"].dropna()
    peak_year = int(per_capita.idxmax())
    latest_year = int(per_capita.index[-1])

    population_growth = data["NGA_POPULATION"].dropna().pct_change() * 100
    comparison = pd.DataFrame(
        {
            "gdp_growth": data["NGA_GDP_GROWTH"],
            "population_growth": population_growth,
        }
    ).dropna()
    comparison["gap"] = (
        comparison["gdp_growth"] - comparison["population_growth"]
    )

    since_peak = comparison.loc[peak_year:]

    return {
        "peak_year": peak_year,
        "peak_value": float(per_capita.max()),
        "latest_year": latest_year,
        "latest_value": float(per_capita.iloc[-1]),
        "shortfall_pct": float(
            (per_capita.iloc[-1] / per_capita.max() - 1) * 100
        ),
        "years_below_peak": int((per_capita.loc[peak_year:] < per_capita.max()).sum()),
        "years_growth_below_population": int((since_peak["gap"] < 0).sum()),
        "years_compared_since_peak": int(len(since_peak)),
        "comparison": comparison,
    }


def price_findings(data: pd.DataFrame, recent_years: int = 10) -> dict:
    """Inflation level and recent acceleration.

    The recent window is relative to the end of the series rather than a
    fixed year, so the function does not silently break on a shorter or
    older series.
    """
    inflation = data["NGA_INFLATION_CPI"].dropna()
    recent = inflation.loc[int(inflation.index[-1]) - recent_years:]

    return {
        "latest_year": int(inflation.index[-1]),
        "latest": float(inflation.iloc[-1]),
        "recent_peak_year": int(recent.idxmax()),
        "recent_peak": float(recent.max()),
        "series_peak_year": int(inflation.idxmax()),
        "series_peak": float(inflation.max()),
        "series": inflation,
    }


def labour_findings(data: pd.DataFrame) -> dict:
    """The headline-unemployment paradox.

    A very low unemployment rate alongside very high vulnerable
    employment is the signature of an economy without unemployment
    insurance: people cannot afford to be jobless, so they are absorbed
    into informal and own-account work rather than recorded as
    unemployed. Unemployment is therefore a weak measure of labour
    market health here, and job quality is the thing to watch.
    """
    unemployment = data["NGA_UNEMPLOYMENT"].dropna()
    vulnerable = data["NGA_VULNERABLE_EMPLOYMENT"].dropna()
    participation = data["NGA_LABOUR_PARTICIPATION"].dropna()
    youth = data["NGA_YOUTH_UNEMPLOYMENT"].dropna()

    latest = int(unemployment.index[-1])

    return {
        "latest_year": latest,
        "unemployment": float(unemployment.iloc[-1]),
        "youth_unemployment": float(youth.iloc[-1]),
        "participation": float(participation.iloc[-1]),
        "vulnerable": float(vulnerable.iloc[-1]),
        "vulnerable_first": float(vulnerable.iloc[0]),
        "vulnerable_first_year": int(vulnerable.index[0]),
        "vulnerable_change": float(
            vulnerable.iloc[-1] - vulnerable.iloc[0]
        ),
        "unemployment_series": unemployment,
        "vulnerable_series": vulnerable,
    }


def structure_findings(data: pd.DataFrame) -> dict:
    """Where labour moved, and what it moved into.

    Labour leaving agriculture is normal development. What is not normal
    is manufacturing's share of output falling at the same time: labour
    is moving into services without an industrial base forming behind
    it, the pattern usually called premature deindustrialisation.
    """
    employment = data[
        [
            "NGA_EMPLOYMENT_AGRICULTURE",
            "NGA_EMPLOYMENT_INDUSTRY",
            "NGA_EMPLOYMENT_SERVICES",
        ]
    ].dropna()

    manufacturing = data["NGA_MANUF_VALUE_ADDED"].dropna()
    agriculture_output = data["NGA_AGRI_VALUE_ADDED"].dropna()
    oil = data["NGA_OIL_RENTS"].dropna()

    first_year = int(employment.index[0])
    last_year = int(employment.index[-1])
    shift = employment.loc[last_year] - employment.loc[first_year]

    oil_growth = data[["NGA_OIL_RENTS", "NGA_GDP_GROWTH"]].dropna()

    return {
        "first_year": first_year,
        "last_year": last_year,
        "agriculture_shift": float(shift["NGA_EMPLOYMENT_AGRICULTURE"]),
        "industry_shift": float(shift["NGA_EMPLOYMENT_INDUSTRY"]),
        "services_shift": float(shift["NGA_EMPLOYMENT_SERVICES"]),
        "manufacturing_first": float(manufacturing.iloc[0]),
        "manufacturing_last": float(manufacturing.iloc[-1]),
        "manufacturing_last_year": int(manufacturing.index[-1]),
        "manufacturing_trough": float(manufacturing.min()),
        "manufacturing_trough_year": int(manufacturing.idxmin()),
        "agriculture_output_last": float(agriculture_output.iloc[-1]),
        "oil_peak": float(oil.max()),
        "oil_peak_year": int(oil.idxmax()),
        "oil_last": float(oil.iloc[-1]),
        "oil_last_year": int(oil.index[-1]),
        "oil_growth_correlation": float(oil_growth.corr().iloc[0, 1]),
        "oil_growth_n": int(len(oil_growth)),
        "employment": employment,
        "manufacturing": manufacturing,
    }


def _style_axes(axes, *, ylabel: str) -> None:
    """Recessive chrome: horizontal gridlines only, muted ink."""
    axes.set_facecolor(SURFACE)
    axes.figure.set_facecolor(SURFACE)

    axes.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    axes.set_axisbelow(True)

    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(BASELINE)

    axes.tick_params(colors=MUTED, labelsize=9, length=0)
    axes.set_ylabel(ylabel, color=MUTED, fontsize=9)
    axes.set_xlabel("")


def _save(figure, name: str) -> Path:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURE_DIR / name
    figure.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    return path


def figure_per_capita(data: pd.DataFrame, findings: dict) -> Path:
    """GDP per capita against its own peak."""
    import matplotlib.pyplot as plt

    series = data["NGA_GDP_PER_CAPITA"].dropna()

    figure, axes = plt.subplots(figsize=(8, 4))
    _style_axes(axes, ylabel="GDP per capita (constant 2015 US$)")

    axes.axhline(
        findings["peak_value"], color=MUTED, linewidth=1, linestyle="--"
    )
    axes.plot(series.index, series.values, color=BLUE, linewidth=2)
    axes.plot(
        [findings["peak_year"]],
        [findings["peak_value"]],
        "o",
        color=BLUE,
        markersize=8,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
    )
    axes.plot(
        [findings["latest_year"]],
        [findings["latest_value"]],
        "o",
        color=RED,
        markersize=8,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
    )

    axes.annotate(
        f"{findings['peak_year']} peak  ${findings['peak_value']:,.0f}",
        xy=(findings["peak_year"], findings["peak_value"]),
        xytext=(-10, 10),
        textcoords="offset points",
        fontsize=9,
        color=INK,
        ha="right",
    )
    axes.annotate(
        f"{findings['latest_year']}  ${findings['latest_value']:,.0f}"
        f"  ({findings['shortfall_pct']:+.1f}%)",
        xy=(findings["latest_year"], findings["latest_value"]),
        xytext=(-8, 14),
        textcoords="offset points",
        fontsize=9,
        color=RED,
        ha="right",
        va="bottom",
    )

    axes.set_title(
        "Nigeria's GDP per capita has not regained its "
        f"{findings['peak_year']} peak",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "01_gdp_per_capita_vs_peak.png")


def figure_growth_vs_population(findings: dict) -> Path:
    """Output growth against population growth."""
    import matplotlib.pyplot as plt

    comparison = findings["comparison"]

    figure, axes = plt.subplots(figsize=(8, 4))
    _style_axes(axes, ylabel="Annual growth (%)")

    axes.axhline(0, color=BASELINE, linewidth=1)
    axes.fill_between(
        comparison.index,
        comparison["gdp_growth"],
        comparison["population_growth"],
        where=comparison["gdp_growth"] < comparison["population_growth"],
        color=RED,
        alpha=0.12,
        interpolate=True,
        label="GDP growth below population growth",
    )
    axes.plot(
        comparison.index,
        comparison["population_growth"],
        color=MUTED,
        linewidth=2,
        linestyle="--",
        label="Population growth",
    )
    axes.plot(
        comparison.index,
        comparison["gdp_growth"],
        color=BLUE,
        linewidth=2,
        label="GDP growth",
    )

    axes.legend(
        frameon=False,
        fontsize=9,
        labelcolor=MUTED,
        loc="lower left",
    )
    axes.set_title(
        "Growth must clear population growth to raise incomes",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "02_growth_vs_population.png")


def figure_inflation(findings: dict) -> Path:
    """Consumer price inflation."""
    import matplotlib.pyplot as plt

    series = findings["series"]

    figure, axes = plt.subplots(figsize=(8, 4))
    _style_axes(axes, ylabel="Inflation (annual %)")

    axes.plot(series.index, series.values, color=ORANGE, linewidth=2)
    axes.plot(
        [findings["recent_peak_year"]],
        [findings["recent_peak"]],
        "o",
        color=ORANGE,
        markersize=8,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
    )
    axes.annotate(
        f"{findings['recent_peak_year']}  {findings['recent_peak']:.1f}%",
        xy=(findings["recent_peak_year"], findings["recent_peak"]),
        xytext=(-8, 8),
        textcoords="offset points",
        fontsize=9,
        color=INK,
        ha="right",
    )

    axes.set_title(
        "Inflation returned to levels last seen in the 1990s",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "03_inflation.png")


def figure_labour_paradox(findings: dict) -> Path:
    """Unemployment against vulnerable employment, one axis."""
    import matplotlib.pyplot as plt

    unemployment = findings["unemployment_series"]
    vulnerable = findings["vulnerable_series"]

    figure, axes = plt.subplots(figsize=(8, 4))
    _style_axes(axes, ylabel="Percent")

    axes.plot(
        vulnerable.index, vulnerable.values, color=ORANGE, linewidth=2
    )
    axes.plot(
        unemployment.index, unemployment.values, color=BLUE, linewidth=2
    )

    axes.annotate(
        f"Vulnerable employment  {findings['vulnerable']:.1f}%",
        xy=(vulnerable.index[-1], vulnerable.iloc[-1]),
        xytext=(-8, 8),
        textcoords="offset points",
        fontsize=9,
        color=INK,
        ha="right",
    )
    axes.annotate(
        f"Unemployment  {findings['unemployment']:.1f}%",
        xy=(unemployment.index[-1], unemployment.iloc[-1]),
        xytext=(-8, 8),
        textcoords="offset points",
        fontsize=9,
        color=INK,
        ha="right",
    )

    axes.set_ylim(0, 100)
    axes.set_title(
        "Low unemployment, overwhelmingly insecure work",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "04_labour_paradox.png")


def figure_employment_structure(findings: dict) -> Path:
    """Sectoral composition of employment."""
    import matplotlib.pyplot as plt

    employment = findings["employment"]

    figure, axes = plt.subplots(figsize=(8, 4))
    _style_axes(axes, ylabel="Share of total employment (%)")

    labels = ["Agriculture", "Industry", "Services"]
    axes.stackplot(
        employment.index,
        employment["NGA_EMPLOYMENT_AGRICULTURE"],
        employment["NGA_EMPLOYMENT_INDUSTRY"],
        employment["NGA_EMPLOYMENT_SERVICES"],
        colors=[BLUE, ORANGE, AQUA],
        edgecolor=SURFACE,
        linewidth=2,
    )

    # Direct labels: the aqua band is below 3:1 against the surface, so
    # identity must not rest on colour alone.
    last = employment.index[-1]
    row = employment.loc[last]
    positions = [
        row["NGA_EMPLOYMENT_AGRICULTURE"] / 2,
        row["NGA_EMPLOYMENT_AGRICULTURE"]
        + row["NGA_EMPLOYMENT_INDUSTRY"] / 2,
        row["NGA_EMPLOYMENT_AGRICULTURE"]
        + row["NGA_EMPLOYMENT_INDUSTRY"]
        + row["NGA_EMPLOYMENT_SERVICES"] / 2,
    ]
    values = [
        row["NGA_EMPLOYMENT_AGRICULTURE"],
        row["NGA_EMPLOYMENT_INDUSTRY"],
        row["NGA_EMPLOYMENT_SERVICES"],
    ]

    for label, position, value in zip(labels, positions, values):
        axes.annotate(
            f"{label}  {value:.1f}%",
            xy=(last, position),
            xytext=(-10, 0),
            textcoords="offset points",
            fontsize=9,
            color=SURFACE,
            ha="right",
            va="center",
        )

    axes.set_ylim(0, 100)
    axes.set_title(
        "Labour left agriculture for services, not industry",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "05_employment_structure.png")


def figure_manufacturing(findings: dict) -> Path:
    """Manufacturing's share of output."""
    import matplotlib.pyplot as plt

    series = findings["manufacturing"]

    figure, axes = plt.subplots(figsize=(8, 4))
    _style_axes(axes, ylabel="Manufacturing value added (% of GDP)")

    axes.plot(series.index, series.values, color=BLUE, linewidth=2)
    axes.plot(
        [findings["manufacturing_trough_year"]],
        [findings["manufacturing_trough"]],
        "o",
        color=RED,
        markersize=8,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
    )

    axes.annotate(
        f"{findings['manufacturing_last_year']}  "
        f"{findings['manufacturing_last']:.1f}%",
        xy=(
            findings["manufacturing_last_year"],
            findings["manufacturing_last"],
        ),
        xytext=(-8, 12),
        textcoords="offset points",
        fontsize=9,
        color=INK,
        ha="right",
    )
    axes.annotate(
        f"{findings['manufacturing_trough_year']} trough  "
        f"{findings['manufacturing_trough']:.1f}%",
        xy=(
            findings["manufacturing_trough_year"],
            findings["manufacturing_trough"],
        ),
        xytext=(0, -16),
        textcoords="offset points",
        fontsize=9,
        color=RED,
        ha="center",
    )

    axes.set_ylim(0, None)
    axes.set_title(
        "Industry absorbed labour while manufacturing output shrank",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "06_manufacturing_value_added.png")


def build_figures() -> list[Path]:
    """Produce every figure used in the report."""
    import matplotlib

    matplotlib.use("Agg")

    data = load_indicators()

    growth = growth_findings(data)
    prices = price_findings(data)
    labour = labour_findings(data)
    structure = structure_findings(data)

    return [
        figure_per_capita(data, growth),
        figure_growth_vs_population(growth),
        figure_inflation(prices),
        figure_labour_paradox(labour),
        figure_employment_structure(structure),
        figure_manufacturing(structure),
    ]


def print_findings() -> None:
    """Print every computed figure quoted in the report."""
    data = load_indicators()

    growth = growth_findings(data)
    prices = price_findings(data)
    labour = labour_findings(data)
    structure = structure_findings(data)

    print("GROWTH")
    print(
        f"  per-capita peak {growth['peak_year']}: "
        f"${growth['peak_value']:,.0f}"
    )
    print(
        f"  latest {growth['latest_year']}: "
        f"${growth['latest_value']:,.0f} "
        f"({growth['shortfall_pct']:+.1f}% vs peak)"
    )
    print(f"  years below peak: {growth['years_below_peak']}")
    print(
        "  years growth below population growth since peak: "
        f"{growth['years_growth_below_population']}"
        f"/{growth['years_compared_since_peak']}"
    )

    print("PRICES")
    print(f"  latest {prices['latest_year']}: {prices['latest']:.1f}%")
    print(
        f"  recent peak {prices['recent_peak_year']}: "
        f"{prices['recent_peak']:.1f}%"
    )
    print(
        f"  series peak {prices['series_peak_year']}: "
        f"{prices['series_peak']:.1f}%"
    )

    print("LABOUR (modelled estimates)")
    print(f"  unemployment {labour['latest_year']}: {labour['unemployment']:.1f}%")
    print(f"  youth unemployment: {labour['youth_unemployment']:.1f}%")
    print(f"  participation: {labour['participation']:.1f}%")
    print(
        f"  vulnerable employment: {labour['vulnerable']:.1f}% "
        f"(from {labour['vulnerable_first']:.1f}% in "
        f"{labour['vulnerable_first_year']}, "
        f"{labour['vulnerable_change']:+.1f}pp)"
    )

    print("STRUCTURE")
    print(
        f"  employment shift {structure['first_year']}-"
        f"{structure['last_year']} (pp): "
        f"agriculture {structure['agriculture_shift']:+.1f}, "
        f"industry {structure['industry_shift']:+.1f}, "
        f"services {structure['services_shift']:+.1f}"
    )
    print(
        f"  manufacturing {structure['first_year']}: "
        f"{structure['manufacturing_first']:.1f}% -> "
        f"{structure['manufacturing_last_year']}: "
        f"{structure['manufacturing_last']:.1f}% "
        f"(trough {structure['manufacturing_trough_year']}: "
        f"{structure['manufacturing_trough']:.1f}%)"
    )
    print(
        f"  oil rents peak {structure['oil_peak_year']}: "
        f"{structure['oil_peak']:.1f}% -> "
        f"{structure['oil_last_year']}: {structure['oil_last']:.1f}%"
    )
    print(
        "  correlation(oil rents, GDP growth) = "
        f"{structure['oil_growth_correlation']:.3f} "
        f"(n={structure['oil_growth_n']})"
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyse Nigeria indicators held in the warehouse."
    )
    parser.add_argument(
        "--figures",
        action="store_true",
        help="Write the report figures to reports/figures/",
    )
    parser.add_argument(
        "--national-only",
        action="store_true",
        help="Skip the state-level section",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Skip the modelling and spatial section, which bootstraps "
            "and permutes and so takes appreciably longer"
        ),
    )
    args = parser.parse_args()

    print_findings()

    if not args.national_only:
        states = load_states()
        print()
        print_state_findings()
        print()
        print_poverty_findings()
        if not args.quick:
            print()
            print_statistical_findings(states)

    if args.figures:
        print("\nFIGURES")
        paths = build_figures()
        if not args.national_only:
            paths += build_state_figures()
            paths.append(
                figure_poverty_vs_dependency(poverty_findings(states))
            )
            if not args.quick:
                paths += build_statistical_figures(states)
        for path in paths:
            print(f"  {path.relative_to(PROJECT_ROOT)}")



STATE_QUERY = """
SELECT s.geo_code AS state_code,
       s.geo_name AS state,
       z.geo_name AS zone,
       i.indicator_code AS code,
       o.value::float AS value
FROM indicator_observations AS o
JOIN indicators AS i
  ON i.indicator_id = o.indicator_id
JOIN geographies AS s
  ON s.geography_id = o.geography_id
JOIN geographies AS z
  ON z.geography_id = s.parent_id
WHERE s.geo_level = 'state'
ORDER BY s.geo_code
"""


def load_states() -> pd.DataFrame:
    """Return state-level indicators, one row per state."""
    long_form = pd.read_sql(text(STATE_QUERY), engine)

    if long_form.empty:
        raise RuntimeError(
            "No state-level observations found. Load them first with "
            "python -m nigeria_economic_intelligence.sources."
            "hdx_population --ingest"
        )

    wide = long_form.pivot(
        index=["state_code", "state", "zone"],
        columns="code",
        values="value",
    ).reset_index()
    wide.columns.name = None

    return wide


def state_findings(states: pd.DataFrame) -> dict:
    """The north-south split in age structure.

    Dependency ratio is the sharpest single summary: it says how many
    children and elderly each working-age person supports. A ratio above
    100 means the working-age population is outnumbered by those it
    supports, which constrains household saving and schooling in a way
    that income figures alone do not reveal.
    """
    by_zone = (
        states.groupby("zone")
        .agg(
            population=("NGA_STATE_POPULATION", "sum"),
            working_age=("NGA_STATE_WORKING_AGE_POPULATION", "sum"),
            dependency=("NGA_STATE_DEPENDENCY_RATIO", "mean"),
            working_age_share=("NGA_STATE_WORKING_AGE_SHARE", "mean"),
        )
        .sort_values("dependency", ascending=False)
    )

    ranked = states.sort_values("NGA_STATE_DEPENDENCY_RATIO")
    above_100 = states[states["NGA_STATE_DEPENDENCY_RATIO"] > 100]

    return {
        "state_count": int(len(states)),
        "total_population": float(states["NGA_STATE_POPULATION"].sum()),
        "lowest_state": str(ranked.iloc[0]["state"]),
        "lowest_value": float(
            ranked.iloc[0]["NGA_STATE_DEPENDENCY_RATIO"]
        ),
        "highest_state": str(ranked.iloc[-1]["state"]),
        "highest_value": float(
            ranked.iloc[-1]["NGA_STATE_DEPENDENCY_RATIO"]
        ),
        "states_above_100": sorted(above_100["state"].tolist()),
        "zone_summary": by_zone,
    }


def figure_state_dependency(states: pd.DataFrame) -> Path:
    """Age dependency ratio for every state, ranked."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    ranked = states.sort_values("NGA_STATE_DEPENDENCY_RATIO")
    values = ranked["NGA_STATE_DEPENDENCY_RATIO"]

    # Sequential: magnitude is the only thing colour encodes here.
    ramp = LinearSegmentedColormap.from_list(
        "blues", ["#b5d4f4", "#185fa5"]
    )
    spread = values.max() - values.min()
    colours = [ramp((value - values.min()) / spread) for value in values]

    figure, axes = plt.subplots(figsize=(8, 10))
    _style_axes(axes, ylabel="")
    axes.grid(axis="y", visible=False)
    axes.grid(axis="x", color=GRID, linewidth=1)

    positions = range(len(ranked))
    axes.barh(positions, values, color=colours, height=0.72, zorder=2)

    axes.set_yticks(list(positions))
    axes.set_yticklabels(
        [
            f"{row.state}  ({row.zone.replace('North', 'N').replace('South', 'S')})"
            for row in ranked.itertuples()
        ],
        fontsize=8,
    )
    axes.set_xlabel(
        "Dependants per 100 people aged 15-64", color=MUTED, fontsize=9
    )
    # The 100 line is the point where dependants outnumber workers; the
    # labelled axis says what it means, so it needs no caption.
    axes.axvline(100, color=RED, linewidth=1, linestyle="--")

    for position, value in zip(positions, values):
        axes.annotate(
            f"{value:.0f}",
            xy=(value, position),
            xytext=(4, 0),
            textcoords="offset points",
            fontsize=8,
            color=INK,
            va="center",
        )

    axes.set_xlim(0, values.max() * 1.12)
    axes.set_title(
        "Age dependency splits Nigeria north from south",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "07_state_dependency_ratio.png")


def figure_zone_working_age(findings: dict) -> Path:
    """Where the working-age population actually is."""
    import matplotlib.pyplot as plt

    summary = findings["zone_summary"].sort_values("working_age")

    figure, axes = plt.subplots(figsize=(8, 4.5))
    _style_axes(axes, ylabel="")
    axes.grid(axis="y", visible=False)
    axes.grid(axis="x", color=GRID, linewidth=1)

    positions = range(len(summary))
    millions = summary["working_age"] / 1e6

    axes.barh(positions, millions, color=BLUE, height=0.68, zorder=2)
    axes.set_yticks(list(positions))
    axes.set_yticklabels(summary.index, fontsize=9)
    axes.set_xlabel(
        "Working-age population, millions (15-64)",
        color=MUTED,
        fontsize=9,
    )

    for position, (value, dependency) in enumerate(
        zip(millions, summary["dependency"])
    ):
        axes.annotate(
            f"{value:.1f}m   dependency {dependency:.0f}",
            xy=(value, position),
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=8,
            color=INK,
            va="center",
        )

    axes.set_xlim(0, millions.max() * 1.45)
    axes.set_title(
        "The largest workforce carries the heaviest dependency",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "08_zone_working_age.png")


def build_state_figures() -> list[Path]:
    """Produce the state-level figures."""
    import matplotlib

    matplotlib.use("Agg")

    states = load_states()
    findings = state_findings(states)

    return [
        figure_state_dependency(states),
        figure_zone_working_age(findings),
    ]


def print_state_findings() -> None:
    """Print the state-level numbers quoted in the report."""
    states = load_states()
    findings = state_findings(states)

    print("STATES (2022 projections)")
    print(
        f"  {findings['state_count']} states, "
        f"{findings['total_population']:,.0f} people"
    )
    print(
        f"  lowest dependency:  {findings['lowest_state']} "
        f"{findings['lowest_value']:.1f}"
    )
    print(
        f"  highest dependency: {findings['highest_state']} "
        f"{findings['highest_value']:.1f}"
    )
    print(
        f"  states above 100 dependants per 100 workers "
        f"({len(findings['states_above_100'])}): "
        f"{', '.join(findings['states_above_100'])}"
    )
    print("  by zone:")
    for zone, row in findings["zone_summary"].iterrows():
        print(
            f"    {zone:<14} pop {row['population'] / 1e6:6.1f}m   "
            f"working age {row['working_age'] / 1e6:6.1f}m   "
            f"dependency {row['dependency']:5.1f}"
        )


def poverty_findings(states: pd.DataFrame) -> dict:
    """State poverty, and how it tracks age structure.

    The association with the dependency ratio is strong, but a shared
    driver explains much of it: high fertility raises the child
    population, which mechanically raises dependency and is itself
    associated with poverty. The correlation is therefore evidence that
    the two describe the same regional divide, not that age structure
    causes poverty.
    """
    from scipy import stats

    paired = states.dropna(
        subset=["NGA_MPI_HEADCOUNT", "NGA_STATE_DEPENDENCY_RATIO"]
    )

    pearson, pearson_p = stats.pearsonr(
        paired["NGA_STATE_DEPENDENCY_RATIO"],
        paired["NGA_MPI_HEADCOUNT"],
    )
    spearman, _ = stats.spearmanr(
        paired["NGA_STATE_DEPENDENCY_RATIO"],
        paired["NGA_MPI_HEADCOUNT"],
    )

    # The pooled correlation can be an artefact of two separated
    # groups, so test within each before believing it.
    northern = paired["zone"].str.startswith("North")
    within = {}
    for label, group in (
        ("north", paired[northern]),
        ("south", paired[~northern]),
    ):
        coefficient, probability = stats.pearsonr(
            group["NGA_STATE_DEPENDENCY_RATIO"],
            group["NGA_MPI_HEADCOUNT"],
        )
        # Rank correlation as well, so an absent result cannot be
        # dismissed as Pearson's r missing a monotone relationship.
        rank, _ = stats.spearmanr(
            group["NGA_STATE_DEPENDENCY_RATIO"],
            group["NGA_MPI_HEADCOUNT"],
        )
        within[label] = {
            "n": int(len(group)),
            "r": float(coefficient),
            "p": float(probability),
            "rho": float(rank),
            "mean_headcount": float(group["NGA_MPI_HEADCOUNT"].mean()),
        }

    # How separated the two groups are, stated as a count rather than
    # left to a reader to infer from a scatter: a correlation computed
    # across two barely-overlapping clusters is mostly the gap between
    # them.
    northern_states = paired[northern]
    southern_states = paired[~northern]
    southern_max = float(southern_states["NGA_MPI_HEADCOUNT"].max())
    northern_min = float(northern_states["NGA_MPI_HEADCOUNT"].min())
    above = northern_states["NGA_MPI_HEADCOUNT"] > southern_max
    inside = northern_states.loc[~above].sort_values("NGA_MPI_HEADCOUNT")

    separation = {
        "northern_n": int(len(northern_states)),
        "northern_above_every_southern_state": int(above.sum()),
        "southern_max": southern_max,
        "northern_min": northern_min,
        "northern_inside_southern_range": [
            (str(row["state"]), float(row["NGA_MPI_HEADCOUNT"]))
            for _, row in inside.iterrows()
        ],
        "northern_median": float(
            northern_states["NGA_MPI_HEADCOUNT"].median()
        ),
        "southern_median": float(
            southern_states["NGA_MPI_HEADCOUNT"].median()
        ),
    }

    ranked = paired.sort_values("NGA_MPI_HEADCOUNT")
    by_zone = (
        paired.groupby("zone")["NGA_MPI_HEADCOUNT"]
        .agg(states="count", mean="mean", lowest="min", highest="max")
        .sort_values("mean")
    )

    return {
        "n": int(len(paired)),
        "within": within,
        "separation": separation,
        "lowest_state": str(ranked.iloc[0]["state"]),
        "lowest": float(ranked.iloc[0]["NGA_MPI_HEADCOUNT"]),
        "highest_state": str(ranked.iloc[-1]["state"]),
        "highest": float(ranked.iloc[-1]["NGA_MPI_HEADCOUNT"]),
        "ratio": float(
            ranked.iloc[-1]["NGA_MPI_HEADCOUNT"]
            / ranked.iloc[0]["NGA_MPI_HEADCOUNT"]
        ),
        "pearson": float(pearson),
        "pearson_p": float(pearson_p),
        "spearman": float(spearman),
        "zone_summary": by_zone,
        "paired": paired,
    }


def figure_poverty_vs_dependency(findings: dict) -> Path:
    """State poverty against age structure."""
    import matplotlib.pyplot as plt

    paired = findings["paired"]
    northern = paired["zone"].str.startswith("North")

    figure, axes = plt.subplots(figsize=(8, 5.5))
    _style_axes(axes, ylabel="Multidimensionally poor (% of population)")

    grid = np.linspace(
        paired["NGA_STATE_DEPENDENCY_RATIO"].min(),
        paired["NGA_STATE_DEPENDENCY_RATIO"].max(),
        50,
    )

    # The pooled line first and underneath, because the point of the
    # chart is that it fits neither group.
    slope, intercept = np.polyfit(
        paired["NGA_STATE_DEPENDENCY_RATIO"],
        paired["NGA_MPI_HEADCOUNT"],
        1,
    )
    axes.plot(
        grid,
        slope * grid + intercept,
        color=MUTED,
        linewidth=1.4,
        linestyle="--",
        zorder=2,
        label=f"Pooled fit, r = {findings['pearson']:.2f}",
    )

    # Two groups, two marker shapes: identity never rests on colour.
    for mask, colour, marker, label, key in (
        (northern, ORANGE, "o", "Northern zones", "north"),
        (~northern, BLUE, "s", "Southern zones", "south"),
    ):
        subset = paired[mask]
        group = findings["within"][key]
        axes.scatter(
            subset["NGA_STATE_DEPENDENCY_RATIO"],
            subset["NGA_MPI_HEADCOUNT"],
            color=colour,
            marker=marker,
            s=58,
            edgecolor=SURFACE,
            linewidth=1.4,
            zorder=4,
            label=f"{label}, r = {group['r']:.2f} (n = {group['n']})",
        )

        # Each group's own fit, drawn only across its own range so the
        # lines make no claim outside the data that produced them.
        group_slope, group_intercept = np.polyfit(
            subset["NGA_STATE_DEPENDENCY_RATIO"],
            subset["NGA_MPI_HEADCOUNT"],
            1,
        )
        inside = (
            grid >= subset["NGA_STATE_DEPENDENCY_RATIO"].min()
        ) & (grid <= subset["NGA_STATE_DEPENDENCY_RATIO"].max())
        axes.plot(
            grid[inside],
            group_slope * grid[inside] + group_intercept,
            color=colour,
            linewidth=2.2,
            alpha=0.85,
            zorder=3,
        )

    for state in ("Lagos", "Bauchi", "Kaduna"):
        row = paired[paired["state"] == state]
        if row.empty:
            continue
        axes.annotate(
            state,
            (
                float(row["NGA_STATE_DEPENDENCY_RATIO"].iloc[0]),
                float(row["NGA_MPI_HEADCOUNT"].iloc[0]),
            ),
            xytext=(7, 4),
            textcoords="offset points",
            fontsize=8,
            color=INK,
        )

    axes.set_xlabel(
        "Dependants per 100 people aged 15-64", color=MUTED, fontsize=9
    )
    axes.legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper left")
    axes.set_title(
        "One pooled line, two different relationships",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "09_poverty_vs_dependency.png")


def print_poverty_findings() -> None:
    """Print the poverty numbers quoted in the report."""
    states = load_states()

    if "NGA_MPI_HEADCOUNT" not in states.columns:
        print("POVERTY: no MPI data loaded.")
        return

    findings = poverty_findings(states)

    print("POVERTY (OPHI MPI, MICS 2021)")
    print(
        f"  headcount ranges {findings['lowest']:.1f}% "
        f"({findings['lowest_state']}) to {findings['highest']:.1f}% "
        f"({findings['highest_state']}) - a {findings['ratio']:.0f}x spread"
    )
    print(
        "  vs dependency ratio: pearson "
        f"{findings['pearson']:.3f} (p={findings['pearson_p']:.1e}), "
        f"spearman {findings['spearman']:.3f}, n={findings['n']}"
    )
    print("  within groups (the pooled figure hides two regimes):")
    for label, group in findings["within"].items():
        print(
            f"    {label:<6} n={group['n']:<3} r={group['r']:+.3f} "
            f"p={group['p']:.3f} rho={group['rho']:+.3f}   "
            f"mean headcount {group['mean_headcount']:.1f}%"
        )
    gap = findings["separation"]
    print(
        f"  separation: {gap['northern_above_every_southern_state']} of "
        f"{gap['northern_n']} northern states exceed every southern "
        f"state (southern max {gap['southern_max']:.1f}%)"
    )
    if gap["northern_inside_southern_range"]:
        print(
            "    northern states inside the southern range: "
            + ", ".join(
                f"{name} {value:.1f}%"
                for name, value in gap["northern_inside_southern_range"]
            )
        )
    print(
        f"    medians: north {gap['northern_median']:.1f}%, "
        f"south {gap['southern_median']:.1f}%"
    )
    print("  mean headcount by zone:")
    for zone, row in findings["zone_summary"].iterrows():
        print(
            f"    {zone:<14} {row['mean']:5.1f}%   "
            f"(range {row['lowest']:.1f}-{row['highest']:.1f})"
        )



# ---------------------------------------------------------------------
# Phase 2: uncertainty, a model in place of two correlations, and a test
# of whether the north-south pattern is spatial rather than merely named.
# ---------------------------------------------------------------------

BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20261119


def correlation_interval(
    x,
    y,
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Pearson's r with two 95% intervals that are computed differently.

    Fisher's z transform gives the textbook interval. It assumes the
    pair is bivariate normal, which 37 states with a long right tail of
    poverty rates are not obliged to be, so a percentile bootstrap over
    resampled state pairs is reported beside it. Where the two agree,
    the interval is not an artefact of the assumption; where they
    disagree, the bootstrap is the one to believe.

    Both are wide at this sample size, which is the point of showing
    them: r = 0.07 and r = 0.86 are point estimates on 17 and 20
    observations.
    """
    from scipy import stats

    first = np.asarray(x, dtype=float)
    second = np.asarray(y, dtype=float)

    if len(first) != len(second):
        raise ValueError("Correlation needs paired series of equal length")
    if len(first) < 4:
        raise ValueError(
            f"A correlation interval needs at least 4 pairs, got {len(first)}"
        )

    count = len(first)
    r, p_value = stats.pearsonr(first, second)

    # Fisher z: arctanh(r) is approximately normal with sd 1/sqrt(n-3).
    critical = stats.norm.ppf(0.975)
    z = np.arctanh(r)
    margin = critical / np.sqrt(count - 3)
    fisher = (float(np.tanh(z - margin)), float(np.tanh(z + margin)))

    generator = np.random.default_rng(seed)
    resampled = np.empty(draws, dtype=float)
    taken = 0
    for _ in range(draws * 3):
        if taken == draws:
            break
        picks = generator.integers(0, count, count)
        sample_x = first[picks]
        sample_y = second[picks]
        # A resample can be degenerate; skip it rather than let a nan
        # into the percentiles.
        if sample_x.std() == 0 or sample_y.std() == 0:
            continue
        resampled[taken] = stats.pearsonr(sample_x, sample_y)[0]
        taken += 1

    if taken < draws:
        resampled = resampled[:taken]

    bootstrap = (
        float(np.percentile(resampled, 2.5)),
        float(np.percentile(resampled, 97.5)),
    )

    return {
        "n": count,
        "r": float(r),
        "p": float(p_value),
        "fisher_low": fisher[0],
        "fisher_high": fisher[1],
        "bootstrap_low": bootstrap[0],
        "bootstrap_high": bootstrap[1],
        "bootstrap_draws": int(taken),
        "includes_zero": bootstrap[0] <= 0.0 <= bootstrap[1],
        "width": float(bootstrap[1] - bootstrap[0]),
    }


def poverty_intervals(states: pd.DataFrame) -> dict:
    """Interval estimates for the three correlations the report quotes."""
    paired = states.dropna(
        subset=["NGA_MPI_HEADCOUNT", "NGA_STATE_DEPENDENCY_RATIO"]
    )
    northern = paired["zone"].str.startswith("North")

    groups = {
        "pooled": paired,
        "north": paired[northern],
        "south": paired[~northern],
    }

    return {
        label: correlation_interval(
            group["NGA_STATE_DEPENDENCY_RATIO"],
            group["NGA_MPI_HEADCOUNT"],
        )
        for label, group in groups.items()
    }


def poverty_model(states: pd.DataFrame) -> dict:
    """Fit poverty on dependency, allowing the slope to differ by region.

    Reporting two separate correlations says the relationship differs
    between north and south without ever testing that claim. One model
    with an interaction term does test it: the interaction coefficient
    *is* the difference between the two slopes, and its p-value is the
    test of whether that difference is distinguishable from zero.

    Standard errors are HC3, which is the heteroscedasticity-consistent
    estimator with the best small-sample behaviour of the usual family --
    and the residuals here are plainly heteroscedastic, being compressed
    near zero in the south and spread wide in the north.

    Influence diagnostics come from the ordinary fit, because leverage
    and Cook's distance are properties of the design and the residuals
    rather than of the covariance estimator.
    """
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    paired = states.dropna(
        subset=["NGA_MPI_HEADCOUNT", "NGA_STATE_DEPENDENCY_RATIO"]
    ).copy()

    frame = pd.DataFrame(
        {
            "state": paired["state"].to_numpy(),
            "zone": paired["zone"].to_numpy(),
            "headcount": paired["NGA_MPI_HEADCOUNT"].to_numpy(float),
            "dependency": paired["NGA_STATE_DEPENDENCY_RATIO"].to_numpy(float),
            "north": paired["zone"]
            .str.startswith("North")
            .astype(int)
            .to_numpy(),
        }
    )

    formula = "headcount ~ dependency * north"
    plain = smf.ols(formula, data=frame).fit()
    robust = smf.ols(formula, data=frame).fit(cov_type="HC3")

    intervals = robust.conf_int()
    terms = {}
    for name in robust.params.index:
        terms[name] = {
            "estimate": float(robust.params[name]),
            "robust_se": float(robust.bse[name]),
            "classical_se": float(plain.bse[name]),
            "p": float(robust.pvalues[name]),
            "low": float(intervals.loc[name, 0]),
            "high": float(intervals.loc[name, 1]),
        }

    southern_slope = terms["dependency"]["estimate"]
    difference = terms["dependency:north"]["estimate"]

    influence = plain.get_influence()
    cooks = influence.cooks_distance[0]
    leverage = influence.hat_matrix_diag
    studentised = influence.resid_studentized_external

    count = len(frame)
    threshold = 4.0 / count

    diagnostics = pd.DataFrame(
        {
            "state": frame["state"],
            "zone": frame["zone"],
            "cooks_d": cooks,
            "leverage": leverage,
            "studentised_residual": studentised,
        }
    ).sort_values("cooks_d", ascending=False)

    influential = diagnostics[diagnostics["cooks_d"] > threshold]

    # The honest test of an influential point is what happens without
    # it, so refit without every state the threshold flags.
    kept = frame[~frame["state"].isin(influential["state"])]
    refit = smf.ols(formula, data=kept).fit(cov_type="HC3")

    return {
        "n": count,
        "formula": formula,
        "terms": terms,
        "southern_slope": float(southern_slope),
        "northern_slope": float(southern_slope + difference),
        "slope_difference": float(difference),
        "slope_difference_p": terms["dependency:north"]["p"],
        "r_squared": float(robust.rsquared),
        "adjusted_r_squared": float(robust.rsquared_adj),
        "cooks_threshold": float(threshold),
        "diagnostics": diagnostics,
        "influential": influential,
        "refit_n": int(len(kept)),
        "refit_southern_slope": float(refit.params["dependency"]),
        "refit_northern_slope": float(
            refit.params["dependency"] + refit.params["dependency:north"]
        ),
        "refit_difference_p": float(refit.pvalues["dependency:north"]),
        "breusch_pagan_p": float(
            sm.stats.diagnostic.het_breuschpagan(
                plain.resid, plain.model.exog
            )[1]
        ),
        "frame": frame,
        "fit": robust,
    }


def spatial_findings(states: pd.DataFrame) -> dict:
    """Test whether the north-south pattern is spatial clustering.

    Every state-level finding so far has been expressed through zones,
    a grouping imposed before the data was looked at. Moran's I needs no
    such grouping: it asks whether states with similar values are closer
    together than a random re-allocation of the same values would put
    them.
    """
    from . import spatial
    from .sources import cod_ab_boundaries

    boundaries = {
        boundary.pcode: boundary
        for boundary in cod_ab_boundaries.load_admin1()
    }

    missing = set(states["state_code"]) - set(boundaries)
    if missing:
        raise RuntimeError(
            f"No boundary for state P-codes {sorted(missing)}; the "
            "boundary file and the warehouse disagree about Nigeria."
        )

    measures = {
        "poverty": "NGA_MPI_HEADCOUNT",
        "dependency": "NGA_STATE_DEPENDENCY_RATIO",
    }

    results = {}
    for label, column in measures.items():
        usable = states.dropna(subset=[column])
        points = [
            boundaries[code].centre for code in usable["state_code"]
        ]
        values = usable[column].to_numpy(float)

        headline = spatial.morans_i(
            values, spatial.knn_weights(points, spatial.DEFAULT_K)
        )
        sensitivity = spatial.moran_across_k(values, points)

        results[label] = {
            "column": column,
            "headline": headline,
            "sensitivity": sensitivity,
            "values": values,
            "points": points,
            "states": usable["state"].tolist(),
            "codes": usable["state_code"].tolist(),
        }

    return {
        "k": spatial.DEFAULT_K,
        "permutations": spatial.DEFAULT_PERMUTATIONS,
        "measures": results,
        "boundaries": boundaries,
    }


def figure_correlation_intervals(intervals: dict) -> Path:
    """The three correlations with their uncertainty attached."""
    import matplotlib.pyplot as plt

    labels = [
        ("pooled", "All 37 states", MUTED),
        ("north", "Northern zones", ORANGE),
        ("south", "Southern zones", BLUE),
    ]

    figure, axes = plt.subplots(figsize=(8.5, 4.2))
    _style_axes(axes, ylabel="")

    axes.axvline(0, color=BASELINE, linewidth=1.2, zorder=1)

    for position, (key, label, colour) in enumerate(reversed(labels)):
        row = intervals[key]
        axes.plot(
            [row["bootstrap_low"], row["bootstrap_high"]],
            [position, position],
            color=colour,
            linewidth=3,
            solid_capstyle="round",
            zorder=3,
        )
        axes.plot(
            [row["fisher_low"], row["fisher_high"]],
            [position + 0.17, position + 0.17],
            color=colour,
            linewidth=1.2,
            alpha=0.75,
            zorder=3,
        )
        axes.scatter(
            [row["r"]], [position],
            color=colour, s=70, zorder=4,
            edgecolor=SURFACE, linewidth=1.4,
        )
        axes.annotate(
            f"r = {row['r']:.2f}   [{row['bootstrap_low']:.2f}, "
            f"{row['bootstrap_high']:.2f}]   n = {row['n']}",
            (row["bootstrap_high"], position),
            xytext=(10, -3),
            textcoords="offset points",
            fontsize=9,
            color=INK,
            va="center",
        )
        axes.annotate(
            label,
            (row["bootstrap_low"], position),
            xytext=(-10, -3),
            textcoords="offset points",
            fontsize=9,
            color=MUTED,
            ha="right",
            va="center",
        )

    axes.set_yticks([])
    axes.set_ylim(-0.6, len(labels) - 0.2)
    axes.set_xlim(-1.05, 1.5)
    axes.set_xticks([-0.5, 0, 0.5, 1.0])
    axes.set_xlabel(
        "Pearson correlation, poverty against dependency "
        "(thick: bootstrap 95%, thin: Fisher z)",
        color=MUTED,
        fontsize=9,
    )
    axes.grid(axis="y", visible=False)
    axes.set_title(
        "The southern interval contains zero; the northern one is far from it",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "10_correlation_intervals.png")


def figure_model_diagnostics(model: dict) -> Path:
    """Leverage against residual, sized by influence."""
    import matplotlib.pyplot as plt

    diagnostics = model["diagnostics"]
    threshold = model["cooks_threshold"]
    northern = diagnostics["zone"].str.startswith("North")

    figure, axes = plt.subplots(figsize=(8.5, 5.5))
    _style_axes(axes, ylabel="Externally studentised residual")

    axes.axhline(0, color=BASELINE, linewidth=1.2, zorder=1)
    for level in (-2, 2):
        axes.axhline(
            level, color=BASELINE, linewidth=1, linestyle=":", zorder=1
        )

    for mask, colour, marker, label in (
        (northern, ORANGE, "o", "Northern zones"),
        (~northern, BLUE, "s", "Southern zones"),
    ):
        subset = diagnostics[mask]
        axes.scatter(
            subset["leverage"],
            subset["studentised_residual"],
            s=60 + 5200 * subset["cooks_d"],
            color=colour,
            marker=marker,
            alpha=0.75,
            edgecolor=SURFACE,
            linewidth=1.3,
            zorder=3,
            label=label,
        )

    # Label the five largest influences, marking which clear the
    # threshold, so a large bubble is never left unexplained.
    # Only the states over the threshold are named. Labelling the next
    # few as well put two labels on top of each other, and the marker
    # sizes already show where the other large influences are.
    flagged = diagnostics[diagnostics["cooks_d"] > threshold]
    for _, row in flagged.iterrows():
        name = str(row["state"]).replace(
            "Federal Capital Territory", "FCT"
        )
        axes.annotate(
            f"{name}  D = {row['cooks_d']:.2f}",
            (row["leverage"], row["studentised_residual"]),
            xytext=(13, 7),
            textcoords="offset points",
            fontsize=8.5,
            color=INK,
        )

    axes.set_xlabel("Leverage (hat value)", color=MUTED, fontsize=9)
    axes.set_xlim(right=diagnostics["leverage"].max() * 1.22)

    # The scatter sizes encode Cook's distance, so the legend needs its
    # own handles or it reproduces the largest bubble at full size.
    from matplotlib.lines import Line2D

    axes.legend(
        handles=[
            Line2D(
                [], [], linestyle="none", marker=marker, markersize=8,
                markerfacecolor=colour, markeredgecolor=SURFACE,
                label=label,
            )
            for colour, marker, label in (
                (ORANGE, "o", "Northern zones"),
                (BLUE, "s", "Southern zones"),
            )
        ],
        frameon=False, fontsize=9, labelcolor=MUTED, loc="lower right",
    )
    axes.set_title(
        "Marker size is Cook's distance; the "
        f"{len(flagged)} states above 4/n = {threshold:.2f} are named",
        color=INK,
        fontsize=12,
        loc="left",
        pad=14,
    )

    return _save(figure, "11_model_diagnostics.png")


def _choropleth(axes, boundaries, values_by_code, *, low, high, cmap):
    """Draw one map panel and return the colour mapping used."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import PatchCollection
    from matplotlib.colors import Normalize
    from matplotlib.patches import Polygon as MplPolygon

    norm = Normalize(vmin=low, vmax=high)
    colours = plt.get_cmap(cmap)

    patches = []
    face_colours = []

    for code, boundary in sorted(boundaries.items()):
        value = values_by_code.get(code)
        for ring in boundary.polygons:
            patches.append(MplPolygon(np.asarray(ring), closed=True))
            face_colours.append(
                colours(norm(value)) if value is not None else SURFACE
            )

    collection = PatchCollection(
        patches,
        facecolor=face_colours,
        edgecolor=SURFACE,
        linewidth=0.6,
    )
    axes.add_collection(collection)
    axes.autoscale_view()
    axes.set_aspect("equal")
    axes.axis("off")

    return plt.cm.ScalarMappable(norm=norm, cmap=colours)


def figure_state_maps(states: pd.DataFrame, spatial_result: dict) -> Path:
    """Poverty and dependency, mapped side by side."""
    import matplotlib.pyplot as plt

    boundaries = spatial_result["boundaries"]

    panels = [
        (
            "NGA_MPI_HEADCOUNT",
            "Multidimensional poverty (% poor)",
            "Oranges",
        ),
        (
            "NGA_STATE_DEPENDENCY_RATIO",
            "Dependants per 100 aged 15-64",
            "Blues",
        ),
    ]

    figure, axes_pair = plt.subplots(1, 2, figsize=(11.5, 5.2))
    figure.patch.set_facecolor(SURFACE)
    figure.subplots_adjust(
        top=0.88, bottom=0.06, left=0.02, right=0.98, wspace=0.02
    )

    for axes, (column, caption, cmap) in zip(axes_pair, panels):
        usable = states.dropna(subset=[column])
        values = dict(zip(usable["state_code"], usable[column]))

        mappable = _choropleth(
            axes,
            boundaries,
            values,
            low=min(values.values()),
            high=max(values.values()),
            cmap=cmap,
        )
        axes.set_facecolor(SURFACE)

        bar = figure.colorbar(
            mappable, ax=axes, orientation="horizontal",
            fraction=0.045, pad=0.04,
        )
        bar.outline.set_visible(False)
        bar.ax.tick_params(labelsize=8, colors=MUTED, length=0)
        bar.set_label(caption, color=MUTED, fontsize=9)

        moran = spatial_result["measures"][
            "poverty" if "MPI" in column else "dependency"
        ]["headline"]
        axes.set_title(
            f"Moran's I = {moran.i:.2f}  (p = {moran.p_value:.4f})",
            color=INK,
            fontsize=11,
            loc="center",
            pad=8,
        )

    figure.suptitle(
        "Both measures cluster in space, not just in the zone labels",
        color=INK,
        fontsize=12.5,
        x=0.02,
        ha="left",
        y=0.98,
    )

    return _save(figure, "12_state_maps.png")


def figure_moran_scatter(spatial_result: dict) -> Path:
    """Each state's value against the mean of its nearest neighbours."""
    import matplotlib.pyplot as plt

    from . import spatial as spatial_module

    measure = spatial_result["measures"]["poverty"]
    values = measure["values"]
    weights = spatial_module.knn_weights(
        measure["points"], spatial_result["k"]
    )

    standardised = (values - values.mean()) / values.std(ddof=0)
    lagged = weights @ standardised

    figure, axes = plt.subplots(figsize=(8.5, 5.5))
    _style_axes(axes, ylabel="Mean of the four nearest states (standardised)")

    axes.axhline(0, color=BASELINE, linewidth=1.1, zorder=1)
    axes.axvline(0, color=BASELINE, linewidth=1.1, zorder=1)

    high = standardised > 0
    for mask, colour, marker, label in (
        (high, ORANGE, "o", "Above-average state"),
        (~high, BLUE, "s", "Below-average state"),
    ):
        axes.scatter(
            standardised[mask],
            lagged[mask],
            color=colour,
            marker=marker,
            s=58,
            edgecolor=SURFACE,
            linewidth=1.3,
            zorder=3,
            label=label,
        )

    slope, intercept = np.polyfit(standardised, lagged, 1)
    grid = np.linspace(standardised.min() - 0.2, standardised.max() + 0.2, 20)
    axes.plot(
        grid, slope * grid + intercept,
        color=INK, linewidth=1.6, zorder=2,
    )

    headline = measure["headline"]
    axes.set_xlabel(
        "State poverty headcount (standardised)", color=MUTED, fontsize=9
    )
    axes.legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper left")
    axes.set_title(
        f"Moran's I = {headline.i:.3f}, the slope of this line "
        f"(p = {headline.p_value:.4f}, the floor for "
        f"{headline.permutations:,} permutations)",
        color=INK,
        fontsize=11.5,
        loc="left",
        pad=14,
    )

    return _save(figure, "13_moran_scatter.png")


def build_statistical_figures(states: pd.DataFrame | None = None) -> list[Path]:
    """The Phase 2 figures: intervals, diagnostics and space."""
    import matplotlib

    matplotlib.use("Agg")

    if states is None:
        states = load_states()

    intervals = poverty_intervals(states)
    model = poverty_model(states)
    spatial_result = spatial_findings(states)

    return [
        figure_correlation_intervals(intervals),
        figure_model_diagnostics(model),
        figure_state_maps(states, spatial_result),
        figure_moran_scatter(spatial_result),
    ]


def print_statistical_findings(states: pd.DataFrame | None = None) -> None:
    """Print the Phase 2 numbers quoted in the report."""
    if states is None:
        states = load_states()

    if "NGA_MPI_HEADCOUNT" not in states.columns:
        print("STATISTICS: no MPI data loaded.")
        return

    intervals = poverty_intervals(states)
    print("CORRELATION INTERVALS (95%)")
    for label in ("pooled", "north", "south"):
        row = intervals[label]
        print(
            f"  {label:<7} n={row['n']:<3} r={row['r']:+.3f}   "
            f"bootstrap [{row['bootstrap_low']:+.3f}, "
            f"{row['bootstrap_high']:+.3f}]   "
            f"fisher [{row['fisher_low']:+.3f}, {row['fisher_high']:+.3f}]"
            f"{'   includes zero' if row['includes_zero'] else ''}"
        )

    model = poverty_model(states)
    print()
    print(f"MODEL  {model['formula']}  (HC3 robust standard errors)")
    for name, term in model["terms"].items():
        print(
            f"  {name:<18} {term['estimate']:+8.3f}  "
            f"se {term['robust_se']:6.3f} (classical {term['classical_se']:.3f})"
            f"  p={term['p']:.4f}  "
            f"[{term['low']:+.3f}, {term['high']:+.3f}]"
        )
    print(
        f"  southern slope {model['southern_slope']:+.3f} points of poverty "
        "per dependant"
    )
    print(f"  northern slope {model['northern_slope']:+.3f}")
    print(
        f"  difference     {model['slope_difference']:+.3f} "
        f"(p={model['slope_difference_p']:.4f})"
    )
    print(
        f"  R2 {model['r_squared']:.3f}, adjusted {model['adjusted_r_squared']:.3f}"
        f", Breusch-Pagan p={model['breusch_pagan_p']:.4f}"
    )
    print(
        f"  influential states (Cook's D > {model['cooks_threshold']:.3f}): "
        + (
            ", ".join(
                f"{row['state']} {row['cooks_d']:.2f}"
                for _, row in model["influential"].iterrows()
            )
            or "none"
        )
    )
    print(
        f"  refit without them (n={model['refit_n']}): "
        f"south {model['refit_southern_slope']:+.3f}, "
        f"north {model['refit_northern_slope']:+.3f}, "
        f"difference p={model['refit_difference_p']:.4f}"
    )

    spatial_result = spatial_findings(states)
    print()
    print(
        f"SPATIAL AUTOCORRELATION (k={spatial_result['k']} nearest "
        f"neighbours, {spatial_result['permutations']:,} permutations)"
    )
    for label, measure in spatial_result["measures"].items():
        headline = measure["headline"]
        print(
            f"  {label:<10} I={headline.i:+.3f}  "
            f"E[I]={headline.expected:+.3f}  "
            f"z={headline.z_score:+.2f}  p={headline.p_value:.4f}"
        )
        across = "  ".join(
            f"k={result.k}: {result.i:+.2f}" for result in measure["sensitivity"]
        )
        print(f"             across k -> {across}")

if __name__ == "__main__":
    main()
