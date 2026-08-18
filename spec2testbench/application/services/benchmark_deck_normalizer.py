"""Immutable-DUT normalization helpers for benchmark execution.

The normalizer externalizes execution directives while preserving topology,
device models, component values and source definitions.  It is intentionally
not a circuit-repair stage.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

IMPLEMENTED_METRICS={
    "minimum_device_drain_current_a","dc_gain_db",
    "inverter_high_input_output_v","inverter_low_input_output_v","inverter_output_separation_v",
    "current_stability_delta_a","minimum_output_current_a",
    "comparator_output_separation_v","comparator_monotonicity_percent",
    "lowpass_attenuation_db","lowpass_monotonicity_percent","highpass_attenuation_db","highpass_monotonicity_percent",
    "bandpass_peak_separation_db","bandstop_notch_depth_db",
    "oscillation_cycle_count","output_swing_v","oscillation_period_cv",
    "integrator_ramp_slope","integrator_linearity","differentiator_output_amplitude_v",
    "hysteresis_width",
}

@dataclass(frozen=True)
class NormalizedDeck:
    original_path: str
    original_sha256: str
    text: str
    topology_and_values_preserved: bool=True


def _sha(text: bytes)->str: return sha256(text).hexdigest()

def externalize_execution_directives(text: str)->str:
    out=[]; control=False
    for raw in text.splitlines():
        low=raw.strip().lower()
        if low==".control": control=True; continue
        if control:
            if low==".endc": control=False
            continue
        if re.match(r"^\s*\.(?:op|dc|ac|tran|four|noise|tf|sens|print|plot|measure|meas|save|wrdata)\b",raw,re.I): continue
        if low==".end": continue
        out.append(raw)
    return "\n".join(out).rstrip()+"\n"

def normalize_benchmark_deck(path: str|Path)->NormalizedDeck:
    p=Path(path); raw=p.read_bytes(); text=raw.decode("utf-8",errors="replace")
    return NormalizedDeck(str(p),_sha(raw),externalize_execution_directives(text),True)
