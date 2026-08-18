from pathlib import Path

from spec2testbench.infrastructure.schematic.connected_drawer import netlist_to_connected_schematic
from spec2testbench.infrastructure.schematic.topology_drawers.lowpass_filter_drawer import draw_lowpass_filter
from spec2testbench.infrastructure.schematic.topology_drawers.current_mirror_drawer import draw_current_mirror
from spec2testbench.infrastructure.schematic.topology_drawers.differential_pair_drawer import draw_differential_pair
from spec2testbench.infrastructure.schematic.topology_drawers.oscillator_drawer import draw_oscillator


FILTERS = {
    "lowpass_filter",
    "highpass_filter",
    "bandpass_filter",
    "notch_filter",
    "rc_integrator",
    "rc_differentiator",
}

CURRENT_MIRRORS = {
    "current_mirror",
    "cascode_current_mirror",
    "widlar_current_source",
}

DIFFERENTIAL = {
    "differential_amplifier",
    "operational_amplifier",
    "ota",
    "folded_cascode_opamp",
    "two_stage_opamp",
    "instrumentation_amplifier",
}

OSCILLATORS = {
    "ring_oscillator",
    "lc_oscillator",
    "relaxation_oscillator",
    "vco",
}


def infer_circuit_type(netlist_path: str) -> str:
    return Path(netlist_path).stem


def draw_schematic_auto(netlist_path: str, output_path: str) -> str:
    circuit_type = infer_circuit_type(netlist_path)
    netlist = Path(netlist_path).read_text(encoding="utf-8")

    if circuit_type in FILTERS:
        return draw_lowpass_filter(output_path)

    if circuit_type in CURRENT_MIRRORS:
        return draw_current_mirror(output_path)

    if circuit_type in DIFFERENTIAL:
        return draw_differential_pair(output_path)

    if circuit_type in OSCILLATORS:
        return draw_oscillator(output_path)

    return netlist_to_connected_schematic(netlist, output_path)