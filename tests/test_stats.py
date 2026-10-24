"""W0.3 unit tests for pipeline/stats.py (SPEC §0.8/§1). Required 3 hand-computed
fixtures: Cohen's kappa on a 2-class toy, PABAK, bootstrap-CI reproducibility under a
fixed seed. Plus coverage of the §0.8 extensions (Brennan–Prediger, point-biserial,
Fisher exact, permutation determinism, bootstrap-over-pairs).
"""
import sys
from pathlib import Path

import pytest

SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "pipeline"))
import stats as S  # noqa: E402

# Textbook 2-class toy: po = 4/5 = 0.8; marginals a{yes3,no2} b{yes2,no3};
# pe = (3/5)(2/5)+(2/5)(3/5)=0.48; kappa = (0.8-0.48)/(1-0.48)=0.32/0.52.
A = ["yes", "yes", "no", "no", "yes"]
B = ["yes", "no", "no", "no", "yes"]


# --- fixture 1: Cohen's kappa on a 2-class toy --------------------------- #
def test_cohen_kappa_2class():
    assert S.cohen_kappa(A, B) == pytest.approx(0.32 / 0.52, abs=1e-9)  # 0.615384…


def test_cohen_kappa_edge_cases():
    assert S.cohen_kappa([], []) == 0.0
    assert S.cohen_kappa(["x", "x"], ["x", "x"]) == 1.0  # single category → 1.0


# --- fixture 2: PABAK ---------------------------------------------------- #
def test_pabak():
    # po = 0.8 -> 2*0.8 - 1 = 0.6
    assert S.pabak(A, B) == pytest.approx(0.6, abs=1e-9)


# --- fixture 3: bootstrap CI reproducibility under fixed seed ------------ #
def test_bootstrap_reproducible_fixed_seed():
    units = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1]
    mean = lambda u: sum(u) / len(u)
    r1 = S.bootstrap_ci(units, mean, n_boot=2000, seed=12345)
    r2 = S.bootstrap_ci(units, mean, n_boot=2000, seed=12345)
    assert r1 == r2                      # identical stream under identical seed
    assert r1[1] <= r1[0] <= r1[2]       # lo <= point <= hi
    # point estimate is the data mean (seed-independent); CI bounds are valid
    assert r1[0] == pytest.approx(sum(units) / len(units))
    r3 = S.bootstrap_ci(units, mean, n_boot=2000, seed=999)
    assert r3[0] == pytest.approx(r1[0])   # point estimate seed-independent
    assert r3[1] <= r3[0] <= r3[2]


def test_bootstrap_default_seed_from_config():
    assert S.default_seed() == 20261022  # seeds.global in pipeline/config.yaml


# --- extensions ---------------------------------------------------------- #
def test_brennan_prediger_equals_pabak_for_2class():
    # BP with k=2: (po - 0.5)/(1-0.5) = PABAK
    assert S.brennan_prediger(A, B) == pytest.approx(S.pabak(A, B), abs=1e-9)
    assert S.brennan_prediger(A, B, n_categories=2) == pytest.approx(0.6, abs=1e-9)


def test_point_biserial():
    r, p = S.point_biserial([0, 0, 1, 1], [1.0, 2.0, 3.0, 4.0])
    assert r == pytest.approx(0.894427, abs=1e-5)  # (2/ sqrt(1.25)) * 0.5
    assert 0.0 <= p <= 1.0


def test_fisher_exact_tea_tasting():
    odds, p = S.fisher_exact([[3, 1], [1, 3]])
    assert odds == pytest.approx(9.0, abs=1e-9)
    assert p == pytest.approx(0.4857142857, abs=1e-6)


def test_permutation_deterministic_and_separates():
    a = [10.0, 11.0, 12.0, 13.0]
    b = [1.0, 2.0, 3.0, 4.0]
    obs1, p1 = S.permutation_test(a, b, n_perm=2000, seed=7)
    obs2, p2 = S.permutation_test(a, b, n_perm=2000, seed=7)
    assert (obs1, p1) == (obs2, p2)              # deterministic under seed
    assert obs1 == pytest.approx(9.0)            # mean_diff = 11.5 - 2.5
    assert p1 < 0.05                             # clearly separated groups
    # identical groups -> non-significant
    _, p_eq = S.permutation_test([1, 2, 3], [1, 2, 3], n_perm=2000, seed=7)
    assert p_eq > 0.05


def test_bootstrap_over_pairs_matches_bootstrap_ci():
    pairs = [(1, 1), (1, 0), (0, 0), (1, 1), (0, 1)]
    agree = lambda ps: sum(1 for x, y in ps if x == y) / len(ps)
    assert S.bootstrap_over_pairs(pairs, agree, n_boot=500, seed=42) == \
        S.bootstrap_ci(pairs, agree, n_boot=500, seed=42)
