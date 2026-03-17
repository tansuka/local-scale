from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

from app.models import Profile
from app.services.bia import DEFAULT_FEATURES, TARGET_METRICS, feature_map, fit_metric


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit body-composition calibration coefficients from paired OKOK readings."
    )
    parser.add_argument("csv_path", type=Path, help="CSV file with paired measurements.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bia-calibration.json"),
        help="Where to write the fitted calibration JSON.",
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def build_profile(row: dict[str, str]) -> Profile:
    return Profile(
        id=1,
        name=row.get("profile_name", "Calibration"),
        sex=row["sex"],
        birth_date=parse_date(row["birth_date"]),
        height_cm=float(row["height_cm"]),
        units="metric",
        color="#0f766e",
        active=True,
    )


def load_samples(csv_path: Path) -> list[dict[str, float]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError("Calibration CSV is empty.")

    samples: list[dict[str, float]] = []
    for row in rows:
        profile = build_profile(row)
        weight_kg = float(row["weight_kg"])
        impedance_ohm = float(row["impedance_ohm"])
        measurement_date = parse_date(row["measurement_date"])
        features = feature_map(
            profile=profile,
            weight_kg=weight_kg,
            impedance_ohm=impedance_ohm,
            measurement_date=measurement_date,
        )
        sample = dict(features)
        for metric in TARGET_METRICS:
            raw_value = row.get(metric, "").strip()
            if raw_value:
                sample[metric] = float(raw_value)
        samples.append(sample)
    return samples


def fit_calibration(samples: list[dict[str, float]]) -> dict[str, object]:
    metrics_payload: dict[str, dict[str, object]] = {}
    for metric in TARGET_METRICS:
        metric_samples = [sample for sample in samples if metric in sample]
        if len(metric_samples) < 3:
            continue
        fitted = fit_metric(metric_samples, metric=metric, features=DEFAULT_FEATURES)
        metrics_payload[metric] = {
            "features": list(fitted.features),
            "coefficients": [round(value, 10) for value in fitted.coefficients],
            "sample_count": len(metric_samples),
        }
    return {
        "version": 1,
        "generated_from": "fit_bia_calibration.py",
        "metrics": metrics_payload,
    }


def main() -> None:
    args = parse_args()
    samples = load_samples(args.csv_path)
    payload = fit_calibration(samples)
    if not payload["metrics"]:
        raise ValueError(
            "No metrics were fitted. Provide at least 3 rows per target metric in the calibration CSV."
        )
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote calibration to {args.output}")


if __name__ == "__main__":
    main()
