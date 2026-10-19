"""Public-data source reading an ECB-style reference-rate CSV (design in chat,
spec §4.6). Fixtures are generated from the CSV schema; no real data."""

import itertools
import math
import random
from pathlib import Path

import pytest

from src.data.factory import dataset_identity, load_source, same_dataset
from src.data.schema import SPLITS
from src.data.synthetic import SyntheticConfig
from src.experiments.config import Exp1Config

SIZES = {"pilot": 5, "calib": 20, "thresh": 20, "test": 20, "test_shift": 20}


def write_csv(path: Path, n: int = 1200, seed: int = 0, usd_missing_every: int = 50):
    """ECB-like layout: header Date,USD,JPY,; newest row first; 'N/A' gaps."""
    rng = random.Random(seed)
    price, rows = 1.1, []
    for k in range(n):  # oldest -> newest
        price *= math.exp(rng.gauss(0, 0.005))
        day = f"{2000 + k // 336}-{1 + (k // 28) % 12:02d}-{1 + k % 28:02d}"
        usd = "N/A" if k % usd_missing_every == 7 else f"{price:.4f}"
        rows.append((day, usd, f"{price * 130:.2f}"))
    lines = ["Date,USD,JPY,"] + [f"{d},{u},{j}," for d, u, j in reversed(rows)]
    path.write_text("\n".join(lines) + "\n")
    return {d: u for d, u, _ in rows}


def cfg_dict(path: Path, **extra) -> dict:
    return {
        "source": "ecb_csv",
        "path": str(path),
        "column": "USD",
        "split_sizes": SIZES,
        **extra,
    }


def make_source(tmp_path: Path, **kw):
    csv = tmp_path / "rates.csv"
    by_day = write_csv(csv, **kw)
    cfg = Exp1Config.model_validate({"data": cfg_dict(csv)}).data
    return load_source(cfg), cfg, csv, by_day


def test_samples_are_chronological_unknown_regime_and_leak_free(tmp_path):
    source, cfg, _, _ = make_source(tmp_path)
    assert source.samples("calib")
    assert {s.regime for split in SPLITS for s in source.samples(split)} == {"unknown"}
    by_split = {sp: [s.t_index for s in source.samples(sp)] for sp in SPLITS}
    for a, b in itertools.pairwise(SPLITS):  # oldest -> newest, with embargo
        gap = (min(by_split[b]) - cfg.window + 1) - (max(by_split[a]) + cfg.horizon)
        assert gap >= cfg.embargo_bars
    bars = source.bars
    for s in source.samples("test_shift"):
        t = s.t_index
        assert s.state["bars"] == [
            round(b, 4) for b in bars[t - cfg.window + 1 : t + 1]
        ]
        assert set(s.state) == {"bars"}
        assert s.label == ("HIGH" if bars[t + cfg.horizon] > bars[t] else "LOW")


def test_missing_values_are_dropped_and_series_is_oldest_first(tmp_path):
    source, _, _, by_day = make_source(tmp_path)
    expected = [float(v) for _, v in sorted(by_day.items()) if v != "N/A"]
    # the loader uses the most recent bars that the splits need
    assert source.bars == expected[len(expected) - len(source.bars) :]
    assert not any(math.isnan(v) for v in source.bars)


def test_excluded_ties_are_counted_for_every_split(tmp_path):
    source, _, _, _ = make_source(tmp_path)
    assert set(source.excluded) == set(SPLITS)


def test_too_short_file_is_rejected(tmp_path):
    csv = tmp_path / "short.csv"
    write_csv(csv, n=80)
    cfg = Exp1Config.model_validate({"data": cfg_dict(csv)}).data
    with pytest.raises(ValueError, match="bars"):
        load_source(cfg)


def test_unknown_column_is_rejected(tmp_path):
    csv = tmp_path / "rates.csv"
    write_csv(csv)
    cfg = Exp1Config.model_validate({"data": cfg_dict(csv, column="XXX")}).data
    with pytest.raises(ValueError, match="XXX"):
        load_source(cfg)


def test_dataset_identity_follows_file_content_and_config(tmp_path):
    source, cfg, csv, _ = make_source(tmp_path)
    before = dataset_identity(cfg)
    first_ids = {s.input_id for s in source.samples("calib")}
    assert first_ids == {s.input_id for s in load_source(cfg).samples("calib")}

    csv.write_text(csv.read_text().replace("N/A", "1.2345", 1))  # content change
    assert dataset_identity(cfg) != before
    assert not first_ids & {s.input_id for s in load_source(cfg).samples("calib")}


def test_same_dataset_distinguishes_sources_and_paths(tmp_path):
    csv = tmp_path / "rates.csv"
    write_csv(csv)
    ecb = Exp1Config.model_validate({"data": cfg_dict(csv)}).data.model_dump()
    synth = SyntheticConfig().model_dump()
    assert not same_dataset(ecb, synth)
    assert same_dataset(ecb, dict(ecb))
    assert not same_dataset(ecb, {**ecb, "column": "JPY"})


def test_default_config_stays_synthetic_and_keeps_its_dataset_id():
    cfg = Exp1Config()
    assert cfg.data.source == "synthetic"
    # id of the configuration used for the first real run (stored inputs)
    first_run = SyntheticConfig(
        seed=0,
        split_sizes={
            "pilot": 30,
            "calib": 200,
            "thresh": 200,
            "test": 300,
            "test_shift": 300,
        },
    )
    assert dataset_identity(first_run) == "0d17642b"
    # configs stored before `source` existed still validate as synthetic
    old = {k: v for k, v in first_run.model_dump().items() if k != "source"}
    assert Exp1Config.model_validate({"data": old}).data.source == "synthetic"


async def test_fit_refuses_when_the_csv_changed_after_the_run(tmp_path):
    import asyncio

    import typesafe_sdk as ts

    from src.experiments.cli import main
    from src.experiments.runner import ArmSpec, run_arm
    from src.judges.jev_executor import JevStageExecutor
    from src.storage import db
    from src.storage.writer import SqliteStorageWriter

    class FlatClient:
        async def system_one(self, *, state, questions, **kwargs):
            return ts.SystemOneResponse(
                model="m",
                usage=ts.Usage(input_tokens=1, output_tokens=1),
                answers={n: ts.NoulAnswer(noul=0.4) for n in questions},
            )

    csv = tmp_path / "rates.csv"
    write_csv(csv)
    cfg = Exp1Config.model_validate(
        {"data": cfg_dict(csv), "db_path": str(tmp_path / "e.db")}
    )
    config_path = tmp_path / "cfg.json"
    config_path.write_text(cfg.model_dump_json())

    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    spec = ArmSpec(study_id=cfg.study_id, arm="A", horizon=cfg.data.horizon)
    source = load_source(cfg.data)
    extra = {"data": cfg.data.model_dump(), "dataset_id": dataset_identity(cfg.data)}
    executor = JevStageExecutor(FlatClient(), writer)
    for split in ("calib", "thresh"):
        await run_arm(
            spec, source.samples(split), executor, writer, conn, config_extra=extra
        )
    conn.close()

    csv.write_text(csv.read_text().replace("N/A", "1.2345", 1))  # file replaced
    argv = ["fit", "--config", str(config_path), "--arm", "A"]
    argv += ["--experiment", spec.experiment_id]
    with pytest.raises(ValueError, match="different dataset"):
        await asyncio.to_thread(main, argv)
