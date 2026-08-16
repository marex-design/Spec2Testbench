from pathlib import Path

import pytest

typer_testing = pytest.importorskip("typer.testing")
CliRunner = typer_testing.CliRunner

from spec2testbench.domain.entities.specification import Specification
from spec2testbench.infrastructure.testbench import TestBenchGenerator as FrameworkTestBenchGenerator
from spec2testbench.presentation.cli.main import app


runner = CliRunner()


P01_NETLIST = """* AnalogCoder-Pro p1
.MODEL nmos_model NMOS (LEVEL=1 KP=0.0001 VTO=0.5)
Vdd Vdd 0 5
Vin Vin 0 DC 1.0 AC 1n
Rload Vout Vdd 10k
M1 Vout Vin 0 0 nmos_model W=5e-05 L=1e-06
.OP
.AC DEC 100 1 1G
.END
"""


def test_explicit_test_categories_preserve_transient(tmp_path):
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        "\n".join([
            "name: explicit_transient_case",
            "circuit_type: amplifier",
            "performance_targets:",
            "  dc_gain_db:",
            "    min: 10",
            "    unit: dB",
            "input_conditions:",
            "  vdd: 5.0",
            "  vss: 0.0",
            "  vcm: 2.5",
            "  input_nodes: Vin",
            "  output_nodes: Vout",
            "test_categories:",
            "  - dc",
            "  - ac",
            "  - transient",
        ]),
        encoding="utf-8",
    )
    specification = Specification.from_yaml(spec_path)

    testbench = FrameworkTestBenchGenerator(use_llm=False).generate(specification)

    analysis_names = {analysis.type.value for analysis in testbench.analyses}
    assert "dc" in analysis_names
    assert "ac" in analysis_names
    assert "tran" in analysis_names


def test_cli_plan_exports_intermediate_json(tmp_path):
    netlist_path = tmp_path / "p01.cir"
    netlist_path.write_text(P01_NETLIST, encoding="utf-8")
    output_path = tmp_path / "plan.json"

    result = runner.invoke(
        app,
        [
            "plan",
            "--specs",
            "benchmark/analogcoder_pro/specs/p01_amplifier.yaml",
            "--netlist",
            str(netlist_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    content = output_path.read_text(encoding="utf-8")
    assert '"circuit_name": "analogcoder_pro_p01_amplifier"' in content
    assert '"source_actions"' in content
    assert '"analysis_actions"' in content


def test_cli_plan_requires_key_when_planner_llm_requested(tmp_path, monkeypatch):
    netlist_path = tmp_path / "p01.cir"
    netlist_path.write_text(P01_NETLIST, encoding="utf-8")
    monkeypatch.setattr("spec2testbench.presentation.cli.main.settings.llm.openai_api_key", "")
    monkeypatch.setattr("spec2testbench.presentation.cli.main.settings.llm.deepseek_api_key", "")
    monkeypatch.setattr("spec2testbench.presentation.cli.main.settings.llm.groq_api_key", "")
    monkeypatch.setattr("spec2testbench.presentation.cli.main.settings.llm.google_api_key", "")
    monkeypatch.setattr("spec2testbench.presentation.cli.main.settings.llm.anthropic_api_key", "")

    result = runner.invoke(
        app,
        [
            "plan",
            "--specs",
            "benchmark/analogcoder_pro/specs/p01_amplifier.yaml",
            "--netlist",
            str(netlist_path),
            "--planner-llm",
        ],
    )

    assert result.exit_code == 1
    assert "Planner LLM requested but no API key is configured" in result.stdout
