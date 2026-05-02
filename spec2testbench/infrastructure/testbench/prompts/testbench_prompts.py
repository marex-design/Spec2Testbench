# spec2testbench/infrastructure/testbench/prompts/testbench_prompts.py

"""
Prompts for LLM-based testbench generation.
"""

from typing import Dict, Any
from ....domain.entities.specification import Specification


class TestBenchPrompts:
    """Collection of prompts for testbench generation."""
    
    def build_category_prompt(self, specification: Specification, category: str) -> str:
        """Build prompt for a specific test category."""
        
        category_requirements = self._get_category_requirements(category)
        context = specification.to_prompt_context()
        
        prompt = '''
You are an expert analog circuit verification engineer specializing in SPICE simulation.

## TASK
Generate a complete PySpice testbench for ''' + category.upper() + ''' verification of the following circuit.

## CIRCUIT SPECIFICATIONS
''' + context + '''

## TEST CATEGORY: ''' + category.upper() + '''

### Requirements for ''' + category.upper() + ''' testing:

''' + category_requirements + '''

## OUTPUT FORMAT
Return a JSON object with the following structure:

{
  "testbench_name": "string",
  "description": "Brief description of this test",
  "stimuli": [
    {
      "name": "stimulus_name",
      "type": "dc|ac|pulse|sin|pwl",
      "node_positive": "1",
      "node_negative": "0",
      "parameters": {
        "value": 1.2,
        "magnitude": 1,
        "frequency": 1e6
      }
    }
  ],
  "analyses": [
    {
      "type": "dc|ac|tran|noise|disto",
      "parameters": {
        "start": 0,
        "stop": 5,
        "step": 0.01
      }
    }
  ],
  "measurements": [
    {
      "name": "measurement_name",
      "expression": "20*log10(V(out)/V(in))",
      "expected_min": 60,
      "expected_max": null,
      "unit": "dB",
      "node": "out"
    }
  ]
}

## EXAMPLE FOR AC AMPLIFIER TEST

{
  "testbench_name": "ac_gain_bandwidth_test",
  "description": "Measure open-loop gain and bandwidth",
  "stimuli": [
    {
      "name": "vin",
      "type": "ac",
      "node_positive": "in",
      "node_negative": "0",
      "parameters": {"magnitude": 1, "phase": 0}
    }
  ],
  "analyses": [
    {
      "type": "ac",
      "parameters": {
        "sweep_type": "dec",
        "points_per_decade": 10,
        "start_freq": 1,
        "stop_freq": 1e9
      }
    }
  ],
  "measurements": [
    {
      "name": "dc_gain",
      "expression": "20*log10(V(out)/V(in))",
      "expected_min": 60,
      "unit": "dB"
    },
    {
      "name": "gbw",
      "expression": "gain * bandwidth",
      "expected_min": 100e6,
      "unit": "Hz"
    }
  ]
}

Generate the testbench now. Return ONLY valid JSON.
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