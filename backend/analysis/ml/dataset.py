"""Geração do conjunto de dados da sintonia aprendida (sem dependência do Django)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from ..engine.learned import FEATURES, label_plant, normalize_gains, plant_features, random_plant
from ..engine.loop import build_loop

COLUMNS = (["idx", "num", "den", "delay"] + FEATURES + ["K0", "tch", "L", "T", "kp", "ki", "kd", "kp_n", "ki_n", "kd_n",
           "feasible", "opt_iae", "opt_overshoot", "opt_settling", "zn_iae", "zn_overshoot", "zn_diverged"])


def make_row(idx: int, seed: int = 1) -> dict | None:
    rng = np.random.default_rng(seed * 1_000_003 + idx)
    spec = random_plant(rng)
    lp = build_loop(spec)
    feats = plant_features(lp)
    if feats is None:
        return None
    lab = label_plant(lp, feats)
    n = normalize_gains(lab["gains"], feats)
    m, z = lab["metrics"], lab["zn_metrics"]
    return {
        "idx": idx, "num": spec["plant"]["num"], "den": spec["plant"]["den"], "delay": spec.get("delay", 0.0),
        **{f: feats[f] for f in FEATURES},
        "K0": feats["_K0"], "tch": feats["_tch"], "L": feats["_L"], "T": feats["_T"],
        **lab["gains"], "kp_n": n["kp"], "ki_n": n["ki"], "kd_n": n["kd"],
        "feasible": int(lab["feasible"]), "opt_iae": m.get("iae"), "opt_overshoot": m.get("overshoot"),
        "opt_settling": m.get("settling_time"), "zn_iae": z.get("iae"), "zn_overshoot": z.get("overshoot"),
        "zn_diverged": int(bool(z.get("diverged"))),
    }


def _safe_row(args):
    idx, seed = args
    try:
        return make_row(idx, seed)
    except Exception:  # noqa: BLE001 - uma planta problemática não interrompe a geração
        return None


def generate(n: int, out: Path, workers: int = 4, seed: int = 1, start: int = 0, log=print) -> int:
    from multiprocessing import Pool

    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists() or out.stat().st_size == 0
    done = 0
    with out.open("a", newline="", encoding="utf-8") as fh, Pool(workers) as pool:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(_safe_row, [(k, seed) for k in range(start, start + n)], chunksize=4)):
            if row:
                w.writerow(row)
                done += 1
            if (i + 1) % 50 == 0:
                fh.flush()
                log(f"{i + 1}/{n} plantas processadas ({done} válidas)")
    return done
