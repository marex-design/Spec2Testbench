"""
Complete verification pipeline orchestrating all three modules.
"""

import logging
import math
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import TestBench
from ...domain.value_objects.verdict import Verdict, CheckResult, ValidationStatus
from ...domain.value_objects.multimodal_result import MultimodalResult
from ...infrastructure.testbench import TestBenchGenerator
from ...infrastructure.spec_checker import SpecChecker
from ...infrastructure.waveform_checker import WaveformChecker, WaveformPlotter
from ...infrastructure.simulator.pyspice_simulator import PySpiceSimulator
from ...config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class VerificationReport:
    circuit_name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    specification: Optional[Specification] = None
    testbench: Optional[TestBench] = None
    testbench_generation_success: bool = False
    simulation_success: bool = False
    spec_results: List[CheckResult] = field(default_factory=list)
    waveform_analyses: List[MultimodalResult] = field(default_factory=list)
    simulation_logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    @property
    def overall_verdict(self) -> ValidationStatus:
        metric_verdicts = [result.verdict for result in self.spec_results]

        if self.errors or not self.testbench_generation_success or not self.simulation_success:
            return ValidationStatus.FAIL
        if any(verdict == Verdict.ERROR for verdict in metric_verdicts):
            return ValidationStatus.FAIL
        if any(verdict == Verdict.FAIL for verdict in metric_verdicts):
            return ValidationStatus.RUN
        if self.has_pvt_coverage and self.pvt_compliance_score == 1.0 and self.nominal_compliance_score == 1.0:
            return ValidationStatus.ROBUST_PASS
        return ValidationStatus.PASS
    
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
            f"Spec2TestBench - Verification Report",
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
    def __init__(self, use_llm: bool = True, llm_client=None, *, allow_mock: bool = False, timeout_seconds: float = 300.0):
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.allow_mock = bool(allow_mock)
        self.timeout_seconds = float(timeout_seconds)
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
            testbench = self.testbench_gen.generate(specification, netlist_path=netlist_path)
            report.testbench = testbench
            report.testbench_generation_success = testbench is not None
            logger.info(f"  Generated testbench with {len(testbench.measurements)} measurements")
            
            if simulation_results is None and netlist_path and netlist_path.exists():
                logger.info("Step 2/4: Running simulation with ngspice...")
                simulation_results = self._run_simulation_with_ngspice(netlist_path, testbench)
                report.simulation_logs = simulation_results.get("logs", [])
            elif simulation_results is None:
                if self.allow_mock:
                    logger.warning("No netlist provided; explicit mock mode enabled")
                    simulation_results = self._run_mock_simulation(testbench)
                else:
                    simulation_results = {
                        'success': False, 'execution_status': 'ERROR', 'simulation_mode': 'NONE',
                        'error_type': 'netlist_missing', 'error_message': 'No netlist provided',
                        'logs': [], 'errors': ['No netlist provided'], 'metrics': {},
                        'dc': {}, 'ac': {}, 'transient': {}, 'fourier': {}, 'pvt': {}, 'currents': {},
                    }

            report.simulation_success = bool(simulation_results.get("success", True))
            
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
        """Run authoritative ngspice simulation without silently promoting partial/mock data."""
        if self.simulator is None:
            self.simulator = PySpiceSimulator(allow_mock=self.allow_mock, timeout_seconds=self.timeout_seconds)

        if not self.simulator.is_available:
            if self.allow_mock:
                return self._run_mock_simulation(testbench)
            return {
                'success': False, 'execution_status': 'ERROR', 'simulation_mode': 'NONE',
                'error_type': 'backend_unavailable',
                'error_message': 'ngspice executable is not available',
                'logs': [], 'errors': ['ngspice executable is not available'],
                'metrics': {}, 'dc': {}, 'ac': {}, 'transient': {}, 'fourier': {}, 'pvt': {}, 'currents': {},
            }

        result = self.simulator.run(netlist_path, testbench)
        return {
            'success': bool(result.get('success', False)),
            'execution_status': result.get('execution_status'),
            'simulation_mode': result.get('simulation_mode'),
            'error_type': result.get('error_type'),
            'error_message': result.get('error_message'),
            'metrics': result.get('metrics', {}),
            'native_metrics': result.get('native_metrics', {}),
            'logs': result.get('logs', []),
            'errors': result.get('errors', []),
            'dc': result.get('dc', {}),
            'ac': result.get('ac', {}),
            'transient': result.get('transient', result.get('tran', {})),
            'fourier': result.get('fourier', {}),
            'pvt': result.get('pvt', {}),
            'currents': result.get('currents', {}),
            'vdd': result.get('vdd', 0.0),
            'artifact_dir': result.get('artifact_dir'),
            'executed_deck_path': result.get('executed_deck_path'),
            'transient_completion': result.get('transient_completion'),
            'op_bias_probe': result.get('op_bias_probe'),
        }
    
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
