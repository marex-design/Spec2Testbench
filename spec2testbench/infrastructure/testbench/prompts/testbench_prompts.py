# spec2testbench/infrastructure/testbench/prompts/testbench_prompts.py

"""
Prompts for LLM-based testbench generation.
"""

from typing import Dict, Any, List
from ....domain.entities.specification import Specification


class TestBenchPrompts:
    """Collection of prompts for testbench generation."""
    
    def build_category_prompt(self, specification: Specification, category: str) -> str:
        """Build prompt for a specific test category."""
        
        category_requirements = self._get_category_requirements(category)
        context = specification.to_prompt_context()
        naming_contract = self._build_naming_contract(specification, category)
        
        prompt = '''
You are an analog verification engineer.

TASK
Generate a JSON testbench for ''' + category.upper() + ''' only.

CIRCUIT SPECIFICATIONS
''' + context + '''

CATEGORY REQUIREMENTS
''' + category_requirements + '''

FRAMEWORK CONTRACT
''' + naming_contract + '''

RETURN ONLY THIS JSON SHAPE
{
  "testbench_name": "string",
  "description": "string",
  "stimuli": [
    {
      "name": "string",
      "type": "dc|ac|pulse|sin|pwl",
      "node_positive": "string",
      "node_negative": "string",
      "parameters": {}
    }
  ],
  "analyses": [
    {
      "type": "dc|ac|tran|fourier|pvt",
      "parameters": {}
    }
  ],
  "measurements": [
    {
      "name": "allowed_measurement_name",
      "expression": "string",
      "expected_min": null,
      "expected_max": null,
      "unit": "string",
      "node": "string"
    }
  ]
}
'''
        return prompt
    
    def build_extraction_prompt(self, text: str) -> str:
        """Build prompt for extracting specifications from natural language."""
        
        prompt = '''
You are an expert analog circuit designer. Extract circuit specifications from the following description.

## USER DESCRIPTION
''' + text + '''

## TASK
Extract structured specifications from the text above.

## OUTPUT FORMAT
Return a JSON object with:

{
  "name": "circuit_name",
  "circuit_type": "amplifier|opamp|filter|oscillator|comparator|...",
  "performance_targets": {
    "dc_gain": {"min": 60, "unit": "dB"},
    "bandwidth": {"min": 10000000, "unit": "Hz"},
    "power": {"max": 0.01, "unit": "W"}
  },
  "input_conditions": {
    "vdd": 1.8,
    "vcm": 0.9,
    "cl": 0.0000000001
  }
}

If a value is not specified, omit it.
Return ONLY valid JSON.
'''
        return prompt

    def _build_naming_contract(self, specification: Specification, category: str) -> str:
        allowed_measurements = self._allowed_measurements(specification, category)
        allowed_analysis_types = self._allowed_analysis_types(category)
        allowed_stimuli = self._allowed_stimulus_types(category)
        input_nodes = specification.input_nodes or ["in"]
        output_nodes = specification.output_nodes or ["out"]

        lines = [
            "Strict rules:",
            f"- Allowed measurement names: {', '.join(allowed_measurements)}.",
            f"- Allowed input nodes: {', '.join(input_nodes)}.",
            f"- Allowed output nodes: {', '.join(output_nodes)}.",
            f"- Allowed analysis types: {', '.join(allowed_analysis_types)}.",
            f"- Allowed stimulus types: {', '.join(allowed_stimuli)}.",
            "- Reuse exact spec names; do not invent synonyms or duplicate equivalent measurements.",
            "- Use node 0 for ground.",
            "- Set expected_min, expected_max, and unit from the specification whenever available.",
            "- If a metric is not allowed, omit it.",
            "- Return raw JSON only.",
        ]
        return "\n".join(lines)

    def _allowed_measurements(self, specification: Specification, category: str) -> List[str]:
        category_defaults = {
            "dc": ["operating_point", "quiescent_current", "power", "dc_gain", "dc_gain_db"],
            "ac": ["dc_gain", "dc_gain_db", "bandwidth", "unity_gain_frequency", "phase_margin"],
            "transient": ["slew_rate", "settling_time", "propagation_delay", "frequency_hz", "startup_amplitude"],
            "spectral": ["thd_percent", "fundamental_frequency", "frequency_hz", "sfdr_db"],
            "pvt": ["pvt_dc_gain_variation", "pvt_vout_variation", "pvt_power_variation"],
            "differential": ["differential_gain", "common_mode_gain", "cmrr", "input_common_mode_range"],
        }
        names = list(specification.performance_targets.keys())
        for candidate in category_defaults.get(category, []):
            if candidate not in names:
                names.append(candidate)
        return names

    @staticmethod
    def _allowed_analysis_types(category: str) -> List[str]:
        mapping = {
            "dc": ["dc"],
            "ac": ["ac"],
            "transient": ["tran"],
            "spectral": ["tran", "fourier"],
            "pvt": ["pvt"],
            "differential": ["ac", "tran"],
        }
        return mapping.get(category, ["dc", "ac", "tran"])

    @staticmethod
    def _allowed_stimulus_types(category: str) -> List[str]:
        mapping = {
            "dc": ["dc"],
            "ac": ["ac"],
            "transient": ["pulse"],
            "spectral": ["sin"],
            "pvt": ["dc"],
            "differential": ["ac", "pulse"],
        }
        return mapping.get(category, ["dc", "ac", "pulse"])
    
    def _get_category_requirements(self, category: str) -> str:
        """Get specific requirements for a test category."""
        
        requirements = {
            "dc": """
- Ensure proper DC biasing (VGS > VTH for MOSFETs)
- Verify operating point (VOUT = VDD/2)
- Measure quiescent current IDD
- Sweep input voltage to find linear range
""",
            "ac": """
- Small-signal analysis (AC magnitude = 1 for transfer function)
- Sweep frequency from 1Hz to 1GHz or higher
- Extract DC gain, -3dB bandwidth, GBW
- Calculate phase margin at GBW
- Measure CMRR and PSRR if applicable
""",
            "transient": """
- Apply pulse input with appropriate rise/fall times
- Measure slew rate (dV/dt max)
- Measure settling time to 1% or 0.1%
- Check for overshoot and ringing
- Verify step response stability
""",
            "pvt": """
- Run simulations across process corners (TT, FF, SS, FS, SF)
- Sweep temperature (-40C, 27C, 125C)
- Vary supply voltage (+/- 10 percent)
- Verify performance across all combinations
""",
            "spectral": """
- Apply sinusoidal input at test frequency
- Run transient long enough for steady state
- Compute FFT of output signal
- Calculate THD from first 9 harmonics
- Measure SFDR (spurious-free dynamic range)
""",
            "differential": """
- For differential circuits, apply differential input
- Measure differential gain Ad = Vout_diff / Vin_diff
- Measure common-mode gain Acm
- Calculate CMRR = |Ad/Acm|
- Measure input common-mode range
""",
        }
        
        return requirements.get(category, "- Follow standard SPICE simulation practices.")
