"""Shared fakes for the Experiment 2 CLI and end-to-end tests (no network)."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import typesafe_sdk as ts

from src.data.synthetic import SyntheticConfig
from src.experiments.exp2_config import Exp2Config

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
    cfg = Exp2Config(
        study_id=name,
        db_path=str(tmp_path / f"{name}.db"),
        data=SyntheticConfig(seed=11, split_sizes=dict(SMALL_SIZES)),
        bootstrap_resamples=100,
        bootstrap_block_len=12,
        **update,
    )
    path = tmp_path / f"{name}.json"
    path.write_text(cfg.model_dump_json())
    return path
