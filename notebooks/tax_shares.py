import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import polars as pl

    data_path = Path(__file__).resolve().parents[1] / "data" / "gov_10a_taxag.parquet"
    taxes = pl.read_parquet(data_path)
    return alt, pl, taxes


@app.cell
def _(pl, taxes):
    # Mutually exclusive ESA parts of general-government tax and
    # social-contribution revenue. Household and corporate income stay
    # inside D51 because not every member reports that split.
    sources = pl.DataFrame(
        {
            "na_item": ["D211", "D212", "D214", "D29", "D51", "D59", "D91", "D61"],
            "source": [
                "VAT",
                "Import duties excluding VAT",
                "Other taxes on products",
                "Other taxes on production",
                "Taxes on income",
                "Other current taxes",
                "Capital taxes",
                "Net social contributions",
            ],
            "source_order": list(range(8)),
        }
    )
    countries = pl.DataFrame(
        {
            "geo": [
                "AT",
                "BE",
                "BG",
                "HR",
                "CY",
                "CZ",
                "DK",
                "EE",
                "FI",
                "FR",
                "DE",
                "EL",
                "HU",
                "IE",
                "IT",
                "LV",
                "LT",
                "LU",
                "MT",
                "NL",
                "PL",
                "PT",
                "RO",
                "SK",
                "SI",
                "ES",
                "SE",
            ],
            "country": [
                "Austria",
                "Belgium",
                "Bulgaria",
                "Croatia",
                "Cyprus",
                "Czechia",
                "Denmark",
                "Estonia",
                "Finland",
                "France",
                "Germany",
                "Greece",
                "Hungary",
                "Ireland",
                "Italy",
                "Latvia",
                "Lithuania",
                "Luxembourg",
                "Malta",
                "Netherlands",
                "Poland",
                "Portugal",
                "Romania",
                "Slovakia",
                "Slovenia",
                "Spain",
                "Sweden",
            ],
        }
    )
    member_codes = countries.get_column("geo").to_list()
    source_codes = sources.get_column("na_item").to_list()
    observed = taxes.filter(
        (pl.col("unit") == "PC_TOT")
        & (pl.col("sector") == "S13")
        & (pl.col("TIME_PERIOD") == 2025)
        & pl.col("geo").is_in(member_codes)
        & pl.col("na_item").is_in(source_codes)
    ).select("geo", "na_item", pl.col("OBS_VALUE").alias("share"))
    # Absent import duties and capital taxes are zero: the parent totals
    # already match the parts that are present.
    shares = (
        countries.join(sources, how="cross")
        .join(observed, on=["geo", "na_item"], how="left")
        .with_columns(pl.col("share").fill_null(0.0))
        .select("country", "source", "source_order", "share")
        .sort("country", "source_order")
    )
    source_names = sources.sort("source_order").get_column("source").to_list()
    return shares, source_names


@app.cell
def _(alt, shares, source_names):
    chart = (
        alt.Chart(shares)
        .mark_bar()
        .encode(
            x=alt.X(
                "share:Q",
                title="Percent of total tax and social-contribution revenue",
                stack="zero",
            ),
            y=alt.Y(
                "country:N",
                # Vega-Lite draws the first alphabetical name at the top.
                sort="ascending",
                title=None,
                axis=alt.Axis(labelLimit=140),
            ),
            color=alt.Color(
                "source:N",
                title="Revenue source",
                scale=alt.Scale(domain=source_names, scheme="tableau10"),
                legend=alt.Legend(orient="bottom", columns=2),
            ),
            order=alt.Order("source_order:Q"),
            tooltip=[
                alt.Tooltip("country:N", title="Country"),
                alt.Tooltip("source:N", title="Source"),
                alt.Tooltip("share:Q", title="Share (%)", format=".1f"),
            ],
        )
        .properties(
            title=alt.Title(
                "Where EU tax revenue comes from, 2025",
                subtitle=(
                    "General government. Each bar is that country's taxes "
                    "and social contributions."
                ),
            ),
            width="container",
            height=27 * 24,
        )
    )
    chart
    return


if __name__ == "__main__":
    app.run()
