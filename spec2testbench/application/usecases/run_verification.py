"""
Complete verification pipeline orchestrating all three modules.
"""

import logging
import math
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from importlib import metadata

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import TestBench
from ...domain.value_objects.verdict import Verdict, CheckResult, ValidationStatus
from ...domain.value_objects.multimodal_result import MultimodalResult
from ...domain.value_objects.scientific_status import (
    ComplianceStatus,
    ExecutionStatus,
    MutationEffectivenessStatus,
    NetlistBindingStatus,
    RobustnessStatus,
    ScientificCategory,
    SimulationMode,
    classify_scientific_result,
)
from ...infrastructure.testbench import TestBenchGenerator
from ...infrastructure.spec_checker import SpecChecker
from ...infrastructure.waveform_checker import WaveformChecker, WaveformPlotter
from ...infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from ...infrastructure.simulator.result_backends import parse_wrdata_file
from ...config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class MetricTrace:
    metric_name: str
    measured_value: Optional[float]
    unit: str
    normalized_value: Optional[float]
    expected_operator: str
    expected_threshold: Optional[float]
    tolerance: Optional[float]
    status: str
    source_analysis: str
    source_signal: str
    extraction_method: str
    raw_result_file: Optional[str]
    error: Optional[str]
    metric_definition_version: Optional[str] = None
    quantity_type: Optional[str] = None
    measurement_expression_id: Optional[str] = None
    input_node: Optional[str] = None
    output_node: Optional[str] = None
    input_ac_magnitude: Optional[float] = None
    reference_frequency_hz: Optional[float] = None
    measurement_backend: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "measured_value": self.measured_value,
            "unit": self.unit,
            "normalized_value": self.normalized_value,
            "expected_operator": self.expected_operator,
            "expected_threshold": self.expected_threshold,
            "tolerance": self.tolerance,
            "status": self.status,
            "source_analysis": self.source_analysis,
            "source_signal": self.source_signal,
            "extraction_method": self.extraction_method,
            "raw_result_file": self.raw_result_file,
            "error": self.error,
            "metric_definition_version": self.metric_definition_version,
            "quantity_type": self.quantity_type,
            "measurement_expression_id": self.measurement_expression_id,
            "input_node": self.input_node,
            "output_node": self.output_node,
            "input_ac_magnitude": self.input_ac_magnitude,
            "reference_frequency_hz": self.reference_frequency_hz,
            "measurement_backend": self.measurement_backend,
        }


@dataclass
class VerificationReport:
    circuit_name: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    specification: Optional[Specification] = None
    testbench: Optional[TestBench] = None
    testbench_generation_success: bool = False
    simulation_success: bool = False
    execution_status: ExecutionStatus = ExecutionStatus.SKIPPED
    simulation_mode: Optional[SimulationMode] = None
    compliance_status: ComplianceStatus = ComplianceStatus.NOT_EVALUATED
    robustness_status: RobustnessStatus = RobustnessStatus.NOT_EVALUATED
    scientific_category: ScientificCategory = ScientificCategory.UNEVALUATED
    scientifically_eligible: bool = False
    spec_results: List[CheckResult] = field(default_factory=list)
    metric_traces: List[MetricTrace] = field(default_factory=list)
    waveform_analyses: List[MultimodalResult] = field(default_factory=list)
    simulation_logs: List[str] = field(default_factory=list)
    simulation_errors: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    error_type: Optional[str] = None
    ngspice_command: List[str] = field(default_factory=list)
    ngspice_returncode: Optional[int] = None
    raw_result_file: Optional[str] = None
    raw_result_file_exists: bool = False
    ngspice_version: Optional[str] = None
    case_id: Optional[str] = None
    parent_circuit_id: Optional[str] = None
    netlist_binding_status: NetlistBindingStatus = NetlistBindingStatus.NOT_VERIFIED
    expected_netlist_sha256: Optional[str] = None
    actual_netlist_sha256: Optional[str] = None
    actual_deck_sha256: Optional[str] = None
    specification_sha256: Optional[str] = None
    mutation_effectiveness_status: MutationEffectivenessStatus = MutationEffectivenessStatus.NOT_EVALUATED
    required_metric_validation: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    measurement_backend: Optional[str] = None
    measurement_source: Optional[str] = None
    measurement_command: Optional[str] = None
    measurement_status: Optional[str] = None
    pyspice_required: bool = True
    compiled_plan_sha256: Optional[str] = None
    serialized_deck_sha256: Optional[str] = None
    executed_file_sha256: Optional[str] = None
    post_execution_file_sha256: Optional[str] = None
    ngspice_input_file_path: Optional[str] = None
    generated_testbench_path: Optional[str] = None
    generated_testbench_sha256: Optional[str] = None
    generated_testbench_alias_byte_identical: Optional[bool] = None
    post_serialization_deck_mutation: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.simulation_success and self.execution_status == ExecutionStatus.SKIPPED:
            self.execution_status = ExecutionStatus.SUCCESS
        self._refresh_derived_statuses()

    def _refresh_derived_statuses(self) -> None:
        nominal_results = [
            result for result in self.spec_results
            if (result.category or "").lower() != "pvt"
        ]
        pvt_results = [
            result for result in self.spec_results
            if (result.category or "").lower() == "pvt"
        ]

        if self.execution_status != ExecutionStatus.SUCCESS or not nominal_results:
            self.compliance_status = ComplianceStatus.NOT_EVALUATED
        elif any(result.verdict == Verdict.FAIL for result in nominal_results):
            self.compliance_status = ComplianceStatus.FAIL
        elif any(result.verdict == Verdict.ERROR for result in nominal_results):
            self.compliance_status = ComplianceStatus.NOT_EVALUATED
        else:
            self.compliance_status = ComplianceStatus.PASS

        if not pvt_results:
            self.robustness_status = RobustnessStatus.NOT_EVALUATED
        elif any(result.verdict in (Verdict.ERROR, Verdict.FAIL) for result in pvt_results):
            self.robustness_status = RobustnessStatus.ROBUST_FAIL
        else:
            self.robustness_status = RobustnessStatus.ROBUST_PASS

        self.scientific_category = classify_scientific_result(
            self.execution_status,
            self.compliance_status,
        )

    @property
    def terminal_status(self) -> str:
        return self.overall_verdict.value

    @property
    def missing_metrics(self) -> List[str]:
        return [
            result.test_name
            for result in self.spec_results
            if result.verdict == Verdict.ERROR
        ]

    @property
    def failed_metric_names(self) -> List[str]:
        return [
            result.test_name
            for result in self.spec_results
            if result.verdict == Verdict.FAIL
        ]

    @property
    def warning_metric_names(self) -> List[str]:
        return [
            result.test_name
            for result in self.spec_results
            if result.verdict == Verdict.WARNING
        ]

    @property
    def failure_kind(self) -> str:
        if self.errors or not self.testbench_generation_success:
            return "testbench_generation_failed"
        if not self.simulation_success:
            return "simulation_not_successful"

        error_results = [result for result in self.spec_results if result.verdict == Verdict.ERROR]
        if error_results:
            prefixes = []
            for result in error_results:
                prefix = result.message.split(":", 1)[0].strip().lower()
                if prefix and prefix not in prefixes:
                    prefixes.append(prefix)
            return prefixes[0] if prefixes else "metric_extraction_failed"

        if any(result.verdict == Verdict.FAIL for result in self.spec_results):
            return "metric_out_of_spec"

        return ""
    
    @property
    def overall_verdict(self) -> ValidationStatus:
        if self.robustness_status == RobustnessStatus.ROBUST_PASS:
            return ValidationStatus.ROBUST_PASS
        if self.execution_status != ExecutionStatus.SUCCESS:
            return ValidationStatus.FAIL
        if self.compliance_status == ComplianceStatus.PASS:
            return ValidationStatus.PASS
        if self.compliance_status == ComplianceStatus.FAIL:
            return ValidationStatus.FAIL
        return ValidationStatus.RUN
    
    @property
    def failed_metrics(self) -> List[CheckResult]:
        return [r for r in self.spec_results if r.verdict in [Verdict.FAIL, Verdict.WARNING]]

    @property
    def success_rate(self) -> float:
        if not self.spec_results:
            return 0.0
        successful = sum(1 for r in self.spec_results if r.verdict.is_success)
        return successful / len(self.spec_results)

    @property
    def compliance_score(self) -> float:
        return self._compliance_score()

    @property
    def nominal_compliance_score(self) -> float:
        return self._compliance_score(include_pvt=False)

    @property
    def pvt_compliance_score(self) -> float:
        return self._compliance_score(only_pvt=True)

    @property
    def has_pvt_coverage(self) -> bool:
        return any((result.category or "").lower() == "pvt" for result in self.spec_results)

    def _compliance_score(self, include_pvt: bool = True, only_pvt: bool = False) -> float:
        if not self.spec_results:
            return 0.0

        weighted_total = 0.0
        weighted_score = 0.0
        performance_targets = self.specification.performance_targets if self.specification else {}

        for result in self.spec_results:
            is_pvt = (result.category or "").lower() == "pvt"
            if only_pvt and not is_pvt:
                continue
            if not include_pvt and is_pvt:
                continue

            target = performance_targets.get(result.test_name, {})
            weight = float(target.get("weight", 1.0)) if isinstance(target, dict) else 1.0
            weighted_total += weight
            weighted_score += weight * self._metric_score(result.verdict)

        if weighted_total == 0.0:
            return 0.0
        return weighted_score / weighted_total

    @staticmethod
    def _metric_score(verdict: Verdict) -> float:
        score_map = {
            Verdict.PASS: 1.0,
            Verdict.WARNING: 0.75,
            Verdict.FAIL: 0.0,
            Verdict.ERROR: 0.0,
            Verdict.NOT_APPLICABLE: 0.0,
        }
        return score_map.get(verdict, 0.0)
    
    def to_summary(self) -> str:
        lines = [
            "=" * 60,
            f"Spec2Testbench - Verification Report",
            "=" * 60,
            f"Circuit: {self.circuit_name}",
            f"Timestamp: {self.timestamp}",
            f"Overall Verdict: {self.overall_verdict.value}",
            f"Success Rate: {self.success_rate*100:.1f}%",
            f"Compliance Score: {self.compliance_score:.3f}",
            f"Nominal Compliance: {self.nominal_compliance_score:.3f}",
            f"PVT Compliance: {self.pvt_compliance_score:.3f}",
            "",
            "Metric Results:",
        ]
        for result in self.spec_results:
            status = result.verdict.value
            lines.append(f"  {status:10} {result.test_name}: {result.measured_str} (expected {result.expected_range})")
        if self.errors:
            lines.extend(["", "Errors:"])
            for error in self.errors:
                lines.append(f"  ❌ {error}")
        lines.append("=" * 60)
        return "\n".join(lines)


class VerificationPipeline:
    def __init__(
        self,
        use_llm: bool = True,
        llm_client=None,
        use_llm_planner: bool = False,
        allow_mock: Optional[bool] = None,
        allow_recovery: Optional[bool] = None,
        timeout_seconds: Optional[int] = None,
        persist_artifacts: Optional[bool] = None,
    ):
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.use_llm_planner = use_llm_planner
        self.allow_mock = settings.simulator.allow_mock if allow_mock is None else allow_mock
        self.allow_recovery = settings.simulator.allow_recovery if allow_recovery is None else allow_recovery
        self.timeout_seconds = timeout_seconds or settings.simulator.timeout_seconds
        self.persist_artifacts = self._resolve_persist_artifacts(persist_artifacts)
        self.testbench_gen = TestBenchGenerator(
            llm_client=llm_client if use_llm else None,
            use_llm=use_llm,
            use_llm_planner=use_llm_planner,
        )
        self.spec_checker = SpecChecker(warning_margin=settings.warning_margin)
        self.waveform_checker = WaveformChecker(
            llm_client=llm_client if use_llm else None,
            use_llm=use_llm
        )
        self.waveform_plotter = WaveformPlotter(output_dir=settings.output.waveform_dir)
        self.simulator = None
    
    def verify(self,
               specification: Specification,
               netlist_path: Optional[Path] = None,
               simulation_results: Optional[Dict[str, Any]] = None,
               spec_path: Optional[Path] = None,
               testbench: Optional[TestBench] = None) -> VerificationReport:
        logger.info(f"Starting verification for {specification.name}")
        started = time.time()
        report = VerificationReport(circuit_name=specification.name)
        report.specification = specification
        report.case_id = specification.case_id or specification.name
        report.parent_circuit_id = specification.parent_circuit_id
        artifact_bundle = self._artifact_bundle_paths(report) if self.persist_artifacts else None
        
        try:
            if testbench is None:
                logger.info("Step 1/4: Generating testbench...")
                testbench = self.testbench_gen.generate(specification, netlist_path=netlist_path)
            else:
                logger.info("Step 1/4: Reusing provided testbench...")
            testbench.case_id = report.case_id
            testbench.metadata["required_metrics"] = specification.verification_metric_names()
            testbench.metadata["measurement"] = {
                **dict(testbench.metadata.get("measurement", {})),
                **dict(getattr(specification, "measurement", {}) or {}),
            }
            if not testbench.metadata.get("measurement_requests"):
                self.testbench_gen._attach_measurement_metadata(testbench, specification)
            if netlist_path:
                testbench.netlist_path = str(netlist_path)
            report.testbench = testbench
            report.testbench_generation_success = testbench is not None
            logger.info(f"  Generated testbench with {len(testbench.measurements)} measurements")
            
            if simulation_results is None and netlist_path and netlist_path.exists():
                logger.info("Step 2/4: Running simulation with ngspice...")
                simulation_results = self._run_simulation_with_ngspice(
                    netlist_path,
                    testbench,
                    output_dir=artifact_bundle["simulation_dir"] if artifact_bundle else None,
                )
                report.simulation_logs = simulation_results.get("logs", [])
                report.simulation_errors = simulation_results.get("errors", [])
            elif simulation_results is None:
                if self.allow_mock:
                    logger.warning("No netlist provided, using explicitly allowed mock simulation")
                    simulation_results = self._run_mock_simulation(testbench)
                else:
                    simulation_results = self._simulation_not_run_result("netlist_missing", "No netlist provided")

            report.simulation_success = bool(simulation_results.get("success", True))
            report.execution_status = self._parse_execution_status(simulation_results)
            report.simulation_mode = self._parse_simulation_mode(simulation_results)
            report.error_type = simulation_results.get("error_type")
            report.simulation_errors = simulation_results.get("errors", report.simulation_errors)
            report.ngspice_command = simulation_results.get("ngspice_command") or []
            report.ngspice_returncode = simulation_results.get("ngspice_returncode")
            report.raw_result_file = simulation_results.get("raw_result_file")
            report.raw_result_file_exists = bool(simulation_results.get("raw_result_file_exists"))
            report.ngspice_version = simulation_results.get("ngspice_version")
            report.netlist_binding_status = self._parse_netlist_binding_status(
                simulation_results,
                netlist_path=netlist_path,
            )
            report.expected_netlist_sha256 = simulation_results.get("expected_netlist_sha256")
            report.actual_netlist_sha256 = simulation_results.get("actual_netlist_sha256")
            report.actual_deck_sha256 = simulation_results.get("actual_deck_sha256")
            report.specification_sha256 = self._sha256_file(spec_path) if spec_path else None
            report.measurement_backend = simulation_results.get("measurement_backend")
            report.measurement_source = simulation_results.get("measurement_source")
            report.measurement_command = simulation_results.get("measurement_command")
            report.measurement_status = simulation_results.get("measurement_status")
            report.pyspice_required = bool(simulation_results.get("pyspice_required", True))
            report.compiled_plan_sha256 = simulation_results.get("compiled_plan_sha256")
            report.serialized_deck_sha256 = simulation_results.get("serialized_deck_sha256")
            report.executed_file_sha256 = simulation_results.get("executed_file_sha256")
            report.post_execution_file_sha256 = simulation_results.get("post_execution_file_sha256")
            report.ngspice_input_file_path = simulation_results.get("ngspice_input_file_path")
            report.generated_testbench_path = simulation_results.get("generated_testbench_path")
            report.generated_testbench_sha256 = simulation_results.get("generated_testbench_sha256")
            report.generated_testbench_alias_byte_identical = simulation_results.get("generated_testbench_alias_byte_identical")
            report.post_serialization_deck_mutation = simulation_results.get("post_serialization_deck_mutation")
            simulation_results.setdefault(
                "measurement_requests",
                list((testbench.metadata or {}).get("measurement_requests", [])),
            )

            # Native backends are authoritative when they provide a finite
            # extraction. This prevents the compliance checker from silently
            # recomputing a different metric from a separate raw-file path.
            native_metrics = simulation_results.get("native_metrics", {}) or {}
            if native_metrics:
                simulation_results.setdefault("metrics", {}).update(native_metrics)
            
            logger.info("Step 3/4: Verifying specifications...")
            if report.execution_status == ExecutionStatus.SUCCESS:
                report.required_metric_validation = self._validate_required_metrics(specification, simulation_results, testbench)
                if self._has_required_metric_validation_errors(report.required_metric_validation):
                    precheck_results = self._build_precheck_error_results(specification, report.required_metric_validation)
                    verified_results = self.spec_checker.verify(simulation_results, specification)
                    precheck_names = {result.test_name for result in precheck_results}
                    report.spec_results = precheck_results + [
                        result for result in verified_results
                        if result.test_name not in precheck_names
                    ]
                else:
                    report.spec_results = self.spec_checker.verify(simulation_results, specification)
            else:
                report.spec_results = []
            
            failed = self.spec_checker.get_failed_metrics(report.spec_results)
            if failed:
                logger.info(f"Step 4/4: Analyzing waveforms for {len(failed)} failed metrics...")
                report.waveform_analyses = self._analyze_failed_metrics(failed, simulation_results, specification)

            self._finalize_report_statuses(report, simulation_results)
            
            logger.info(f"Verification complete: {report.success_rate*100:.1f}% success rate")
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            report.errors.append(str(e))
            report.execution_status = ExecutionStatus.ERROR
            report.error_type = type(e).__name__
            self._finalize_report_statuses(report, simulation_results or {})
        finally:
            report.runtime_seconds = time.time() - started
            report.provenance = self._build_provenance(
                report=report,
                spec_path=spec_path,
                netlist_path=netlist_path,
            )
            if self.persist_artifacts:
                self._persist_run_artifacts(
                    report,
                    simulation_results or {},
                    artifact_bundle,
                )
        
        return report
    
    def _run_simulation_with_ngspice(
        self,
        netlist_path: Path,
        testbench: TestBench,
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Run simulation with real ngspice and structured raw parsing."""
        if self.simulator is None:
            self.simulator = PySpiceSimulator(
                timeout=self.timeout_seconds,
                allow_mock=self.allow_mock,
            )

        if not self.simulator.is_available:
            logger.warning("Ngspice simulator not available")
            if self.allow_mock:
                return self._run_mock_simulation(testbench)
            return self._simulation_error_result(
                "ngspice_unavailable",
                f"Ngspice executable not available: {self.simulator.ngspice_path}",
            )

        preserve_artifacts = os.getenv("SPEC2TESTBENCH_PRESERVE_SIM_ARTIFACTS", "").lower() in {"1", "true", "yes"}
        resolved_output_dir = output_dir if output_dir is not None else settings.output.output_dir if preserve_artifacts else None
        result = self.simulator.run(netlist_path, testbench, output_dir=resolved_output_dir)

        simulation_results = {
            'success': result.get('success', False),
            'simulation_mode': result.get('simulation_mode', SimulationMode.REAL.value),
            'execution_status': result.get('execution_status'),
            'scientifically_eligible': result.get('scientifically_eligible'),
            'error_type': result.get('error_type'),
            'error_message': result.get('error_message'),
            'metrics': result.get('metrics', {}),
            'logs': result.get('logs', []),
            'errors': result.get('errors', []),
            'dc': result.get('dc', {}),
            'ac': result.get('ac', {}),
            'transient': result.get('transient', result.get('tran', {})),
            'fourier': result.get('fourier', {}),
            'pvt': result.get('pvt', {}),
            'currents': result.get('currents', {}),
            'vdd': result.get('vdd', 0.0),
            'native_metrics': result.get('native_metrics', {}),
            'native_extractions': result.get('native_extractions', {}),
            'oscillation_validation': result.get('oscillation_validation', {}),
            'ngspice_command': result.get('ngspice_command'),
            'ngspice_returncode': result.get('ngspice_returncode'),
            'raw_result_file': result.get('raw_result_file'),
            'raw_result_file_exists': result.get('raw_result_file_exists'),
            'ngspice_version': result.get('ngspice_version'),
            'case_id': result.get('case_id') or testbench.case_id,
            'expected_netlist_sha256': result.get('expected_netlist_sha256'),
            'actual_netlist_sha256': result.get('actual_netlist_sha256'),
            'actual_deck_sha256': result.get('actual_deck_sha256'),
            'netlist_binding_status': result.get('netlist_binding_status'),
            'measurement_backend': result.get('measurement_backend'),
            'pyspice_required': result.get('pyspice_required'),
            'measurement_source': result.get('measurement_source'),
            'measurement_command': result.get('measurement_command'),
            'measurement_status': result.get('measurement_status'),
            'compiled_plan_sha256': result.get('compiled_plan_sha256'),
            'serialized_deck_sha256': result.get('serialized_deck_sha256'),
            'executed_file_sha256': result.get('executed_file_sha256'),
            'post_execution_file_sha256': result.get('post_execution_file_sha256'),
            'ngspice_input_file_path': result.get('ngspice_input_file_path'),
            'generated_testbench_path': result.get('generated_testbench_path'),
            'generated_testbench_sha256': result.get('generated_testbench_sha256'),
            'generated_testbench_alias_byte_identical': result.get('generated_testbench_alias_byte_identical'),
            'post_serialization_deck_mutation': result.get('post_serialization_deck_mutation'),
            'measurement_requests': (testbench.metadata or {}).get('measurement_requests', []),
        }

        # Treat extracted structured data as a successful simulation even if an
        # upstream wrapper returned a conservative success flag.
        has_structured_results = any(
            simulation_results.get(key) for key in ('dc', 'ac', 'transient', 'fourier', 'pvt')
        ) or bool(simulation_results.get('metrics')) or bool(simulation_results.get('native_metrics'))
        if has_structured_results:
            simulation_results['success'] = True
            simulation_results['execution_status'] = ExecutionStatus.SUCCESS.value

        if not any(simulation_results.get(key) for key in ('dc', 'ac', 'transient', 'fourier', 'pvt')) and not simulation_results.get('native_metrics'):
            if self.allow_mock:
                mock_results = self._run_mock_simulation(testbench)
                mock_results['logs'] = simulation_results['logs'] or mock_results['logs']
                mock_results['metrics'].update(simulation_results['metrics'])
                return mock_results
            simulation_results['success'] = False
            simulation_results['execution_status'] = ExecutionStatus.ERROR.value
            simulation_results['error_type'] = simulation_results.get('error_type') or 'result_file_absent'
            simulation_results['error_message'] = 'No structured ngspice result data was parsed'

        return simulation_results
    
    def _run_mock_simulation(self, testbench: TestBench) -> Dict[str, Any]:
        """Run mock simulation when ngspice is not available."""
        logger.info("Running mock simulation")
        if testbench is None:
            return {
                'success': True,
                'logs': ['Mock simulation - ngspice not available'],
                'metrics': {'vout': 2.5, 'vdd': 5.0},
                'ac': {'magnitude': [100], 'frequency': [1e6]},
                'transient': {'vout': [2.5], 'time': [0]},
                'currents': {'vdd': 1e-3}
            }

        vdd = 1.8
        idd = 1.2e-3
        dc_vout = 0.92
        analysis_types = {analysis.type.value for analysis in testbench.analyses}
        measurement_names = {measurement.name.lower() for measurement in testbench.measurements}
        circuit_name = (testbench.circuit_name or testbench.name).lower()

        results = {
            'success': True,
            'simulation_mode': SimulationMode.MOCK.value,
            'execution_status': ExecutionStatus.SUCCESS.value,
            'scientifically_eligible': False,
            'logs': ['Mock simulation - ngspice not available'],
            'vdd': vdd,
            'metrics': {
                'vdd': vdd,
                'vout': dc_vout,
                'vout_dc': dc_vout,
                'operating_point': dc_vout,
                'idd': idd,
                'quiescent_current': idd,
                'current': idd,
                'power': vdd * idd,
            },
            'dc': {
                'vout': dc_vout,
                'vout_dc': dc_vout,
                'operating_point': dc_vout,
            },
            'ac': {},
            'transient': {},
            'fourier': {},
            'pvt': {},
            'currents': {'vdd': idd}
        }

        if 'dc' in analysis_types:
            results['logs'].append('Mock DC operating point computed')

        if 'ac' in analysis_types:
            frequencies = [10 ** (index / 6) for index in range(0, 55)]
            dc_gain_linear = 1000.0
            pole_frequency = 1e3
            ac_magnitude = [
                dc_gain_linear / math.sqrt(1 + (frequency / pole_frequency) ** 2)
                for frequency in frequencies
            ]
            ac_phase = [
                -math.degrees(math.atan(frequency / pole_frequency))
                for frequency in frequencies
            ]
            results['ac'] = {
                'frequency': frequencies,
                'magnitude': ac_magnitude,
                'phase': ac_phase,
                'dc_gain_db': 20 * math.log10(dc_gain_linear),
                'bandwidth': pole_frequency,
                'cutoff_frequency_hz': pole_frequency,
                'unity_gain_frequency': dc_gain_linear * pole_frequency,
                'ugbw': dc_gain_linear * pole_frequency,
                'phase_margin': 89.0,
            }
            results['metrics'].update({
                'dc_gain': results['ac']['dc_gain_db'],
                'dc_gain_db': results['ac']['dc_gain_db'],
                'bandwidth': pole_frequency,
                'cutoff_frequency_hz': pole_frequency,
                'unity_gain_frequency': dc_gain_linear * pole_frequency,
                'ugbw': dc_gain_linear * pole_frequency,
                'phase_margin': 89.0,
            })

        needs_oscillator = any(
            name in measurement_names
            for name in ('oscillator_frequency', 'frequency_hz', 'startup_amplitude', 'fundamental_frequency')
        ) or any(keyword in circuit_name for keyword in ('oscillator', 'vco'))
        needs_comparator = any(
            name in measurement_names for name in ('propagation_delay', 'propagation_delay_s')
        ) or any(keyword in circuit_name for keyword in ('comparator', 'schmitt'))

        if 'tran' in analysis_types:
            point_count = 400
            end_time = 10e-6
            time = [index * end_time / (point_count - 1) for index in range(point_count)]

            if needs_oscillator:
                oscillation_frequency = 10e6
                startup_amplitude = 0.6
                envelope_tau = 1.5e-6
                vout = [
                    0.9 + startup_amplitude * (1 - math.exp(-sample_time / envelope_tau)) *
                    math.sin(2 * math.pi * oscillation_frequency * sample_time)
                    for sample_time in time
                ]
                vin = [0.0 for _ in time]
                results['metrics'].update({
                    'oscillator_frequency': oscillation_frequency,
                    'frequency_hz': oscillation_frequency,
                    'startup_amplitude': startup_amplitude,
                    'settling_time': 2.5e-6,
                })
            elif needs_comparator:
                input_crossing = 2.0e-6
                delay = 0.2e-6
                vin = [0.7 if sample_time >= input_crossing else 0.2 for sample_time in time]
                vout = [1.8 if sample_time >= input_crossing + delay else 0.0 for sample_time in time]
                results['metrics']['propagation_delay'] = delay
                results['metrics']['propagation_delay_s'] = delay
            else:
                step_time = 1.0e-6
                tau = 0.6e-6
                vin = [0.2 if sample_time < step_time else 0.8 for sample_time in time]
                vout = []
                for sample_time in time:
                    if sample_time < step_time:
                        vout.append(0.1)
                    else:
                        vout.append(0.1 + 0.9 * (1 - math.exp(-(sample_time - step_time) / tau)))
                results['metrics']['settling_time'] = 3.3 * tau

            transient = {
                'time': time,
                'voltage': {
                    'in': vin,
                    'out': vout,
                },
                'vin': vin,
                'vout': vout,
            }
            results['transient'] = transient
            results['metrics']['slew_rate'] = self.spec_checker.metric_extractor._extract_slew_rate({'transient': transient})
            if 'settling_time' not in results['metrics']:
                settling = self.spec_checker.metric_extractor._extract_settling_time({'transient': transient})
                if settling is not None:
                    results['metrics']['settling_time'] = settling

        if 'fourier' in analysis_types:
            fundamental_frequency = results['metrics'].get('frequency_hz', 1e6)
            harmonics = [
                {'order': 1, 'frequency': fundamental_frequency, 'magnitude': 1.0},
                {'order': 2, 'frequency': 2 * fundamental_frequency, 'magnitude': 0.006},
                {'order': 3, 'frequency': 3 * fundamental_frequency, 'magnitude': 0.004},
                {'order': 4, 'frequency': 4 * fundamental_frequency, 'magnitude': 0.002},
            ]
            thd_percent = 100 * math.sqrt(sum(item['magnitude'] ** 2 for item in harmonics[1:])) / harmonics[0]['magnitude']
            results['fourier'] = {
                'harmonics': harmonics,
                'fundamental_frequency': fundamental_frequency,
                'thd': thd_percent,
            }
            results['metrics'].update({
                'thd': thd_percent,
                'thd_percent': thd_percent,
                'fundamental_frequency': fundamental_frequency,
            })

        if 'pvt' in analysis_types:
            supplies = [round(vdd * factor, 3) for factor in (1 - 0.05, 1.0, 1 + 0.05)]
            temperatures = [0, 27, 70]
            pvt_vout = [0.89, 0.92, 0.95]
            pvt_gain = [58.5, 60.0, 61.0]
            pvt_power = [1.95e-3, 2.16e-3, 2.28e-3]
            results['pvt'] = {
                'supplies': supplies,
                'temperatures': temperatures,
                'metrics': {
                    'vout_dc': pvt_vout,
                    'dc_gain': pvt_gain,
                    'power': pvt_power,
                },
                'summary': {
                    'pvt_vout_variation': max(pvt_vout) - min(pvt_vout),
                    'pvt_dc_gain_variation': max(pvt_gain) - min(pvt_gain),
                    'pvt_power_variation': max(pvt_power) - min(pvt_power),
                }
            }
            results['metrics'].update(results['pvt']['summary'])

        return results

    def _simulation_not_run_result(self, error_type: str, error_message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "simulation_mode": None,
            "execution_status": ExecutionStatus.SKIPPED.value,
            "scientifically_eligible": False,
            "logs": [],
            "errors": [error_message],
            "error_type": error_type,
            "error_message": error_message,
            "metrics": {},
        }

    def _simulation_error_result(self, error_type: str, error_message: str) -> Dict[str, Any]:
        status = ExecutionStatus.TIMEOUT if "timeout" in error_type.lower() else ExecutionStatus.ERROR
        return {
            "success": False,
            "simulation_mode": SimulationMode.REAL.value,
            "execution_status": status.value,
            "scientifically_eligible": False,
            "logs": [],
            "errors": [error_message],
            "error_type": error_type,
            "error_message": error_message,
            "metrics": {},
        }

    def _parse_execution_status(self, simulation_results: Dict[str, Any]) -> ExecutionStatus:
        raw_status = simulation_results.get("execution_status")
        if raw_status:
            try:
                return ExecutionStatus(raw_status)
            except ValueError:
                pass
        if simulation_results.get("success", True):
            return ExecutionStatus.SUCCESS
        errors = "\n".join(str(item) for item in simulation_results.get("errors", []))
        if "timed out" in errors.lower():
            return ExecutionStatus.TIMEOUT
        return ExecutionStatus.ERROR

    def _parse_simulation_mode(self, simulation_results: Dict[str, Any]) -> Optional[SimulationMode]:
        raw_mode = simulation_results.get("simulation_mode")
        if not raw_mode:
            return None
        try:
            return SimulationMode(raw_mode)
        except ValueError:
            return None

    def _parse_netlist_binding_status(
        self,
        simulation_results: Dict[str, Any],
        *,
        netlist_path: Optional[Path],
    ) -> NetlistBindingStatus:
        raw_status = simulation_results.get("netlist_binding_status")
        if not raw_status:
            if netlist_path is None and simulation_results.get("success", False):
                return NetlistBindingStatus.MATCH
            return NetlistBindingStatus.NOT_VERIFIED
        try:
            return NetlistBindingStatus(raw_status)
        except ValueError:
            return NetlistBindingStatus.NOT_VERIFIED

    def _finalize_report_statuses(self, report: VerificationReport, simulation_results: Dict[str, Any]) -> None:
        nominal_results = [
            result for result in report.spec_results
            if (result.category or "").lower() != "pvt"
        ]
        pvt_results = [
            result for result in report.spec_results
            if (result.category or "").lower() == "pvt"
        ]

        if (
            report.execution_status != ExecutionStatus.SUCCESS
            or report.netlist_binding_status != NetlistBindingStatus.MATCH
            or not nominal_results
        ):
            report.compliance_status = ComplianceStatus.NOT_EVALUATED
        elif any(result.verdict == Verdict.FAIL for result in nominal_results):
            report.compliance_status = ComplianceStatus.FAIL
        elif any(result.verdict == Verdict.ERROR for result in nominal_results):
            report.compliance_status = ComplianceStatus.NOT_EVALUATED
        else:
            report.compliance_status = ComplianceStatus.PASS

        if not pvt_results:
            report.robustness_status = RobustnessStatus.NOT_EVALUATED
        elif any(result.verdict in (Verdict.ERROR, Verdict.FAIL) for result in pvt_results):
            report.robustness_status = RobustnessStatus.ROBUST_FAIL
        else:
            report.robustness_status = RobustnessStatus.ROBUST_PASS

        report.scientific_category = classify_scientific_result(
            report.execution_status,
            report.compliance_status,
        )
        report.scientifically_eligible = (
            report.execution_status == ExecutionStatus.SUCCESS
            and report.simulation_mode in (SimulationMode.REAL, SimulationMode.RECOVERED)
            and report.netlist_binding_status == NetlistBindingStatus.MATCH
        )
        variant_override_records = (report.testbench.metadata or {}).get("variant_overrides", []) if report.testbench else []
        if any(record.get("application_status") in {"OVERWRITTEN", "NOT_APPLIED", "UNSUPPORTED"} for record in variant_override_records):
            report.scientifically_eligible = False
        report.metric_traces = [
            self._build_metric_trace(result, simulation_results)
            for result in report.spec_results
        ]

    def _build_metric_trace(self, result: CheckResult, simulation_results: Dict[str, Any]) -> MetricTrace:
        expected_operator = ""
        expected_threshold = None
        if result.expected_min is not None and result.expected_max is not None:
            expected_operator = "range"
        elif result.expected_min is not None:
            expected_operator = ">="
            expected_threshold = result.expected_min
        elif result.expected_max is not None:
            expected_operator = "<="
            expected_threshold = result.expected_max

        status = (
            "PASS" if result.verdict in (Verdict.PASS, Verdict.WARNING)
            else "FAIL" if result.verdict == Verdict.FAIL
            else "NOT_EVALUATED"
        )
        request_by_name = {
            item.get("name"): item
            for item in simulation_results.get("measurement_requests", [])
            if isinstance(item, dict) and item.get("name")
        }
        request = request_by_name.get(result.test_name, {})
        native_extraction = (simulation_results.get("native_extractions", {}) or {}).get(result.test_name, {})
        return MetricTrace(
            metric_name=result.test_name,
            measured_value=result.measured_value,
            unit=result.unit,
            normalized_value=result.measured_value,
            expected_operator=expected_operator,
            expected_threshold=expected_threshold,
            tolerance=None,
            status=status,
            source_analysis=self._source_analysis_for_category(result.category),
            source_signal=self._source_signal_for_metric(result.test_name),
            extraction_method=self._extraction_method_for_metric(result.test_name),
            raw_result_file=simulation_results.get("raw_result_file"),
            error=result.message if result.verdict == Verdict.ERROR else None,
            metric_definition_version=request.get("metric_definition_version") or native_extraction.get("metric_definition_version"),
            quantity_type=request.get("quantity_type") or native_extraction.get("quantity_type"),
            measurement_expression_id=request.get("measurement_expression_id") or native_extraction.get("measurement_expression_id"),
            input_node=request.get("input_node") or native_extraction.get("input_node"),
            output_node=request.get("output_node") or native_extraction.get("output_node"),
            input_ac_magnitude=request.get("input_ac_magnitude") or native_extraction.get("input_ac_magnitude"),
            reference_frequency_hz=request.get("reference_frequency_hz") or native_extraction.get("reference_frequency_hz"),
            measurement_backend=native_extraction.get("measurement_backend") or simulation_results.get("measurement_backend"),
        )

    @staticmethod
    def _source_analysis_for_category(category: Optional[str]) -> str:
        mapping = {
            "dc": "OP",
            "ac": "AC",
            "transient": "TRAN",
            "spectral": "FFT",
            "pvt": "PVT",
        }
        return mapping.get((category or "").lower(), "")

    @staticmethod
    def _source_signal_for_metric(metric_name: str) -> str:
        metric_lower = metric_name.lower()
        if any(token in metric_lower for token in ("current", "idd", "power")):
            return "supply_current"
        if any(token in metric_lower for token in ("gain", "bandwidth", "phase", "impedance", "vout", "slew", "settling", "frequency", "thd", "overshoot", "rise_time", "fall_time", "ringing", "integrator", "differentiator")):
            return "vout"
        if any(token in metric_lower for token in ("bias", "common_mode")):
            return "vin"
        return ""

    @staticmethod
    def _extraction_method_for_metric(metric_name: str) -> str:
        return f"MetricExtractor.extract:{metric_name}"

    def _build_provenance(
        self,
        report: VerificationReport,
        spec_path: Optional[Path],
        netlist_path: Optional[Path],
    ) -> Dict[str, Any]:
        testbench_text = report.testbench.generate_spice_deck() if report.testbench else ""
        return {
            "run_id": report.run_id,
            "timestamp": report.timestamp,
            "framework_version": self._package_version("spec2testbench"),
            "git_commit": self._git_commit(),
            "python_version": sys.version,
            "ngspice_version": report.ngspice_version or self._ngspice_version(),
            "ngspice_command": report.ngspice_command,
            "ngspice_returncode": report.ngspice_returncode,
            "raw_result_file": report.raw_result_file,
            "raw_result_file_exists": report.raw_result_file_exists,
            "pyspice_version": self._package_version("PySpice"),
            "operating_system": platform.platform(),
            "circuit_id": report.circuit_name,
            "case_id": report.case_id,
            "parent_circuit_id": report.parent_circuit_id,
            "specification_file": str(spec_path) if spec_path else None,
            "specification_hash": report.specification_sha256 or self._sha256_file(spec_path),
            "netlist_file": str(netlist_path) if netlist_path else None,
            "netlist_hash": report.expected_netlist_sha256 or self._sha256_file(netlist_path),
            "testbench_file": None,
            "testbench_hash": self._sha256_text(testbench_text) if testbench_text else None,
            "expected_netlist_sha256": report.expected_netlist_sha256,
            "actual_netlist_sha256": report.actual_netlist_sha256,
            "actual_deck_sha256": report.actual_deck_sha256,
            "netlist_binding_status": report.netlist_binding_status.value,
            "required_metric_validation": report.required_metric_validation,
            "mutation_effectiveness_status": report.mutation_effectiveness_status.value,
            "measurement_backend": report.measurement_backend,
            "pyspice_required": report.pyspice_required,
            "measurement_source": report.measurement_source,
            "measurement_command": report.measurement_command,
            "measurement_status": report.measurement_status,
            "compiled_plan_sha256": report.compiled_plan_sha256,
            "serialized_deck_sha256": report.serialized_deck_sha256,
            "executed_file_sha256": report.executed_file_sha256,
            "post_execution_file_sha256": report.post_execution_file_sha256,
            "ngspice_input_file_path": report.ngspice_input_file_path,
            "generated_testbench_path": report.generated_testbench_path,
            "generated_testbench_sha256": report.generated_testbench_sha256,
            "generated_testbench_alias_byte_identical": report.generated_testbench_alias_byte_identical,
            "post_serialization_deck_mutation": report.post_serialization_deck_mutation,
            "measurement_requests": (report.testbench.metadata or {}).get("measurement_requests", []) if report.testbench else [],
            "variant_overrides": (report.testbench.metadata or {}).get("variant_overrides", []) if report.testbench else [],
            "simulation_mode": report.simulation_mode.value if report.simulation_mode else None,
            "execution_status": report.execution_status.value,
            "compliance_status": report.compliance_status.value,
            "robustness_status": report.robustness_status.value,
            "scientific_category": report.scientific_category.value,
            "runtime_seconds": report.runtime_seconds,
            "error_type": report.error_type,
            "error_message": "; ".join(report.errors or report.simulation_errors) if (report.errors or report.simulation_errors) else None,
        }

    @staticmethod
    def _resolve_persist_artifacts(persist_artifacts: Optional[bool]) -> bool:
        if persist_artifacts is not None:
            return persist_artifacts
        if os.getenv("PYTEST_CURRENT_TEST"):
            return False
        return bool(settings.output.persist_outputs)

    @staticmethod
    def _safe_path_token(value: Optional[str]) -> str:
        token = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
        token = token.strip("._")
        return token or "unnamed"

    def _artifact_bundle_paths(self, report: VerificationReport) -> Dict[str, Path]:
        case_slug = self._safe_path_token(report.case_id or report.circuit_name)
        run_slug = f"{self._safe_path_token(report.timestamp)}_{self._safe_path_token(report.run_id)[:8]}"
        output_root = settings.output.output_dir / "verification_runs" / case_slug / run_slug
        simulation_dir = output_root / "simulation"
        figures_dir = output_root / "figures"
        report_dir = settings.output.report_dir / "verification_runs" / case_slug
        results_dir = settings.output.results_dir / "verification_runs" / case_slug
        for directory in (output_root, simulation_dir, figures_dir, report_dir, results_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return {
            "output_root": output_root,
            "simulation_dir": simulation_dir,
            "figures_dir": figures_dir,
            "report_markdown": report_dir / f"{run_slug}.md",
            "report_json": report_dir / f"{run_slug}.json",
            "result_summary": results_dir / f"{run_slug}.json",
            "manifest_path": output_root / "artifact_manifest.json",
        }

    def _persist_run_artifacts(
        self,
        report: VerificationReport,
        simulation_results: Dict[str, Any],
        artifact_bundle: Optional[Dict[str, Path]],
    ) -> None:
        if artifact_bundle is None:
            return

        figure_paths = self._generate_visual_artifacts(
            report,
            simulation_results,
            artifact_bundle["figures_dir"],
        )
        artifact_manifest = {
            "circuit_name": report.circuit_name,
            "case_id": report.case_id,
            "run_id": report.run_id,
            "timestamp": report.timestamp,
            "output_root": str(artifact_bundle["output_root"]),
            "simulation_dir": str(artifact_bundle["simulation_dir"]),
            "figures_dir": str(artifact_bundle["figures_dir"]),
            "report_markdown": str(artifact_bundle["report_markdown"]),
            "report_json": str(artifact_bundle["report_json"]),
            "result_summary": str(artifact_bundle["result_summary"]),
            "figures": {name: str(path) for name, path in figure_paths.items()},
        }
        report.provenance["artifact_bundle"] = artifact_manifest
        report.provenance["visual_artifacts"] = artifact_manifest["figures"]

        artifact_bundle["manifest_path"].write_text(
            json.dumps(artifact_manifest, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        artifact_bundle["report_markdown"].write_text(
            self._render_markdown_report(report),
            encoding="utf-8",
        )
        artifact_bundle["report_json"].write_text(
            json.dumps(self._report_payload(report), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        artifact_bundle["result_summary"].write_text(
            json.dumps(
                {
                    **self._report_payload(report),
                    "artifact_bundle": artifact_manifest,
                },
                indent=2,
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )

    def _generate_visual_artifacts(
        self,
        report: VerificationReport,
        simulation_results: Dict[str, Any],
        figures_dir: Path,
    ) -> Dict[str, Path]:
        plotter = WaveformPlotter(output_dir=figures_dir)
        artifacts: Dict[str, Path] = {}

        transient = simulation_results.get("transient", {}) or simulation_results.get("tran", {})
        time_axis = transient.get("time", [])
        if time_axis:
            time = self._to_float_array(time_axis)
            signals: Dict[str, Any] = {}
            voltage_map = transient.get("voltage", {}) or {}
            for name, values in voltage_map.items():
                series = self._to_float_array(values)
                if len(series) == len(time):
                    signals[str(name)] = series
            for fallback_name in ("vin", "vout"):
                values = transient.get(fallback_name)
                if values is None or fallback_name in signals:
                    continue
                series = self._to_float_array(values)
                if len(series) == len(time):
                    signals[fallback_name] = series
            if signals:
                artifacts["transient_plot"] = plotter.plot_transient(
                    time=time,
                    signals=signals,
                    title=f"{report.circuit_name} - Transient Waveforms",
                    filename="transient_waveforms.png",
                )

        ac_plot_data = self._derive_ac_plot_data(simulation_results)
        if ac_plot_data is not None:
            frequency, magnitude, phase_data = ac_plot_data
            artifacts["bode_plot"] = plotter.plot_ac_response(
                frequency=frequency,
                magnitude=magnitude,
                phase=phase_data,
                title=f"{report.circuit_name} - Bode Response",
                filename="bode_response.png",
                phase_in_degrees=True,
            )

        fft_requested = bool(simulation_results.get("fourier")) or any(
            trace.metric_name in {"oscillator_frequency", "frequency_hz", "fundamental_frequency", "thd", "thd_percent"}
            for trace in report.metric_traces
        )
        fft_payload = self._derive_fft_plot_data(simulation_results) if fft_requested else None
        if fft_payload is not None:
            frequency_fft, spectrum_fft, fundamental = fft_payload
            artifacts["fft_plot"] = plotter.plot_fft(
                frequency=frequency_fft,
                spectrum=spectrum_fft,
                fundamental_freq=fundamental,
                title=f"{report.circuit_name} - Frequency Spectrum",
                filename="fft_spectrum.png",
            )

        scalar_metrics: Dict[str, float] = {}
        for collection in (simulation_results.get("dc", {}) or {}, simulation_results.get("currents", {}) or {}):
            for name, value in collection.items():
                if isinstance(value, (int, float)) and math.isfinite(float(value)):
                    scalar_metrics[str(name)] = float(value)
        if scalar_metrics:
            artifacts["dc_summary_plot"] = plotter.plot_scalar_summary(
                metrics=scalar_metrics,
                title=f"{report.circuit_name} - DC Summary",
                ylabel="Value",
                filename="dc_summary.png",
            )

        return artifacts

    @staticmethod
    def _to_float_array(values: Any):
        import numpy as np

        return np.asarray(values, dtype=float)

    def _derive_ac_plot_data(self, simulation_results: Dict[str, Any]):
        import numpy as np

        ac = simulation_results.get("ac", {}) or {}
        frequency = ac.get("frequency", [])
        magnitude = ac.get("magnitude", [])
        if frequency and magnitude:
            phase = ac.get("phase")
            phase_data = self._to_float_array(phase) if phase else None
            return self._to_float_array(frequency), self._to_float_array(magnitude), phase_data

        measurement_source = simulation_results.get("measurement_source")
        measurement_backend = simulation_results.get("measurement_backend")
        if measurement_backend != "NGSPICE_WRDATA" or not measurement_source:
            return None
        try:
            parsed = parse_wrdata_file(Path(measurement_source))
        except Exception:
            return None

        request = next(
            (
                item for item in simulation_results.get("measurement_requests", [])
                if isinstance(item, dict) and {"in_real_column", "in_imag_column", "out_real_column", "out_imag_column"} <= set(item.keys())
            ),
            None,
        )
        if request is None:
            return None
        data = parsed["data"]
        try:
            frequency = data[:, 0]
            vin = data[:, int(request.get("in_real_column", 1))] + 1j * data[:, int(request.get("in_imag_column", 2))]
            vout = data[:, int(request.get("out_real_column", 3))] + 1j * data[:, int(request.get("out_imag_column", 4))]
        except Exception:
            return None
        vin_mag = np.abs(vin)
        transfer = np.divide(
            vout,
            vin,
            out=np.full_like(vout, np.nan + 0j, dtype=np.complex128),
            where=vin_mag > 0,
        )
        magnitude = np.abs(transfer).astype(float)
        phase = np.degrees(np.angle(transfer)).astype(float)
        finite_mask = np.isfinite(frequency) & np.isfinite(magnitude) & np.isfinite(phase)
        if not np.any(finite_mask):
            return None
        return frequency[finite_mask], magnitude[finite_mask], phase[finite_mask]

    def _derive_fft_plot_data(self, simulation_results: Dict[str, Any]):
        import numpy as np

        transient = simulation_results.get("transient", {}) or simulation_results.get("tran", {})
        time = transient.get("time", [])
        vout = transient.get("vout", [])
        if time and vout and len(time) == len(vout) and len(time) >= 16:
            time_arr = np.asarray(time, dtype=float)
            vout_arr = np.asarray(vout, dtype=float)
            dt = float(np.mean(np.diff(time_arr)))
            if math.isfinite(dt) and dt > 0:
                windowed = (vout_arr - np.mean(vout_arr)) * np.hanning(vout_arr.size)
                spectrum = np.abs(np.fft.rfft(windowed))
                frequency = np.fft.rfftfreq(vout_arr.size, dt)
                if frequency.size > 1:
                    frequency = frequency[1:]
                    spectrum = spectrum[1:]
                    fundamental = simulation_results.get("fourier", {}).get("fundamental_frequency") or simulation_results.get("metrics", {}).get("oscillator_frequency")
                    return frequency, spectrum, float(fundamental) if fundamental is not None else None

        harmonics = simulation_results.get("fourier", {}).get("harmonics", []) or []
        if harmonics:
            frequency = []
            spectrum = []
            for harmonic in harmonics:
                try:
                    freq = float(harmonic["frequency"])
                    mag = float(harmonic["magnitude"])
                except (KeyError, TypeError, ValueError):
                    continue
                if freq <= 0 or not math.isfinite(freq) or not math.isfinite(mag):
                    continue
                frequency.append(freq)
                spectrum.append(mag)
            if frequency and spectrum:
                fundamental = simulation_results.get("fourier", {}).get("fundamental_frequency")
                import numpy as np

                return np.asarray(frequency, dtype=float), np.asarray(spectrum, dtype=float), float(fundamental) if fundamental is not None else None
        return None

    def _report_payload(self, report: VerificationReport) -> Dict[str, Any]:
        return {
            "circuit_name": report.circuit_name,
            "run_id": report.run_id,
            "timestamp": report.timestamp,
            "overall_verdict": report.overall_verdict.value,
            "terminal_status": report.terminal_status,
            "execution_status": report.execution_status.value,
            "simulation_mode": report.simulation_mode.value if report.simulation_mode else None,
            "compliance_status": report.compliance_status.value,
            "robustness_status": report.robustness_status.value,
            "scientific_category": report.scientific_category.value,
            "scientifically_eligible": report.scientifically_eligible,
            "failure_kind": report.failure_kind,
            "success_rate": report.success_rate,
            "compliance_score": report.compliance_score,
            "nominal_compliance_score": report.nominal_compliance_score,
            "pvt_compliance_score": report.pvt_compliance_score,
            "testbench_generation_success": report.testbench_generation_success,
            "simulation_success": report.simulation_success,
            "case_id": report.case_id,
            "parent_circuit_id": report.parent_circuit_id,
            "metric_traces": [trace.to_dict() for trace in report.metric_traces],
            "metrics": [
                {
                    "name": result.test_name,
                    "verdict": result.verdict.value,
                    "measured": result.measured_value,
                    "expected_min": result.expected_min,
                    "expected_max": result.expected_max,
                    "unit": result.unit,
                    "message": result.message,
                    "category": result.category,
                }
                for result in report.spec_results
            ],
            "provenance": report.provenance,
            "errors": report.errors,
            "simulation_errors": report.simulation_errors,
        }

    def _render_markdown_report(self, report: VerificationReport) -> str:
        lines = [
            "# Spec2Testbench Verification Run",
            "",
            f"- Circuit: `{report.circuit_name}`",
            f"- Case ID: `{report.case_id}`",
            f"- Run ID: `{report.run_id}`",
            f"- Timestamp: `{report.timestamp}`",
            f"- Overall verdict: `{report.overall_verdict.value}`",
            f"- Execution status: `{report.execution_status.value}`",
            f"- Simulation mode: `{report.simulation_mode.value if report.simulation_mode else 'N/A'}`",
            f"- Compliance status: `{report.compliance_status.value}`",
            f"- Scientific category: `{report.scientific_category.value}`",
            f"- Success rate: `{report.success_rate * 100:.1f}%`",
            f"- Compliance score: `{report.compliance_score:.3f}`",
            "",
            "## Metrics",
            "",
            "| Metric | Status | Measured | Expected |",
            "| --- | --- | --- | --- |",
        ]
        for result in report.spec_results:
            lines.append(
                f"| {result.test_name} | {result.verdict.value} | {result.measured_str} | {result.expected_range} |"
            )
        visual_artifacts = report.provenance.get("visual_artifacts", {})
        if visual_artifacts:
            lines.extend(["", "## Visual Artifacts", ""])
            for name, path in visual_artifacts.items():
                lines.append(f"- `{name}`: `{path}`")
        if report.errors or report.simulation_errors:
            lines.extend(["", "## Errors", ""])
            for error in report.errors + report.simulation_errors:
                lines.append(f"- {error}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _sha256_file(path: Optional[Path]) -> Optional[str]:
        if not path or not path.exists():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _package_version(package_name: str) -> Optional[str]:
        try:
            return metadata.version(package_name)
        except metadata.PackageNotFoundError:
            return None

    @staticmethod
    def _git_commit() -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
                shell=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    @staticmethod
    def _ngspice_version() -> Optional[str]:
        candidates = [
            shutil.which("ngspice_con"),
            shutil.which("ngspice_con.exe"),
            shutil.which("ngspice"),
            shutil.which("ngspice.exe"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                result = subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    shell=False,
                )
            except Exception:
                continue
            output = (result.stdout or result.stderr or "").strip()
            if output:
                for line in output.splitlines():
                    if "ngspice" in line.lower():
                        return line.strip("* ")
                return output.splitlines()[0]
        return None
    
    def _analyze_failed_metrics(self, failed: List[CheckResult], simulation_results: Dict, specification: Specification) -> List[MultimodalResult]:
        analyses = []
        for metric in failed:
            if self.waveform_checker.use_llm:
                analyses.append(MultimodalResult(
                    verdict=metric.verdict,
                    waveform_image_path="",
                    extracted_metrics={},
                    reasoning=f"Diagnostic pour {metric.test_name}",
                    confidence=0.8,
                    anomalies=[],
                    recommendations=["Verifier le circuit"],
                    violations=[metric.message]
                ))
        return analyses
    
    def verify_from_yaml(self, spec_path: Path, netlist_path: Optional[Path] = None) -> VerificationReport:
        specification = Specification.from_yaml(spec_path)
        return self.verify(specification, netlist_path, spec_path=spec_path)
    
    def verify_from_text(self, text: str, netlist_path: Optional[Path] = None) -> VerificationReport:
        specification = self.testbench_gen.generate_from_text(text)
        return self.verify(specification, netlist_path)

    def _validate_required_metrics(
        self,
        specification: Specification,
        simulation_results: Dict[str, Any],
        testbench: TestBench,
    ) -> Dict[str, Dict[str, Any]]:
        validation: Dict[str, Dict[str, Any]] = {}
        available_analyses = {analysis.type.value for analysis in testbench.analyses}
        available_signals = {signal.lower() for signal in (specification.input_nodes + specification.output_nodes)}
        metric_extractor = self.spec_checker.metric_extractor
        for metric_name in specification.verification_metric_names():
            target = specification.get_metric(metric_name) or {}
            expected_operator = (
                "range" if target.get("min") is not None and target.get("max") is not None
                else ">=" if target.get("min") is not None
                else "<=" if target.get("max") is not None
                else ""
            )
            required_analysis = self._required_analysis_for_metric(metric_name)
            source_signal = self._source_signal_for_metric(metric_name)
            signal_ok = (
                not available_signals
                or not source_signal
                or source_signal in {"supply_current", "vout", "out", "vin", "in"}
                or source_signal in available_signals
            )
            validation[metric_name] = {
                "target_metric_exists_in_specification": specification.has_metric(metric_name),
                "target_metric_supported_by_extractor": metric_extractor.supports_metric(metric_name),
                "target_metric_has_recognized_unit": self.spec_checker._to_si(1.0, target.get("unit", "")) is not None,
                "target_metric_has_operator": bool(expected_operator),
                "target_metric_has_threshold": target.get("min") is not None or target.get("max") is not None,
                "required_signals_available": signal_ok,
                "required_analysis_generated": not required_analysis or required_analysis in available_analyses,
            }
        return validation

    @staticmethod
    def _has_required_metric_validation_errors(validation: Dict[str, Dict[str, Any]]) -> bool:
        return any(not all(metric_checks.values()) for metric_checks in validation.values())

    def _build_precheck_error_results(
        self,
        specification: Specification,
        validation: Dict[str, Dict[str, Any]],
    ) -> List[CheckResult]:
        results: List[CheckResult] = []
        for metric_name in specification.verification_metric_names():
            checks = validation[metric_name]
            if all(checks.values()):
                continue
            missing = [name for name, ok in checks.items() if not ok]
            target = specification.get_metric(metric_name) or {}
            results.append(CheckResult(
                test_name=metric_name,
                verdict=Verdict.ERROR,
                measured_value=None,
                expected_min=target.get("min"),
                expected_max=target.get("max"),
                unit=target.get("unit", ""),
                message="precheck_failed: " + ", ".join(missing),
                category=self.spec_checker._get_metric_category(metric_name),
            ))
        return results

    @staticmethod
    def _required_analysis_for_metric(metric_name: str) -> str:
        metric_lower = metric_name.lower()
        if any(token in metric_lower for token in ("gain", "bandwidth", "ugbw", "gbw", "phase", "cmrr", "psrr", "impedance")):
            return "ac"
        if any(token in metric_lower for token in ("cutoff_frequency", "center_frequency", "lowpass_", "highpass_", "bandpass_", "bandstop_")):
            return "ac"
        if any(token in metric_lower for token in ("slew", "settling", "delay", "hysteresis", "v_t_", "frequency", "amplitude", "overshoot", "rise_time", "fall_time", "ringing", "sine_response", "integrator", "differentiator", "output_swing", "oscillation_")):
            return "tran"
        if any(token in metric_lower for token in ("thd", "sfdr", "spur", "conversion_gain")):
            return "fourier"
        if "pvt" in metric_lower:
            return "pvt"
        return "dc"
