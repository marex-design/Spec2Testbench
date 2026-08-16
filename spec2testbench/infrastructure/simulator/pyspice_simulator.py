# spec2testbench/infrastructure/simulator/pyspice_simulator.py

"""
Real SPICE simulator using PySpice and Ngspice.
Compatible with Windows, Linux, and macOS.
"""

import logging
import csv
import tempfile
import subprocess
import os
import re
import shutil
import copy
import hashlib
import json
import shutil as filesystem_shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
import numpy as np

from ...domain.entities.testbench import TestBench, AnalysisType, Stimulus
from ...domain.interfaces.icircuit_simulator import ICircuitSimulator
from ...domain.value_objects.scientific_status import ExecutionStatus, NetlistBindingStatus, SimulationMode
from ...application.services.llm_metric_registry import get_metric_definition
from .result_backends import (
    MetricExtraction,
    NgspiceMeasureBackend,
    NgspiceWrdataBackend,
    PySpiceResultBackend,
    SimulationArtifacts,
    parse_wrdata_file,
)

logger = logging.getLogger(__name__)


class SimulationError(Exception):
    """Raised when simulation fails."""
    pass


@dataclass
class SimulationResult:
    """Results from a SPICE simulation."""
    success: bool
    logs: List[str]
    errors: List[str]
    ac: Optional[Dict[str, np.ndarray]] = None
    tran: Optional[Dict[str, np.ndarray]] = None
    dc: Optional[Dict[str, np.ndarray]] = None
    currents: Optional[Dict[str, float]] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    raw_output: str = ""


class PySpiceSimulator(ICircuitSimulator):
    """
    Real SPICE simulator using PySpice with Ngspice backend.
    
    Requirements:
    - PySpice installed: pip install PySpice
    - Ngspice installed: 
        Windows: Download from https://ngspice.sourceforge.io/
        Linux: sudo apt-get install ngspice
        macOS: brew install ngspice
    """
    _SPICE_SCALE_SUFFIXES = {
        "t": 1e12,
        "g": 1e9,
        "meg": 1e6,
        "k": 1e3,
        "m": 1e-3,
        "u": 1e-6,
        "n": 1e-9,
        "p": 1e-12,
        "f": 1e-15,
    }
    
    def __init__(
        self,
        ngspice_path: Optional[str] = None,
        timeout: int = 300,
        allow_mock: bool = False,
    ):
        """
        Initialize the PySpice simulator.
        
        Args:
            ngspice_path: Path to ngspice executable (auto-detect if None)
            timeout: Simulation timeout in seconds
        """
        self.ngspice_path = ngspice_path or self._find_ngspice()
        self.timeout = timeout
        self.allow_mock = allow_mock
        self.disable_pyspice = os.getenv("SPEC2TESTBENCH_DISABLE_PYSPICE", "").lower() in {"1", "true", "yes"}
        self._ngspice_available = self._check_ngspice()

    @classmethod
    def _parse_spice_numeric(cls, value: Any) -> Optional[float]:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            pass

        match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]+)", raw)
        if not match:
            return None
        magnitude = float(match.group(1))
        suffix = match.group(2).lower()
        scale = cls._SPICE_SCALE_SUFFIXES.get(suffix)
        if scale is None:
            return None
        return magnitude * scale
    
    def _find_ngspice(self) -> str:
        """Find a usable ngspice executable path across Windows/Linux/macOS.

        Resolution order is explicit environment override, executable on PATH,
        then known Windows installation locations.  A known path is accepted
        only when it actually exists; this avoids selecting an unrelated
        Chocolatey path on Linux/macOS.
        """
        env_override = os.getenv("NGSPICE_PATH", "").strip()
        if env_override:
            return env_override

        for executable in ("ngspice_con", "ngspice_con.exe", "ngspice", "ngspice.exe"):
            resolved = shutil.which(executable)
            if resolved:
                return resolved

        known_windows_paths = [
            r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice_con.exe",
            r"C:\ProgramData\chocolatey\bin\ngspice_con.exe",
            r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe",
            r"C:\ProgramData\chocolatey\bin\ngspice.exe",
            r"C:\Program Files\ngspice\bin\ngspice.exe",
        ]
        for candidate in known_windows_paths:
            if Path(candidate).is_file():
                return candidate
        return "ngspice"
    
    def _check_ngspice(self) -> bool:
        """Check whether the resolved executable is callable/present."""
        configured = str(self.ngspice_path or "").strip()
        if configured and (Path(configured).is_file() or shutil.which(configured)):
            logger.info("Ngspice executable found at %s", configured)
            return True
        logger.warning("Ngspice executable not available: %s", configured or "ngspice")
        logger.warning("Install ngspice or set NGSPICE_PATH in .env")
        return False
    
    @property
    def is_available(self) -> bool:
        """Check if simulator is available."""
        return self._ngspice_available
    
    def run(self,
            netlist_path: Path,
            testbench: TestBench,
            output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Run simulation with real SPICE.
        
        Args:
            netlist_path: Path to SPICE netlist
            testbench: TestBench configuration
            output_dir: Output directory for raw files
            
        Returns:
            Dictionary with simulation results
        """
        logger.info(f"Running simulation for {testbench.circuit_name}")
        
        runner = getattr(self, "_run_ngspice")
        runner_func = getattr(runner, "__func__", None)
        runner_overridden = runner_func is None or runner_func is not type(self)._run_ngspice
        if not self._ngspice_available and not runner_overridden:
            if self.allow_mock:
                logger.warning("Ngspice not available, using explicit mock simulation")
                return self._run_mock_simulation(testbench)
            return self._error_result(
                "ngspice_unavailable",
                f"Ngspice executable not available: {self.ngspice_path}",
            )
        
        preserve_artifacts = output_dir is not None
        artifact_dir = Path(output_dir).resolve() if output_dir is not None else Path(tempfile.mkdtemp(prefix="spec2tb_exec_")).resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_file = artifact_dir / "ngspice_stdout.txt"
        stderr_file = artifact_dir / "ngspice_stderr.txt"
        measures_file = artifact_dir / "measures.txt"
        vectors_file = artifact_dir / "vectors.dat"
        vectors_csv = artifact_dir / "vectors.csv"
        vector_metadata = artifact_dir / "vector_metadata.json"
        raw_file = artifact_dir / "simulation.raw"
        executed_deck_path = artifact_dir / "executed_testbench.ckt"
        generated_alias_path = artifact_dir / "generated_testbench.ckt"

        measure_deck = self._generate_measure_deck(netlist_path, testbench, measures_file, vectors_file)
        measure_deck_bytes = measure_deck.encode("utf-8")
        compiled_plan_sha = self._stable_json_sha({
            "testbench": testbench.to_dict(),
            "metadata": getattr(testbench, "metadata", None) or {},
        })
        serialized_deck_sha = hashlib.sha256(measure_deck_bytes).hexdigest()
        executed_deck_path.write_bytes(measure_deck_bytes)
        generated_alias_path.write_bytes(measure_deck_bytes)
        executed_file_sha = self._sha256_file(executed_deck_path)
        generated_alias_sha = self._sha256_file(generated_alias_path)
        expected_netlist_sha = self._sha256_file(netlist_path)
        actual_netlist_sha = expected_netlist_sha if netlist_path and netlist_path.exists() else self._extract_included_netlist_sha(measure_deck)
        actual_deck_sha = executed_file_sha
        binding_status = (
            NetlistBindingStatus.MATCH
            if expected_netlist_sha and actual_netlist_sha and expected_netlist_sha == actual_netlist_sha
            else NetlistBindingStatus.MISMATCH
            if expected_netlist_sha and actual_netlist_sha
            else NetlistBindingStatus.NOT_VERIFIED
        )
        
        try:
            if binding_status != NetlistBindingStatus.MATCH:
                return self._error_result(
                    "netlist_binding_mismatch",
                    "Expected mutated netlist hash does not match the netlist included in the ngspice deck",
                    expected_netlist_sha=expected_netlist_sha,
                    actual_netlist_sha=actual_netlist_sha,
                    actual_deck_sha=actual_deck_sha,
                    binding_status=binding_status,
                    case_id=testbench.case_id,
                    compiled_plan_sha256=compiled_plan_sha,
                    serialized_deck_sha256=serialized_deck_sha,
                    executed_file_sha256=executed_file_sha,
                    ngspice_input_file_path=str(executed_deck_path),
                )
            # Run simulation
            result = self._run_ngspice(executed_deck_path, raw_file, cwd=artifact_dir)
            native_artifacts = self._collect_native_artifacts_from_run(
                artifact_dir=artifact_dir,
                run_result=result,
                testbench=testbench,
                measures_file=measures_file,
                vectors_file=vectors_file,
                vectors_csv=vectors_csv,
                vector_metadata=vector_metadata,
                executed_deck_path=executed_deck_path,
                generated_alias_path=generated_alias_path,
                compiled_plan_sha256=compiled_plan_sha,
                serialized_deck_sha256=serialized_deck_sha,
                executed_file_sha256=executed_file_sha,
            )
            
            # Parse results
            simulation_results = self._parse_results(raw_file, testbench, native_artifacts=native_artifacts)
            simulation_results['logs'] = result['logs']
            simulation_results['errors'] = result['errors']
            simulation_results['success'] = result['success']
            simulation_results['simulation_mode'] = SimulationMode.REAL.value
            simulation_results['execution_status'] = self._execution_status_from_result(result)
            simulation_results['error_type'] = self._error_type_from_result(result)
            simulation_results['ngspice_command'] = result.get('command')
            simulation_results['ngspice_returncode'] = result.get('returncode')
            simulation_results['raw_result_file'] = result.get('raw_result_file')
            simulation_results['raw_result_file_exists'] = result.get('raw_result_file_exists')
            simulation_results['ngspice_version'] = self._get_ngspice_version()
            simulation_results['case_id'] = testbench.case_id
            simulation_results['expected_netlist_sha256'] = expected_netlist_sha
            simulation_results['actual_netlist_sha256'] = actual_netlist_sha
            simulation_results['actual_deck_sha256'] = actual_deck_sha
            simulation_results['netlist_binding_status'] = binding_status.value
            simulation_results['measurement_backend'] = native_artifacts.get('measurement_backend', 'UNAVAILABLE')
            simulation_results['pyspice_required'] = native_artifacts.get('pyspice_required', True)
            simulation_results['measurement_source'] = native_artifacts.get('measurement_source')
            simulation_results['measurement_command'] = native_artifacts.get('measurement_command', '')
            simulation_results['measurement_status'] = native_artifacts.get('measurement_status', 'UNAVAILABLE')
            simulation_results['artifacts'] = native_artifacts.get('artifacts', {})
            simulation_results['measurement_requests'] = self._metric_requests(testbench)
            simulation_results['compiled_plan_sha256'] = compiled_plan_sha
            simulation_results['serialized_deck_sha256'] = serialized_deck_sha
            simulation_results['executed_file_sha256'] = executed_file_sha
            simulation_results['post_execution_file_sha256'] = native_artifacts.get('post_execution_file_sha256')
            simulation_results['ngspice_input_file_path'] = str(executed_deck_path)
            simulation_results['generated_testbench_path'] = str(generated_alias_path)
            simulation_results['generated_testbench_sha256'] = generated_alias_sha
            simulation_results['generated_testbench_alias_byte_identical'] = generated_alias_sha == executed_file_sha
            simulation_results['post_serialization_deck_mutation'] = native_artifacts.get('post_serialization_deck_mutation', False)

            pvt_analysis = next((analysis for analysis in testbench.analyses if analysis.type == AnalysisType.PVT), None)
            if pvt_analysis is not None and (result['success'] or any(simulation_results.get(key) for key in ('dc', 'ac', 'tran', 'transient', 'fourier'))):
                simulation_results['pvt'] = self._run_pvt_variants(
                    measure_deck,
                    testbench,
                    simulation_results,
                    pvt_analysis.parameters,
                )
            
            # Extract metrics
            has_structured_results = any(
                simulation_results.get(key) for key in ('dc', 'ac', 'tran', 'transient', 'fourier')
            ) or bool(simulation_results.get("native_metrics"))
            if result['success'] or has_structured_results:
                if has_structured_results:
                    simulation_results['success'] = True
                    simulation_results['execution_status'] = ExecutionStatus.SUCCESS.value
                metrics = self.extract_metrics(simulation_results, testbench)
                simulation_results['metrics'] = metrics
            
            return simulation_results
            
        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            if self.allow_mock:
                logger.warning("Simulation failed, using explicit mock simulation")
                return self._run_mock_simulation(testbench)
            return self._error_result(type(e).__name__, str(e))
        finally:
            # Cleanup
            if not preserve_artifacts:
                try:
                    filesystem_shutil.rmtree(artifact_dir, ignore_errors=True)
                except Exception:
                    pass
    
    def _run_mock_simulation(self, testbench: TestBench) -> Dict[str, Any]:
        """Run mock simulation when ngspice is not available."""
        logger.info("Running mock simulation")
        
        # Generate mock results based on testbench type
        results = {
            'success': True,
            'simulation_mode': SimulationMode.MOCK.value,
            'execution_status': ExecutionStatus.SUCCESS.value,
            'scientifically_eligible': False,
            'logs': ['Mock simulation - ngspice not available'],
            'errors': [],
            'metrics': {},
            'ac': {},
            'tran': {}
        }
        
        # Mock AC results
        if any(a.type == AnalysisType.AC for a in testbench.analyses):
            freq = np.logspace(0, 9, 100)
            # Simple low-pass response
            mag = 100 / (1 + (freq / 1e6)**2)
            results['ac'] = {
                'frequency': freq,
                'magnitude': mag,
                'phase': -np.arctan2(freq, 1e6) * 180 / np.pi
            }
            results['metrics']['dc_gain_db'] = 20 * np.log10(mag[0])
        
        # Mock transient results
        if any(a.type == AnalysisType.TRANSIENT for a in testbench.analyses):
            time = np.linspace(0, 10e-6, 1000)
            vout = 2.5 + 2.5 * np.sin(2 * np.pi * 1e6 * time)
            results['tran'] = {
                'time': time,
                'vout': vout
            }
            # Calculate mock slew rate
            dv = np.diff(vout)
            dt = np.diff(time)
            results['metrics']['slew_rate_v_s'] = float(np.max(np.abs(dv / dt)))
        
        # Mock DC results
        if any(a.type == AnalysisType.DC for a in testbench.analyses):
            vin = np.linspace(0, 5, 50)
            vout = 2.5 + 2.5 * np.tanh(vin - 2.5)
            results['dc'] = {
                'vin': vin,
                'vout': vout
            }
        
        # Mock currents
        results['currents'] = {'vdd': 1e-3}
        
        return results

    def _error_result(
        self,
        error_type: str,
        error_message: str,
        *,
        expected_netlist_sha: Optional[str] = None,
        actual_netlist_sha: Optional[str] = None,
        actual_deck_sha: Optional[str] = None,
        binding_status: NetlistBindingStatus = NetlistBindingStatus.NOT_VERIFIED,
        case_id: Optional[str] = None,
        **extra_fields: Any,
    ) -> Dict[str, Any]:
        execution_status = (
            ExecutionStatus.TIMEOUT
            if "timeout" in error_type.lower() or "timed out" in error_message.lower()
            else ExecutionStatus.ERROR
        )
        return {
            "success": False,
            "simulation_mode": SimulationMode.REAL.value,
            "execution_status": execution_status.value,
            "scientifically_eligible": False,
            "logs": [],
            "errors": [error_message],
            "error_type": error_type,
            "error_message": error_message,
            "metrics": {},
            "ac": {},
            "tran": {},
            "transient": {},
            "dc": {},
            "fourier": {},
            "pvt": {},
            "currents": {},
            "case_id": case_id,
            "expected_netlist_sha256": expected_netlist_sha,
            "actual_netlist_sha256": actual_netlist_sha,
            "actual_deck_sha256": actual_deck_sha,
            "netlist_binding_status": binding_status.value,
            **extra_fields,
        }

    @staticmethod
    def _sha256_file(path: Optional[Path]) -> Optional[str]:
        if not path or not Path(path).exists():
            return None
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _stable_json_sha(payload: Any) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")).hexdigest()

    def _extract_included_netlist_sha(self, spice_deck: str) -> Optional[str]:
        for line in spice_deck.splitlines():
            stripped = line.strip()
            if not stripped.lower().startswith(".include"):
                continue
            path_text = stripped[len(".include"):].strip().strip('"').strip("'")
            if not path_text:
                return None
            return self._sha256_file(Path(path_text))
        return None

    def _execution_status_from_result(self, result: Dict[str, Any]) -> str:
        if result.get("success"):
            return ExecutionStatus.SUCCESS.value
        joined_errors = "\n".join(result.get("errors", []))
        if "timed out" in joined_errors.lower():
            return ExecutionStatus.TIMEOUT.value
        return ExecutionStatus.ERROR.value

    def _error_type_from_result(self, result: Dict[str, Any]) -> Optional[str]:
        if result.get("success"):
            return None
        joined_errors = "\n".join(result.get("errors", []))
        if "timed out" in joined_errors.lower():
            return "timeout"
        if joined_errors:
            return "ngspice_error"
        return "simulation_error"
    
    def _generate_spice_deck(self, netlist_path: Path, testbench: TestBench) -> str:
        """Generate complete SPICE deck."""
        existing_text = ""
        if netlist_path and netlist_path.exists():
            existing_text = netlist_path.read_text(encoding="utf-8", errors="ignore")
        stimuli = self._collapse_stimuli(testbench.stimuli, testbench.analyses, existing_text)
        plan = (testbench.metadata or {}).get("llm_guided_plan", {})
        lines = [
            f"* TestBench: {testbench.name}",
            f"* Circuit: {testbench.circuit_name}",
            f"* Category: {testbench.category}",
            "*",
            ".OPTIONS POST=2 PROBE",
            ".OPTIONS FILETYPE=ASCII",
        ]

        if netlist_path and netlist_path.exists():
            existing_text = re.sub(r"(?is)\.control\b.*?\.endc", "", existing_text)
            existing_text = re.sub(r"^\s*\.end\s*$", "", existing_text, flags=re.IGNORECASE | re.MULTILINE).strip()
            existing_text = self._resolve_relative_includes(existing_text, netlist_path)
            if plan:
                existing_text = self._apply_guided_source_plan(existing_text, plan)
            else:
                existing_text = self._apply_stimulus_overrides(existing_text, stimuli)
            existing_text = self._apply_analysis_overrides(existing_text, testbench.analyses)
            if existing_text:
                lines.extend(["", existing_text])
        else:
            lines.extend(["", f"* WARNING: Netlist not found: {netlist_path}"])

        if (
            not re.search(r"^\s*\.temp\b", existing_text, re.IGNORECASE | re.MULTILINE)
            and not self._nearly_equal(float(testbench.temperature), 27.0)
        ):
            lines.extend(["", f".TEMP {testbench.temperature}"])

        emitted_sources = set()
        if plan:
            for source_action in plan.get("source_actions", []):
                rendered = self._render_guided_source(source_action)
                source_name = str(source_action.get("target_name", "")).lower()
                if not rendered or source_name in emitted_sources:
                    continue
                if not self._source_exists_in_text(existing_text, source_action):
                    lines.append(rendered)
                    emitted_sources.add(source_name)
        else:
            for stimulus in stimuli:
                source_name = f"v{stimulus.name}".lower()
                if source_name in emitted_sources:
                    continue
                if not re.search(rf"^\s*V{re.escape(stimulus.name)}\b", existing_text, re.IGNORECASE | re.MULTILINE):
                    lines.append(stimulus.to_spice())
                    emitted_sources.add(source_name)

        analysis_commands = {
            AnalysisType.DC: r"^\s*\.dc\b",
            AnalysisType.AC: r"^\s*\.ac\b",
            AnalysisType.TRANSIENT: r"^\s*\.tran\b",
            AnalysisType.FOURIER: r"^\s*\.fourier\b",
        }
        for analysis in testbench.analyses:
            pattern = analysis_commands.get(analysis.type)
            if analysis.type == AnalysisType.DC:
                start = analysis.parameters.get('start')
                stop = analysis.parameters.get('stop')
                step = analysis.parameters.get('step', 0.0)
                if start is not None and stop is not None:
                    try:
                        if abs(float(stop) - float(start)) <= max(abs(float(step)), 1e-18):
                            pattern = r"^\s*\.(dc|op)\b"
                    except (TypeError, ValueError):
                        pass
            if pattern and re.search(pattern, existing_text, re.IGNORECASE | re.MULTILINE):
                continue
            lines.append(analysis.to_spice())

        lines.extend(["", ".END"])
        return "\n".join(lines)

    def _apply_guided_source_plan(self, existing_text: str, plan: Dict[str, Any]) -> str:
        updated_text = existing_text
        for source_action in plan.get("source_actions", []):
            replacement = self._render_guided_source(source_action)
            if not replacement:
                continue
            candidate_names = [
                f"V{source_action.get('target_name', '')}",
                str(source_action.get("target_name", "")),
            ]
            new_source = source_action.get("new_source", {})
            pos = str(new_source.get("node_positive", "")).strip()
            if pos:
                candidate_names.extend([f"V{pos}", pos])
            count = 0
            for candidate in dict.fromkeys(name for name in candidate_names if name):
                pattern = rf"(?im)^\s*{re.escape(candidate)}\b.*$"
                updated_text, count = re.subn(pattern, replacement, updated_text, count=1)
                if count:
                    break
            if count:
                continue
        return updated_text

    def _render_guided_source(self, source_action: Dict[str, Any]) -> str:
        source = source_action.get("new_source", {})
        kind = str(source.get("kind", "voltage")).lower()
        if kind != "voltage":
            return ""
        name = source_action.get("target_name") or source.get("node_positive", "in")
        pos = source.get("node_positive", "in")
        neg = source.get("node_negative", "0")
        source_type = str(source.get("type", "dc")).lower()

        if source_type == "multimode":
            source_type = "ac" if source.get("ac_magnitude") is not None else "dc"

        if source_type == "dc":
            return f"V{name} {pos} {neg} DC {source.get('dc_value', 0)}"
        if source_type == "ac":
            line = f"V{name} {pos} {neg}"
            dc_value = source.get("dc_value")
            if dc_value is not None:
                line += f" DC {dc_value}"
            line += f" AC {source.get('ac_magnitude', 1.0)}"
            return line

        transient = source.get("transient", {})
        dc_value = source.get("dc_value")
        ac_magnitude = source.get("ac_magnitude")
        prefix = f"V{name} {pos} {neg}"
        prefix_parts = [prefix]
        if dc_value is not None:
            prefix_parts.append(f"DC {dc_value}")
        if ac_magnitude is not None:
            prefix_parts.append(f"AC {ac_magnitude}")
        prefix = " ".join(prefix_parts)
        if source_type == "pulse":
            return (
                f"{prefix} "
                f"PULSE({transient.get('v1', 0)} {transient.get('v2', 1)} "
                f"{transient.get('delay', 0)} {transient.get('rise', '1N')} "
                f"{transient.get('fall', '1N')} {transient.get('width', '1U')} "
                f"{transient.get('period', '2U')})"
            )
        if source_type == "sin":
            return (
                f"{prefix} "
                f"SIN({transient.get('offset', 0)} {transient.get('amplitude', 1)} "
                f"{transient.get('frequency', 1e6)})"
            )
        if source_type == "pwl":
            points = transient.get("points", [])
            point_text = " ".join(f"{t} {v}" for t, v in points)
            return f"{prefix} PWL({point_text})"
        return ""

    def _source_exists_in_text(self, existing_text: str, source_action: Dict[str, Any]) -> bool:
        target_name = str(source_action.get("target_name", "")).strip()
        if target_name and re.search(rf"^\s*V{re.escape(target_name)}\b", existing_text, re.IGNORECASE | re.MULTILINE):
            return True
        source = source_action.get("new_source", {})
        pos = str(source.get("node_positive", "")).strip()
        if pos and re.search(rf"^\s*V{re.escape(pos)}\b", existing_text, re.IGNORECASE | re.MULTILINE):
            return True
        return False

    def _resolve_relative_includes(self, existing_text: str, netlist_path: Path) -> str:
        """
        Rewrite relative .include/.lib paths so they remain valid after the
        combined deck is emitted into a temporary directory for ngspice.
        """
        base_dir = netlist_path.parent.resolve()

        def replace_include(match: re.Match[str]) -> str:
            directive = match.group("directive")
            quote = match.group("quote") or ""
            path_text = (match.group("path") or "").strip()
            suffix = match.group("suffix") or ""
            if not path_text:
                return match.group(0)
            if path_text.startswith("$"):
                return match.group(0)

            include_path = Path(path_text)
            if not include_path.is_absolute():
                include_path = (base_dir / include_path).resolve()
            normalized = include_path.as_posix()
            quoted = f'"{normalized}"' if quote or " " in normalized else normalized
            return f".{directive} {quoted}{suffix}"

        pattern = re.compile(
            r"(?im)^\s*\.(?P<directive>include|lib)\s+"
            r"(?P<quote>[\"'])?(?P<path>[^\"'\s]+)(?(quote)(?P=quote))"
            r"(?P<suffix>\s+.*)?$"
        )
        return pattern.sub(replace_include, existing_text)

    def _collapse_stimuli(self, stimuli: List[Stimulus], analyses: List[Any], existing_text: str = "") -> List[Stimulus]:
        analysis_types = {analysis.type for analysis in analyses}
        preferred_types = self._preferred_stimulus_types(analysis_types)

        grouped: Dict[str, List[Stimulus]] = {}
        order: List[str] = []
        for stimulus in stimuli:
            key = stimulus.name.lower()
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(stimulus)

        collapsed: List[Stimulus] = []
        for key in order:
            candidates = grouped[key]
            chosen = candidates[-1]
            for preferred in preferred_types:
                match = next((candidate for candidate in reversed(candidates) if candidate.type == preferred), None)
                if match is not None:
                    chosen = match
                    break
            chosen = self._merge_bias_into_stimulus(chosen, candidates, existing_text)
            collapsed.append(chosen)
        return collapsed

    def _merge_bias_into_stimulus(self, chosen: Stimulus, candidates: List[Stimulus], existing_text: str) -> Stimulus:
        if chosen.type != "ac":
            return chosen

        parameters = dict(chosen.parameters)
        if parameters.get("dc_value") is not None:
            return Stimulus(
                name=chosen.name,
                type=chosen.type,
                parameters=parameters,
                node_positive=chosen.node_positive,
                node_negative=chosen.node_negative,
            )

        dc_candidate = next(
            (candidate for candidate in reversed(candidates) if candidate.type == "dc" and "value" in candidate.parameters),
            None,
        )
        if dc_candidate is not None:
            parameters["dc_value"] = dc_candidate.parameters.get("value")
        else:
            existing_dc = self._extract_dc_bias_from_netlist(existing_text, chosen.name)
            if existing_dc is not None:
                parameters["dc_value"] = existing_dc
            else:
                parameters["dc_value"] = 0.0
                logger.warning(
                    "No DC bias found for AC stimulus %s; falling back to 0.0 V",
                    chosen.name,
                )

        return Stimulus(
            name=chosen.name,
            type=chosen.type,
            parameters=parameters,
            node_positive=chosen.node_positive,
            node_negative=chosen.node_negative,
        )

    def _extract_dc_bias_from_netlist(self, existing_text: str, stimulus_name: str) -> Optional[float]:
        if not existing_text:
            return None

        candidate_names = [stimulus_name]
        prefixed = f"V{stimulus_name}"
        if prefixed.lower() not in {name.lower() for name in candidate_names}:
            candidate_names.append(prefixed)

        for candidate_name in candidate_names:
            pattern = re.compile(
                rf"(?im)^\s*{re.escape(candidate_name)}\b\s+\S+\s+\S+\s+(?P<body>.+?)\s*$"
            )
            match = pattern.search(existing_text)
            if not match:
                continue

            body = match.group("body").strip()
            dc_match = re.search(r"(?i)\bDC\s+([^\s]+)", body)
            raw_value = dc_match.group(1) if dc_match else body.split()[0]
            return self._parse_spice_numeric(raw_value)
        return None

    def _preferred_stimulus_types(self, analysis_types: set[AnalysisType]) -> List[str]:
        if AnalysisType.AC in analysis_types:
            return ["ac", "dc", "pulse", "sin"]
        if AnalysisType.FOURIER in analysis_types:
            return ["sin", "pulse", "dc", "ac"]
        if AnalysisType.TRANSIENT in analysis_types:
            return ["pulse", "sin", "dc", "ac"]
        return ["dc", "ac", "pulse", "sin"]

    def _apply_stimulus_overrides(self, existing_text: str, stimuli: List[Stimulus]) -> str:
        updated_text = existing_text
        for stimulus in stimuli:
            replacement = stimulus.to_spice()
            candidate_names = [
                f"V{stimulus.name}",
                str(stimulus.name),
                f"V{stimulus.node_positive}",
                str(stimulus.node_positive),
            ]
            count = 0
            for candidate in dict.fromkeys(name for name in candidate_names if name):
                pattern = rf"(?im)^\s*{re.escape(candidate)}\b.*$"
                updated_text, count = re.subn(pattern, replacement, updated_text, count=1)
                if count:
                    logger.debug(
                        "Overrode existing source %s with generated stimulus %s",
                        candidate,
                        stimulus.name,
                    )
                    break
            if count:
                continue
        return updated_text

    def _apply_analysis_overrides(self, existing_text: str, analyses: List[AnalysisType]) -> str:
        updated_text = existing_text
        patterns = {
            AnalysisType.DC: r"(?im)^\s*\.(dc|op)\b.*$",
            AnalysisType.AC: r"(?im)^\s*\.ac\b.*$",
            AnalysisType.TRANSIENT: r"(?im)^\s*\.tran\b.*$",
            AnalysisType.FOURIER: r"(?im)^\s*\.four(ier)?\b.*$",
        }
        for pattern in patterns.values():
            updated_text = re.sub(pattern, "", updated_text)
        for analysis in analyses:
            if analysis.type not in patterns:
                continue
            updated_text = updated_text.rstrip() + "\n" + analysis.to_spice() + "\n"
        return updated_text
    
    def _run_ngspice(
        self,
        spice_file: Path,
        raw_file: Path,
        timeout_override: Optional[int] = None,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Run ngspice simulation.
        
        Returns:
            Dictionary with success flag and logs
        """
        # Command to run ngspice in batch mode
        spice_argument = str(spice_file.resolve()) if cwd else str(spice_file)
        cmd = [
            self.ngspice_path,
            "-b",  # Batch mode
            spice_argument
        ]
        
        effective_timeout = timeout_override or self.timeout

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                shell=False,
                cwd=str(cwd) if cwd else None,
            )
            
            logs = result.stdout.splitlines() if result.stdout else []
            errors = result.stderr.splitlines() if result.stderr else []
            
            # Check for convergence issues
            all_output = (result.stdout or "") + (result.stderr or "")
            all_output_lower = all_output.lower()
            
            success = result.returncode == 0
            if 'error' in all_output_lower or 'no convergence' in all_output_lower:
                success = False
            
            return {
                'success': success,
                'logs': logs,
                'errors': errors,
                'command': cmd,
                'returncode': result.returncode,
                'raw_result_file': str(raw_file),
                'raw_result_file_exists': raw_file.exists(),
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'logs': [],
                'errors': [f"Simulation timed out after {effective_timeout} seconds"],
                'command': cmd,
                'returncode': None,
                'raw_result_file': str(raw_file),
                'raw_result_file_exists': raw_file.exists(),
            }
        except Exception as e:
            return {
                'success': False,
                'logs': [],
                'errors': [str(e)],
                'command': cmd,
                'returncode': None,
                'raw_result_file': str(raw_file),
                'raw_result_file_exists': raw_file.exists(),
            }
    
    def _parse_results(self, raw_file: Path, testbench: TestBench, native_artifacts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse ngspice raw output file.
        
        Returns:
            Structured results dictionary
        """
        results = {
            'ac': {},
            'tran': {},
            'transient': {},
            'dc': {},
            'currents': {},
            'fourier': {},
        }
        
        if raw_file.exists():
            try:
                # Try to parse with PySpice
                from PySpice.Spice.RawFile import RawFile
                
                raw = RawFile(str(raw_file))
                parsed_plots = self._extract_rawfile_plots(raw)
                results.update(self._build_structured_results(parsed_plots))
                
            except ImportError:
                logger.warning("PySpice not available for parsing")
            except Exception as e:
                logger.warning(f"Failed to parse raw file with PySpice parser: {e}")

            if not any(results[key] for key in ('ac', 'tran', 'dc', 'currents')):
                parsed_plots = self._parse_raw_fallback(raw_file)
                if parsed_plots:
                    results.update(self._build_structured_results(parsed_plots))

        if native_artifacts:
            metric_requests = self._metric_requests(testbench)
            measurement_config = (getattr(testbench, "metadata", None) or {}).get("measurement", {})
            self._active_required_backend = measurement_config.get("required_backend")
            self._active_allow_backend_fallback = measurement_config.get("allow_backend_fallback", True)
            artifacts = SimulationArtifacts(
                raw_file=raw_file,
                stdout_file=Path(native_artifacts["artifacts"]["stdout"]) if native_artifacts.get("artifacts", {}).get("stdout") else None,
                stderr_file=Path(native_artifacts["artifacts"]["stderr"]) if native_artifacts.get("artifacts", {}).get("stderr") else None,
                measures_file=Path(native_artifacts["artifacts"]["measures"]) if native_artifacts.get("artifacts", {}).get("measures") else None,
                vectors_file=Path(native_artifacts["artifacts"]["vectors"]) if native_artifacts.get("artifacts", {}).get("vectors") else None,
                vector_csv_file=Path(native_artifacts["artifacts"]["vectors_csv"]) if native_artifacts.get("artifacts", {}).get("vectors_csv") else None,
                vector_metadata_file=Path(native_artifacts["artifacts"]["vector_metadata"]) if native_artifacts.get("artifacts", {}).get("vector_metadata") else None,
            )
            self._hydrate_results_from_vectors(results, testbench, artifacts.vectors_file)
            backend_results = self._extract_metrics_with_backends(artifacts, metric_requests, raw_file)
            self._active_required_backend = None
            self._active_allow_backend_fallback = True
            results.setdefault("native_metrics", {})
            results.setdefault("native_extractions", {})
            request_by_name = {request["name"]: request for request in metric_requests}
            for metric_name, extraction in backend_results.items():
                request = request_by_name.get(metric_name, {})
                results["native_extractions"][metric_name] = {
                    "metric_name": metric_name,
                    "measured_value": extraction.value,
                    "status": extraction.status,
                    "reason": extraction.error or extraction.status,
                    "synthetic_value_used": False,
                    "measurement_backend": extraction.backend,
                    "metric_definition_version": request.get("metric_definition_version"),
                    "quantity_type": request.get("quantity_type"),
                    "measurement_expression_id": request.get("measurement_expression_id"),
                    "input_node": request.get("input_node"),
                    "output_node": request.get("output_node"),
                    "input_ac_magnitude": request.get("input_ac_magnitude"),
                    "reference_frequency_hz": request.get("reference_frequency_hz"),
                }
                if extraction.value is not None:
                    results["native_metrics"][metric_name] = extraction.value
        
        return results

    def _hydrate_results_from_vectors(
        self,
        results: Dict[str, Any],
        testbench: TestBench,
        vectors_file: Optional[Path],
    ) -> None:
        if vectors_file is None or not vectors_file.exists():
            return
        analysis_types = {analysis.type for analysis in testbench.analyses}
        try:
            data = parse_wrdata_file(vectors_file)["data"]
        except ValueError:
            return
        if data.ndim != 2 or data.shape[1] < 2:
            return

        if (
            AnalysisType.TRANSIENT in analysis_types
            and AnalysisType.AC not in analysis_types
            and not (results.get("transient") or results.get("tran"))
        ):
            transient = {
                "time": data[:, 0].tolist(),
                "vout": data[:, -1].tolist(),
            }
            if data.shape[1] >= 3:
                transient["vin"] = data[:, 1].tolist()
            results["tran"] = transient
            results["transient"] = dict(transient)
        if AnalysisType.DC in analysis_types and not results.get("dc"):
            value = float(data[-1, -1])
            results["dc"] = {
                "vout_dc": value,
                "operating_point": value,
                "vout": value,
            }
    
    def extract_metrics(self, 
                        results: Dict[str, Any],
                        testbench: TestBench) -> Dict[str, float]:
        """
        Extract metrics from simulation results.
        """
        metrics = {}
        
        ac = results.get('ac', {})
        if ac.get('dc_gain_db') is not None:
            metrics['dc_gain_db'] = float(ac['dc_gain_db'])
        if ac.get('bandwidth') is not None:
            metrics['bandwidth'] = float(ac['bandwidth'])
            metrics['cutoff_frequency_hz'] = float(ac['bandwidth'])
        if ac.get('unity_gain_frequency') is not None:
            metrics['unity_gain_frequency'] = float(ac['unity_gain_frequency'])
            metrics['ugbw'] = float(ac['unity_gain_frequency'])
        if ac.get('phase_margin') is not None:
            metrics['phase_margin'] = float(ac['phase_margin'])

        dc = results.get('dc', {})
        for key in ('vout_dc', 'operating_point'):
            if key in dc:
                metrics[key] = float(dc[key])

        currents = results.get('currents', {})
        current = currents.get('vdd')
        supply = results.get('vdd', 0.0)
        current_items = []
        for key, value in currents.items():
            if value is None:
                continue
            try:
                current_items.append((key.lower(), float(abs(value))))
            except Exception:
                continue

        supply_current = self._select_supply_current(currents)
        if supply_current is not None:
            metrics['supply_current_a'] = supply_current
            metrics['quiescent_current'] = supply_current
            metrics['idd'] = supply_current
            if supply:
                metrics['power'] = float(abs(supply * supply_current))
        else:
            averaged_currents = [value for key, value in current_items if key != 'vdd']
            if not averaged_currents and current is not None:
                averaged_currents = [float(abs(current))]

            mean_current = float(np.mean(averaged_currents)) if averaged_currents else None
            if mean_current is not None:
                metrics['mean_current_a'] = mean_current
                logger.warning(
                    "Falling back to averaged branch current for quiescent_current; no supply current identified"
                )
                metrics['quiescent_current'] = mean_current
                metrics['idd'] = mean_current
                if supply:
                    metrics['power'] = float(abs(supply * mean_current))
            elif current is not None:
                metrics['supply_current_a'] = float(abs(current))
                metrics['quiescent_current'] = float(abs(current))
                metrics['idd'] = float(abs(current))
                if supply:
                    metrics['power'] = float(abs(supply * current))

        tran = results.get('transient') or results.get('tran', {})
        native_extractions = results.get("native_extractions", {})
        blocked_native_metrics = {
            name for name, extraction in native_extractions.items()
            if extraction.get("status") != "SUCCESS"
        }
        vout = tran.get('vout', [])
        time = tran.get('time', [])
        if len(vout) > 1 and len(time) > 1:
            dv = np.diff(vout)
            dt = np.diff(time)
            with np.errstate(divide='ignore'):
                sr = np.max(np.abs(dv / dt))
            if not np.isnan(sr) and not np.isinf(sr):
                metrics['slew_rate_v_s'] = float(sr)
                metrics['slew_rate'] = float(sr)
            schmitt_metrics = self._extract_schmitt_metrics(tran)
            if "propagation_delay" in blocked_native_metrics:
                schmitt_metrics.pop("propagation_delay", None)
                schmitt_metrics.pop("propagation_delay_s", None)
            metrics.update({key: value for key, value in schmitt_metrics.items() if value is not None})
            oscillation_validation = self._validate_oscillation(
                tran,
                amplitude_threshold=float(testbench.metadata.get("oscillation_amplitude_threshold", 1e-6)),
                minimum_cycles=int(testbench.metadata.get("oscillation_minimum_cycles", 3)),
                max_period_cv=float(testbench.metadata.get("oscillation_max_period_cv", 0.25)),
                min_spectral_prominence=float(testbench.metadata.get("oscillation_min_spectral_prominence", 5.0)),
            )
            results["oscillation_validation"] = oscillation_validation
            oscillation_frequency = self._estimate_transient_frequency(tran)
            if oscillation_frequency is not None and oscillation_validation["status"] == "VALID_OSCILLATION":
                metrics['oscillator_frequency'] = float(oscillation_frequency)
                metrics['frequency_hz'] = float(oscillation_frequency)
            startup_amplitude = self._estimate_startup_amplitude(tran)
            if startup_amplitude is not None:
                metrics['startup_amplitude'] = float(startup_amplitude)

        guard_status = results.get("oscillation_validation", {}).get("status")
        if guard_status and guard_status != "VALID_OSCILLATION":
            for metric_name in ("oscillator_frequency", "frequency_hz"):
                results.get("native_metrics", {}).pop(metric_name, None)
                if metric_name in native_extractions:
                    native_extractions[metric_name]["measured_value"] = None
                    native_extractions[metric_name]["status"] = "NOT_EVALUATED"
                    native_extractions[metric_name]["reason"] = f"OSCILLATION_GUARD_{guard_status}"

        fourier = results.get('fourier', {})
        if 'thd' in fourier:
            metrics['thd'] = float(fourier['thd'])
            metrics['thd_percent'] = float(fourier['thd'])
        if 'fundamental_frequency' in fourier:
            metrics['fundamental_frequency'] = float(fourier['fundamental_frequency'])
            if results.get("oscillation_validation", {}).get("status") == "VALID_OSCILLATION":
                metrics.setdefault('oscillator_frequency', float(fourier['fundamental_frequency']))
                metrics.setdefault('frequency_hz', float(fourier['fundamental_frequency']))

        for measurement in testbench.measurements:
            extraction = native_extractions.get(measurement.name, {})
            if extraction and extraction.get("status") != "SUCCESS":
                continue
            for container in (results.get('native_metrics', {}), metrics, dc, ac, fourier, results.get('pvt', {}).get('summary', {})):
                if measurement.name in container:
                    value = container[measurement.name]
                    if value is None:
                        continue
                    metrics[measurement.name] = float(value)
                    break
        
        return metrics

    def _validate_oscillation(
        self,
        transient: Dict[str, Any],
        *,
        amplitude_threshold: float,
        minimum_cycles: int,
        max_period_cv: float,
        min_spectral_prominence: float,
    ) -> Dict[str, Any]:
        time = np.array(transient.get("time", []), dtype=float)
        vout = np.array(transient.get("vout", []), dtype=float)
        if time.size < 8 or vout.size < 8:
            return {"status": "NOT_EVALUATED"}

        vpp = float(np.max(vout) - np.min(vout))
        if not np.isfinite(vpp) or vpp < amplitude_threshold:
            return {"status": "AMPLITUDE_TOO_LOW", "vpp": vpp}

        mean_value = float(np.mean(vout))
        crossings: List[float] = []
        for index in range(1, len(vout)):
            if vout[index - 1] <= mean_value < vout[index]:
                crossings.append(float(time[index]))
        if len(crossings) < minimum_cycles + 1:
            return {"status": "INSUFFICIENT_CYCLES", "cycles": max(0, len(crossings) - 1), "vpp": vpp}

        periods = np.diff(crossings)
        valid_periods = periods[periods > 0]
        if len(valid_periods) < minimum_cycles:
            return {"status": "INSUFFICIENT_CYCLES", "cycles": int(len(valid_periods)), "vpp": vpp}
        period_cv = float(np.std(valid_periods) / np.mean(valid_periods)) if np.mean(valid_periods) > 0 else float("inf")
        if not np.isfinite(period_cv) or period_cv > max_period_cv:
            return {"status": "UNSTABLE_PERIOD", "period_cv": period_cv, "vpp": vpp}

        centered = vout - np.mean(vout)
        dt = float(np.mean(np.diff(time)))
        if not np.isfinite(dt) or dt <= 0:
            return {"status": "NOT_EVALUATED", "vpp": vpp}
        spectrum = np.fft.rfft(centered * np.hanning(centered.size))
        magnitudes = np.abs(spectrum)
        if magnitudes.size < 2:
            return {"status": "NO_VALID_PEAK", "vpp": vpp}
        dc_mag = max(magnitudes[0], 1e-30)
        magnitudes[0] = 0.0
        peak = float(np.max(magnitudes))
        if peak <= 0:
            return {"status": "NO_VALID_PEAK", "vpp": vpp}
        if peak / dc_mag < min_spectral_prominence:
            return {"status": "DC_DOMINATED", "spectral_prominence": peak / dc_mag, "vpp": vpp}
        return {
            "status": "VALID_OSCILLATION",
            "vpp": vpp,
            "cycles": int(len(valid_periods)),
            "period_cv": period_cv,
            "spectral_prominence": peak / dc_mag,
        }

    def _run_native_extraction_passes(self, netlist_path: Path, testbench: TestBench) -> Dict[str, Any]:
        artifact_dir = Path(tempfile.mkdtemp(prefix="spec2tb_native_"))
        stdout_file = artifact_dir / "ngspice_stdout.txt"
        stderr_file = artifact_dir / "ngspice_stderr.txt"
        measures_file = artifact_dir / "measures.txt"
        vectors_file = artifact_dir / "vectors.dat"
        vectors_csv = artifact_dir / "vectors.csv"
        vector_metadata = artifact_dir / "vector_metadata.json"

        measure_deck = self._generate_measure_deck(netlist_path, testbench, measures_file, vectors_file)
        deck_path = artifact_dir / "native_backend.cir"
        deck_path.write_text(measure_deck, encoding="utf-8")
        cmd = [self.ngspice_path, "-b", str(deck_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=False, cwd=str(artifact_dir))
        stdout_file.write_text(result.stdout or "", encoding="utf-8")
        stderr_file.write_text(result.stderr or "", encoding="utf-8")
        if result.stdout:
            measures_file.write_text(result.stdout, encoding="utf-8")
        if vectors_file.exists():
            self._wrdata_to_csv(vectors_file, vectors_csv)
        vector_metadata.write_text(json.dumps({
            "vectors_file": str(vectors_file) if vectors_file.exists() else None,
            "vectors_csv": str(vectors_csv) if vectors_csv.exists() else None,
        }, indent=2), encoding="utf-8")
        measurement_config = (getattr(testbench, "metadata", None) or {}).get("measurement", {})
        measurement_requests = self._metric_requests(testbench)
        required_backend = measurement_config.get("required_backend")
        has_measures = measures_file.exists() and measures_file.read_text(encoding="utf-8", errors="ignore").strip()
        has_vectors = vectors_file.exists()
        preferred_backends = {
            request.get("preferred_backend")
            for request in measurement_requests
            if request.get("preferred_backend") in {"NGSPICE_MEASURE", "NGSPICE_WRDATA"}
        }
        backend = self._select_native_backend(
            required_backend=required_backend,
            has_measures=bool(has_measures),
            has_vectors=has_vectors,
            preferred_backends=preferred_backends,
        )
        if backend == "NGSPICE_MEASURE":
            source = str(measures_file)
        elif backend == "NGSPICE_WRDATA":
            source = str(vectors_file)
        elif backend == "MIXED":
            source = json.dumps({"measures": str(measures_file), "vectors": str(vectors_file)})
        else:
            source = ""
        return {
            "measurement_backend": backend,
            "pyspice_required": False,
            "measurement_source": source,
            "measurement_command": " ".join(cmd),
            "measurement_status": "SUCCESS" if backend != "UNAVAILABLE" and result.returncode == 0 else "UNAVAILABLE",
            "artifacts": {
                "stdout": str(stdout_file),
                "stderr": str(stderr_file),
                "measures": str(measures_file),
                "vectors": str(vectors_file),
                "vectors_csv": str(vectors_csv),
                "vector_metadata": str(vector_metadata),
            },
        }

    def _collect_native_artifacts_from_run(
        self,
        *,
        artifact_dir: Path,
        run_result: Dict[str, Any],
        testbench: TestBench,
        measures_file: Path,
        vectors_file: Path,
        vectors_csv: Path,
        vector_metadata: Path,
        executed_deck_path: Path,
        generated_alias_path: Path,
        compiled_plan_sha256: str,
        serialized_deck_sha256: str,
        executed_file_sha256: Optional[str],
    ) -> Dict[str, Any]:
        stdout_file = artifact_dir / "ngspice_stdout.txt"
        stderr_file = artifact_dir / "ngspice_stderr.txt"
        stdout_text = "\n".join(run_result.get("logs", [])) if run_result.get("logs") else ""
        stderr_text = "\n".join(run_result.get("errors", [])) if run_result.get("errors") else ""
        stdout_file.write_text(stdout_text, encoding="utf-8")
        stderr_file.write_text(stderr_text, encoding="utf-8")
        if stdout_text:
            measures_file.write_text(stdout_text, encoding="utf-8")
        if vectors_file.exists():
            self._wrdata_to_csv(vectors_file, vectors_csv)
        vector_metadata.write_text(json.dumps({
            "vectors_file": str(vectors_file) if vectors_file.exists() else None,
            "vectors_csv": str(vectors_csv) if vectors_csv.exists() else None,
        }, indent=2), encoding="utf-8")
        measurement_config = (getattr(testbench, "metadata", None) or {}).get("measurement", {})
        measurement_requests = self._metric_requests(testbench)
        required_backend = measurement_config.get("required_backend")
        has_measures = measures_file.exists() and measures_file.read_text(encoding="utf-8", errors="ignore").strip()
        has_vectors = vectors_file.exists()
        preferred_backends = {
            request.get("preferred_backend")
            for request in measurement_requests
            if request.get("preferred_backend") in {"NGSPICE_MEASURE", "NGSPICE_WRDATA"}
        }
        backend = self._select_native_backend(
            required_backend=required_backend,
            has_measures=bool(has_measures),
            has_vectors=has_vectors,
            preferred_backends=preferred_backends,
        )
        if backend == "NGSPICE_MEASURE":
            source = str(measures_file)
        elif backend == "NGSPICE_WRDATA":
            source = str(vectors_file)
        elif backend == "MIXED":
            source = json.dumps({"measures": str(measures_file), "vectors": str(vectors_file)})
        else:
            source = ""
        post_execution_file_sha256 = self._sha256_file(executed_deck_path)
        generated_alias_sha256 = self._sha256_file(generated_alias_path)
        return {
            "measurement_backend": backend,
            "pyspice_required": False,
            "measurement_source": source,
            "measurement_command": " ".join(run_result.get("command", [])),
            "measurement_status": "SUCCESS" if backend != "UNAVAILABLE" and run_result.get("returncode") == 0 else "UNAVAILABLE",
            "compiled_plan_sha256": compiled_plan_sha256,
            "serialized_deck_sha256": serialized_deck_sha256,
            "executed_file_sha256": executed_file_sha256,
            "post_execution_file_sha256": post_execution_file_sha256,
            "post_serialization_deck_mutation": bool(executed_file_sha256 and post_execution_file_sha256 and executed_file_sha256 != post_execution_file_sha256),
            "artifacts": {
                "stdout": str(stdout_file),
                "stderr": str(stderr_file),
                "measures": str(measures_file),
                "vectors": str(vectors_file),
                "vectors_csv": str(vectors_csv),
                "vector_metadata": str(vector_metadata),
                "executed_deck": str(executed_deck_path),
                "generated_testbench": str(generated_alias_path),
                "generated_testbench_sha256": generated_alias_sha256,
            },
        }

    def _generate_measure_deck(self, netlist_path: Path, testbench: TestBench, measures_file: Path, vectors_file: Path) -> str:
        base_deck = self._generate_spice_deck(netlist_path, testbench)
        lines = base_deck.splitlines()
        if lines and lines[-1].strip().lower() == ".end":
            lines = lines[:-1]
        lines.extend(self._native_measure_commands(testbench))
        lines.extend(self._native_control_block(testbench, vectors_file))
        lines.append(".END")
        return "\n".join(lines) + "\n"

    def _native_measure_commands(self, testbench: TestBench) -> List[str]:
        commands: List[str] = []
        required_metrics = set(testbench.metadata.get("required_metrics", [])) if getattr(testbench, "metadata", None) else set()
        measurement_context = (getattr(testbench, "metadata", None) or {}).get("measurement_context", {})
        input_node = measurement_context.get("input_node", "vin")
        output_node = measurement_context.get("output_node", "vout")
        output_threshold = measurement_context.get("output_threshold", 2.5)
        for measurement in testbench.measurements:
            name = measurement.name
            if required_metrics and name not in required_metrics:
                continue
            if name in {"operating_point", "vout_dc"}:
                commands.append(f".meas dc operating_point FIND v({output_node}) AT=0")
                commands.append(f".meas dc vout_dc FIND v({output_node}) AT=0")
            elif name in {"quiescent_current", "idd"}:
                commands.append(".meas dc quiescent_current FIND i(vdd) AT=0")
                commands.append(".meas dc idd FIND i(vdd) AT=0")
            elif name == "power":
                commands.append(".meas dc power param='abs(v(vdd)*i(vdd))'")
            elif name in {"dc_gain", "dc_gain_db"}:
                commands.append(f".meas ac vin_mag FIND vm({input_node}) AT=1")
                commands.append(f".meas ac vout_mag FIND vm({output_node}) AT=1")
                commands.append(".meas ac dc_gain_db param='20*log10(vout_mag/vin_mag)'")
            elif name == "startup_amplitude":
                commands.append(f".meas tran vmax MAX v({output_node})")
                commands.append(f".meas tran vmin MIN v({output_node})")
                commands.append(".meas tran startup_amplitude param='(vmax-vmin)/2'")
            elif name in {"propagation_delay", "propagation_delay_s"}:
                commands.append(
                    f".meas tran propagation_delay_s TRIG v({input_node}) VAL={output_threshold} RISE=1 "
                    f"TARG v({output_node}) VAL={output_threshold} RISE=1"
                )
                commands.append(
                    f".meas tran propagation_delay TRIG v({input_node}) VAL={output_threshold} RISE=1 "
                    f"TARG v({output_node}) VAL={output_threshold} RISE=1"
                )
        return list(dict.fromkeys(commands))

    def _native_control_block(self, testbench: TestBench, vectors_file: Path) -> List[str]:
        analysis_types = {analysis.type for analysis in testbench.analyses}
        required_metrics = set(testbench.metadata.get("required_metrics", [])) if getattr(testbench, "metadata", None) else set()
        measurement_context = (getattr(testbench, "metadata", None) or {}).get("measurement_context", {})
        measurement_requests = self._metric_requests(testbench)
        input_node = measurement_context.get("input_node", "vin")
        output_node = measurement_context.get("output_node", "vout")
        if AnalysisType.AC in analysis_types:
            return [
                ".control",
                "set filetype=ascii",
                "set wr_singlescale",
                "run",
                "setplot ac1",
                f'wrdata {vectors_file.name} real(v({input_node})) imag(v({input_node})) '
                f'real(v({output_node})) imag(v({output_node}))',
                "quit",
                ".endc",
            ]
        if AnalysisType.TRANSIENT in analysis_types:
            needs_input = any(
                request.get("name") in {
                    "propagation_delay",
                    "propagation_delay_s",
                    "v_t_plus",
                    "v_t_minus",
                    "hysteresis_width",
                    "switching_threshold_rising_v",
                    "switching_threshold_falling_v",
                    "hysteresis_width_v",
                }
                for request in measurement_requests
            ) or any(
                name in required_metrics
                for name in {
                    "propagation_delay",
                    "propagation_delay_s",
                    "v_t_plus",
                    "v_t_minus",
                    "hysteresis_width",
                    "switching_threshold_rising_v",
                    "switching_threshold_falling_v",
                    "hysteresis_width_v",
                }
            )
            vector_args = f"v({input_node}) v({output_node})" if needs_input else f"v({output_node})"
            return [
                ".control",
                "set filetype=ascii",
                "set wr_singlescale",
                "run",
                "setplot tran1",
                f'wrdata {vectors_file.name} {vector_args}',
                "quit",
                ".endc",
            ]
        if AnalysisType.DC in analysis_types:
            return [
                ".control",
                "set filetype=ascii",
                "set wr_singlescale",
                "run",
                f'wrdata {vectors_file.name} v({output_node}) i(vdd)',
                "quit",
                ".endc",
            ]
        return []

    @staticmethod
    def _select_native_backend(
        *,
        required_backend: Optional[str],
        has_measures: bool,
        has_vectors: bool,
        preferred_backends: set[str],
    ) -> str:
        if required_backend == "NGSPICE_WRDATA":
            return "NGSPICE_WRDATA" if has_vectors else "UNAVAILABLE"
        if required_backend == "NGSPICE_MEASURE":
            return "NGSPICE_MEASURE" if has_measures else "UNAVAILABLE"
        if preferred_backends == {"NGSPICE_WRDATA"}:
            return "NGSPICE_WRDATA" if has_vectors else "UNAVAILABLE"
        if preferred_backends == {"NGSPICE_MEASURE"}:
            return "NGSPICE_MEASURE" if has_measures else "UNAVAILABLE"
        if has_measures and has_vectors and len(preferred_backends) > 1:
            return "MIXED"
        if has_measures:
            return "NGSPICE_MEASURE"
        if has_vectors:
            return "NGSPICE_WRDATA"
        return "UNAVAILABLE"

    @staticmethod
    def _wrdata_to_csv(vectors_file: Path, csv_file: Path) -> None:
        rows = [line.split() for line in vectors_file.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)

    def _metric_requests(self, testbench: TestBench) -> List[Dict[str, Any]]:
        metadata = getattr(testbench, "metadata", None) or {}
        if metadata.get("measurement_requests"):
            return [dict(item) for item in metadata["measurement_requests"]]
        measurement_context = self._infer_measurement_context(testbench)
        output_threshold = measurement_context.get("output_threshold", 2.5)
        input_ac_magnitude = measurement_context.get("input_ac_magnitude")
        reference_frequency_hz = measurement_context.get("reference_frequency_hz")
        supply_voltage = measurement_context.get("supply_voltage")
        requests = []
        for measurement in testbench.measurements:
            definition = get_metric_definition(measurement.name)
            request = {
                "name": measurement.name,
                "unit": measurement.unit,
                "expression": measurement.expression,
                "preferred_backend": definition.preferred_backend.value if definition else "AUTO",
                "metric_definition_version": definition.definition_version if definition else "unversioned",
                "quantity_type": definition.quantity_type.value if definition and definition.quantity_type else None,
                "measurement_expression_id": definition.measurement_expression_id if definition else measurement.name.upper(),
                "semantic_guards": sorted(definition.required_semantic_guards.keys()) if definition else [],
                "output_threshold": output_threshold,
                "input_node": measurement_context.get("input_node", "vin"),
                "output_node": measurement.node or measurement_context.get("output_node", "vout"),
            }
            if measurement.name in {"operating_point", "vout_dc"}:
                request.setdefault("value_column", 1)
            elif measurement.name in {"quiescent_current", "idd"}:
                request.setdefault("current_column", 2)
                request["supply_voltage"] = supply_voltage
            elif measurement.name == "power":
                request.setdefault("current_column", 2)
                request["supply_voltage"] = supply_voltage
            elif measurement.name in {"dc_gain", "dc_gain_db", "absolute_output_dbv", "absolute_input_dbv", "transfer_magnitude_linear", "transfer_phase_deg", "cutoff_frequency_hz", "bandwidth", "unity_gain_frequency", "ugbw", "phase_margin", "lowpass_attenuation_db", "lowpass_monotonicity_percent", "highpass_attenuation_db", "highpass_monotonicity_percent", "bandpass_peak_separation_db", "bandstop_notch_depth_db"}:
                request.setdefault("in_real_column", 1)
                request.setdefault("in_imag_column", 2)
                request.setdefault("out_real_column", 3)
                request.setdefault("out_imag_column", 4)
                request["input_ac_magnitude"] = input_ac_magnitude
                request["reference_frequency_hz"] = reference_frequency_hz
            elif measurement.name in {"frequency_hz", "oscillator_frequency", "startup_amplitude", "fundamental_frequency", "thd", "thd_percent", "output_swing_v", "oscillation_period_cv", "oscillation_cycle_count"}:
                request.setdefault("time_column", 0)
                request.setdefault("value_column", 1)
            elif measurement.name in {"propagation_delay", "propagation_delay_s", "v_t_plus", "v_t_minus", "hysteresis_width"}:
                request.setdefault("time_column", 0)
                request.setdefault("vin_column", 1)
                request.setdefault("vout_column", 2)
            requests.append(request)
        if any(measurement.name == "hysteresis_width" for measurement in testbench.measurements):
            requests.extend([
                {
                    "name": "switching_threshold_rising_v",
                    "unit": "V",
                    "preferred_backend": "NGSPICE_WRDATA",
                    "metric_definition_version": "switching_threshold_rising_v1",
                    "quantity_type": None,
                    "measurement_expression_id": "TRAN_SWITCHING_THRESHOLD_RISING",
                    "semantic_guards": ["requires_input_and_output_waveforms"],
                    "output_threshold": output_threshold,
                    "time_column": 0,
                    "vin_column": 1,
                    "vout_column": 2,
                    "input_node": measurement_context.get("input_node", "vin"),
                    "output_node": measurement_context.get("output_node", "vout"),
                },
                {
                    "name": "switching_threshold_falling_v",
                    "unit": "V",
                    "preferred_backend": "NGSPICE_WRDATA",
                    "metric_definition_version": "switching_threshold_falling_v1",
                    "quantity_type": None,
                    "measurement_expression_id": "TRAN_SWITCHING_THRESHOLD_FALLING",
                    "semantic_guards": ["requires_input_and_output_waveforms"],
                    "output_threshold": output_threshold,
                    "time_column": 0,
                    "vin_column": 1,
                    "vout_column": 2,
                    "input_node": measurement_context.get("input_node", "vin"),
                    "output_node": measurement_context.get("output_node", "vout"),
                },
                {
                    "name": "hysteresis_width_v",
                    "unit": "V",
                    "preferred_backend": "NGSPICE_WRDATA",
                    "metric_definition_version": "hysteresis_width_v1",
                    "quantity_type": None,
                    "measurement_expression_id": "TRAN_HYSTERESIS_WIDTH",
                    "semantic_guards": ["requires_input_and_output_waveforms"],
                    "output_threshold": output_threshold,
                    "time_column": 0,
                    "vin_column": 1,
                    "vout_column": 2,
                    "input_node": measurement_context.get("input_node", "vin"),
                    "output_node": measurement_context.get("output_node", "vout"),
                },
            ])
        return requests

    def _infer_measurement_context(self, testbench: TestBench) -> Dict[str, Any]:
        metadata = getattr(testbench, "metadata", None) or {}
        if metadata.get("measurement_context"):
            return dict(metadata["measurement_context"])

        input_node = "vin"
        output_node = "vout"
        for stimulus in testbench.stimuli:
            if stimulus.node_positive and stimulus.node_positive != "0":
                input_node = stimulus.node_positive
                break
        for measurement in testbench.measurements:
            if measurement.node:
                output_node = measurement.node
                break

        input_ac_magnitude = None
        for stimulus in testbench.stimuli:
            if stimulus.node_positive != input_node:
                continue
            if stimulus.type == "ac":
                input_ac_magnitude = self._parse_spice_numeric(stimulus.parameters.get("magnitude"))
            elif stimulus.parameters.get("ac_magnitude") is not None:
                input_ac_magnitude = self._parse_spice_numeric(stimulus.parameters.get("ac_magnitude"))
            if input_ac_magnitude is not None:
                break

        reference_frequency_hz = None
        for analysis in testbench.analyses:
            if analysis.type != AnalysisType.AC:
                continue
            reference_frequency_hz = self._parse_spice_numeric(
                analysis.parameters.get("start_freq", analysis.parameters.get("frequency_start_hz"))
            )
            if reference_frequency_hz is not None:
                break

        return {
            "input_node": input_node,
            "output_node": output_node,
            "output_threshold": 2.5,
            "input_ac_magnitude": input_ac_magnitude,
            "reference_frequency_hz": reference_frequency_hz,
            "supply_voltage": metadata.get("measurement_context", {}).get("supply_voltage"),
        }

    def _extract_metrics_with_backends(self, artifacts: SimulationArtifacts, metric_requests: List[Dict[str, Any]], raw_file: Path) -> Dict[str, MetricExtraction]:
        required_backend = getattr(self, "_active_required_backend", None)
        allow_backend_fallback = getattr(self, "_active_allow_backend_fallback", True)
        native_backends = {
            "NGSPICE_MEASURE": NgspiceMeasureBackend(),
            "NGSPICE_WRDATA": NgspiceWrdataBackend(),
        }
        if required_backend in native_backends and not allow_backend_fallback:
            return native_backends[required_backend].extract(artifacts, metric_requests)

        backends = list(native_backends.values())
        if self.disable_pyspice:
            backend_results_by_name = {
                backend.backend_name: backend.extract(artifacts, metric_requests)
                for backend in backends
            }
            merged = self._merge_backend_results(metric_requests, backend_results_by_name)
            return merged
        try:
            from PySpice.Spice.RawFile import RawFile
            backends.append(PySpiceResultBackend(lambda raw_path: {} if raw_path is None else self.extract_metrics(self._build_structured_results(self._extract_rawfile_plots(RawFile(str(raw_path)))), TestBench(name="raw", category="raw"))))
        except Exception:
            pass
        backend_results_by_name = {
            backend.backend_name: backend.extract(artifacts, metric_requests)
            for backend in backends
        }
        return self._merge_backend_results(metric_requests, backend_results_by_name)

    @staticmethod
    def _merge_backend_results(
        metric_requests: List[Dict[str, Any]],
        backend_results_by_name: Dict[str, Dict[str, MetricExtraction]],
    ) -> Dict[str, MetricExtraction]:
        merged: Dict[str, MetricExtraction] = {}
        for request in metric_requests:
            name = request["name"]
            preferred = request.get("preferred_backend")
            ordered_backend_names = [preferred] if preferred in backend_results_by_name else []
            ordered_backend_names.extend(
                backend_name
                for backend_name in backend_results_by_name
                if backend_name not in ordered_backend_names
            )
            for backend_name in ordered_backend_names:
                extraction = backend_results_by_name[backend_name].get(name)
                if extraction is None:
                    continue
                if name not in merged or (merged[name].value is None and extraction.value is not None):
                    merged[name] = extraction
                elif (
                    merged[name].value is None
                    and extraction.value is None
                    and (merged[name].error in {None, "NGSPICE_MEASURE_FAILED"} or merged[name].backend == "NGSPICE_MEASURE")
                    and extraction.error not in {None, "NGSPICE_MEASURE_FAILED"}
                ):
                    merged[name] = extraction
                if extraction.value is not None:
                    break
        return merged

    def _run_pvt_variants(
        self,
        spice_deck: str,
        testbench: TestBench,
        nominal_results: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        temperatures = self._normalize_temperature_points(parameters.get('temperatures', []))
        supply_variation = self._coerce_float(parameters.get('supply_variation'), default=0.0) or 0.0
        supply_scales = [1.0]
        if supply_variation > 0:
            supply_scales.extend([max(0.0, 1.0 - supply_variation), 1.0 + supply_variation])

        nominal_temperature = self._extract_nominal_temperature(spice_deck, testbench.temperature)
        base_variants: List[Tuple[str, Optional[float], float]] = []
        for temperature in temperatures:
            if temperature is None or self._nearly_equal(temperature, nominal_temperature):
                continue
            label = f"temp_{int(temperature) if float(temperature).is_integer() else temperature}c"
            base_variants.append((label, temperature, 1.0))
        for scale in supply_scales:
            if self._nearly_equal(scale, 1.0):
                continue
            direction = "minus" if scale < 1.0 else "plus"
            delta_pct = abs(scale - 1.0) * 100.0
            suffix = int(round(delta_pct)) if abs(delta_pct - round(delta_pct)) < 1e-9 else round(delta_pct, 3)
            label = f"vdd_{direction}_{suffix}pct"
            base_variants.append((label, None, scale))

        variant_rows = []
        if not base_variants:
            return {"variants": [], "summary": {}}

        variant_testbench = copy.deepcopy(testbench)
        variant_testbench.analyses = [analysis for analysis in variant_testbench.analyses if analysis.type != AnalysisType.PVT]
        variant_testbench.analyses = self._select_pvt_variant_analyses(variant_testbench)

        nominal_metrics = self.extract_metrics(nominal_results, variant_testbench)
        for label, temperature, supply_scale in base_variants:
            variant_deck, modified_supplies = self._apply_pvt_variant_to_deck(spice_deck, temperature, supply_scale)
            variant_result = self._run_spice_deck_text(
                variant_deck,
                variant_testbench,
                timeout_override=min(self.timeout, 20),
            )
            variant_metrics = self.extract_metrics(variant_result, variant_testbench) if variant_result.get('success') else {}
            variant_rows.append({
                "label": label,
                "temperature_c": temperature,
                "supply_scale": supply_scale,
                "modified_supplies": modified_supplies,
                "success": bool(variant_result.get("success")),
                "errors": variant_result.get("errors", []),
                "metrics": variant_metrics,
            })

        return {
            "variants": variant_rows,
            "summary": self._summarize_pvt_variants(nominal_metrics, variant_rows),
        }

    def _select_pvt_variant_analyses(self, testbench: TestBench) -> List[Any]:
        measurements = {measurement.name.lower() for measurement in testbench.measurements}
        required_types = set()

        if any(name in measurements for name in ("pvt_vout_variation", "pvt_power_variation", "pvt_dc_gain_variation")):
            required_types.add(AnalysisType.DC)
        if "pvt_dc_gain_variation" in measurements:
            required_types.add(AnalysisType.AC)
        if any(name in measurements for name in ("pvt_delay_variation", "pvt_frequency_variation")):
            required_types.add(AnalysisType.TRANSIENT)
        if "pvt_thd_variation" in measurements:
            required_types.update({AnalysisType.TRANSIENT, AnalysisType.FOURIER})

        if not required_types:
            return testbench.analyses

        filtered = [analysis for analysis in testbench.analyses if analysis.type in required_types]
        return filtered or testbench.analyses

    def _run_spice_deck_text(
        self,
        spice_deck: str,
        testbench: TestBench,
        timeout_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, encoding='utf-8') as handle:
            handle.write(spice_deck)
            spice_file = Path(handle.name)

        raw_file = spice_file.with_suffix('.raw')
        try:
            run_result = self._run_ngspice(spice_file, raw_file, timeout_override=timeout_override)
            parsed_results = self._parse_results(raw_file, testbench)
            parsed_results['logs'] = run_result['logs']
            parsed_results['errors'] = run_result['errors']
            parsed_results['success'] = run_result['success']
            return parsed_results
        finally:
            try:
                spice_file.unlink(missing_ok=True)
                raw_file.unlink(missing_ok=True)
            except Exception:
                pass

    def _summarize_pvt_variants(self, nominal_metrics: Dict[str, float], variant_rows: List[Dict[str, Any]]) -> Dict[str, float]:
        summary: Dict[str, float] = {"pvt_variants_run": float(len(variant_rows))}
        tracked = {
            "pvt_vout_variation": [self._safe_metric_float(nominal_metrics.get("vout_dc")), self._safe_metric_float(nominal_metrics.get("operating_point"))],
            "pvt_power_variation": [self._safe_metric_float(nominal_metrics.get("power"))],
            "pvt_dc_gain_variation": [self._safe_metric_float(nominal_metrics.get("dc_gain_db"))],
            "pvt_frequency_variation": [self._safe_metric_float(nominal_metrics.get("frequency_hz")), self._safe_metric_float(nominal_metrics.get("oscillator_frequency")), self._safe_metric_float(nominal_metrics.get("fundamental_frequency"))],
            "pvt_delay_variation": [self._safe_metric_float(nominal_metrics.get("propagation_delay")), self._safe_metric_float(nominal_metrics.get("propagation_delay_s"))],
            "pvt_thd_variation": [self._safe_metric_float(nominal_metrics.get("thd_percent")), self._safe_metric_float(nominal_metrics.get("thd"))],
        }
        metric_map = {
            "pvt_vout_variation": ("vout_dc", "operating_point"),
            "pvt_power_variation": ("power",),
            "pvt_dc_gain_variation": ("dc_gain_db",),
            "pvt_frequency_variation": ("frequency_hz", "oscillator_frequency", "fundamental_frequency"),
            "pvt_delay_variation": ("propagation_delay", "propagation_delay_s"),
            "pvt_thd_variation": ("thd_percent", "thd"),
        }

        for row in variant_rows:
            variant_metrics = row.get("metrics", {})
            for summary_key, metric_names in metric_map.items():
                for metric_name in metric_names:
                    value = self._safe_metric_float(variant_metrics.get(metric_name))
                    if value is not None:
                        tracked[summary_key].append(value)
                        break

        for summary_key, values in tracked.items():
            numeric_values = [value for value in values if value is not None]
            if len(numeric_values) >= 2:
                summary[summary_key] = float(max(numeric_values) - min(numeric_values))
        return summary

    def _apply_pvt_variant_to_deck(self, spice_deck: str, temperature: Optional[float], supply_scale: float) -> Tuple[str, int]:
        updated = re.sub(r"^\s*\.temp\b.*$", "", spice_deck, flags=re.IGNORECASE | re.MULTILINE)
        sources = self._supply_sources_from_deck(updated)

        for source_name, positive_node, negative_node, nominal, has_dc_keyword in sources:
            scaled = nominal * supply_scale
            keyword_pattern = r"(?:DC\s+)?" if has_dc_keyword else r"(?:DC\s+)?"
            pattern = re.compile(
                rf"^({re.escape(source_name)}\s+{re.escape(positive_node)}\s+{re.escape(negative_node)}\s+{keyword_pattern})([^\s]+)",
                re.IGNORECASE | re.MULTILINE,
            )
            updated = pattern.sub(rf"\g<1>{scaled}", updated, count=1)

        if temperature is not None:
            updated = updated.rstrip() + f"\n.TEMP {temperature}\n"

        return updated, len(sources)

    def _supply_sources_from_deck(self, spice_deck: str) -> List[Tuple[str, str, str, float, bool]]:
        pattern = re.compile(
            r"^(V[\w$]+)\s+(\S+)\s+(\S+)\s+(DC\s+)?([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
            re.IGNORECASE | re.MULTILINE,
        )
        sources: List[Tuple[str, str, str, float, bool]] = []
        for match in pattern.finditer(spice_deck):
            source_name, positive_node, negative_node, dc_keyword, value = match.groups()
            lowered = f"{source_name} {positive_node}".lower()
            if any(token in lowered for token in ("vdd", "vcc", "supply")) and negative_node == "0":
                try:
                    sources.append((source_name, positive_node, negative_node, float(value), bool(dc_keyword)))
                except ValueError:
                    continue
        return sources

    def _extract_nominal_temperature(self, spice_deck: str, default_temperature: float) -> float:
        match = re.search(r"^\s*\.temp\s+([^\s]+)", spice_deck, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return float(default_temperature)
        return self._coerce_float(match.group(1), default=float(default_temperature)) or float(default_temperature)

    @staticmethod
    def _normalize_temperature_points(raw_temperatures: Any) -> List[Optional[float]]:
        if not isinstance(raw_temperatures, list):
            return []
        normalized: List[Optional[float]] = []
        for value in raw_temperatures:
            try:
                normalized.append(float(value))
            except Exception:
                continue
        return normalized

    @staticmethod
    def _safe_metric_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            numeric = float(value)
            if np.isnan(numeric) or np.isinf(numeric):
                return None
            return numeric
        except Exception:
            return None

    @staticmethod
    def _coerce_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _nearly_equal(left: float, right: float, tolerance: float = 1e-12) -> bool:
        return abs(float(left) - float(right)) <= tolerance * max(abs(float(left)), abs(float(right)), 1.0)

    def _extract_schmitt_metrics(self, transient: Dict[str, Any]) -> Dict[str, float]:
        time = transient.get('time', [])
        vin = transient.get('vin', [])
        vout = transient.get('vout', [])
        if len(time) < 2 or len(vin) < 2 or len(vout) < 2:
            return {}

        sample_count = min(len(time), len(vin), len(vout))
        time = time[:sample_count]
        vin = vin[:sample_count]
        vout = vout[:sample_count]
        vout_threshold = (max(vout) + min(vout)) / 2.0
        input_slopes = [vin[index] - vin[index - 1] for index in range(1, sample_count)]

        metrics: Dict[str, float] = {}
        crossings: List[Tuple[str, int]] = []
        for index in range(1, sample_count):
            previous = vout[index - 1]
            current = vout[index]
            if previous < vout_threshold <= current:
                crossings.append(("rising", index))
            elif previous > vout_threshold >= current:
                crossings.append(("falling", index))

        for direction, index in crossings:
            vin_value = float(vin[index])
            if direction == "rising" and "v_t_plus" not in metrics:
                metrics["v_t_plus"] = vin_value
            if direction == "falling" and "v_t_minus" not in metrics:
                metrics["v_t_minus"] = vin_value

            output_time = float(time[index])
            expected_sign = 1 if direction == "rising" else -1
            input_index = None
            for candidate in range(index, 0, -1):
                slope = input_slopes[candidate - 1]
                if expected_sign * slope > 0:
                    input_index = candidate
                    break
            if input_index is not None and "propagation_delay" not in metrics:
                metrics["propagation_delay"] = output_time - float(time[input_index])
                metrics["propagation_delay_s"] = metrics["propagation_delay"]

        if "v_t_plus" in metrics and "v_t_minus" in metrics:
            metrics["hysteresis_width"] = abs(metrics["v_t_plus"] - metrics["v_t_minus"])

        return metrics

    def _estimate_transient_frequency(self, transient: Dict[str, Any]) -> Optional[float]:
        time = transient.get('time', [])
        vout = transient.get('vout', [])
        if len(time) < 3 or len(vout) < 3:
            return None

        mean_value = float(np.mean(vout))
        crossings: List[float] = []
        for index in range(1, len(vout)):
            if vout[index - 1] <= mean_value < vout[index]:
                crossings.append(float(time[index]))
        if len(crossings) < 2:
            return None

        periods = [crossings[index] - crossings[index - 1] for index in range(1, len(crossings))]
        valid_periods = [period for period in periods if period > 0]
        if not valid_periods:
            return None
        average_period = float(np.mean(valid_periods))
        if average_period <= 0:
            return None
        return 1.0 / average_period

    def _estimate_startup_amplitude(self, transient: Dict[str, Any]) -> Optional[float]:
        vout = transient.get('vout', [])
        if len(vout) < 5:
            return None
        tail_start = max(0, int(len(vout) * 0.8))
        steady_state = vout[tail_start:]
        if not steady_state:
            return None
        return float((max(steady_state) - min(steady_state)) / 2.0)

    def _select_supply_current(self, currents: Dict[str, Any]) -> Optional[float]:
        priority_tokens = ('ivdd', 'vdd', 'ivdda', 'vdda', 'ivcc', 'vcc', 'supply')
        normalized = []
        for key, value in (currents or {}).items():
            if value is None:
                continue
            try:
                normalized.append((str(key).lower(), float(abs(value))))
            except Exception:
                continue

        for token in priority_tokens:
            for key, value in normalized:
                if key == token or token in key:
                    return value
        return None

    def _extract_rawfile_plots(self, raw: Any) -> Dict[str, Dict[str, np.ndarray]]:
        parsed_plots: Dict[str, Dict[str, np.ndarray]] = {}
        plots = getattr(raw, 'plots', None)
        if not plots:
            plots = [raw]

        for plot_index, plot in enumerate(plots):
            plot_name = getattr(plot, 'plot_name', f'plot_{plot_index}') or f'plot_{plot_index}'
            dataset: Dict[str, np.ndarray] = {}
            variables = getattr(plot, 'variables', [])
            for variable in variables:
                var_name = getattr(variable, 'name', None) or str(variable)
                try:
                    data = plot.get_variable(var_name)
                except Exception:
                    try:
                        data = raw.get_variable(var_name)
                    except Exception:
                        continue
                if data is not None:
                    dataset[var_name] = np.array(data)
            if dataset:
                parsed_plots[plot_name.lower()] = dataset
        return parsed_plots

    def _parse_raw_fallback(self, raw_file: Path) -> Dict[str, Dict[str, np.ndarray]]:
        try:
            text = raw_file.read_text(errors='ignore')
        except Exception:
            return {}

        if not text.lstrip().startswith('Title:'):
            return {}

        lines = text.splitlines()
        plot_starts = [index for index, line in enumerate(lines) if line.startswith('Plotname:')]
        if not plot_starts:
            return {}
        plot_starts.append(len(lines))

        plots: Dict[str, Dict[str, np.ndarray]] = {}
        for block_index in range(len(plot_starts) - 1):
            section = lines[plot_starts[block_index]:plot_starts[block_index + 1]]
            plot_name = section[0].split(':', 1)[1].strip().lower()
            variables: List[str] = []
            values_index = None
            point_count = None

            for index, line in enumerate(section):
                lower = line.lower().strip()
                if lower.startswith('no. points'):
                    point_count = int(line.split(':', 1)[1].strip())
                elif lower == 'variables:':
                    cursor = index + 1
                    while cursor < len(section):
                        current = section[cursor].strip()
                        if current.lower() == 'values:':
                            break
                        tokens = current.split()
                        if len(tokens) >= 2 and tokens[0].isdigit():
                            variables.append(tokens[1])
                        cursor += 1
                elif lower == 'values:':
                    values_index = index + 1
                    break

            if not variables or values_index is None:
                continue

            parsed_columns = {name: [] for name in variables}
            cursor = values_index
            points_read = 0
            while cursor < len(section) and (point_count is None or points_read < point_count):
                line = section[cursor]
                match = re.match(r'^\s*(\d+)\s+(.+?)\s*$', line)
                if not match:
                    cursor += 1
                    continue

                parsed_columns[variables[0]].append(self._parse_raw_value(match.group(2), variables[0]))
                cursor += 1
                for variable_index in range(1, len(variables)):
                    if cursor >= len(section):
                        break
                    parsed_columns[variables[variable_index]].append(
                        self._parse_raw_value(section[cursor].strip(), variables[variable_index])
                    )
                    cursor += 1
                points_read += 1

            plots[plot_name] = {name: np.array(values) for name, values in parsed_columns.items()}

        return plots

    def _parse_raw_value(self, raw_value: str, variable_name: str) -> complex | float:
        raw_value = raw_value.strip()
        if ',' in raw_value:
            try:
                real_str, imag_str = raw_value.split(',', 1)
                real = float(real_str)
                imag = float(imag_str)
                return real if variable_name.lower() == 'frequency' else complex(real, imag)
            except Exception:
                return float('nan')
        try:
            return float(raw_value)
        except Exception:
            return float('nan')

    def _build_structured_results(self, plots: Dict[str, Dict[str, np.ndarray]]) -> Dict[str, Any]:
        results = {
            'ac': {},
            'tran': {},
            'transient': {},
            'dc': {},
            'currents': {},
            'fourier': {},
        }
        if not plots:
            return results

        ac_plot = next((dataset for name, dataset in plots.items() if 'ac analysis' in name), None)
        tran_plot = next((dataset for name, dataset in plots.items() if 'transient analysis' in name), None)
        dc_plot = next((dataset for name, dataset in plots.items() if 'operating point' in name or 'dc transfer' in name), None)

        if ac_plot is None and any('frequency' in key.lower() for dataset in plots.values() for key in dataset):
            ac_plot = next(dataset for dataset in plots.values() if any('frequency' in key.lower() for key in dataset))
        if tran_plot is None and any('time' in key.lower() for dataset in plots.values() for key in dataset):
            tran_plot = next(dataset for dataset in plots.values() if any('time' in key.lower() for key in dataset))
        if dc_plot is None:
            dc_plot = next((dataset for dataset in plots.values() if dataset is not ac_plot and dataset is not tran_plot), None)

        if ac_plot is not None:
            results['ac'] = self._build_ac_results(ac_plot)
        if tran_plot is not None:
            transient = self._build_transient_results(tran_plot)
            results['tran'] = transient
            results['transient'] = transient
            results['fourier'] = self._estimate_fourier(transient)
        if dc_plot is not None:
            dc, currents = self._build_dc_results(dc_plot)
            results['dc'] = dc
            results['currents'].update(currents)
        return results

    def _build_ac_results(self, dataset: Dict[str, np.ndarray]) -> Dict[str, Any]:
        frequency_key = next((key for key in dataset if 'frequency' in key.lower()), None)
        if frequency_key is None:
            return {}

        frequency = np.real(np.atleast_1d(dataset[frequency_key])).astype(float)
        voltage_keys = [key for key in dataset if key.lower().startswith('v(')]
        out_key = self._choose_voltage_node(voltage_keys, preferred=('out', 'vout'))
        in_key = self._choose_voltage_node(voltage_keys, preferred=('in', 'vin', 'inp'))

        if out_key is None:
            return {'frequency': frequency.tolist()}

        vout = np.atleast_1d(dataset[out_key])
        vin = np.atleast_1d(dataset[in_key]) if in_key and in_key in dataset else None

        with np.errstate(divide='ignore', invalid='ignore'):
            transfer = vout / vin if vin is not None and np.any(np.abs(vin) > 0) else vout
        magnitude = np.abs(transfer).astype(float)
        phase = np.degrees(np.angle(transfer)).astype(float)

        ac = {
            'frequency': frequency.tolist(),
            'magnitude': magnitude.tolist(),
            'phase': phase.tolist(),
        }
        if magnitude.size:
            ac['dc_gain_db'] = float(20 * np.log10(max(magnitude[0], 1e-30)))
            bandpass_metrics = self._find_bandpass_characteristics(frequency, magnitude)
            if bandpass_metrics is not None:
                ac.update(bandpass_metrics)
                ac['peak_gain_db'] = float(20 * np.log10(max(np.max(magnitude), 1e-30)))
            else:
                ac['bandwidth'] = self._find_minus_3db_bandwidth(frequency, magnitude)
            ac['unity_gain_frequency'] = self._find_unity_gain_frequency(frequency, magnitude)
        if phase.size and ac.get('unity_gain_frequency') is not None:
            phase_at_ugf = self._sample_at_frequency(frequency, phase, ac['unity_gain_frequency'])
            if phase_at_ugf is not None:
                ac['phase_margin'] = float(max(0.0, min(180.0, 180.0 + phase_at_ugf)))
        return ac

    def _build_transient_results(self, dataset: Dict[str, np.ndarray]) -> Dict[str, Any]:
        time_key = next((key for key in dataset if 'time' in key.lower()), None)
        if time_key is None:
            return {}

        time = np.real(np.atleast_1d(dataset[time_key])).astype(float)
        voltage_keys = [key for key in dataset if key.lower().startswith('v(')]
        out_key = self._choose_voltage_node(voltage_keys, preferred=('out', 'vout'))
        in_key = self._choose_voltage_node(voltage_keys, preferred=('in', 'vin', 'inp'))

        voltage_map = {}
        for key in voltage_keys:
            clean = self._clean_node_name(key)
            voltage_map[clean] = np.real(np.atleast_1d(dataset[key])).astype(float).tolist()

        transient = {
            'time': time.tolist(),
            'voltage': voltage_map,
        }
        if out_key:
            transient['vout'] = np.real(np.atleast_1d(dataset[out_key])).astype(float).tolist()
        if in_key:
            transient['vin'] = np.real(np.atleast_1d(dataset[in_key])).astype(float).tolist()
        return transient

    def _build_dc_results(self, dataset: Dict[str, np.ndarray]) -> Tuple[Dict[str, Any], Dict[str, float]]:
        dc: Dict[str, Any] = {}
        currents: Dict[str, float] = {}
        voltage_keys = [key for key in dataset if key.lower().startswith('v(')]
        out_key = self._choose_voltage_node(voltage_keys, preferred=('out', 'vout', 'vref'))

        if out_key is not None:
            out_array = np.real(np.atleast_1d(dataset[out_key])).astype(float)
            value = out_array[0]
            dc['vout_dc'] = float(value)
            dc['operating_point'] = float(value)
            dc['vout'] = out_array.tolist() if out_array.size > 1 else float(value)
            dc['vout_values'] = out_array.tolist()

        voltage_map = {}
        for key in voltage_keys:
            clean = self._clean_node_name(key).lower()
            voltage_map[clean] = np.real(np.atleast_1d(dataset[key])).astype(float).tolist()
        if voltage_map:
            dc['voltage'] = voltage_map
            vin_key = next((key for key in voltage_map if key in {'vin', 'in'} or 'vin' in key), None)
            if vin_key:
                dc['vin'] = voltage_map[vin_key]

        # ngspice raw files often expose the DC sweep variable as a non-voltage
        # vector. Preserve it when Vin itself is not present.
        if not isinstance(dc.get('vin'), list):
            for key, values in dataset.items():
                if key == out_key or key.lower().startswith('i(') or key.lower().startswith('v('):
                    continue
                array = np.real(np.atleast_1d(values)).astype(float)
                if array.size > 1:
                    dc['sweep'] = array.tolist()
                    dc['vin'] = array.tolist()
                    break

        current_waveforms = {}
        for key, values in dataset.items():
            if key.lower().startswith('i('):
                clean = self._clean_node_name(key)
                array = np.real(np.atleast_1d(values)).astype(float)
                if array.size:
                    current_waveforms[clean] = array.tolist()
                    currents[clean] = float(np.mean(array))
                    if 'vdd' in clean.lower():
                        currents['vdd'] = float(np.mean(array))
        if current_waveforms:
            dc['current_waveforms'] = current_waveforms

        return dc, currents

    def _estimate_fourier(self, transient: Dict[str, Any]) -> Dict[str, Any]:
        time = np.array(transient.get('time', []), dtype=float)
        vout = np.array(transient.get('vout', []), dtype=float)
        if time.size < 8 or vout.size < 8:
            return {}

        dt = float(np.mean(np.diff(time)))
        if not np.isfinite(dt) or dt <= 0:
            return {}

        windowed = (vout - np.mean(vout)) * np.hanning(vout.size)
        spectrum = np.fft.rfft(windowed)
        frequencies = np.fft.rfftfreq(vout.size, dt)
        magnitudes = np.abs(spectrum)
        if magnitudes.size < 2:
            return {}

        magnitudes[0] = 0.0
        fundamental_index = int(np.argmax(magnitudes))
        if fundamental_index <= 0 or fundamental_index >= frequencies.size:
            return {}

        fundamental_frequency = float(frequencies[fundamental_index])
        fundamental_magnitude = float(magnitudes[fundamental_index])
        harmonics = [{'order': 1, 'frequency': fundamental_frequency, 'magnitude': fundamental_magnitude}]

        sum_squares = 0.0
        for harmonic_order in range(2, 6):
            target_frequency = harmonic_order * fundamental_frequency
            harmonic_index = int(np.argmin(np.abs(frequencies - target_frequency)))
            harmonic_magnitude = float(magnitudes[harmonic_index]) if harmonic_index < magnitudes.size else 0.0
            harmonics.append({
                'order': harmonic_order,
                'frequency': float(frequencies[harmonic_index]),
                'magnitude': harmonic_magnitude,
            })
            sum_squares += harmonic_magnitude ** 2

        thd = 100.0 * np.sqrt(sum_squares) / max(fundamental_magnitude, 1e-30)
        return {
            'fundamental_frequency': fundamental_frequency,
            'harmonics': harmonics,
            'thd': float(thd),
        }

    def _choose_voltage_node(self, voltage_keys: List[str], preferred: Tuple[str, ...]) -> Optional[str]:
        lowered = [(key, key.lower()) for key in voltage_keys]
        for token in preferred:
            for key, key_lower in lowered:
                if token in key_lower:
                    return key
        return voltage_keys[0] if voltage_keys else None

    def _clean_node_name(self, name: str) -> str:
        return name.replace('(', '').replace(')', '').replace('v', '', 1) if name.lower().startswith('v(') else name.replace('(', '').replace(')', '')

    def _find_minus_3db_bandwidth(self, frequency: np.ndarray, magnitude: np.ndarray) -> Optional[float]:
        if frequency.size == 0 or magnitude.size == 0:
            return None
        target = magnitude[0] / np.sqrt(2.0)
        for index, value in enumerate(magnitude):
            if value <= target:
                return float(frequency[index])
        return None

    def _find_bandpass_characteristics(self, frequency: np.ndarray, magnitude: np.ndarray) -> Optional[Dict[str, float]]:
        if frequency.size < 3 or magnitude.size < 3:
            return None

        peak_index = int(np.argmax(magnitude))
        if peak_index == 0 or peak_index == magnitude.size - 1:
            return None

        peak_magnitude = float(magnitude[peak_index])
        edge_floor = max(float(magnitude[0]), float(magnitude[-1]), 1e-30)
        if peak_magnitude < edge_floor * np.sqrt(2.0):
            return None

        target = peak_magnitude / np.sqrt(2.0)
        lower_cutoff = None
        for index in range(peak_index, -1, -1):
            if magnitude[index] <= target:
                lower_cutoff = float(frequency[index])
                break

        upper_cutoff = None
        for index in range(peak_index, magnitude.size):
            if magnitude[index] <= target:
                upper_cutoff = float(frequency[index])
                break

        if lower_cutoff is None or upper_cutoff is None or upper_cutoff <= lower_cutoff:
            return None

        return {
            'lower_cutoff_frequency': lower_cutoff,
            'upper_cutoff_frequency': upper_cutoff,
            'center_frequency': float(frequency[peak_index]),
            'bandwidth': upper_cutoff - lower_cutoff,
            'cutoff_frequency_hz': upper_cutoff - lower_cutoff,
        }

    def _find_unity_gain_frequency(self, frequency: np.ndarray, magnitude: np.ndarray) -> Optional[float]:
        if frequency.size == 0 or magnitude.size == 0:
            return None
        for index, value in enumerate(magnitude):
            if value <= 1.0:
                return float(frequency[index])
        return None

    def _sample_at_frequency(self, frequency: np.ndarray, values: np.ndarray, target_frequency: float) -> Optional[float]:
        if frequency.size == 0 or values.size == 0:
            return None
        index = int(np.argmin(np.abs(frequency - target_frequency)))
        if index >= values.size:
            return None
        return float(values[index])
    
    def get_waveform(self, 
                     results: Any,
                     node: str,
                     analysis_type: str = "tran") -> Dict[str, list]:
        """
        Get waveform data for a specific node.
        """
        if analysis_type == "tran" and hasattr(results, 'tran'):
            tran = results.tran
            if node in tran:
                return {
                    'time': tran['time'].tolist() if hasattr(tran['time'], 'tolist') else list(tran['time']),
                    'voltage': tran[node].tolist() if hasattr(tran[node], 'tolist') else list(tran[node])
                }
        
        return {'time': [], 'voltage': []}
    
    def check_convergence(self, logs: str) -> bool:
        """
        Check if simulation converged.
        """
        logs_lower = logs.lower()
        
        failure_indicators = [
            'no convergence',
            'timestep too small',
            'singular matrix',
            'failed',
            'error'
        ]
        
        for indicator in failure_indicators:
            if indicator in logs_lower:
                return False
        
        return True
    
    def get_simulator_info(self) -> Dict[str, str]:
        """
        Get simulator information.
        """
        return {
            'name': 'PySpice with Ngspice',
            'version': self._get_ngspice_version(),
            'backend': 'ngspice',
            'status': 'available' if self._ngspice_available else 'unavailable',
            'path': self.ngspice_path
        }
    
    def _get_ngspice_version(self) -> str:
        """Get ngspice version."""
        if not self._ngspice_available:
            return "not installed"
        
        try:
            result = subprocess.run(
                [self.ngspice_path, "-v"],
                capture_output=True,
                text=True,
                timeout=2,
                shell=False
            )
            output = result.stdout or result.stderr
            for line in output.splitlines():
                if "ngspice" in line.lower():
                    return line.strip("* ")
            return output.splitlines()[0] if output else "available"
        except Exception:
            return "available"
    
    def supports_pvt_analysis(self) -> bool:
        """Check if PVT analysis is supported."""
        return True
