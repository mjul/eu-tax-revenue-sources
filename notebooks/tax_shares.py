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
def _(alt, countries, member_codes, pl, population, source_codes, sources, taxes):
    import colorsys
    import math

    import marimo as mo

    spoke_count = sources.height
    # Twelve o'clock, then clockwise. source_order follows that sequence.
    spoke_angles = [
        math.pi / 2 - index * (2 * math.pi / spoke_count)
        for index in range(spoke_count)
    ]

    def _polar(source_order: int, radius: float) -> tuple[float, float]:
        order = source_order % spoke_count
        angle = spoke_angles[order]
        return radius * math.cos(angle), radius * math.sin(angle)

    def _series(amount: pl.DataFrame) -> pl.DataFrame:
        # Each spoke runs from zero to the highest member, so a small
        # category is still readable next to income taxes.
        maxima = amount.group_by("source", "source_order").agg(
            pl.col("amount").max().alias("axis_max")
        )
        scaled = amount.join(maxima, on=["source", "source_order"]).with_columns(
            pl.when(pl.col("axis_max") == 0)
            .then(0.0)
            .otherwise(pl.col("amount") / pl.col("axis_max"))
            .alias("radius")
        )
        coordinates = [
            _polar(order, radius)
            for order, radius in scaled.select("source_order", "radius").iter_rows()
        ]
        scaled = scaled.with_columns(
            pl.Series("x", [item[0] for item in coordinates]),
            pl.Series("y", [item[1] for item in coordinates]),
        )
        closing = scaled.filter(pl.col("source_order") == 0).with_columns(
            pl.lit(spoke_count, dtype=pl.Int64).alias("source_order")
        )
        return pl.concat([scaled, closing]).sort("country", "source_order")

    def _guide() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        rings: list[dict[str, float | int]] = []
        for level in (0.25, 0.5, 0.75, 1.0):
            for order in (*range(spoke_count), spoke_count):
                x_pos, y_pos = _polar(order, level)
                rings.append(
                    {"level": level, "source_order": order, "x": x_pos, "y": y_pos}
                )
        spokes: list[dict[str, float]] = []
        labels: list[dict[str, float | str | int]] = []
        for order in range(spoke_count):
            x_pos, y_pos = _polar(order, 1.0)
            spokes.append({"x": 0.0, "y": 0.0, "x2": x_pos, "y2": y_pos})
            label_x, label_y = _polar(order, 1.16)
            if label_x > 0.2:
                align, baseline, dx, dy = "left", "middle", 4, 0
            elif label_x < -0.2:
                align, baseline, dx, dy = "right", "middle", -4, 0
            elif label_y > 0:
                align, baseline, dx, dy = "center", "bottom", 0, -2
            else:
                align, baseline, dx, dy = "center", "top", 0, 2
            labels.append(
                {
                    "source_order": order,
                    "x": label_x,
                    "y": label_y,
                    "align": align,
                    "baseline": baseline,
                    "dx": dx,
                    "dy": dy,
                }
            )
        return pl.DataFrame(rings), pl.DataFrame(spokes), pl.DataFrame(labels)

    def _amounts(unit: str) -> pl.DataFrame:
        observed = taxes.filter(
            (pl.col("unit") == unit)
            & (pl.col("sector") == "S13")
            & (pl.col("TIME_PERIOD") == 2025)
            & pl.col("geo").is_in(member_codes)
            & pl.col("na_item").is_in(source_codes)
        ).select("geo", "na_item", pl.col("OBS_VALUE").alias("amount"))
        return (
            countries.join(sources, how="cross")
            .join(observed, on=["geo", "na_item"], how="left")
            .with_columns(pl.col("amount").fill_null(0.0))
            .select("country", "source", "source_order", "amount")
        )

    gdp_amounts = _amounts("PC_GDP")
    revenue = _amounts("MIO_EUR")
    people = population.filter(
        (pl.col("unit") == "THS_PER")
        & (pl.col("na_item") == "POP_NC")
        & (pl.col("TIME_PERIOD") == 2025)
        & pl.col("geo").is_in(member_codes)
    ).select("geo", pl.col("OBS_VALUE").alias("thousands"))
    per_capita_amounts = (
        revenue.join(countries.select("country", "geo"), on="country")
        .join(people, on="geo", how="inner")
        .with_columns((pl.col("amount") * 1000 / pl.col("thousands")).alias("amount"))
        .select("country", "source", "source_order", "amount")
    )
    country_names = countries.sort("country").get_column("country").to_list()
    palette = []
    for index, _name in enumerate(country_names):
        red, green, blue = colorsys.hls_to_rgb(
            (index * 137.508 % 360) / 360, 0.38, 0.70
        )
        palette.append(
            f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"
        )
    rings, spokes, axis_labels = _guide()
    gdp_series = _series(gdp_amounts)
    per_capita_series = _series(per_capita_amounts)
    return (
        axis_labels,
        country_names,
        gdp_series,
        mo,
        palette,
        per_capita_series,
        rings,
        spokes,
    )


@app.cell
def _(
    Path,
    alt,
    axis_labels,
    country_names,
    gdp_series,
    mo,
    palette,
    per_capita_series,
    pl,
    rings,
    spokes,
):
    def _radar(
        series: pl.DataFrame,
        title: str,
        subtitle: str,
        value_title: str,
        value_format: str,
        axis_suffix: str,
    ):
        maxima = (
            series.filter(pl.col("source_order") < series["source_order"].max())
            .group_by("source", "source_order")
            .agg(pl.col("axis_max").first())
            .sort("source_order")
        )
        labels = axis_labels.join(maxima, on="source_order").with_columns(
            pl.col("axis_max")
            .map_elements(
                lambda value: f"{format(value, value_format)}{axis_suffix}",
                return_dtype=pl.String,
            )
            .alias("axis_text")
        )
        # Category name, then the value at the outer ring.
        labels = labels.with_columns(
            (pl.col("source") + "\n" + pl.col("axis_text")).alias("text")
        )
        highlight = alt.selection_point(fields=["country"], bind="legend")
        # An empty selection shows every country. Choosing one in the
        # legend dims the rest.
        opacity = alt.condition(highlight, alt.value(1), alt.value(0.12), empty=True)
        x_axis = alt.X(
            "x:Q", axis=None, scale=alt.Scale(domain=[-1.55, 1.55], nice=False)
        )
        y_axis = alt.Y(
            "y:Q", axis=None, scale=alt.Scale(domain=[-1.45, 1.45], nice=False)
        )
        guide = alt.Chart(spokes).mark_rule(color="#e4e4e4", strokeWidth=1).encode(
            x=x_axis, y=y_axis, x2="x2:Q", y2="y2:Q"
        ) + alt.Chart(rings).mark_line(color="#d0d0d0", strokeWidth=1).encode(
            x=x_axis,
            y=y_axis,
            order="source_order:Q",
            detail="level:N",
        )
        countries_layer = (
            alt.Chart(series)
            .mark_line(strokeWidth=1.6)
            .encode(
                x=x_axis,
                y=y_axis,
                color=alt.Color(
                    "country:N",
                    title="Country",
                    scale=alt.Scale(domain=country_names, range=palette),
                    legend=alt.Legend(
                        orient="bottom",
                        columns=3,
                        symbolLimit=30,
                        labelLimit=140,
                    ),
                ),
                order="source_order:Q",
                opacity=opacity,
                tooltip=[
                    alt.Tooltip("country:N", title="Country"),
                    alt.Tooltip("source:N", title="Category"),
                    alt.Tooltip("amount:Q", title=value_title, format=value_format),
                ],
            )
            .add_params(highlight)
        )
        names = []
        style = labels.select("align", "baseline", "dx", "dy").unique()
        for align, baseline, dx, dy in style.iter_rows():
            placed = labels.filter(
                (pl.col("align") == align)
                & (pl.col("baseline") == baseline)
                & (pl.col("dx") == dx)
                & (pl.col("dy") == dy)
            )
            names.append(
                alt.Chart(placed)
                .mark_text(
                    align=align,
                    baseline=baseline,
                    dx=int(dx),
                    dy=int(dy),
                    fontSize=11,
                    lineHeight=13,
                    lineBreak="\n",
                    color="#222",
                )
                .encode(x=x_axis, y=y_axis, text="text:N")
            )
        names = alt.layer(*names)
        return (
            (guide + countries_layer + names)
            .properties(
                width=560,
                height=520,
                title=alt.Title(title, subtitle=subtitle),
            )
            .configure_view(stroke=None)
        )

    gdp_radar = _radar(
        gdp_series,
        "Revenue as percent of GDP, 2025",
        (
            "Each spoke is one tax, from zero at the center to the highest "
            "member state. General government."
        ),
        "Percent of GDP",
        ".1f",
        "% of GDP",
    )
    per_capita_radar = _radar(
        per_capita_series,
        "Revenue in euro per person, 2025",
        (
            "Euro per person is million euro divided by the national-accounts "
            "population. Each spoke runs from zero to the highest member state."
        ),
        "Euro per person",
        ",.0f",
        " euro",
    )
    radar_asset_dir = Path(__file__).resolve().parents[1] / "assets"
    radar_asset_dir.mkdir(parents=True, exist_ok=True)
    gdp_radar.save(radar_asset_dir / "tax_radar_gdp_2025.svg")
    per_capita_radar.save(radar_asset_dir / "tax_radar_per_capita_2025.svg")
    mo.vstack([gdp_radar, per_capita_radar])
    return


if __name__ == "__main__":
    app.run()
