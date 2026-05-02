# spec2testbench/domain/value_objects/circuit_type.py

from enum import Enum


class CircuitType(Enum):
    """
    Types of analog circuits supported by Spec2TestBench.
    
    Basé sur les 13 types de circuits du benchmark AnalogCoder-Pro :
    - Amplifiers, operational amplifiers, current mirrors
    - Mixers, filters, comparators
    - Oscillators, integrators, differentiators
    - Schmitt triggers, PLL, ADC, DAC, etc.
    """
    
    # ========== AMPLIFIERS (Tasks 1-8, 22-28 dans le benchmark) ==========
    AMPLIFIER = "amplifier"
    """Single-stage or multi-stage amplifier"""
    
    OPERATIONAL_AMPLIFIER = "opamp"
    """Operational amplifier (two-stage, folded cascode, etc.)"""
    
    DIFFERENTIAL_AMPLIFIER = "differential_amplifier"
    """Differential amplifier with active load"""
    
    INSTRUMENTATION_AMPLIFIER = "instrumentation_amplifier"
    """Precision instrumentation amplifier"""
    
    CURRENT_MIRROR = "current_mirror"
    """Basic, cascode, or Wilson current mirror"""
    
    # ========== MIXERS (Task 9 dans le benchmark) ==========
    MIXER = "mixer"
    """Single-transistor or Gilbert cell mixer"""
    
    # ========== FILTERS ==========
    FILTER = "filter"
    """Generic filter (low-pass, high-pass, band-pass, notch)"""
    
    LOW_PASS_FILTER = "low_pass_filter"
    """Low-pass filter (active or passive)"""
    
    HIGH_PASS_FILTER = "high_pass_filter"
    """High-pass filter (active or passive)"""
    
    BAND_PASS_FILTER = "band_pass_filter"
    """Band-pass filter (active or passive)"""
    
    NOTCH_FILTER = "notch_filter"
    """Notch/Band-stop filter"""
    
    # ========== OSCILLATORS (Tasks 10-13 dans le benchmark) ==========
    OSCILLATOR = "oscillator"
    """RC, LC, or crystal oscillator"""
    
    RING_OSCILLATOR = "ring_oscillator"
    """CMOS ring oscillator (3-stage, 5-stage, etc.)"""
    
    COLPITTS_OSCILLATOR = "colpitts_oscillator"
    """Colpitts oscillator (LC tank)"""
    
    RC_PHASE_SHIFT_OSCILLATOR = "rc_phase_shift_oscillator"
    """RC phase-shift oscillator using opamp"""
    
    VCO = "vco"
    """Voltage-Controlled Oscillator"""
    
    # ========== INTEGRATORS & DIFFERENTIATORS ==========
    INTEGRATOR = "integrator"
    """Opamp-based integrator circuit"""
    
    DIFFERENTIATOR = "differentiator"
    """Opamp-based differentiator circuit"""
    
    # ========== COMPARATORS ==========
    COMPARATOR = "comparator"
    """Voltage comparator (open-loop opamp or dedicated)"""
    
    SCHMITT_TRIGGER = "schmitt_trigger"
    """Schmitt trigger with hysteresis (CMOS or BJT)"""
    
    # ========== DATA CONVERTERS ==========
    ADC = "adc"
    """Analog-to-Digital Converter (flash, SAR, sigma-delta)"""
    
    DAC = "dac"
    """Digital-to-Analog Converter (R-2R, current steering)"""
    
    # ========== POWER & REFERENCE ==========
    POWER_SUPPLY = "power_supply"
    """Linear or switching power supply"""
    
    VOLTAGE_REFERENCE = "voltage_reference"
    """Bandgap voltage reference"""
    
    LDO = "ldo"
    """Low-Dropout Regulator"""
    
    # ========== SPECIALTY CIRCUITS ==========
    PLL = "pll"
    """Phase-Locked Loop"""
    
    CHARGE_PUMP = "charge_pump"
    """Charge pump circuit"""
    
    SAMPLE_AND_HOLD = "sample_and_hold"
    """Sample and hold circuit"""
    
    ENVELOPE_DETECTOR = "envelope_detector"
    """Envelope/peak detector"""
    
    # ========== COMPOSITE CIRCUITS (Tasks 9, 22-28) ==========
    COMPOSITE = "composite"
    """Composite circuit using subcircuit library (opamp + feedback)"""
    
    OPAMP_INTEGRATOR = "opamp_integrator"
    """Opamp-based integrator (uses opamp subcircuit)"""
    
    OPAMP_DIFFERENTIATOR = "opamp_differentiator"
    """Opamp-based differentiator (uses opamp subcircuit)"""
    
    OPAMP_FILTER = "opamp_filter"
    """Active filter using opamp subcircuit"""
    
    OPAMP_COMPARATOR = "opamp_comparator"
    """Comparator using opamp in open-loop"""
    
    OPAMP_SCHMITT = "opamp_schmitt"
    """Schmitt trigger using opamp with positive feedback"""
    
    # ========== MAPPING POUR ANALOGCODER-PRO (28 tâches) ==========
    @classmethod
    def from_analogcoder_task(cls, task_number: int) -> "CircuitType":
        """
        Map AnalogCoder-Pro benchmark task number to CircuitType.
        
        Tableau des 28 tâches du benchmark AnalogCoder-Pro :
        - Tasks 1-8: Basic amplifiers, opamps, current mirrors
        - Task 9: Mixer
        - Tasks 10-13: Oscillators
        - Tasks 14-21: Filters, comparators, integrators, differentiators
        - Tasks 22-28: Composite circuits (opamp-based)
        """
        mapping = {
            # Amplifiers (1-8)
            1: cls.AMPLIFIER,
            2: cls.OPERATIONAL_AMPLIFIER,
            3: cls.DIFFERENTIAL_AMPLIFIER,
            4: cls.CURRENT_MIRROR,
            5: cls.AMPLIFIER,
            6: cls.OPERATIONAL_AMPLIFIER,
            7: cls.DIFFERENTIAL_AMPLIFIER,
            8: cls.CURRENT_MIRROR,
            # Mixer (9)
            9: cls.MIXER,
            # Oscillators (10-13)
            10: cls.OSCILLATOR,
            11: cls.RING_OSCILLATOR,
            12: cls.COLPITTS_OSCILLATOR,
            13: cls.RC_PHASE_SHIFT_OSCILLATOR,
            # Filters, comparators (14-21)
            14: cls.LOW_PASS_FILTER,
            15: cls.HIGH_PASS_FILTER,
            16: cls.BAND_PASS_FILTER,
            17: cls.NOTCH_FILTER,
            18: cls.COMPARATOR,
            19: cls.INTEGRATOR,
            20: cls.DIFFERENTIATOR,
            21: cls.SCHMITT_TRIGGER,
            # Composite circuits (22-28) - opamp-based
            22: cls.OPAMP_INTEGRATOR,
            23: cls.OPAMP_DIFFERENTIATOR,
            24: cls.OPAMP_FILTER,
            25: cls.OPAMP_FILTER,
            26: cls.OPAMP_COMPARATOR,
            27: cls.OPAMP_SCHMITT,
            28: cls.COMPOSITE,
        }
        if task_number not in mapping:
            raise ValueError(f"Task {task_number} not in AnalogCoder-Pro benchmark (1-28)")
        return mapping[task_number]
    
    # ========== PROPRIÉTÉS POUR LES CATÉGORIES DE TESTS ==========
    
    def requires_transient_analysis(self) -> bool:
        """Return True if transient analysis is required."""
        transient_circuits = {
            CircuitType.OSCILLATOR,
            CircuitType.RING_OSCILLATOR,
            CircuitType.COLPITTS_OSCILLATOR,
            CircuitType.RC_PHASE_SHIFT_OSCILLATOR,
            CircuitType.VCO,
            CircuitType.COMPARATOR,
            CircuitType.SCHMITT_TRIGGER,
            CircuitType.OPAMP_SCHMITT,
            CircuitType.MIXER,
            CircuitType.INTEGRATOR,
            CircuitType.DIFFERENTIATOR,
            CircuitType.OPAMP_INTEGRATOR,
            CircuitType.OPAMP_DIFFERENTIATOR,
            CircuitType.SAMPLE_AND_HOLD,
            CircuitType.ENVELOPE_DETECTOR,
        }
        return self in transient_circuits
    
    def requires_ac_analysis(self) -> bool:
        """Return True if AC analysis is required."""
        ac_circuits = {
            CircuitType.AMPLIFIER,
            CircuitType.OPERATIONAL_AMPLIFIER,
            CircuitType.DIFFERENTIAL_AMPLIFIER,
            CircuitType.INSTRUMENTATION_AMPLIFIER,
            CircuitType.LOW_PASS_FILTER,
            CircuitType.HIGH_PASS_FILTER,
            CircuitType.BAND_PASS_FILTER,
            CircuitType.NOTCH_FILTER,
            CircuitType.OPAMP_FILTER,
            CircuitType.VOLTAGE_REFERENCE,
            CircuitType.PLL,
        }
        return self in ac_circuits
    
    def requires_spectral_analysis(self) -> bool:
        """Return True if FFT/spectral analysis is required."""
        spectral_circuits = {
            CircuitType.OSCILLATOR,
            CircuitType.RING_OSCILLATOR,
            CircuitType.COLPITTS_OSCILLATOR,
            CircuitType.RC_PHASE_SHIFT_OSCILLATOR,
            CircuitType.VCO,
            CircuitType.MIXER,
            CircuitType.ADC,
            CircuitType.DAC,
            CircuitType.PLL,
        }
        return self in spectral_circuits
    
    def requires_dc_analysis(self) -> bool:
        """Return True if DC analysis is required (almost always True)."""
        # Tous les circuits sauf peut-être les oscillateurs purs
        exclude_dc = {
            CircuitType.OSCILLATOR,
            CircuitType.RING_OSCILLATOR,
            CircuitType.VCO,
        }
        return self not in exclude_dc
    
    def requires_noise_analysis(self) -> bool:
        """Return True if noise analysis is required."""
        noise_circuits = {
            CircuitType.AMPLIFIER,
            CircuitType.OPERATIONAL_AMPLIFIER,
            CircuitType.DIFFERENTIAL_AMPLIFIER,
            CircuitType.INSTRUMENTATION_AMPLIFIER,
            CircuitType.LOW_PASS_FILTER,
            CircuitType.HIGH_PASS_FILTER,
            CircuitType.BAND_PASS_FILTER,
            CircuitType.PLL,
            CircuitType.VCO,
        }
        return self in noise_circuits
    
    def requires_pvt_analysis(self) -> bool:
        """Return True if PVT (Process, Voltage, Temperature) analysis is required."""
        # La plupart des circuits industriels nécessitent PVT
        pvt_circuits = {
            CircuitType.AMPLIFIER,
            CircuitType.OPERATIONAL_AMPLIFIER,
            CircuitType.DIFFERENTIAL_AMPLIFIER,
            CircuitType.INSTRUMENTATION_AMPLIFIER,
            CircuitType.VOLTAGE_REFERENCE,
            CircuitType.LDO,
            CircuitType.PLL,
            CircuitType.ADC,
            CircuitType.DAC,
        }
        return self in pvt_circuits
    
    def is_composite(self) -> bool:
        """Return True if circuit uses subcircuits from library."""
        composite_circuits = {
            CircuitType.COMPOSITE,
            CircuitType.OPAMP_INTEGRATOR,
            CircuitType.OPAMP_DIFFERENTIATOR,
            CircuitType.OPAMP_FILTER,
            CircuitType.OPAMP_COMPARATOR,
            CircuitType.OPAMP_SCHMITT,
            CircuitType.PLL,
            CircuitType.ADC,
            CircuitType.DAC,
        }
        return self in composite_circuits
    
    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        names = {
            # Amplifiers
            CircuitType.AMPLIFIER: "Amplifier",
            CircuitType.OPERATIONAL_AMPLIFIER: "Operational Amplifier",
            CircuitType.DIFFERENTIAL_AMPLIFIER: "Differential Amplifier",
            CircuitType.INSTRUMENTATION_AMPLIFIER: "Instrumentation Amplifier",
            CircuitType.CURRENT_MIRROR: "Current Mirror",
            # Mixers
            CircuitType.MIXER: "Mixer",
            # Filters
            CircuitType.FILTER: "Filter",
            CircuitType.LOW_PASS_FILTER: "Low-Pass Filter",
            CircuitType.HIGH_PASS_FILTER: "High-Pass Filter",
            CircuitType.BAND_PASS_FILTER: "Band-Pass Filter",
            CircuitType.NOTCH_FILTER: "Notch Filter",
            # Oscillators
            CircuitType.OSCILLATOR: "Oscillator",
            CircuitType.RING_OSCILLATOR: "Ring Oscillator",
            CircuitType.COLPITTS_OSCILLATOR: "Colpitts Oscillator",
            CircuitType.RC_PHASE_SHIFT_OSCILLATOR: "RC Phase-Shift Oscillator",
            CircuitType.VCO: "Voltage-Controlled Oscillator",
            # Integrators & Differentiators
            CircuitType.INTEGRATOR: "Integrator",
            CircuitType.DIFFERENTIATOR: "Differentiator",
            # Comparators
            CircuitType.COMPARATOR: "Comparator",
            CircuitType.SCHMITT_TRIGGER: "Schmitt Trigger",
            # Data Converters
            CircuitType.ADC: "Analog-to-Digital Converter",
            CircuitType.DAC: "Digital-to-Analog Converter",
            # Power & Reference
            CircuitType.POWER_SUPPLY: "Power Supply",
            CircuitType.VOLTAGE_REFERENCE: "Voltage Reference",
            CircuitType.LDO: "Low-Dropout Regulator",
            # Specialty
            CircuitType.PLL: "Phase-Locked Loop",
            CircuitType.CHARGE_PUMP: "Charge Pump",
            CircuitType.SAMPLE_AND_HOLD: "Sample and Hold",
            CircuitType.ENVELOPE_DETECTOR: "Envelope Detector",
            # Composite
            CircuitType.COMPOSITE: "Composite Circuit",
            CircuitType.OPAMP_INTEGRATOR: "Opamp Integrator",
            CircuitType.OPAMP_DIFFERENTIATOR: "Opamp Differentiator",
            CircuitType.OPAMP_FILTER: "Active Filter",
            CircuitType.OPAMP_COMPARATOR: "Opamp Comparator",
            CircuitType.OPAMP_SCHMITT: "Opamp Schmitt Trigger",
        }
        return names.get(self, self.value)
    
    @classmethod
    def all_circuit_types(cls) -> list:
        """Return all circuit types."""
        return list(cls)
    
    @classmethod
    def amplifier_types(cls) -> list:
        """Return amplifier circuit types."""
        return [
            cls.AMPLIFIER,
            cls.OPERATIONAL_AMPLIFIER,
            cls.DIFFERENTIAL_AMPLIFIER,
            cls.INSTRUMENTATION_AMPLIFIER,
            cls.CURRENT_MIRROR,
        ]
    
    @classmethod
    def oscillator_types(cls) -> list:
        """Return oscillator circuit types."""
        return [
            cls.OSCILLATOR,
            cls.RING_OSCILLATOR,
            cls.COLPITTS_OSCILLATOR,
            cls.RC_PHASE_SHIFT_OSCILLATOR,
            cls.VCO,
        ]
    
    @classmethod
    def filter_types(cls) -> list:
        """Return filter circuit types."""
        return [
            cls.FILTER,
            cls.LOW_PASS_FILTER,
            cls.HIGH_PASS_FILTER,
            cls.BAND_PASS_FILTER,
            cls.NOTCH_FILTER,
            cls.OPAMP_FILTER,
        ]