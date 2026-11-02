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
    """Per-capita income relative to its historical peak."""
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


def price_findings(data: pd.DataFrame) -> dict:
    """Inflation level and recent acceleration."""
    inflation = data["NGA_INFLATION_CPI"].dropna()
    recent = inflation.loc[2015:]

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
    """Per-capita income against its own peak."""
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
        "Nigeria's income per person has not regained its "
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
        f"{series.index[0]}  {findings['manufacturing_first']:.1f}%",
        xy=(series.index[0], findings["manufacturing_first"]),
        xytext=(6, 4),
        textcoords="offset points",
        fontsize=9,
        color=INK,
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
    args = parser.parse_args()

    print_findings()

    if args.figures:
        print("\nFIGURES")
        for path in build_figures():
            print(f"  {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
