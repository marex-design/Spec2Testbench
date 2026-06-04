"""
Complete verification pipeline orchestrating all three modules.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import TestBench
from ...domain.value_objects.verdict import Verdict, CheckResult
from ...domain.value_objects.multimodal_result import MultimodalResult
from ...infrastructure.testbench import TestBenchGenerator
from ...infrastructure.spec_checker import SpecChecker
from ...infrastructure.waveform_checker import WaveformChecker, WaveformPlotter
from ...infrastructure.simulator import WSLSimulator
from ...config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class VerificationReport:
    circuit_name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    specification: Optional[Specification] = None
    testbench: Optional[TestBench] = None
    spec_results: List[CheckResult] = field(default_factory=list)
    waveform_analyses: List[MultimodalResult] = field(default_factory=list)
    simulation_logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def overall_verdict(self) -> Verdict:
        if self.errors:
            return Verdict.ERROR
        for result in self.spec_results:
            if result.verdict == Verdict.FAIL:
                return Verdict.FAIL
            if result.verdict == Verdict.WARNING:
                return Verdict.WARNING
        return Verdict.PASS

    @property
    def failed_metrics(self) -> List[CheckResult]:
        return [r for r in self.spec_results if r.verdict in [Verdict.FAIL, Verdict.WARNING]]

    @property
    def success_rate(self) -> float:
        if not self.spec_results:
            return 0.0
        passed = sum(1 for r in self.spec_results if r.verdict == Verdict.PASS)
        return passed / len(self.spec_results)


class VerificationPipeline:
    def __init__(self, use_llm: bool = True, llm_client=None):
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.testbench_gen = TestBenchGenerator(
            llm_client=llm_client if use_llm else None,
            use_llm=use_llm
        )
        self.spec_checker = SpecChecker(warning_margin=settings.warning_margin)
        self.waveform_checker = WaveformChecker(
            llm_client=llm_client if use_llm else None,
            use_llm=use_llm
        )
        self.waveform_plotter = WaveformPlotter(output_dir=settings.output.waveform_dir)
        self.simulator = WSLSimulator()

    def verify(self,
               specification: Specification,
               netlist_path: Optional[Path] = None,
               simulation_results: Optional[Dict[str, Any]] = None) -> VerificationReport:
        logger.info(f"Starting verification for {specification.name}")
        
        report = VerificationReport(
            circuit_name=specification.name,
            specification=specification
        )
        
        # Exécuter la simulation si besoin
        measurements = {}
        if simulation_results:
            measurements = simulation_results
            logger.info(f"Using provided simulation results: {list(measurements.keys())}")
        elif netlist_path and netlist_path.exists():
            logger.info(f"Running simulation on {netlist_path}")
            try:
                netlist_content = netlist_path.read_text()
                sim_result = self.simulator.run(netlist_content)
                
                if sim_result.get('success', False):
                    measurements = sim_result.get('metrics', {})
                    logger.info(f"Simulation completed. Found metrics: {list(measurements.keys())}")
                    report.simulation_logs.append(f"Simulation successful: {len(measurements)} metrics found")
                else:
                    error_msg = sim_result.get('error', 'Unknown error')
                    logger.error(f"Simulation failed: {error_msg}")
                    report.errors.append(f"Simulation failed: {error_msg}")
            except Exception as e:
                logger.error(f"Error running simulation: {e}")
                report.errors.append(f"Error running simulation: {str(e)}")
        
        # Vérifier chaque métrique
        for metric_name, target in specification.performance_targets.items():
            if metric_name in measurements:
                measured_value = measurements[metric_name]
                
                # Extraire min, max, unit
                if hasattr(target, 'min'):
                    expected_min = target.min
                    expected_max = target.max if hasattr(target, 'max') else None
                    unit = target.unit if hasattr(target, 'unit') else ""
                elif isinstance(target, dict):
                    expected_min = target.get('min')
                    expected_max = target.get('max')
                    unit = target.get('unit', "")
                else:
                    expected_min = target
                    expected_max = None
                    unit = ""
                
                # Déterminer le verdict
                if expected_min is not None and expected_max is not None:
                    if expected_min <= measured_value <= expected_max:
                        verdict = Verdict.PASS
                        message = f"OK: {measured_value:.3f} dans [{expected_min}, {expected_max}] {unit}"
                    else:
                        verdict = Verdict.FAIL
                        message = f"HORS: {measured_value:.3f} hors [{expected_min}, {expected_max}] {unit}"
                elif expected_min is not None:
                    if measured_value >= expected_min:
                        verdict = Verdict.PASS
                        message = f"OK: {measured_value:.3f} >= {expected_min} {unit}"
                    else:
                        verdict = Verdict.FAIL
                        message = f"HORS: {measured_value:.3f} < {expected_min} {unit}"
                elif expected_max is not None:
                    if measured_value <= expected_max:
                        verdict = Verdict.PASS
                        message = f"OK: {measured_value:.3f} <= {expected_max} {unit}"
                    else:
                        verdict = Verdict.FAIL
                        message = f"HORS: {measured_value:.3f} > {expected_max} {unit}"
                else:
                    verdict = Verdict.WARNING
                    message = f"Pas de spécification pour {metric_name}"
                
                # Créer CheckResult sans measured_str/expected_range (ce sont des propriétés)
                check_result = CheckResult(
                    test_name=metric_name,
                    verdict=verdict,
                    measured_value=measured_value,
                    expected_min=expected_min,
                    expected_max=expected_max,
                    unit=unit,
                    message=message
                )
                report.spec_results.append(check_result)
                logger.info(f"Metric {metric_name}: {verdict.value}")
            else:
                logger.warning(f"Metric {metric_name} not found in simulation results")
                check_result = CheckResult(
                    test_name=metric_name,
                    verdict=Verdict.ERROR,
                    measured_value=None,
                    expected_min=None,
                    expected_max=None,
                    unit="",
                    message=f"Metric '{metric_name}' not found in results"
                )
                report.spec_results.append(check_result)
        
        logger.info(f"Verification complete. Success rate: {report.success_rate*100:.1f}%")
        return report

    def verify_from_yaml(self, specs_path: Path, netlist_path: Optional[Path] = None) -> VerificationReport:
        """Verify circuit from YAML specification file."""
        specification = Specification.from_yaml(specs_path)
        return self.verify(specification, netlist_path)
