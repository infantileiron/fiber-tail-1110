from fractions import Fraction
from itertools import groupby

from src.constants.domain import ALGORITHM_VERSION, MIN_SAMPLES, Outcome


class InsufficientSamples(ValueError):
    pass


def percent(value):
    return float(value * 100)


def _tail_takes(samples, tail_pct):
    """Walk samples from the highest impurity rate down until the tail share is filled.

    Returns ordered (ratio, code, dry_g, used_g) takes and the exact tail grams.
    Tied rates are broken by sample code, so each code appears at most once and a
    boundary sample contributes only its truncated grams.
    """
    total_g = sum(sample["dry_g"] for sample in samples)
    tail_g = total_g * Fraction(tail_pct) / 100
    remaining_g = tail_g
    takes = []
    pairs = sorted(
        (Fraction(sample["impurity_g"], sample["dry_g"]), sample["code"], sample["dry_g"])
        for sample in samples
    )
    for ratio, code, dry_g in sorted(pairs, key=lambda item: (-item[0], item[1])):
        used_g = min(remaining_g, dry_g)
        takes.append((ratio, code, dry_g, used_g))
        remaining_g -= used_g
        if remaining_g == 0:
            break
    return takes, tail_g


def tail_grams(samples, tail_pct):
    """Exact grams each sample contributes to the tail share, keyed by sample code."""
    takes, tail_g = _tail_takes(samples, tail_pct)
    return {code: used_g for _, code, _, used_g in takes}, tail_g


def sample_changes(before, after):
    """Snapshot rows that were added, removed or reweighed between two snapshots."""
    before_by_code = {row["code"]: row for row in before}
    after_by_code = {row["code"]: row for row in after}
    changes = []
    for code in sorted(set(before_by_code) | set(after_by_code)):
        previous, current = before_by_code.get(code), after_by_code.get(code)
        if previous != current:
            changes.append({"code": code, "before": previous, "after": current})
    return changes


def tail_diff(before_samples, before_tail_pct, after_samples, after_tail_pct):
    """Per-sample tail gram difference between two versions.

    Deltas are exact rationals: tied rates align by sample code and boundary
    samples keep their truncated grams, so the per-sample deltas always sum to
    the change of the two tail totals.
    """
    before_map, before_total = tail_grams(before_samples, before_tail_pct)
    after_map, after_total = tail_grams(after_samples, after_tail_pct)
    entries = []
    for code in sorted(set(before_map) | set(after_map)):
        before_g = before_map.get(code, Fraction(0))
        after_g = after_map.get(code, Fraction(0))
        if before_g != after_g:
            entries.append({
                "code": code,
                "before_g": float(before_g),
                "after_g": float(after_g),
                "delta_g": float(after_g - before_g),
            })
    return {
        "entries": entries,
        "before_total_g": float(before_total),
        "after_total_g": float(after_total),
    }


def analyze(samples, parameters):
    """Compute the empirical distribution with unit dry grams as the weights."""
    if len(samples) < MIN_SAMPLES:
        raise InsufficientSamples(f"有效干样至少需要 {MIN_SAMPLES} 份，本次仅锁定 {len(samples)} 份。")

    threshold = Fraction(parameters["threshold_pct"]) / 100
    exceed_cap = Fraction(parameters["exceed_cap_pct"]) / 100
    tail_cap = Fraction(parameters["tail_cap_pct"]) / 100
    total_g = sum(sample["dry_g"] for sample in samples)
    impurity_g = sum(sample["impurity_g"] for sample in samples)
    pairs = sorted(
        (Fraction(sample["impurity_g"], sample["dry_g"]), sample["code"], sample["dry_g"])
        for sample in samples
    )
    exceed_g = sum(dry_g for ratio, _, dry_g in pairs if ratio > threshold)
    cumulative_g = 0
    ecdf = []
    for ratio, group in groupby(pairs, key=lambda item: item[0]):
        entries = list(group)
        dry_g = sum(weight for _, _, weight in entries)
        cumulative_g += dry_g
        ecdf.append({
            "concentration_pct": percent(ratio), "group_g": dry_g,
            "cumulative_g": cumulative_g, "cumulative_pct": percent(Fraction(cumulative_g, total_g)),
            "sample_codes": [code for _, code, _ in entries],
        })

    takes, tail_g = _tail_takes(samples, parameters["tail_pct"])
    integrated = Fraction(0)
    contributions = []
    for ratio, code, dry_g, used_g in takes:
        integrated += used_g * ratio
        contributions.append({
            "code": code, "concentration_pct": percent(ratio), "dry_g": dry_g,
            "used_g": float(used_g), "impurity_equivalent_g": float(used_g * ratio),
        })

    exceed_share = Fraction(exceed_g, total_g)
    tail_mean = integrated / tail_g
    triggers = []
    if exceed_share > exceed_cap:
        triggers.append("exceed_share")
    if tail_mean > tail_cap:
        triggers.append("tail_mean")

    return {
        "algorithm": ALGORITHM_VERSION,
        "sample_count": len(samples), "total_dry_g": total_g, "impurity_g": impurity_g,
        "weighted_mean_pct": percent(Fraction(impurity_g, total_g)),
        "exceed_g": exceed_g, "exceed_share_pct": percent(exceed_share),
        "tail_g": float(tail_g), "tail_mean_pct": percent(tail_mean),
        "ecdf": ecdf, "tail_contributions": contributions, "triggers": triggers,
        "recommendation": Outcome.REJECT if triggers else Outcome.ACCEPT,
    }
