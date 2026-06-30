import csv
import json
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "benchmark" / "analogcoder_pro"
SPEC_DIR = ROOT / "examples" / "benchmark_specs"
RESULTS_DIR = ROOT / "results" / "acp28_light_campaign"
SUMMARY_CSV = RESULTS_DIR / "acp28_light_summary.csv"
SUMMARY_JSON = RESULTS_DIR / "acp28_light_summary.json"
SUMMARY_MD = RESULTS_DIR / "acp28_light_report.md"
MANIFEST_PATH = BENCH_DIR / "manifest.csv"
CLI_COMMAND = [
    str(ROOT / ".venv" / "Scripts" / "python.exe"),
    "-m",
    "spec2testbench.presentation.cli.main",
    "verify",
]
CASE_STUDY_PRIORITY = [
    "p01_amplifier_strict",
    "p10_lowpass",
    "p16_opamp",
    "p19_mixer",
    "p22_oscillator",
    "p20_opamp",
    "p28_schmitt",
]


def load_manifest():
    rows = []
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)
    return rows


def load_yaml(path: Path):
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    sanitized = "".join(
        ch for ch in raw_text
        if ch in {"\n", "\r", "\t"} or not unicodedata.category(ch).startswith("C")
    )
    return yaml.safe_load(sanitized)


def latest_json_report(report_dir: Path):
    candidates = sorted(report_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def latest_generated_deck(case_dir: Path):
    decks = [path for path in case_dir.glob("*.cir") if path.is_file()]
    if not decks:
        return None
    return max(decks, key=lambda item: item.stat().st_mtime)


def parse_report(report_path: Path | None):
    if not report_path or not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8"))


def compute_metric_counts(report_data):
    metrics = report_data.get("metrics", []) if report_data else []
    pass_count = sum(1 for metric in metrics if metric.get("verdict") == "PASS")
    fail_count = sum(1 for metric in metrics if metric.get("verdict") in {"FAIL", "WARNING", "ERROR"})
    return len(metrics), pass_count, fail_count


def find_main_error(report_data, stdout_text, stderr_text):
    if report_data:
        errors = report_data.get("errors") or []
        if errors:
            return errors[0]
    combined = "\n".join(part for part in [stdout_text, stderr_text] if part).strip()
    for line in combined.splitlines():
        line = line.strip()
        lowered = line.lower()
        if not line:
            continue
        if "error" in lowered or "exception" in lowered or "traceback" in lowered:
            return line
    return ""


def is_specs_suspicious(spec_data):
    perf = spec_data.get("performance_targets", {}) or {}
    for metric_name, target in perf.items():
        if not isinstance(target, dict):
            continue
        min_value = target.get("min")
        max_value = target.get("max")
        if metric_name == "dc_gain_db" and isinstance(min_value, (int, float)) and min_value <= 0:
            return True
        if metric_name == "thd_percent" and isinstance(max_value, (int, float)) and max_value >= 50:
            return True
    return False


def classify_case(case, report_data, main_error, generated_deck_exists):
    if not report_data:
        if generated_deck_exists:
            return "simulation_failed"
        return "deck_generation_failed"

    if not report_data.get("testbench_generation_success", False):
        return "deck_generation_failed"

    if not report_data.get("simulation_success", False):
        return "simulation_failed"

    metric_count, _, _ = compute_metric_counts(report_data)
    if report_data.get("errors"):
        return "extraction_failed" if metric_count == 0 else "unsupported_or_unclear"

    verdict = report_data.get("overall_verdict", "")
    metrics_by_name = {metric.get("name"): metric.get("measured") for metric in report_data.get("metrics", [])}
    op = metrics_by_name.get("operating_point")
    dc_gain = metrics_by_name.get("dc_gain_db")
    spec_data = case["spec_data"]

    if verdict == "PASS":
        if case["spec_path"].stem == "p01_amplifier":
            return "needs_yaml_strict"
        if is_specs_suspicious(spec_data):
            return "pass_but_specs_suspicious"
        return "ready_for_case_study"

    if verdict == "RUN":
        if case["circuit_type"] in {"amplifier", "opamp", "comparator", "mixer"}:
            if isinstance(op, (int, float)) and case["vdd"] is not None:
                rail_margin = 0.1 * case["vdd"]
                if op <= rail_margin or op >= case["vdd"] - rail_margin:
                    return "needs_bias_search"
            if isinstance(dc_gain, (int, float)) and dc_gain < 0:
                return "needs_bias_search"
        return "unsupported_or_unclear"

    if verdict == "FAIL":
        return "extraction_failed" if main_error else "unsupported_or_unclear"

    return "unsupported_or_unclear"


def recommended_case_studies(rows):
    lookup = {row["circuit_name"]: row for row in rows}
    picks = []
    for name in CASE_STUDY_PRIORITY:
        if name == "p01_amplifier_strict":
            picks.append({
                "circuit_name": name,
                "why": "Cas déjà validé en profondeur avec polarisation corrigée, gain AC crédible et courant IDD cohérent."
            })
            continue
        row = lookup.get(name)
        if not row:
            continue
        if name == "p10_lowpass":
            why = "Filtre passif simple, utile pour valider la chaîne AC et les métriques de bande passante sans ambiguïté de polarisation."
        elif name in {"p16_opamp", "p20_opamp"}:
            why = "Architecture plus riche pour tester génération multi-stimuli, analyses AC et stabilité sur un bloc analogique central."
        elif name == "p19_mixer":
            why = "Cas spectral différentiel intéressant pour éprouver stimuli multiples, transient et FFT sur un circuit non trivial."
        elif name in {"p22_oscillator", "p28_schmitt"}:
            why = "Permet de sonder les chemins temporels plus délicats, démarrage oscillateur ou hystérésis, souvent révélateurs de limites framework."
        else:
            why = "Candidat utile pour une étude de cas plus profonde."
        picks.append({"circuit_name": name, "why": why})
        if len(picks) >= 5:
            break
    return picks[:5]


def detect_framework_bug_buckets(rows):
    buckets = defaultdict(list)
    for row in rows:
        error = (row["main_error"] or "").lower()
        if row["classification"] == "deck_generation_failed":
            buckets["problème de deck"].append(row["circuit_name"])
        if row["classification"] == "simulation_failed":
            buckets["problème de parsing ngspice"].append(row["circuit_name"])
        if row["classification"] == "extraction_failed":
            buckets["problème d’extraction"].append(row["circuit_name"])
        if row["classification"] in {"pass_but_specs_suspicious", "needs_yaml_strict"}:
            buckets["problème de YAML"].append(row["circuit_name"])
        if "stimulus" in error or "source" in error:
            buckets["problème de stimulus"].append(row["circuit_name"])
        if "metric" in error or "métrique" in error or "none" in error:
            buckets["problème de métrique manquante"].append(row["circuit_name"])
    return {key: value for key, value in buckets.items() if value}


def build_markdown(rows, stats, case_studies, bug_buckets):
    lines = [
        "# ACP-28 Light Campaign",
        "",
        "## A. Résumé global",
        "",
        f"- Nombre total de circuits : {stats['total_circuits']}",
        f"- Nombre exécutés : {stats['executed_circuits']}",
        f"- Nombre avec JSON généré : {stats['json_generated_count']}",
        f"- Nombre simulation_success = true : {stats['simulation_success_true']}",
        f"- Nombre simulation_success = false : {stats['simulation_success_false']}",
        f"- Nombre PASS : {stats['verdict_counts'].get('PASS', 0)}",
        f"- Nombre RUN : {stats['verdict_counts'].get('RUN', 0)}",
        f"- Nombre FAIL : {stats['verdict_counts'].get('FAIL', 0)}",
        f"- Nombre ERROR : {stats['error_like_count']}",
        f"- Moyenne compliance_score sur les circuits avec rapport valide : {stats['mean_compliance_score']:.4f}",
        "",
        "## B. Tableau synthétique des 28 circuits",
        "",
        "| Circuit | Type | Simulation | Verdict | Score | #Metrics | Main error | Classification |",
        "|---|---|---:|---|---:|---:|---|---|",
    ]
    for row in rows:
        score = "" if row["compliance_score"] is None else f"{row['compliance_score']:.3f}"
        lines.append(
            f"| {row['circuit_name']} | {row['circuit_type']} | {row['simulation_success']} | "
            f"{row['overall_verdict']} | {score} | {row['number_of_metrics']} | "
            f"{row['main_error'] or '-'} | {row['classification']} |"
        )

    lines.extend([
        "",
        "## C. Classement des circuits",
        "",
    ])
    class_groups = defaultdict(list)
    for row in rows:
        class_groups[row["classification"]].append(row["circuit_name"])
    for classification in [
        "ready_for_case_study",
        "pass_but_specs_suspicious",
        "simulation_failed",
        "extraction_failed",
        "deck_generation_failed",
        "needs_bias_search",
        "needs_yaml_strict",
        "unsupported_or_unclear",
    ]:
        members = ", ".join(class_groups.get(classification, [])) or "aucun"
        lines.append(f"- {classification} : {members}")

    lines.extend([
        "",
        "## D. 5 meilleurs candidats pour études de cas profondes",
        "",
    ])
    for index, item in enumerate(case_studies, start=1):
        lines.append(f"{index}. {item['circuit_name']} : {item['why']}")

    lines.extend([
        "",
        "## E. Bugs framework éventuels détectés",
        "",
    ])
    if not bug_buckets:
        lines.append("- Aucun motif récurrent clair détecté à ce stade.")
    else:
        for label, circuits in bug_buckets.items():
            lines.append(f"- {label} : {', '.join(circuits)}")

    return "\n".join(lines)


def sanitize_for_json(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    return value


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows = load_manifest()
    campaign_started = datetime.now(timezone.utc).isoformat()
    rows = []

    for manifest_row in manifest_rows:
        netlist_name = manifest_row["netlist"]
        spec_name = manifest_row["spec"]
        circuit_stem = Path(netlist_name).stem
        case_dir = RESULTS_DIR / circuit_stem
        case_dir.mkdir(parents=True, exist_ok=True)

        spec_path = SPEC_DIR / spec_name
        netlist_path = BENCH_DIR / netlist_name
        spec_data = load_yaml(spec_path)
        command = CLI_COMMAND + [
            "--specs", str(spec_path),
            "--netlist", str(netlist_path),
            "--no-llm",
            "--format", "json",
            "--output", str(case_dir),
        ]

        print(f"[acp28] {circuit_stem}")
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        stdout_path = case_dir / "stdout.txt"
        stderr_path = case_dir / "stderr.txt"
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")

        report_dir = case_dir / "reports"
        report_path = latest_json_report(report_dir)
        report_data = parse_report(report_path)
        deck_path = latest_generated_deck(case_dir)
        metric_count, metrics_pass, metrics_fail = compute_metric_counts(report_data)
        main_error = find_main_error(report_data, completed.stdout, completed.stderr)

        row = {
            "circuit_id": int(manifest_row["id"]),
            "circuit_name": circuit_stem,
            "circuit_type": manifest_row["circuit_type"],
            "yaml_path": str(spec_path.relative_to(ROOT)),
            "netlist_path": str(netlist_path.relative_to(ROOT)),
            "command": " ".join(command),
            "exit_code": completed.returncode,
            "testbench_generation_success": bool(report_data.get("testbench_generation_success")) if report_data else False,
            "simulation_success": bool(report_data.get("simulation_success")) if report_data else False,
            "overall_verdict": report_data.get("overall_verdict", "ERROR") if report_data else "ERROR",
            "compliance_score": report_data.get("compliance_score") if report_data else None,
            "number_of_metrics": metric_count,
            "metrics_pass": metrics_pass,
            "metrics_fail": metrics_fail,
            "json_report_path": str(report_path.relative_to(ROOT)) if report_path else "",
            "generated_deck_path": str(deck_path.relative_to(ROOT)) if deck_path else "",
            "main_error": main_error,
            "errors": report_data.get("errors", []) if report_data else [main_error] if main_error else [],
            "vdd": spec_data.get("input_conditions", {}).get("vdd"),
            "spec_path": spec_path,
            "spec_data": spec_data,
        }
        row["classification"] = classify_case(row, report_data, main_error, deck_path is not None)
        rows.append(row)

    verdict_counts = Counter(row["overall_verdict"] for row in rows)
    valid_scores = [row["compliance_score"] for row in rows if isinstance(row["compliance_score"], (int, float))]
    stats = {
        "total_circuits": len(rows),
        "executed_circuits": sum(1 for row in rows if row["exit_code"] is not None),
        "json_generated_count": sum(1 for row in rows if row["json_report_path"]),
        "simulation_success_true": sum(1 for row in rows if row["simulation_success"]),
        "simulation_success_false": sum(1 for row in rows if not row["simulation_success"]),
        "verdict_counts": dict(verdict_counts),
        "error_like_count": sum(1 for row in rows if row["overall_verdict"] not in {"PASS", "RUN", "ROBUST_PASS"}),
        "mean_compliance_score": (sum(valid_scores) / len(valid_scores)) if valid_scores else 0.0,
        "classification_counts": dict(Counter(row["classification"] for row in rows)),
    }
    bug_buckets = detect_framework_bug_buckets(rows)
    case_studies = recommended_case_studies(rows)

    csv_columns = [
        "circuit_id",
        "circuit_name",
        "circuit_type",
        "yaml_path",
        "netlist_path",
        "exit_code",
        "testbench_generation_success",
        "simulation_success",
        "overall_verdict",
        "compliance_score",
        "number_of_metrics",
        "metrics_pass",
        "metrics_fail",
        "json_report_path",
        "main_error",
        "classification",
    ]
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in csv_columns})

    summary_payload = {
        "metadata": {
            "campaign_name": "acp28_light_campaign",
            "started_at_utc": campaign_started,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "root": str(ROOT),
            "command_prefix": " ".join(CLI_COMMAND),
            "results_dir": str(RESULTS_DIR),
            "deterministic_mode": True,
            "llm_disabled": True,
        },
        "circuits": [
            sanitize_for_json({
                key: value for key, value in row.items()
                if key not in {"spec_data", "spec_path", "vdd"}
            })
            for row in rows
        ],
        "stats": stats,
        "failure_modes": bug_buckets,
        "recommended_next_actions": [
            "Approfondir les circuits classés ready_for_case_study avec inspection du deck et des métriques physiques.",
            "Traiter séparément les circuits needs_bias_search via campagnes de polarisation ciblées.",
            "Durcir ou dédoubler les YAML classés pass_but_specs_suspicious ou needs_yaml_strict.",
            "Analyser les circuits simulation_failed et extraction_failed pour distinguer limitation circuit et limitation framework.",
        ],
    }
    SUMMARY_JSON.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    SUMMARY_MD.write_text(build_markdown(rows, stats, case_studies, bug_buckets), encoding="utf-8")

    print(f"Campaign complete: {RESULTS_DIR}")
    print(f"CSV: {SUMMARY_CSV}")
    print(f"JSON: {SUMMARY_JSON}")
    print(f"Markdown: {SUMMARY_MD}")


if __name__ == "__main__":
    main()
