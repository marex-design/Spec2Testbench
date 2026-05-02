# spec2testbench/application/usecases/run_verification.py

"""
Complete verification pipeline orchestrating all three modules.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import TestBench
from ...domain.value_objects.verdict import Verdict, CheckResult
from ...domain.value_objects.multimodal_result import MultimodalResult
from ...infrastructure.testbench import TestBenchGenerator
from ...infrastructure.spec_checker import SpecChecker
from ...infrastructure.waveform_checker import WaveformChecker, WaveformPlotter
from ...config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class VerificationReport:
    """
    Complete verification report from the pipeline.
    """
    
    circuit_name: str
    """Name of the verified circuit"""
    
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    """Verification timestamp"""
    
    specification: Optional[Specification] = None
    """Original specification"""
    
    testbench: Optional[TestBench] = None
    """Generated testbench"""
    
    spec_results: List[CheckResult] = field(default_factory=list)
    """Results from SpecChecker"""
    
    waveform_analyses: List[MultimodalResult] = field(default_factory=list)
    """Analyses from WaveformChecker"""
    
    simulation_logs: List[str] = field(default_factory=list)
    """Simulation logs"""
    
    errors: List[str] = field(default_factory=list)
    """Errors encountered"""
    
    @property
    def overall_verdict(self) -> Verdict:
        """Compute overall verdict from all checks."""
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
        """Return failed metrics."""
        return [r for r in self.spec_results if r.verdict in [Verdict.FAIL, Verdict.WARNING]]
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate (0-1)."""
        if not self.spec_results:
            return 0.0
        passed = sum(1 for r in self.spec_results if r.verdict == Verdict.PASS)
        return passed / len(self.spec_results)
    
    def to_summary(self) -> str:
        """Generate text summary."""
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
        
        if self.waveform_analyses:
            lines.append("")
            lines.append("Waveform Analysis:")
            for wa in self.waveform_analyses:
                lines.append(f"  ⚠️ {wa.diagnosis[:100]}...")
        
        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for error in self.errors:
                lines.append(f"  ❌ {error}")
        
        lines.append("=" * 60)
        return "\n".join(lines)


class VerificationPipeline:
    """
    Complete verification pipeline orchestrating the three modules.
    
    Flow:
    1. TestBenchGen generates testbench from specs
    2. Simulator runs simulations (to be implemented)
    3. SpecChecker verifies metrics against specs
    4. WaveformChecker analyzes waveforms for failures
    5. Generate comprehensive report
    """
    
    def __init__(self, use_llm: bool = True, llm_client=None):
        """
        Initialize the verification pipeline.
        
        Args:
            use_llm: Whether to use LLM for generation
            llm_client: LLM client for generation and analysis
        """
        self.use_llm = use_llm
        self.llm_client = llm_client
        
        # Initialize modules
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
    
    def verify(self,
               specification: Specification,
               netlist_path: Optional[Path] = None,
               simulation_results: Optional[Dict[str, Any]] = None) -> VerificationReport:
        """
        Run complete verification pipeline.
        
        Args:
            specification: Circuit specifications
            netlist_path: Path to SPICE netlist (optional)
            simulation_results: Pre-computed simulation results (optional)
            
        Returns:
            VerificationReport with comprehensive results
        """
        logger.info(f"Starting verification for {specification.name}")
        
        report = VerificationReport(circuit_name=specification.name)
        report.specification = specification
        
        try:
            # Step 1: Generate testbench
            logger.info("Step 1/4: Generating testbench...")
            testbench = self.testbench_gen.generate(specification)
            report.testbench = testbench
            logger.info(f"  Generated testbench with {len(testbench.measurements)} measurements")
            
            # Step 2: Run simulation (if netlist provided and no pre-computed results)
            if simulation_results is None:
                simulation_results = self._run_simulation(netlist_path, testbench)
                report.simulation_logs = simulation_results.get("logs", [])
            
            # Step 3: Verify specifications
            logger.info("Step 3/4: Verifying specifications...")
            spec_results = self.spec_checker.verify(simulation_results, specification)
            report.spec_results = spec_results
            
            # Step 4: Analyze waveforms for failed metrics
            failed = self.spec_checker.get_failed_metrics(spec_results)
            if failed:
                logger.info(f"Step 4/4: Analyzing waveforms for {len(failed)} failed metrics...")
                waveform_analyses = self._analyze_failed_metrics(
                    failed, simulation_results, specification
                )
                report.waveform_analyses = waveform_analyses
            
            logger.info(f"Verification complete: {report.success_rate*100:.1f}% success rate")
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            report.errors.append(str(e))
        
        return report
    
    def verify_from_yaml(self,
                         spec_path: Path,
                         netlist_path: Optional[Path] = None) -> VerificationReport:
        """
        Verify circuit from YAML specification file.
        
        Args:
            spec_path: Path to YAML specification file
            netlist_path: Path to SPICE netlist
            
        Returns:
            VerificationReport
        """
        specification = Specification.from_yaml(spec_path)
        return self.verify(specification, netlist_path)
    
    def verify_from_text(self,
                         text: str,
                         netlist_path: Optional[Path] = None) -> VerificationReport:
        """
        Verify circuit from natural language description.
        
        Args:
            text: Natural language specification
            netlist_path: Path to SPICE netlist
            
        Returns:
            VerificationReport
        """
        specification = self.testbench_gen.generate_from_text(text)
        return self.verify(specification, netlist_path)
    
    def _run_simulation(self, netlist_path: Optional[Path], 
                        testbench: TestBench) -> Dict[str, Any]:
        """
        Run simulation (placeholder - to be implemented with actual simulator).
        
        Returns:
            Simulated results
        """
        logger.warning("Simulation not implemented - using mock results")
        
        # Mock results for demonstration
        return {
            "ac": {
                "magnitude": [1000, 500, 100, 10],
                "frequency": [1, 1e3, 1e6, 1e9],
                "phase": [-90, -120, -150, -170]
            },
            "currents": {"vdd": 1e-3},
            "logs": ["Simulation completed successfully (mock)"]
        }
    
    def _analyze_failed_metrics(self,
                                failed: List[CheckResult],
                                simulation_results: Dict[str, Any],
                                specification: Specification) -> List[MultimodalResult]:
        """
        Analyze waveforms for failed metrics.
        
        Args:
            failed: List of failed metrics
            simulation_results: Simulation results
            specification: Circuit specification
            
        Returns:
            List of multimodal analysis results
        """
        analyses = []
        
        for metric in failed:
            # Generate waveform for this metric
            waveform_path = self._generate_waveform_for_metric(metric, simulation_results)
            
            if waveform_path:
                # Analyze waveform
                analysis = self.waveform_checker.diagnose_failure(
                    image_path=waveform_path,
                    specification=specification,
                    failed_metrics=[metric.test_name]
                )
                analyses.append(analysis)
        
        return analyses
    
    def _generate_waveform_for_metric(self,
                                      metric: CheckResult,
                                      simulation_results: Dict[str, Any]) -> Optional[Path]:
        """
        Generate waveform image for a specific metric.
        
        Args:
            metric: Failed metric result
            simulation_results: Simulation results
            
        Returns:
            Path to generated image or None
        """
        try:
            # Check what type of data we have
            if "ac" in simulation_results:
                ac_data = simulation_results["ac"]
                return self.waveform_plotter.plot_ac_response(
                    frequency=np.array(ac_data.get("frequency", [])),
                    magnitude=np.array(ac_data.get("magnitude", [])),
                    phase=np.array(ac_data.get("phase", [])) if "phase" in ac_data else None,
                    title=f"AC Response - {metric.test_name}",
                    save=True
                )
            
            if "transient" in simulation_results:
                tran_data = simulation_results["transient"]
                return self.waveform_plotter.plot_transient(
                    time=np.array(tran_data.get("time", [])),
                    signals=tran_data.get("voltage", {}),
                    title=f"Transient - {metric.test_name}",
                    save=True
                )
        except Exception as e:
            logger.warning(f"Could not generate waveform for {metric.test_name}: {e}")
        
        return None