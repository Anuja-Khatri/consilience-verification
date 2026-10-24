#!/usr/bin/env python3
"""
pipeline/stats.py — sprint statistics (SPEC §0.8, W0.3).

PART A is COPIED VERBATIM from the prior eval's stats.py (REUSE, never redo):
    source: ~/consilience-demo/demo/eval/stats.py
    source sha256: 53c034d671441a492401e88e1a52bc6810646172f0f624de9e16992434974cef
PART B extends it (SPEC §0.8): Brennan–Prediger, point-biserial, Fisher exact,
permutation tests, and bootstrap-over-pairs. Seeds come from pipeline/config.yaml
(seeds.global); callers may override per the config discipline.

Cohen's kappa is implemented from first principles (kept from the source) and
unit-tested against the textbook example in tests/test_stats.py.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

# ======================================================================= #
# PART A — copied verbatim from eval/stats.py (do not edit; reuse-by-copy) #
# ======================================================================= #

# Labels that are not real vocabulary answers — excluded from kappa, kept in confusions.
NONVOCAB = {"OOV", "PARSE_FAIL", "API_FAIL", "none", "refused"}


def _paired(a: Sequence[str], b: Sequence[str], exclude=NONVOCAB) -> Tuple[List[str], List[str], int]:
    """Drop index-aligned pairs where either side is a non-vocab label. Returns the
    kept pairs plus the count excluded."""
    ka, kb, excluded = [], [], 0
    for x, y in zip(a, b):
        if x in exclude or y in exclude:
            excluded += 1
        else:
            ka.append(x)
            kb.append(y)
    return ka, kb, excluded


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa for two raters over categorical labels. Assumes a and b are
    already filtered of non-vocab labels and index-aligned. Returns 0.0 for n==0."""
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    cats = set(ca) | set(cb)
    pe = sum((ca.get(c, 0) / n) * (cb.get(c, 0) / n) for c in cats)
    if pe == 1.0:
        return 1.0  # perfect expected agreement (single category) → define kappa = 1
    return (po - pe) / (1.0 - pe)


def percent_agreement(a: Sequence[str], b: Sequence[str]) -> float:
    n = len(a)
    return (sum(1 for x, y in zip(a, b) if x == y) / n) if n else 0.0


def pabak(a: Sequence[str], b: Sequence[str]) -> float:
    """Prevalence-and-bias-adjusted kappa (for binary fields with skewed marginals):
    PABAK = 2*po - 1. Index-aligned, pre-filtered inputs."""
    return 2.0 * percent_agreement(a, b) - 1.0


def kappa_with_exclusions(a: Sequence[str], b: Sequence[str]):
    """Returns (kappa, n_used, n_excluded, percent_agreement)."""
    ka, kb, excl = _paired(a, b)
    return cohen_kappa(ka, kb), len(ka), excl, percent_agreement(ka, kb)


def fleiss_kappa(ratings: List[dict]) -> float:
    """Fleiss' kappa over N items rated by a fixed number of raters into categories.
    `ratings` is a list (one per item) of {category: count}; each item's counts should
    sum to the same n_raters. Items with differing totals are dropped (common when a
    claim is absent from some runs) — caller should pre-pad or filter. Returns 0.0 for
    degenerate input."""
    items = [r for r in ratings if sum(r.values()) > 1]
    if not items:
        return 0.0
    n = sum(next(iter([sum(r.values())])) for r in items[:1])  # raters per item (first)
    items = [r for r in items if sum(r.values()) == n]
    N = len(items)
    if N == 0 or n < 2:
        return 0.0
    cats = sorted({c for r in items for c in r})
    # P_i: agreement for item i
    P = []
    for r in items:
        s = sum(r.get(c, 0) ** 2 for c in cats)
        P.append((s - n) / (n * (n - 1)))
    Pbar = sum(P) / N
    pj = {c: sum(r.get(c, 0) for r in items) / (N * n) for c in cats}
    Pe = sum(v * v for v in pj.values())
    if Pe == 1.0:
        return 1.0
    return (Pbar - Pe) / (1.0 - Pe)


def bootstrap_ci(units: list, stat_fn, n_boot: int = 2000, seed: int = None,
                 alpha: float = 0.05):
    """Percentile bootstrap CI. Resamples `units` (the unit of analysis) with
    replacement n_boot times, recomputes stat_fn(resample) each time, returns
    (point, lo, hi). One deterministic random stream (seeded) — never reseeded
    per field. Returns (point, point, point) for empty/degenerate input.

    (v2.0.1 change: default seed now comes from config — see default_seed().)"""
    import random
    if seed is None:
        seed = default_seed()
    point = stat_fn(units)
    if not units:
        return (point, point, point)
    rng = random.Random(seed)
    m = len(units)
    vals = []
    for _ in range(n_boot):
        sample = [units[rng.randrange(m)] for _ in range(m)]
        vals.append(stat_fn(sample))
    vals.sort()
    lo = vals[int((alpha / 2) * n_boot)]
    hi = vals[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (point, lo, hi)


def confusion_matrix(a: Sequence[str], b: Sequence[str], labels: Sequence[str]):
    """Full confusion matrix INCLUDING non-vocab categories (nothing dropped)."""
    idx = {l: i for i, l in enumerate(labels)}
    m = [[0] * len(labels) for _ in labels]
    for x, y in zip(a, b):
        if x in idx and y in idx:
            m[idx[x]][idx[y]] += 1
    return m


# ======================================================================= #
# PART B — sprint extensions (SPEC §0.8): seed-from-config, Brennan–Prediger, #
# point-biserial, Fisher exact, permutation tests, bootstrap-over-pairs.    #
# ======================================================================= #

_SEED_CACHE = None


def default_seed() -> int:
    """Global seed from pipeline/config.yaml (seeds.global). Falls back to 20261022
    (the v2.0 global seed) if config is unreadable, so stats stays importable alone."""
    global _SEED_CACHE
    if _SEED_CACHE is not None:
        return _SEED_CACHE
    try:
        import yaml
        cfg = yaml.safe_load((Path(__file__).resolve().parent / "config.yaml").read_text())
        _SEED_CACHE = int(cfg["seeds"]["global"])
    except Exception:
        _SEED_CACHE = 20261022
    return _SEED_CACHE


def wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion k/n (95% default). Returns
    (lo, hi). Used for A5 stability/coverage proportions. Returns (0,0) for n==0."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def brennan_prediger(a: Sequence[str], b: Sequence[str], n_categories: int = None) -> float:
    """Brennan–Prediger coefficient (a.k.a. BP / S / Bennett's S for 2 raters):
    BP = (po - 1/k) / (1 - 1/k), where k = number of categories (chance = 1/k, i.e.
    uniform over categories, independent of marginals). For k=2 this equals PABAK.
    Index-aligned, pre-filtered inputs. k defaults to the observed category count."""
    n = len(a)
    if n == 0:
        return 0.0
    po = percent_agreement(a, b)
    k = n_categories if n_categories else len({*a, *b})
    if k <= 1:
        return 1.0
    pe = 1.0 / k
    return (po - pe) / (1.0 - pe)


def point_biserial(binary: Sequence[int], continuous: Sequence[float]) -> Tuple[float, float]:
    """Point-biserial correlation (binary 0/1 vs continuous). Returns (r, p_two_sided).
    Thin wrapper over scipy.stats.pointbiserialr with a pure-python fallback for r."""
    x = [int(v) for v in binary]
    y = [float(v) for v in continuous]
    if len(set(x)) < 2 or len(x) < 3:
        return (0.0, 1.0)
    try:
        from scipy import stats
        r, p = stats.pointbiserialr(x, y)
        return (float(r), float(p))
    except Exception:
        # Pearson r fallback (no p-value)
        import statistics as st
        mx, my = st.mean(x), st.mean(y)
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        den = (sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y)) ** 0.5
        return ((num / den) if den else 0.0, float("nan"))


def fisher_exact(table_2x2: List[List[int]], alternative: str = "two-sided") -> Tuple[float, float]:
    """Fisher's exact test on a 2×2 contingency table [[a,b],[c,d]].
    Returns (odds_ratio, p_value). Used for A2.survivor_vs_failure_separation etc."""
    from scipy import stats
    odds, p = stats.fisher_exact(table_2x2, alternative=alternative)
    return (float(odds), float(p))


def permutation_test(group_a: Sequence[float], group_b: Sequence[float], *,
                     stat: str = "mean_diff", n_perm: int = 10000, seed: int = None,
                     alternative: str = "two-sided") -> Tuple[float, float]:
    """Two-sample permutation test on a difference statistic. Returns (observed, p).
    `stat`: 'mean_diff' (default) or a callable(a, b) -> float. Deterministic under
    the config seed. p is the fraction of permuted stats at least as extreme."""
    import random
    if seed is None:
        seed = default_seed()
    a = [float(v) for v in group_a]
    b = [float(v) for v in group_b]
    if not a or not b:
        return (0.0, 1.0)

    def _stat(xa, xb):
        if callable(stat):
            return stat(xa, xb)
        return (sum(xa) / len(xa)) - (sum(xb) / len(xb))

    observed = _stat(a, b)
    pooled = a + b
    na = len(a)
    rng = random.Random(seed)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        s = _stat(pooled[:na], pooled[na:])
        if alternative == "two-sided":
            if abs(s) >= abs(observed) - 1e-12:
                count += 1
        elif alternative == "greater":
            if s >= observed - 1e-12:
                count += 1
        else:  # 'less'
            if s <= observed + 1e-12:
                count += 1
    p = (count + 1) / (n_perm + 1)  # add-one (never report p=0)
    return (observed, p)


def bootstrap_over_pairs(pairs: list, stat_fn: Callable[[list], float],
                         n_boot: int = 2000, seed: int = None, alpha: float = 0.05):
    """Bootstrap CI where the resampling unit is the PAIR (SPEC §0.8: 'bootstrap-over-
    pairs'). Identical machinery to bootstrap_ci; named for call-site clarity and to
    make the unit-of-analysis explicit in A2/AB/F2 code. Seeded from config."""
    return bootstrap_ci(pairs, stat_fn, n_boot=n_boot, seed=seed, alpha=alpha)


if __name__ == "__main__":  # self-check
    a = ["yes", "yes", "no", "no", "yes"]
    b = ["yes", "no", "no", "no", "yes"]
    print("seed:", default_seed())
    print("kappa:", round(cohen_kappa(a, b), 4))
    print("pabak:", round(pabak(a, b), 4), "BP:", round(brennan_prediger(a, b), 4))
