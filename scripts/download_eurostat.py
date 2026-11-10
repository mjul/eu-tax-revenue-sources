"""Download Eurostat datasets as one Parquet file each.

uv run python scripts/download_eurostat.py
"""

from __future__ import annotations

import gzip
import shutil
import tempfile
import urllib.request
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq

# One Eurostat online data code per output file in data/.
DATASETS = ("gov_10a_taxag",)

_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"
_API = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{code}"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def dataset_url(code: str) -> str:
    return f"{_API.format(code=code)}?format=SDMX-CSV&compressed=true"


def download_dataset(code: str, data_dir: Path) -> Path:
    """Fetch one SDMX-CSV dataset and write data/<code>.parquet."""
    data_dir.mkdir(parents=True, exist_ok=True)
    destination = data_dir / f"{code}.parquet"
    request = urllib.request.Request(
        dataset_url(code),
        headers={"Accept": _ACCEPT, "User-Agent": "eu-tax-revenue-sources"},
    )

    with tempfile.TemporaryDirectory(prefix=f".{code}.", dir=data_dir) as temporary:
        temp_dir = Path(temporary)
        compressed_path = temp_dir / f"{code}.csv.gz"
        csv_path = temp_dir / f"{code}.csv"
        partial = temp_dir / f"{code}.parquet"

        with (
            urllib.request.urlopen(request, timeout=300) as response,
            compressed_path.open("wb") as handle,
        ):
            shutil.copyfileobj(response, handle)
        with gzip.open(compressed_path, "rb") as source, csv_path.open("wb") as handle:
            shutil.copyfileobj(source, handle)

        # Keep codes and flags as strings. An all-empty confidentiality
        # column would otherwise be stored as a null type.
        table = pa_csv.read_csv(
            csv_path,
            convert_options=pa_csv.ConvertOptions(
                column_types={
                    "DATAFLOW": pa.string(),
                    "LAST UPDATE": pa.string(),
                    "freq": pa.string(),
                    "unit": pa.string(),
                    "sector": pa.string(),
                    "na_item": pa.string(),
                    "geo": pa.string(),
                    "TIME_PERIOD": pa.int64(),
                    "OBS_VALUE": pa.float64(),
                    "OBS_FLAG": pa.string(),
                    "CONF_STATUS": pa.string(),
                }
            ),
        )
        pq.write_table(table, partial, compression="zstd")
        shutil.move(partial, destination)

    return destination


def main() -> None:
    data_dir = repo_root() / "data"
    for code in DATASETS:
        path = download_dataset(code, data_dir)
        rows = pq.read_metadata(path).num_rows
        print(f"{code}: {rows} rows -> {path}")


if __name__ == "__main__":
    main()
