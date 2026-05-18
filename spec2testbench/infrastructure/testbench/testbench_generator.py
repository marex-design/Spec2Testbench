# spec2testbench/infrastructure/testbench/testbench_generator.py

"""
TestBenchGen - Implementation of ITestBenchGenerator.
Uses LLM to convert specifications into executable testbenches.
"""

import json
import logging
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from ...domain.entities.specification import Specification
from ...domain.entities.testbench import (
    TestBench, Stimulus, AnalysisConfig, Measurement, AnalysisType
)
from ...domain.value_objects.circuit_type import CircuitType
from ...domain.interfaces.itestbench_generator import ITestBenchGenerator
from .prompts.testbench_prompts import TestBenchPrompts

# Configure logging
logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Exception raised when testbench generation fails."""
    pass


class TestBenchGenerator(ITestBenchGenerator):
    """
    Implementation of TestBench generator using LLM.
    
    This generator uses a multimodal LLM to:
    1. Parse natural language specifications
    2. Generate appropriate testbenches for each category
    3. Produce executable PySpice code
    """
    
    # Default test categories per circuit type
    DEFAULT_CATEGORIES = {
        CircuitType.AMPLIFIER: ['dc', 'ac', 'transient', 'pvt'],
        CircuitType.OPERATIONAL_AMPLIFIER: ['dc', 'ac', 'transient', 'pvt', 'differential'],
        CircuitType.DIFFERENTIAL_AMPLIFIER: ['dc', 'ac', 'transient', 'differential'],
        CircuitType.CURRENT_MIRROR: ['dc', 'pvt'],
        CircuitType.MIXER: ['dc', 'transient', 'spectral'],
        CircuitType.LOW_PASS_FILTER: ['ac', 'transient', 'spectral'],
        CircuitType.HIGH_PASS_FILTER: ['ac', 'transient', 'spectral'],
        CircuitType.BAND_PASS_FILTER: ['ac', 'transient', 'spectral'],
        CircuitType.NOTCH_FILTER: ['ac', 'transient'],
        CircuitType.OSCILLATOR: ['transient', 'spectral', 'pvt'],
        CircuitType.RING_OSCILLATOR: ['transient', 'spectral', 'pvt'],
        CircuitType.COLPITTS_OSCILLATOR: ['transient', 'spectral', 'pvt'],
        CircuitType.RC_PHASE_SHIFT_OSCILLATOR: ['transient', 'spectral'],
        CircuitType.VCO: ['dc', 'transient', 'spectral', 'pvt'],
        CircuitType.INTEGRATOR: ['dc', 'transient', 'ac'],
        CircuitType.DIFFERENTIATOR: ['dc', 'transient', 'ac'],
        CircuitType.COMPARATOR: ['dc', 'transient', 'differential'],
        CircuitType.SCHMITT_TRIGGER: ['dc', 'transient', 'differential'],
        CircuitType.ADC: ['dc', 'transient', 'spectral', 'pvt'],
        CircuitType.DAC: ['dc', 'transient', 'spectral', 'pvt'],
        CircuitType.VOLTAGE_REFERENCE: ['dc', 'pvt', 'ac'],
        CircuitType.LDO: ['dc', 'transient', 'pvt', 'ac'],
        CircuitType.PLL: ['dc', 'transient', 'spectral', 'pvt', 'ac'],
        CircuitType.OPAMP_INTEGRATOR: ['dc', 'transient', 'ac'],
        CircuitType.OPAMP_DIFFERENTIATOR: ['dc', 'transient', 'ac'],
        CircuitType.OPAMP_FILTER: ['ac', 'transient'],
        CircuitType.OPAMP_COMPARATOR: ['dc', 'transient'],
        CircuitType.OPAMP_SCHMITT: ['dc', 'transient', 'differential'],
        CircuitType.COMPOSITE: ['dc', 'ac', 'transient', 'pvt'],
    }
    
    def __init__(self, llm_client=None, use_llm: bool = True):
        """
        Initialize the TestBench generator.
        
        Args:
            llm_client: Optional LLM client (if None, will use template-based generation)
            use_llm: If False, use template-based generation (faster, no API calls)
        """
        self.llm_client = llm_client
        self.use_llm = use_llm
        self.prompts = TestBenchPrompts()
    
    def generate(self, specification: Specification) -> TestBench:
        """
        Generate a complete testbench from specifications.
        
        Strategy:
        1. Determine required test categories based on circuit type
        2. Generate testbench for each category
        3. Merge all testbenches into one
        """
        logger.info(f"Generating testbench for {specification.name}")
        
        # Determine categories to generate
        categories = self._determine_categories(specification)
        logger.debug(f"Categories to generate: {categories}")
        
        # Generate testbench for each category
        testbenches = []
        for category in categories:
            try:
                tb = self.generate_for_category(specification, category)
                testbenches.append(tb)
            except GenerationError as e:
                logger.warning(f"Failed to generate {category}: {e}")
                continue
        
        if not testbenches:
            raise GenerationError(f"No testbench generated for {specification.name}")
        
        # Merge all testbenches
        merged = self._merge_testbenches(testbenches, specification.name)
        
        # Generate PySpice code
        merged.generate_pyspice_code()
        
        logger.info(f"Generated testbench with {len(merged.measurements)} measurements")
        return merged
    
    def generate_for_category(self, 
                              specification: Specification, 
                              category: str) -> TestBench:
        """
        Generate testbench for a specific category.
        
        Args:
            specification: Circuit specifications
            category: Test category ('dc', 'ac', 'transient', 'pvt', 'spectral', 'differential')
            
        Returns:
            Category-specific TestBench
        """
        logger.debug(f"Generating {category} testbench for {specification.name}")
        
        if self.use_llm and self.llm_client:
            return self._generate_with_llm(specification, category)
        else:
            return self._generate_with_templates(specification, category)
    
    def _generate_with_llm(self, specification: Specification, category: str) -> TestBench:
        """Generate testbench using LLM."""
        
        # Build prompt for this category
        prompt = self.prompts.build_category_prompt(specification, category)
        
        # Call LLM
        try:
            response = self.llm_client.complete(prompt, response_format="json")
            data = json.loads(response)
        except Exception as e:
            raise GenerationError(f"LLM generation failed: {e}")
        
        # Parse response into TestBench
        return self._parse_llm_response(data, specification.name, category)
    
    def _generate_with_templates(self, specification: Specification, category: str) -> TestBench:
        """Generate testbench using templates (no LLM, deterministic)."""
        
        if category == "dc":
            return self._create_dc_testbench(specification)
        elif category == "ac":
            return self._create_ac_testbench(specification)
        elif category == "transient":
            return self._create_transient_testbench(specification)
        elif category == "pvt":
            return self._create_pvt_testbench(specification)
        elif category == "spectral":
            return self._create_spectral_testbench(specification)
        elif category == "differential":
            return self._create_differential_testbench(specification)
        else:
            raise GenerationError(f"Unknown category: {category}")
    
    def _determine_categories(self, specification: Specification) -> List[str]:
        """Determine which test categories to generate."""
        
        # If user specified categories, use them
        if specification.test_categories:
            return specification.test_categories
        
        # Otherwise use defaults based on circuit type
        return self.DEFAULT_CATEGORIES.get(
            specification.circuit_type, 
            ['dc', 'ac', 'transient']
        )
    
    def _merge_testbenches(self, testbenches: List[TestBench], circuit_name: str) -> TestBench:
        """Merge multiple testbenches into one."""
        
        if not testbenches:
            return None
        
        merged = TestBench(
            name=f"{circuit_name}_full_testbench",
            category="full",
            circuit_name=circuit_name,
            stimuli=[],
            analyses=[],
            measurements=[],
        )
        
        for tb in testbenches:
            merged.stimuli.extend(tb.stimuli)
            merged.analyses.extend(tb.analyses)
            merged.measurements.extend(tb.measurements)
        
        return merged
    
    def _parse_llm_response(self, data: dict, circuit_name: str, category: str) -> TestBench:
        """Parse LLM JSON response into TestBench entity."""
        
        # Create stimuli
        stimuli = []
        for s in data.get("stimuli", []):
            stimuli.append(Stimulus(
                name=s.get("name", f"stim_{len(stimuli)}"),
                type=s.get("type", "dc"),
                parameters=s.get("parameters", {}),
                node_positive=s.get("node_positive", "1"),
                node_negative=s.get("node_negative", "0"),
            ))
        
        # Create analyses
        analyses = []
        for a in data.get("analyses", []):
            analysis_type = a.get("type", "dc")
            # Convert string to AnalysisType enum
            try:
                atype = AnalysisType(analysis_type)
            except ValueError:
                atype = AnalysisType.DC
            
            analyses.append(AnalysisConfig(
                type=atype,
                parameters=a.get("parameters", {}),
            ))
        
        # Create measurements
        measurements = []
        for m in data.get("measurements", []):
            measurements.append(Measurement(
                name=m.get("name", f"meas_{len(measurements)}"),
                expression=m.get("expression", ""),
                expected_min=m.get("expected_min"),
                expected_max=m.get("expected_max"),
                unit=m.get("unit", ""),
                node=m.get("node"),
            ))
        
        return TestBench(
            name=data.get("testbench_name", f"{circuit_name}_{category}"),
            category=category,
            circuit_name=circuit_name,
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
            description=data.get("description", ""),
        )
    
    # =========================================================
    # TEMPLATE-BASED GENERATION METHODS
    # =========================================================
    
    def _create_dc_testbench(self, spec: Specification) -> TestBench:
        """Create DC testbench using templates."""
        
        stimuli = [
            Stimulus(
                name="vin",
                type="dc",
                parameters={"value": spec.common_mode_voltage},
                node_positive="in",
                node_negative="0",
            )
        ]
        
        analyses = [
            AnalysisConfig(
                type=AnalysisType.DC,
                parameters={
                    "source": "vin",
                    "start": 0,
                    "stop": spec.vdd,
                    "step": spec.vdd / 100,
                }
            )
        ]
        
        measurements = [
            Measurement(
                name="vout_dc",
                expression="V(out)",
                unit="V",
            ),
            Measurement(
                name="idd",
                expression="I(VDD)",
                unit="A",
            ),
        ]
        
        # Add gain measurement if requested
        if spec.has_metric("dc_gain"):
            measurements.append(Measurement(
                name="dc_gain",
                expression="20*log10(V(out)/V(in))",
                expected_min=spec.get_metric_min("dc_gain"),
                unit="dB",
            ))
        
        return TestBench(
            name=f"{spec.name}_dc",
            category="dc",
            circuit_name=spec.name,
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
        )
    
    def _create_ac_testbench(self, spec: Specification) -> TestBench:
        """Create AC testbench using templates."""
        
        stimuli = [
            Stimulus(
                name="vin",
                type="ac",
                parameters={"magnitude": 1, "phase": 0},
                node_positive="in",
                node_negative="0",
            )
        ]
        
        analyses = [
            AnalysisConfig(
                type=AnalysisType.AC,
                parameters={
                    "sweep_type": "dec",
                    "points_per_decade": 10,
                    "start_freq": 1,
                    "stop_freq": 1e9,
                }
            )
        ]
        
        measurements = [
            Measurement(
                name="dc_gain",
                expression="20*log10(V(out)/V(in))",
                expected_min=spec.get_metric_min("dc_gain"),
                unit="dB",
            ),
            Measurement(
                name="gbw",
                expression="gain * bandwidth",
                expected_min=spec.get_metric_min("unity_gain_bandwidth"),
                unit="Hz",
            ),
        ]
        
        return TestBench(
            name=f"{spec.name}_ac",
            category="ac",
            circuit_name=spec.name,
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
        )
    
    def _create_transient_testbench(self, spec: Specification) -> TestBench:
        """Create transient testbench using templates."""
        
        stimuli = [
            Stimulus(
                name="vin",
                type="pulse",
                parameters={
                    "v1": spec.common_mode_voltage - spec.vdd/4,
                    "v2": spec.common_mode_voltage + spec.vdd/4,
                    "rise": "1n",
                    "fall": "1n",
                    "width": "10u",
                    "period": "20u",
                },
                node_positive="in",
                node_negative="0",
            )
        ]
        
        analyses = [
            AnalysisConfig(
                type=AnalysisType.TRANSIENT,
                parameters={
                    "step_time": "1n",
                    "end_time": "50u",
                    "start_time": 0,
                }
            )
        ]
        
        measurements = [
            Measurement(
                name="slew_rate",
                expression="deriv(V(out))",
                expected_min=spec.get_metric_min("slew_rate"),
                unit="V/s",
            ),
        ]
        
        return TestBench(
            name=f"{spec.name}_transient",
            category="transient",
            circuit_name=spec.name,
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
        )
    
    def _create_pvt_testbench(self, spec: Specification) -> TestBench:
        """Create PVT testbench using templates."""
        
        # PVT is special - we'll create a testbench that notes the PVT configuration
        stimuli = [
            Stimulus(
                name="vdd",
                type="dc",
                parameters={"value": spec.vdd},
                node_positive="vdd",
                node_negative="0",
            )
        ]
        
        analyses = [
            AnalysisConfig(
                type=AnalysisType.PVT,
                parameters={
                    "corners": [c.value for c in spec.process_corners] if spec.process_corners else ["tt"],
                    "temperatures": self._get_temperature_list(spec.temperature_range),
                    "supply_variation": spec.supply_variation,
                }
            )
        ]
        
        return TestBench(
            name=f"{spec.name}_pvt",
            category="pvt",
            circuit_name=spec.name,
            stimuli=stimuli,
            analyses=analyses,
            measurements=[],
        )
    
    def _create_spectral_testbench(self, spec: Specification) -> TestBench:
        """Create spectral/FFT testbench using templates."""
        
        stimuli = [
            Stimulus(
                name="vin",
                type="sin",
                parameters={
                    "offset": spec.common_mode_voltage,
                    "amplitude": spec.vdd / 4,
                    "frequency": spec.test_frequency,
                },
                node_positive="in",
                node_negative="0",
            )
        ]
        
        analyses = [
            AnalysisConfig(
                type=AnalysisType.TRANSIENT,
                parameters={
                    "step_time": f"{1/(spec.test_frequency * 200)}",
                    "end_time": f"{50/spec.test_frequency}",
                }
            ),
            AnalysisConfig(
                type=AnalysisType.FOURIER,
                parameters={
                    "fundamental_frequency": spec.test_frequency,
                    "num_harmonics": 9,
                }
            ),
        ]
        
        measurements = [
            Measurement(
                name="thd",
                expression="sqrt(sum(H2^2 + H3^2 + ...))/H1",
                expected_max=spec.get_metric_max("thd"),
                unit="%",
            ),
        ]
        
        return TestBench(
            name=f"{spec.name}_spectral",
            category="spectral",
            circuit_name=spec.name,
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
        )
    
    def _create_differential_testbench(self, spec: Specification) -> TestBench:
        """Create differential testbench using templates."""
        
        stimuli = [
            Stimulus(
                name="vinp",
                type="ac",
                parameters={"magnitude": 0.5},
                node_positive="inp",
                node_negative="0",
            ),
            Stimulus(
                name="vinm",
                type="ac",
                parameters={"magnitude": 0.5, "phase": 180},
                node_positive="inm",
                node_negative="0",
            ),
        ]
        
        analyses = [
            AnalysisConfig(
                type=AnalysisType.AC,
                parameters={
                    "sweep_type": "dec",
                    "points_per_decade": 10,
                    "start_freq": 1,
                    "stop_freq": 1e9,
                }
            )
        ]
        
        measurements = [
            Measurement(
                name="differential_gain",
                expression="20*log10((V(outp)-V(outm))/(V(inp)-V(inm)))",
                unit="dB",
            ),
        ]
        
        return TestBench(
            name=f"{spec.name}_differential",
            category="differential",
            circuit_name=spec.name,
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
        )
    
    def _get_temperature_list(self, temp_range) -> List[int]:
        """Get temperature list from TemperatureRange enum."""
        temperatures = {
            "commercial": [0, 27, 70],
            "industrial": [-40, 27, 85],
            "military": [-55, 27, 125],
            "extended": [-40, 27, 125],
        }
        return temperatures.get(temp_range.value, [27])
    
    # =========================================================
    # OTHER METHODS
    # =========================================================
    
    def generate_from_text(self, text: str) -> Specification:
        """Extract specifications from natural language text."""
        if not self.use_llm or not self.llm_client:
            raise GenerationError("LLM required for text extraction")
        
        prompt = self.prompts.build_extraction_prompt(text)
        
        try:
            response = self.llm_client.complete(prompt, response_format="json")
            data = json.loads(response)
            
            # Convert to Specification
            return Specification(
                name=data.get("name", "extracted_spec"),
                circuit_type=CircuitType(data.get("circuit_type", "amplifier")),
                performance_targets=data.get("performance_targets", {}),
                input_conditions=data.get("input_conditions", {}),
                raw_specs=text,
            )
        except Exception as e:
            raise GenerationError(f"Text extraction failed: {e}")
    
    def get_supported_circuit_types(self) -> List[str]:
        return list(self.DEFAULT_CATEGORIES.keys())
    
    def get_supported_categories(self) -> List[str]:
        return ['dc', 'ac', 'transient', 'pvt', 'spectral', 'differential']
    
    def validate_specification(self, specification: Specification) -> Tuple[bool, List[str]]:
        """Validate that specification can be generated."""
        errors = []
        
        # Check circuit type support
        if specification.circuit_type not in self.DEFAULT_CATEGORIES:
            errors.append(f"Circuit type {specification.circuit_type.display_name} not supported")
        
        # Check if there are performance targets
        if not specification.performance_targets:
            errors.append("No performance targets specified")
        
        return (len(errors) == 0, errors)