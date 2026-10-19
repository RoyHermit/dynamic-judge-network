"""Public-data source: an ECB-style reference-rate CSV (spec §4.6).

The loader only reads a local file; downloading it and checking the
publisher's licence are human steps. The file lives outside Git (`data/`).
"""

from __future__ import annotations

import csv
import hashlib
import json
from typing import Literal

from src.data.schema import SPLITS, Regime, Sample, Split
from src.data.windowing import WindowSpec, block_bars, cut_samples, total_bars


class EcbCsvConfig(WindowSpec):
    source: Literal["ecb_csv"] = "ecb_csv"
    path: str
    column: str = "USD"  # currency column of `Date,USD,JPY,...`


def read_series(path: str, column: str) -> list[float]:
    """Close series oldest-first; blank and `N/A` cells are dropped."""
    with open(path, newline="") as handle:
        reader = csv.reader(handle)
        header = [h.strip() for h in next(reader)]
        if "Date" not in header or column not in header:
            raise ValueError(f"column {column!r} (or 'Date') not found in {path}")
        date_i, value_i = header.index("Date"), header.index(column)
        rows: list[tuple[str, float]] = []
        for row in reader:
            if len(row) <= max(date_i, value_i):
                continue
            cell = row[value_i].strip()
            if cell in ("", "N/A"):
                continue
            rows.append((row[date_i].strip(), float(cell)))
    rows.sort(key=lambda r: r[0])  # ISO dates sort chronologically
    return [value for _, value in rows]


def file_digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def ecb_identity(cfg: EcbCsvConfig) -> str:
    """Short id from the configuration **and the file content**, so a
    replaced CSV can never be mixed with answers stored for the old one."""
    payload = json.dumps(cfg.model_dump(mode="json"), sort_keys=True)
    digest = hashlib.sha256((payload + file_digest(cfg.path)).encode())
    return digest.hexdigest()[:8]


class EcbSource:
    """DataSource over the most recent bars the configured splits need.

    Splits follow time (oldest first, embargo between them), so
    `test_shift` is the newest period: a real shift in time instead of the
    synthetic volatility multiplier.
    """

    def __init__(self, cfg: EcbCsvConfig) -> None:
        self.config = cfg
        series = read_series(cfg.path, cfg.column)
        need = total_bars(cfg)
        if len(series) < need:
            raise ValueError(f"need {need} bars, file has {len(series)}")
        self.bars = series[len(series) - need :]
        starts: dict[Split, int] = {}
        pos = 0
        for k, split in enumerate(SPLITS):
            if k > 0:
                pos += cfg.embargo_bars
            starts[split] = pos
            pos += block_bars(cfg, split)
        regimes: list[Regime] = ["unknown"] * len(self.bars)
        self._samples, self.excluded = cut_samples(
            self.bars, regimes, starts, cfg, ecb_identity(cfg)
        )

    def samples(self, split: Split) -> list[Sample]:
        return [s for s in self._samples if s.split == split]
