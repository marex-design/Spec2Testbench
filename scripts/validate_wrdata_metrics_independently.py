"""Independent waveform-only validator for the WRDATA extension."""
from __future__ import annotations
import csv, json, math, sys
from pathlib import Path

def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/frozen_pilot_v2_wrdata_extension")
    rows = []
    for csv_path in sorted(root.glob("**/vectors.csv")):
        values = []
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if row:
                    values.append(float(row[-1]))
        independent = (max(values) - min(values)) / 2.0
        sim_path = csv_path.parent / "simulation_results.json"
        payload = json.loads(sim_path.read_text(encoding="utf-8")) if sim_path.exists() else {}
        pipeline = float((payload.get("native_metrics") or {}).get("startup_amplitude", "nan"))
        error = abs(pipeline - independent) if math.isfinite(pipeline) else float("nan")
        relative = error / max(abs(independent), 1e-30) if math.isfinite(error) else float("nan")
        rows.append({"vectors_csv": str(csv_path), "pipeline_value": pipeline, "independent_value": independent, "absolute_error": error, "relative_error": relative, "absolute_tolerance": 1e-12, "relative_tolerance": 1e-6, "agreement": math.isfinite(error) and error <= 1e-12 + 1e-6 * abs(independent)})
    out = Path("results/wrdata_independent_comparisons.csv")
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys() if rows else ["vectors_csv"]); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"comparisons": len(rows), "agreements": sum(bool(r["agreement"]) for r in rows)}, indent=2))

if __name__ == "__main__":
    main()
