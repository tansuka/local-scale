# OKOK Calibration

The live BLE path can now decode:

- `weight_kg`
- `impedance_ohm`

To match OKOK's derived body-composition metrics more closely, fit a calibration file from paired OKOK readings.

## CSV Format

Create a CSV with these columns:

```csv
profile_name,sex,birth_date,height_cm,measurement_date,weight_kg,impedance_ohm,fat_pct,water_pct,muscle_pct,skeletal_muscle_pct,visceral_fat
Tansu,male,1990-01-01,180,2026-03-17,74.19,500,18.7,57.4,49.2,43.1,7
```

Notes:

- Use ISO dates like `2026-03-17`.
- Include at least `3` rows per metric you want fitted.
- More rows are better, especially if weight and impedance vary across measurements.

## Fit Calibration

From the backend directory:

```bash
./.venv/bin/python scripts/fit_bia_calibration.py okok-paired-readings.csv --output bia-calibration.json
```

## Use Calibration

Point the backend at the generated file:

```bash
export LOCAL_SCALE_BIA_CALIBRATION_PATH=/absolute/path/to/bia-calibration.json
```

Then restart the backend. New live advertisement measurements that include impedance can automatically fill:

- `fat_pct`
- `water_pct`
- `muscle_pct`
- `skeletal_muscle_pct`
- `visceral_fat`

The weights for those percentages are still derived locally from total weight.
