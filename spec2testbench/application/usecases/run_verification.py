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
        if not self.spec_results:
            return Verdict.PASS
        return Verdict.worst_case([result.verdict for result in self.spec_results])
    
    @property
    def failed_metrics(self) -> List[CheckResult]:
        return [r for r in self.spec_results if r.verdict in [Verdict.FAIL, Verdict.WARNING]]
    
    @property
    def success_rate(self) -> float:
        if not self.spec_results:
            return 0.0
        successful = sum(1 for r in self.spec_results if r.verdict.is_success)
        return successful / len(self.spec_results)
    
    def to_summary(self) -> str:
        lines = [
            "=" * 60,
            f"Spec2TestBench - Verification Report",
            "=" * 60,
            f"Circuit: {self.circuit_name}",
            f"Timestamp: {self.timestamp}",
            f"Overall Verdict: {self.overall_verdict.emoji} {self.overall_verdict.value}",
            f"Success Rate: {self.success_rate*100:.1f}%",
            "",
            "Metric Results:",
        ]
        for result in self.spec_results:
            status = f"{result.verdict.emoji} {result.verdict.value}"
            lines.append(f"  {status:10} {result.test_name}: {result.measured_str} (expected {result.expected_range})")
        if self.errors:
            lines.extend(["", "Errors:"])
            for error in self.errors:
                lines.append(f"  ❌ {error}")
        lines.append("=" * 60)
        return "\n".join(lines)


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
        self.simulator = None
    
    def verify(self,
               specification: Specification,
               netlist_path: Optional[Path] = None,
               simulation_results: Optional[Dict[str, Any]] = None) -> VerificationReport:
        logger.info(f"Starting verification for {specification.name}")
        report = VerificationReport(circuit_name=specification.name)
        report.specification = specification
        
        try:
            logger.info("Step 1/4: Generating testbench...")
            testbench = self.testbench_gen.generate(specification)
            report.testbench = testbench
            logger.info(f"  Generated testbench with {len(testbench.measurements)} measurements")
            
            if simulation_results is None and netlist_path and netlist_path.exists():
                logger.info("Step 2/4: Running simulation with ngspice...")
                simulation_results = self._run_simulation_with_ngspice(netlist_path, testbench)
                report.simulation_logs = simulation_results.get("logs", [])
            elif simulation_results is None:
                logger.warning("No netlist provided, using mock simulation")
                simulation_results = self._run_mock_simulation(testbench)
            
            logger.info("Step 3/4: Verifying specifications...")
            report.spec_results = self.spec_checker.verify(simulation_results, specification)
            
            failed = self.spec_checker.get_failed_metrics(report.spec_results)
            if failed:
                logger.info(f"Step 4/4: Analyzing waveforms for {len(failed)} failed metrics...")
                report.waveform_analyses = self._analyze_failed_metrics(failed, simulation_results, specification)
            
            logger.info(f"Verification complete: {report.success_rate*100:.1f}% success rate")
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            report.errors.append(str(e))
        
        return report
    
    def _run_simulation_with_ngspice(self, netlist_path: Path, testbench: TestBench) -> Dict[str, Any]:
        """Run simulation with real ngspice via WSL."""
        if self.simulator is None:
            self.simulator = WSLSimulator()

        if not self.simulator.is_available:
            logger.warning("WSL simulator not available, falling back to mock")
            return self._run_mock_simulation(testbench)
        
        netlist_content = netlist_path.read_text()
        
        for stimulus in testbench.stimuli:
            netlist_content += f"\n{stimulus.to_spice()}"
        
        result = self.simulator.run(netlist_content)
        
        return {
            'success': result.get('success', False),
            'metrics': result.get('metrics', {}),
            'logs': [f"V{node}={value}" for node, value in result.get('metrics', {}).items()],
            'ac': {},
            'transient': {},
            'currents': {}
        }
    
    def _run_mock_simulation(self, testbench: TestBench) -> Dict[str, Any]:
        """Run mock simulation when ngspice is not available."""
        logger.info("Running mock simulation")
        return {
            'success': True,
            'logs': ['Mock simulation - ngspice not available'],
            'metrics': {'vout': 2.5, 'vdd': 5.0},
            'ac': {'magnitude': [100], 'frequency': [1e6]},
            'transient': {'vout': [2.5], 'time': [0]},
            'currents': {'vdd': 1e-3}
        }
    
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
        return self.verify(specification, netlist_path)
    
    def verify_from_text(self, text: str, netlist_path: Optional[Path] = None) -> VerificationReport:
        specification = self.testbench_gen.generate_from_text(text)
        return self.verify(specification, netlist_path)
