"""Tests for the pure-Python logistic regression (Experiment 2 spec §8)."""

import math
import random

from src.aggregation.logistic import fit_logistic


def _draw(seed: int, n: int) -> tuple[list[list[float]], list[float]]:
    rng = random.Random(seed)
    xs, ys = [], []
    for _ in range(n):
        z = rng.gauss(0, 1)
        xs.append([z, rng.gauss(0, 1)])
        ys.append(1.0 if z > 0 else 0.0)
    return xs, ys


def test_logistic_learns_separable_signal():
    xs, ys = _draw(3, 400)
    model = fit_logistic(xs, ys, l2=1.0)
    tx, ty = _draw(4, 400)
    hits = sum((model.predict(x) > 0.5) == (y == 1.0) for x, y in zip(tx, ty))
    assert hits / 400 >= 0.95


def test_logistic_zero_variance_column_is_safe():
    xs, ys = _draw(3, 200)
    xs = [[*x, 5.0] for x in xs]
    model = fit_logistic(xs, ys, l2=1.0)
    assert all(math.isfinite(w) for w in model.weights)
    assert math.isfinite(model.bias)
    assert 0.0 <= model.predict(xs[0]) <= 1.0


def test_stronger_l2_shrinks_weights():
    xs, ys = _draw(3, 400)
    weak = fit_logistic(xs, ys, l2=0.01)
    strong = fit_logistic(xs, ys, l2=100.0)
    norm = lambda m: math.sqrt(sum(w * w for w in m.weights))
    assert norm(strong) < norm(weak)
