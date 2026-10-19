"""Moving-block paired bootstrap (spec §7).

Samples are time-ordered; contiguous blocks keep overlapping input
windows and persistent regimes together. Invalid-sample gaps are ignored:
the bootstrap runs over the time-ordered common valid samples.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable


def moving_block_resample(n: int, block_len: int, rng: random.Random) -> list[int]:
    """Indices of `n` items drawn as contiguous blocks of `block_len`."""
    if n == 0:
        return []
    indices: list[int] = []
    for _ in range(math.ceil(n / block_len)):
        start = rng.randrange(0, max(n - block_len, 0) + 1)
        indices.extend(range(start, min(start + block_len, n)))
    return indices[:n]


def paired_block_ci(
    n: int,
    block_len: int,
    n_resamples: int,
    seed: int,
    stat: Callable[[list[int]], float | None],
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile CI of `stat` over resampled index lists; None if `stat`
    is undefined for every resample. The same indices feed both arms
    because `stat` closes over paired data (paired resampling)."""
    if n < 2 * block_len:
        # Fewer than two blocks: every resample repeats the original sample
        # and the CI would collapse to a misleading zero width.
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(n_resamples):
        v = stat(moving_block_resample(n, block_len, rng))
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    lo = values[int(alpha / 2 * len(values))]
    hi = values[min(len(values) - 1, int((1 - alpha / 2) * len(values)))]
    return lo, hi
