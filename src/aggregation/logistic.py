"""Pure-Python L2-regularised logistic regression (Experiment 2 spec §8)."""

from __future__ import annotations

import math

from pydantic import BaseModel

MAX_ITER = 100
TOL = 1e-8
JITTER = 1e-9
MAX_STEP = 10.0  # per-coordinate step cap keeps Newton stable on separable data


def _sigmoid(z: float) -> float:
    """Numerically stable logistic function."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class LogisticModel(BaseModel):
    """Standardising logistic model; `predict` returns P(y = 1)."""

    means: list[float]
    scales: list[float]
    weights: list[float]
    bias: float
    l2: float

    def predict(self, x: list[float]) -> float:
        """Probability of the positive class for one raw feature vector."""
        z = self.bias + sum(
            w * (v - m) / s
            for w, v, m, s in zip(self.weights, x, self.means, self.scales)
        )
        return _sigmoid(z)


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve a x = b by Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        if abs(m[col][col]) < 1e-300:
            raise ValueError("singular matrix")
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def fit_logistic(xs: list[list[float]], ys: list[float], l2: float) -> LogisticModel:
    """Fit by full-batch Newton/IRLS on standardised features.

    Penalty is (l2 / 2) * |w|^2 on the summed log loss; the bias is not
    penalised. A zero-variance column gets scale 1.
    """
    if not xs or len(xs) != len(ys):
        raise ValueError("fit_logistic needs equal-length, non-empty xs and ys")
    n, d = len(xs), len(xs[0])
    means = [sum(r[j] for r in xs) / n for j in range(d)]
    scales = []
    for j in range(d):
        sd = math.sqrt(sum((r[j] - means[j]) ** 2 for r in xs) / n)
        scales.append(sd if sd > 1e-12 else 1.0)
    z = [[(r[j] - means[j]) / scales[j] for j in range(d)] for r in xs]

    beta = [0.0] * (d + 1)  # weights then bias (last)
    for _ in range(MAX_ITER):
        grad = [0.0] * (d + 1)
        hess = [[0.0] * (d + 1) for _ in range(d + 1)]
        for row, y in zip(z, ys):
            f = [*row, 1.0]
            p = _sigmoid(sum(b * v for b, v in zip(beta, f)))
            s = p * (1.0 - p)
            for i in range(d + 1):
                grad[i] += (p - y) * f[i]
                for k in range(d + 1):
                    hess[i][k] += s * f[i] * f[k]
        for j in range(d):
            grad[j] += l2 * beta[j]
            hess[j][j] += l2
        for i in range(d + 1):
            hess[i][i] += JITTER
        step = _solve(hess, grad)
        step = [max(-MAX_STEP, min(MAX_STEP, v)) for v in step]
        beta = [b - v for b, v in zip(beta, step)]
        if max(abs(v) for v in step) < TOL:
            break
    return LogisticModel(
        means=means, scales=scales, weights=beta[:d], bias=beta[d], l2=l2
    )
