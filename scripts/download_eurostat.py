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
# nama_10_pe includes total population (POP_NC, thousands of persons).
DATASETS = ("gov_10a_taxag", "nama_10_pe")

_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"
_API = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{code}"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def dataset_url(code: str) -> str:
    return f"{_API.format(code=code)}?format=SDMX-CSV&compressed=true"


def column_types(csv_path: Path) -> dict[str, pa.DataType]:
    """Type the SDMX-CSV header that this file actually has.

    Tax aggregates include sector; population and employment do not.
    Codes and flags stay strings so an empty confidentiality column is
    not stored as a null type.
    """
    header = csv_path.open(encoding="utf-8").readline().rstrip("\r\n")
    types: dict[str, pa.DataType] = {}
    for name in header.split(","):
        if name == "TIME_PERIOD":
            types[name] = pa.int64()
        elif name == "OBS_VALUE":
            types[name] = pa.float64()
        else:
            types[name] = pa.string()
    return types


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

        table = pa_csv.read_csv(
            csv_path,
            convert_options=pa_csv.ConvertOptions(column_types=column_types(csv_path)),
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
