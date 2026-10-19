"""Shared fakes for the Experiment 2 CLI and end-to-end tests (no network)."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import typesafe_sdk as ts

from src.data.factory import load_source
from src.data.schema import SPLITS
from src.data.synthetic import SyntheticConfig
from src.experiments.exp2_arms import arm_spec
from src.experiments.exp2_config import Exp2Config
from src.experiments.runner import run_arm
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.writer import SqliteStorageWriter

# Small splits; test >= 24 so the block bootstrap (block_len 12) yields a CI.
SMALL_SIZES = {"pilot": 3, "calib": 6, "thresh": 6, "test": 30, "test_shift": 6}
# Role-dependent centre of P(HIGH); unknown judges fall back to 0.5.
ROLE_BASE = {
    "role_trend": 0.62,
    "role_momentum": 0.55,
    "role_mean_reversion": 0.45,
    "role_volatility": 0.5,
    "role_breakout": 0.58,
    "ap_judge": 0.6,
    "hl_judge": 0.52,
}


class RoleClient:
    """Fake Jev client: role-dependent probabilities with seeded noise."""

    def __init__(self, seed: int = 13, constant: float | None = None) -> None:
        self.rng = random.Random(seed)
        self.constant = constant
        self.requests: list[list[str]] = []

    async def system_one(
        self, *, state: dict[str, Any], questions: dict[str, Any], **kwargs: Any
    ) -> ts.SystemOneResponse:
        """Answer every question; records the judge ids of each request."""
        self.requests.append(list(questions))
        answers = {}
        for name in questions:
            if self.constant is not None:
                p = self.constant
            else:
                base = ROLE_BASE.get(name.split("#")[0], 0.5)
                p = min(max(base + self.rng.gauss(0.0, 0.12), 0.02), 0.98)
            answers[name] = ts.NoulAnswer(noul=p)
        return ts.SystemOneResponse(
            model="jev-test",
            usage=ts.Usage(input_tokens=20, output_tokens=2),
            answers=answers,
        )


def small_config(tmp_path: Path, name: str = "exp2", **update: Any) -> Path:
    """Write a small synthetic Exp2 config into `tmp_path`; return its path."""
    data = update.pop("data", None) or SyntheticConfig(
        seed=11, split_sizes=dict(SMALL_SIZES)
    )
    cfg = Exp2Config(
        study_id=name,
        db_path=str(tmp_path / f"{name}.db"),
        data=data,
        bootstrap_resamples=100,
        bootstrap_block_len=12,
        **update,
    )
    path = tmp_path / f"{name}.json"
    path.write_text(cfg.model_dump_json())
    return path


async def run_everything(
    config_path: Path, short: dict[tuple[str, str], int] | None = None
) -> None:
    """Run every LLM arm on every split with a fake client (no network).

    `short[(arm, split)] = k` leaves the last `k` samples of that split unrun.
    """
    cfg = Exp2Config.model_validate_json(Path(config_path).read_text())
    source = load_source(cfg.data)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    executor = JevStageExecutor(RoleClient(), writer)
    for arm in ("A", "C", "Ap", "Ap5", "D"):
        spec = arm_spec(cfg.study_id, arm, cfg.n_replicas, cfg.data.horizon)
        for split in SPLITS:
            samples = source.samples(split)
            drop = (short or {}).get((arm, split), 0)
            await run_arm(spec, samples[: len(samples) - drop], executor, writer, conn)
    conn.close()


def write_ecb_csv(path: Path, n: int = 1200, seed: int = 5) -> Path:
    """Generated ECB-layout CSV (`Date,USD,JPY,`, newest first); no real data."""
    rng = random.Random(seed)
    price, rows = 1.1, []
    for k in range(n):  # oldest -> newest
        price *= math.exp(rng.gauss(0, 0.005))
        day = f"{2000 + k // 336}-{1 + (k // 28) % 12:02d}-{1 + k % 28:02d}"
        rows.append(f"{day},{price:.4f},{price * 130:.2f},")
    path.write_text("\n".join(["Date,USD,JPY,", *reversed(rows)]) + "\n")
    return path
