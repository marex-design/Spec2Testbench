"""Import the 28 AnalogCoder-Pro sample designs into Spec2Testbench.

The upstream AnalogCoder-Pro samples are PySpice scripts. This importer reads
the circuit construction block before the first simulator call and converts the
common PySpice element calls into plain SPICE netlists. It also exports a small
manifest and YAML specs that can be consumed by the verification pipeline.
"""

from __future__ import annotations

import ast
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analogcoder" / "AnalogCoderPro-master"
PROBLEM_SET = SOURCE / "problem_set.tsv"
SAMPLE_DESIGNS = SOURCE / "sample_design"
NETLIST_OUT = ROOT / "benchmark"
SPEC_OUT = ROOT / "examples" / "benchmark_specs"


TYPE_TO_SPEC2TESTBENCH = {
    "Amplifier": "amplifier",
    "Inverter": "amplifier",
    "CurrentMirror": "current_mirror",
    "Comparator": "comparator",
    "LowPass": "low_pass_filter",
    "HighPass": "high_pass_filter",
    "BandPass": "band_pass_filter",
    "BandStop": "notch_filter",
    "Opamp": "opamp",
    "Mixer": "mixer",
    "Oscillator": "oscillator",
    "Integrator": "opamp_integrator",
    "Differentiator": "opamp_differentiator",
    "Adder": "composite",
    "Subtractor": "composite",
    "Schmitt": "schmitt_trigger",
}


DEFAULT_TARGETS = {
    "Amplifier": {
        "operating_point": {"min": 0.0, "max": 5.0, "unit": "V"},
        "dc_gain_db": {"min": 0.0, "unit": "dB"},
        "quiescent_current": {"max": 0.05, "unit": "A"},
    },
    "Inverter": {
        "operating_point": {"min": 0.0, "max": 5.0, "unit": "V"},
        "propagation_delay": {"max": 1e-3, "unit": "s"},
    },
    "CurrentMirror": {
        "operating_point": {"min": 0.0, "max": 5.0, "unit": "V"},
        "quiescent_current": {"max": 0.05, "unit": "A"},
    },
    "Comparator": {
        "propagation_delay": {"max": 1e-3, "unit": "s"},
    },
    "LowPass": {
        "cutoff_frequency_hz": {"min": 1.0, "max": 1e9, "unit": "Hz"},
    },
    "HighPass": {
        "cutoff_frequency_hz": {"min": 1.0, "max": 1e9, "unit": "Hz"},
    },
    "BandPass": {
        "cutoff_frequency_hz": {"min": 1.0, "max": 1e9, "unit": "Hz"},
    },
    "BandStop": {
        "cutoff_frequency_hz": {"min": 1.0, "max": 1e9, "unit": "Hz"},
    },
    "Opamp": {
        "dc_gain_db": {"min": 0.0, "unit": "dB"},
        "phase_margin": {"min": 0.0, "unit": "deg"},
        "quiescent_current": {"max": 0.05, "unit": "A"},
    },
    "Mixer": {
        "thd_percent": {"max": 100.0, "unit": "%"},
        "fundamental_frequency": {"min": 1.0, "unit": "Hz"},
    },
    "Oscillator": {
        "oscillator_frequency": {"min": 1.0, "unit": "Hz"},
        "startup_amplitude": {"min": 1e-6, "unit": "V"},
    },
    "Integrator": {
        "slew_rate": {"min": 1e-6, "unit": "V/s"},
        "settling_time": {"max": 1.0, "unit": "s"},
    },
    "Differentiator": {
        "slew_rate": {"min": 1e-6, "unit": "V/s"},
    },
    "Adder": {
        "operating_point": {"min": 0.0, "max": 5.0, "unit": "V"},
    },
    "Subtractor": {
        "operating_point": {"min": 0.0, "max": 5.0, "unit": "V"},
    },
    "Schmitt": {
        "propagation_delay": {"max": 1e-3, "unit": "s"},
    },
}


ANALYSES = {
    "Amplifier": [".OP", ".AC DEC 100 1 1G"],
    "Inverter": [".OP", ".TRAN 1N 10U"],
    "CurrentMirror": [".OP", ".DC Vdd 0 5 0.1"],
    "Comparator": [".TRAN 1U 10M"],
    "LowPass": [".AC DEC 100 1 1G"],
    "HighPass": [".AC DEC 100 1 1G"],
    "BandPass": [".AC DEC 100 1 1G"],
    "BandStop": [".AC DEC 100 1 1G"],
    "Opamp": [".OP", ".AC DEC 100 1 1G"],
    "Mixer": [".TRAN 1U 20M"],
    "Oscillator": [".TRAN 10U 20M"],
    "Integrator": [".TRAN 10U 20M"],
    "Differentiator": [".TRAN 10U 20M"],
    "Adder": [".OP", ".TRAN 10U 20M"],
    "Subtractor": [".OP", ".TRAN 10U 20M"],
    "Schmitt": [".TRAN 10U 20M"],
}


OPAMP_SUBCKT = """\
.SUBCKT Opamp Vinp Vinn Vout
.MODEL nmos_model NMOS (LEVEL=1 KP=0.0001 VTO=0.5)
.MODEL pmos_model PMOS (LEVEL=1 KP=5e-05 VTO=-0.5)
Vdd Vdd 0 5
Vbias Vbias 0 1.5
M1 Voutp Vinp Source3 Source3 nmos_model W=5e-05 L=1e-06
M2 Vout Vinn Source3 Source3 nmos_model W=5e-05 L=1e-06
M3 Source3 Vbias 0 0 nmos_model W=0.0001 L=1e-06
M4 Voutp Voutp Vdd Vdd pmos_model W=0.0001 L=1e-06
M5 Vout Voutp Vdd Vdd pmos_model W=0.0001 L=1e-06
.ENDS Opamp"""


PREFIX = {
    "V": "V",
    "SinusoidalVoltageSource": "V",
    "PulseVoltageSource": "V",
    "R": "R",
    "C": "C",
    "L": "L",
    "I": "I",
    "MOSFET": "M",
    "BJT": "Q",
    "X": "X",
}


UNIT_FACTORS = {
    "u_V": "",
    "u_kV": "k",
    "u_mV": "m",
    "u_uV": "u",
    "u_V": "",
    "u_Ohm": "",
    "u_ohm": "",
    "u_kOhm": "k",
    "u_MOhm": "Meg",
    "u_F": "",
    "u_mF": "m",
    "u_uF": "u",
    "u_nF": "n",
    "u_pF": "p",
    "u_H": "",
    "u_mH": "m",
    "u_uH": "u",
    "u_kHz": "k",
    "u_Hz": "",
    "u_MHz": "Meg",
    "u_GHz": "G",
    "u_A": "",
    "u_mA": "m",
    "u_uA": "u",
}


@dataclass
class Problem:
    identifier: int
    level: str
    circuit: str
    inputs: str
    outputs: str
    type_name: str
    submodule_name: str
    testbench: str
    normal: str


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return re.sub(r"_+", "_", text)


def read_problem_set() -> list[Problem]:
    with PROBLEM_SET.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [
            Problem(
                identifier=int(row["Id"]),
                level=row["Level"],
                circuit=row["Circuit"],
                inputs=row["Input"],
                outputs=row["Output"],
                type_name=row["Type"],
                submodule_name=row["Submodule Name"],
                testbench=row.get("Testbench", "NA"),
                normal=row.get("Normal", "NA"),
            )
            for row in reader
            if int(row["Id"]) <= 28
        ]


def construction_block(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = []
    for line in lines:
        if "simulator = circuit.simulator()" in line:
            break
        kept.append(line)
    return "\n".join(kept)


def normalize_pyspice_units(expr: str) -> str:
    expr = expr.replace("Î©", "Ohm").replace("Ω", "Ohm")
    return re.sub(r"(\S+)\s*@\s*(u_[A-Za-z]+)", r"unit_value(\1, '\2')", expr)


def unit_value(value: Any, unit_name: str) -> str:
    suffix = UNIT_FACTORS.get(unit_name, "")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}{suffix}"


def call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        if node.func.value.id == "circuit":
            return node.func.attr
    return None


def literal(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "circuit" and node.attr == "gnd":
            return "0"
        return node.attr
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = literal(node.operand, env)
        return -value if isinstance(value, (int, float)) else f"-{value}"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "unit_value":
        return unit_value(literal(node.args[0], env), literal(node.args[1], env))
    try:
        return ast.literal_eval(node)
    except Exception:
        return ast.unparse(node)


def value_to_spice(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text.lower() == "gnd":
            return "0"
        text = re.sub(
            r"unit_value\(([^,]+),\s*'([^']+)'\)",
            lambda match: unit_value(match.group(1).strip(), match.group(2)),
            text,
        )
        text = re.sub(r"^dc\s+", "DC ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+ac\s+", " AC ", text, flags=re.IGNORECASE)
        return text
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def prefixed_name(prefix: str, name: Any) -> str:
    raw = str(name)
    return raw if raw.upper().startswith(prefix) else f"{prefix}{raw}"


def kwargs(call: ast.Call, env: dict[str, Any]) -> dict[str, Any]:
    return {item.arg: literal(item.value, env) for item in call.keywords if item.arg}


def parse_model(call: ast.Call, env: dict[str, Any]) -> str:
    args = [literal(arg, env) for arg in call.args]
    if len(args) < 2:
        return ""
    name, model_type = args[0], args[1]
    params = kwargs(call, env)
    body = " ".join(f"{key.upper()}={value_to_spice(value)}" for key, value in params.items())
    return f".MODEL {name} {str(model_type).upper()} ({body})"


def parse_element(method: str, call: ast.Call, env: dict[str, Any]) -> str | None:
    args = [literal(arg, env) for arg in call.args]
    params = kwargs(call, env)

    if method in {"R", "C", "L", "I"} and len(args) >= 4:
        prefix = PREFIX[method]
        return f"{prefixed_name(prefix, args[0])} {value_to_spice(args[1])} {value_to_spice(args[2])} {value_to_spice(args[3])}"

    if method == "V" and len(args) >= 4:
        return f"{prefixed_name('V', args[0])} {value_to_spice(args[1])} {value_to_spice(args[2])} {value_to_spice(args[3])}"

    if method == "V" and len(args) >= 3:
        dc = params.get("dc_value", params.get("dc", 0))
        ac = params.get("ac_value", params.get("ac", None))
        suffix = f"DC {value_to_spice(dc)}"
        if ac is not None:
            suffix += f" AC {value_to_spice(ac)}"
        return f"{prefixed_name('V', args[0])} {value_to_spice(args[1])} {value_to_spice(args[2])} {suffix}"

    if method == "SinusoidalVoltageSource" and len(args) >= 3:
        offset = params.get("offset", params.get("dc_offset", 0))
        amplitude = params.get("amplitude", 1)
        frequency = params.get("frequency", 1e3)
        return (
            f"{prefixed_name('V', args[0])} {value_to_spice(args[1])} {value_to_spice(args[2])} "
            f"SIN({value_to_spice(offset)} {value_to_spice(amplitude)} {value_to_spice(frequency)})"
        )

    if method == "PulseVoltageSource" and len(args) >= 3:
        initial = params.get("initial_value", params.get("v1", 0))
        pulsed = params.get("pulsed_value", params.get("v2", 5))
        delay = params.get("delay_time", params.get("delay", 0))
        rise = params.get("rise_time", params.get("rise", "1n"))
        fall = params.get("fall_time", params.get("fall", "1n"))
        width = params.get("pulse_width", params.get("width", "1u"))
        period = params.get("period", "2u")
        return (
            f"{prefixed_name('V', args[0])} {value_to_spice(args[1])} {value_to_spice(args[2])} "
            f"PULSE({value_to_spice(initial)} {value_to_spice(pulsed)} {value_to_spice(delay)} "
            f"{value_to_spice(rise)} {value_to_spice(fall)} {value_to_spice(width)} {value_to_spice(period)})"
        )

    if method == "MOSFET" and len(args) >= 5:
        model = params.get("model", args[5] if len(args) > 5 else "NMOS")
        extras = []
        for key in ("w", "l"):
            if key in params:
                extras.append(f"{key.upper()}={value_to_spice(params[key])}")
        return (
            f"{prefixed_name('M', args[0])} {value_to_spice(args[1])} {value_to_spice(args[2])} "
            f"{value_to_spice(args[3])} {value_to_spice(args[4])} {model} {' '.join(extras)}"
        ).strip()

    if method == "X" and len(args) >= 3:
        return f"{prefixed_name('X', args[0])} {' '.join(value_to_spice(arg) for arg in args[2:])} {args[1]}"

    return None


def parse_pyspice(path: Path, problem: Problem) -> tuple[str, list[str]]:
    block = normalize_pyspice_units(construction_block(path))
    tree = ast.parse(block)
    env: dict[str, Any] = {}
    title = f"AnalogCoder-Pro p{problem.identifier}: {problem.circuit}"
    models: list[str] = []
    elements: list[str] = []
    warnings: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = literal(node.value, env)
            except Exception:
                pass
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue

        method = call_name(node.value)
        if method == "model":
            model = parse_model(node.value, env)
            if model:
                models.append(model)
        elif method == "subcircuit":
            warnings.append("subcircuit declaration preserved as external Opamp placeholder")
        elif method in PREFIX:
            element = parse_element(method, node.value, env)
            if element:
                elements.append(element)

    if any(line.startswith("X") and line.endswith(" Opamp") for line in elements):
        models.append("* Opamp subcircuit imported from AnalogCoder-Pro opamp.py")
        models.extend(OPAMP_SUBCKT.splitlines())

    lines = [
        f"* {title}",
        f"* Source: {path.relative_to(ROOT)}",
        f"* AnalogCoder-Pro type: {problem.type_name}",
        f"* Inputs: {problem.inputs}",
        f"* Outputs: {problem.outputs}",
        "",
        *models,
        "",
        *elements,
        "",
        *ANALYSES.get(problem.type_name, [".OP"]),
        ".END",
        "",
    ]
    return "\n".join(lines), warnings


def spec_payload(problem: Problem, netlist_name: str) -> dict[str, Any]:
    circuit_type = TYPE_TO_SPEC2TESTBENCH.get(problem.type_name, "composite")
    return {
        "name": f"analogcoder_pro_p{problem.identifier:02d}_{slugify(problem.type_name)}",
        "circuit_type": circuit_type,
        "technology": "AnalogCoder-Pro/PySpice generic Level-1 models",
        "description": problem.circuit,
        "source": {
            "benchmark": "AnalogCoder-Pro",
            "task_id": problem.identifier,
            "level": problem.level,
            "type": problem.type_name,
            "submodule_name": problem.submodule_name,
            "netlist": f"benchmark/{netlist_name}",
        },
        "performance_targets": DEFAULT_TARGETS.get(problem.type_name, {"operating_point": {"min": 0.0, "max": 5.0, "unit": "V"}}),
        "input_conditions": {
            "vdd": 5.0,
            "vss": 0.0,
            "vcm": 2.5,
            "input_nodes": problem.inputs,
            "output_nodes": problem.outputs,
            "testbench_note": problem.testbench,
            "expected_behavior": problem.normal,
        },
        "test_categories": [category.lower().lstrip(".") for category in category_names(problem.type_name)],
    }


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if (
        text == ""
        or text in {"-", "NA", "null", "true", "false"}
        or any(ch in text for ch in ":#[]{}&*!|>'\"%@`")
        or text.strip() != text
    ):
        return repr(text)
    return text


def yaml_dump(data: Any, indent: int = 0) -> str:
    spaces = " " * indent
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{spaces}{key}:")
                lines.append(yaml_dump(value, indent + 2))
            else:
                lines.append(f"{spaces}{key}: {yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for value in data:
            if isinstance(value, (dict, list)):
                lines.append(f"{spaces}-")
                lines.append(yaml_dump(value, indent + 2))
            else:
                lines.append(f"{spaces}- {yaml_scalar(value)}")
        return "\n".join(lines)
    return f"{spaces}{yaml_scalar(data)}"


def category_names(type_name: str) -> list[str]:
    if type_name in {"LowPass", "HighPass", "BandPass", "BandStop"}:
        return ["ac", "transient"]
    if type_name in {"Oscillator", "Mixer"}:
        return ["transient", "spectral"]
    if type_name in {"Comparator", "Schmitt", "Integrator", "Differentiator"}:
        return ["transient"]
    if type_name in {"Amplifier", "Opamp"}:
        return ["dc", "ac", "transient"]
    return ["dc", "transient"]


def main() -> None:
    problems = read_problem_set()
    if len(problems) != 28:
        raise RuntimeError(f"Expected 28 AnalogCoder-Pro tasks, found {len(problems)}")

    NETLIST_OUT.mkdir(parents=True, exist_ok=True)
    SPEC_OUT.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    for problem in problems:
        source_path = SAMPLE_DESIGNS / f"p{problem.identifier}" / f"p{problem.identifier}.py"
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        netlist_name = f"p{problem.identifier:02d}_{slugify(problem.type_name)}.cir"
        spec_name = f"p{problem.identifier:02d}_{slugify(problem.type_name)}.yaml"
        netlist, warnings = parse_pyspice(source_path, problem)

        (NETLIST_OUT / netlist_name).write_text(netlist, encoding="utf-8")
        (SPEC_OUT / spec_name).write_text(
            yaml_dump(spec_payload(problem, netlist_name)) + "\n",
            encoding="utf-8",
        )

        manifest_rows.append(
            {
                "id": problem.identifier,
                "level": problem.level,
                "type": problem.type_name,
                "circuit_type": TYPE_TO_SPEC2TESTBENCH.get(problem.type_name, "composite"),
                "description": problem.circuit,
                "source_py": str(source_path.relative_to(ROOT)),
                "netlist": netlist_name,
                "spec": spec_name,
                "notes": "; ".join(warnings),
            }
        )

    with (NETLIST_OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Imported {len(manifest_rows)} AnalogCoder-Pro circuits")
    print(f"Netlists: {NETLIST_OUT.relative_to(ROOT)}")
    print(f"Specs: {SPEC_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
