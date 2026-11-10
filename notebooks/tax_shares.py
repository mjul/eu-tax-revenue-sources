import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import polars as pl

    data_dir = Path(__file__).resolve().parents[1] / "data"
    taxes = pl.read_parquet(data_dir / "gov_10a_taxag.parquet")
    population = pl.read_parquet(data_dir / "nama_10_pe.parquet")
    return Path, alt, pl, population, taxes


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
    return countries, member_codes, shares, source_codes, source_names, sources


@app.cell
def _(Path, alt, shares, source_names):
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
    # The notebook chart stretches with the page. The README illustration
    # needs a fixed width, so the saved copy does not use "container".
    asset_dir = Path(__file__).resolve().parents[1] / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    chart.properties(width=760).save(asset_dir / "tax_shares_2025.svg")
    chart
    return


@app.cell
def _(countries, member_codes, pl, population, source_codes, sources, taxes):
    # Effective rate is the category's revenue as a percentage of GDP.
    # Euro per person is that rate times GDP per person, so countries
    # with the same rate still differ when incomes differ.
    revenue = taxes.filter(
        (pl.col("unit") == "MIO_EUR")
        & (pl.col("sector") == "S13")
        & (pl.col("TIME_PERIOD") == 2025)
        & pl.col("geo").is_in(member_codes)
        & pl.col("na_item").is_in(source_codes)
    ).select("geo", "na_item", pl.col("OBS_VALUE").alias("mio_eur"))
    rates = taxes.filter(
        (pl.col("unit") == "PC_GDP")
        & (pl.col("sector") == "S13")
        & (pl.col("TIME_PERIOD") == 2025)
        & pl.col("geo").is_in(member_codes)
        & pl.col("na_item").is_in(source_codes)
    ).select("geo", "na_item", pl.col("OBS_VALUE").alias("rate"))
    people = population.filter(
        (pl.col("unit") == "THS_PER")
        & (pl.col("na_item") == "POP_NC")
        & (pl.col("TIME_PERIOD") == 2025)
        & pl.col("geo").is_in(member_codes)
    ).select("geo", pl.col("OBS_VALUE").alias("thousands"))
    observed_rates = (
        countries.join(sources, how="cross")
        .join(revenue, on=["geo", "na_item"], how="left")
        .join(rates, on=["geo", "na_item"], how="left")
        .join(people, on="geo", how="inner")
        .with_columns(pl.col("mio_eur").fill_null(0.0), pl.col("rate").fill_null(0.0))
        .with_columns(
            (pl.col("mio_eur") * 1000 / pl.col("thousands")).alias("eur_per_capita")
        )
    )
    # Extra rows stretch each panel so country codes are not clipped.
    # They are not countries and are left out of the points and labels.
    padding = observed_rates.group_by("source", "source_order").agg(
        (pl.col("rate").max() * 1.28).alias("rate"),
        (pl.col("eur_per_capita").max() * 1.18).alias("eur_per_capita"),
    )

    def label_shift(frame: pl.DataFrame) -> pl.DataFrame:
        """Pixel offset so neighbouring country codes do not cover each other."""
        panel_width, panel_height = 190.0, 168.0
        shifts: list[dict[str, object]] = []
        for key, group in frame.group_by("source"):
            xmax = float(group["rate"].max() or 0.0)
            ymax = float(group["eur_per_capita"].max() or 0.0)
            placed: list[tuple[float, float, float, float]] = []
            labeled = group.filter(pl.col("geo").is_not_null()).filter(
                (pl.col("rate") != 0.0) | (pl.col("eur_per_capita") != 0.0)
            )
            for geo, rate, eur in (
                labeled.sort("eur_per_capita", descending=True)
                .select("geo", "rate", "eur_per_capita")
                .iter_rows()
            ):
                px = 0.0 if xmax == 0 else float(rate) / xmax * panel_width
                py = 0.0 if ymax == 0 else (1 - float(eur) / ymax) * panel_height
                chosen = 0
                for dy in (0, 9, -9, 18, -18, 27, -27):
                    box = (px + 6, py + dy - 4, 16, 9)
                    hits = False
                    for left, top, wide, high in placed:
                        if (
                            box[0] < left + wide
                            and box[0] + box[2] > left
                            and box[1] < top + high
                            and box[1] + box[3] > top
                        ):
                            hits = True
                            break
                    if not hits:
                        chosen = dy
                        break
                placed.append((px + 6, py + chosen - 4, 16, 9))
                shifts.append({"source": key[0], "geo": geo, "label_dy": chosen})
        return pl.DataFrame(shifts)

    labeled_rates = observed_rates.with_columns(
        pl.when((pl.col("rate") == 0.0) & (pl.col("eur_per_capita") == 0.0))
        .then(pl.lit(None, dtype=pl.String))
        .otherwise(pl.col("geo"))
        .alias("label")
    )
    rate_revenue = (
        pl.concat([labeled_rates, padding], how="diagonal")
        .join(
            label_shift(pl.concat([labeled_rates, padding], how="diagonal")),
            on=["source", "geo"],
            how="left",
        )
        .sort("source_order", "country")
    )
    return rate_revenue


@app.cell
def _(Path, alt, rate_revenue, source_names):
    points = (
        alt.Chart(rate_revenue)
        .transform_filter("datum.geo != null")
        .mark_circle(size=55, color="#4C78A8", opacity=0.9)
        .encode(
            x=alt.X(
                "rate:Q",
                title="Revenue as % of GDP",
                scale=alt.Scale(domainMin=0, nice=True),
            ),
            y=alt.Y(
                "eur_per_capita:Q",
                title="Euro per person",
                scale=alt.Scale(domainMin=0, nice=True),
                axis=alt.Axis(format=",.0f"),
            ),
            tooltip=[
                alt.Tooltip("country:N", title="Country"),
                alt.Tooltip("source:N", title="Source"),
                alt.Tooltip("rate:Q", title="Revenue as % of GDP", format=".1f"),
                alt.Tooltip("eur_per_capita:Q", title="Euro per person", format=",.0f"),
            ],
        )
    )
    # A constant dy per layer. A yOffset field is not applied inside these facets.
    labels = alt.layer(
        *[
            alt.Chart(rate_revenue)
            .transform_filter(f"datum.label != null && datum.label_dy == {dy}")
            .mark_text(
                align="left",
                baseline="middle",
                dx=6,
                dy=dy,
                fontSize=8,
                color="#1f2a33",
            )
            .encode(x="rate:Q", y="eur_per_capita:Q", text="label:N")
            for dy in (0, 9, -9, 18, -18, 27, -27)
        ]
    )
    extent = (
        alt.Chart(rate_revenue)
        .mark_point(opacity=0)
        .encode(x="rate:Q", y="eur_per_capita:Q")
    )
    rate_chart = (
        (points + labels + extent)
        .properties(width=190, height=168)
        .facet(
            facet=alt.Facet(
                "source:N",
                title=None,
                sort=source_names,
                header=alt.Header(labelFontSize=11, labelLimit=200),
            ),
            columns=4,
        )
        .resolve_scale(x="independent", y="independent")
        .properties(
            title=alt.Title(
                "Tax rate and revenue per person, 2025",
                subtitle=[
                    (
                        "Each point is a member state. The rate is that "
                        "category's general-government revenue as a "
                        "percentage of GDP."
                    ),
                    (
                        "Revenue is euro per person. The same rate can raise "
                        "different amounts when GDP per person differs."
                    ),
                ],
            )
        )
    )
    rate_asset_dir = Path(__file__).resolve().parents[1] / "assets"
    rate_asset_dir.mkdir(parents=True, exist_ok=True)
    rate_chart.save(rate_asset_dir / "rate_revenue_2025.svg")
    rate_chart
    return


if __name__ == "__main__":
    app.run()
