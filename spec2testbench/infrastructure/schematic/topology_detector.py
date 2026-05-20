from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TopologyInfo:
    circuit_type: str
    family: str
    renderer: str
    description: str


class TopologyDetector:
    CIRCUIT_TOPOLOGY_MAP = {
        "lowpass_filter": TopologyInfo(
            "lowpass_filter",
            "rc_filter",
            "rc_filter_renderer",
            "RC low-pass filter",
        ),
        "highpass_filter": TopologyInfo(
            "highpass_filter",
            "rc_filter",
            "rc_filter_renderer",
            "RC high-pass filter",
        ),
        "bandpass_filter": TopologyInfo(
            "bandpass_filter",
            "rc_filter",
            "rc_filter_renderer",
            "RC band-pass filter",
        ),
        "notch_filter": TopologyInfo(
            "notch_filter",
            "rc_filter",
            "rc_filter_renderer",
            "RC notch filter",
        ),
        "rc_integrator": TopologyInfo(
            "rc_integrator",
            "rc_filter",
            "rc_filter_renderer",
            "RC integrator",
        ),
        "rc_differentiator": TopologyInfo(
            "rc_differentiator",
            "rc_filter",
            "rc_filter_renderer",
            "RC differentiator",
        ),

        "common_source_amplifier": TopologyInfo(
            "common_source_amplifier",
            "amplifier",
            "amplifier_renderer",
            "Common-source amplifier",
        ),
        "common_drain_amplifier": TopologyInfo(
            "common_drain_amplifier",
            "amplifier",
            "amplifier_renderer",
            "Common-drain amplifier",
        ),
        "common_gate_amplifier": TopologyInfo(
            "common_gate_amplifier",
            "amplifier",
            "amplifier_renderer",
            "Common-gate amplifier",
        ),
        "source_follower": TopologyInfo(
            "source_follower",
            "amplifier",
            "amplifier_renderer",
            "Source follower",
        ),
        "lna": TopologyInfo(
            "lna",
            "amplifier",
            "amplifier_renderer",
            "Low-noise amplifier",
        ),
        "active_load_amplifier": TopologyInfo(
            "active_load_amplifier",
            "amplifier",
            "amplifier_renderer",
            "Amplifier with active load",
        ),

        "current_mirror": TopologyInfo(
            "current_mirror",
            "current_mirror",
            "current_mirror_renderer",
            "Basic current mirror",
        ),
        "cascode_current_mirror": TopologyInfo(
            "cascode_current_mirror",
            "current_mirror",
            "current_mirror_renderer",
            "Cascode current mirror",
        ),
        "widlar_current_source": TopologyInfo(
            "widlar_current_source",
            "current_mirror",
            "current_mirror_renderer",
            "Widlar current source",
        ),

        "differential_amplifier": TopologyInfo(
            "differential_amplifier",
            "differential",
            "differential_renderer",
            "Differential amplifier",
        ),
        "ota": TopologyInfo(
            "ota",
            "differential",
            "differential_renderer",
            "Operational transconductance amplifier",
        ),
        "folded_cascode_opamp": TopologyInfo(
            "folded_cascode_opamp",
            "differential",
            "differential_renderer",
            "Folded-cascode operational amplifier",
        ),
        "two_stage_opamp": TopologyInfo(
            "two_stage_opamp",
            "differential",
            "differential_renderer",
            "Two-stage operational amplifier",
        ),
        "instrumentation_amplifier": TopologyInfo(
            "instrumentation_amplifier",
            "differential",
            "differential_renderer",
            "Instrumentation amplifier",
        ),

        "operational_amplifier": TopologyInfo(
            "operational_amplifier",
            "opamp_macro",
            "opamp_macro_renderer",
            "Operational amplifier macro-model",
        ),
        "transimpedance_amplifier": TopologyInfo(
            "transimpedance_amplifier",
            "opamp_macro",
            "opamp_macro_renderer",
            "Transimpedance amplifier",
        ),

        "ring_oscillator": TopologyInfo(
            "ring_oscillator",
            "oscillator",
            "oscillator_renderer",
            "Ring oscillator",
        ),
        "lc_oscillator": TopologyInfo(
            "lc_oscillator",
            "oscillator",
            "oscillator_renderer",
            "LC oscillator",
        ),
        "relaxation_oscillator": TopologyInfo(
            "relaxation_oscillator",
            "oscillator",
            "oscillator_renderer",
            "Relaxation oscillator",
        ),
        "vco": TopologyInfo(
            "vco",
            "oscillator",
            "oscillator_renderer",
            "Voltage-controlled oscillator",
        ),

        "rectifier": TopologyInfo(
            "rectifier",
            "diode_circuit",
            "diode_circuit_renderer",
            "Rectifier circuit",
        ),
        "peak_detector": TopologyInfo(
            "peak_detector",
            "diode_circuit",
            "diode_circuit_renderer",
            "Peak detector",
        ),
        "voltage_reference": TopologyInfo(
            "voltage_reference",
            "diode_circuit",
            "diode_circuit_renderer",
            "Voltage reference",
        ),
        "bandgap_reference": TopologyInfo(
            "bandgap_reference",
            "diode_circuit",
            "diode_circuit_renderer",
            "Bandgap-like reference",
        ),
        "charge_pump": TopologyInfo(
            "charge_pump",
            "diode_circuit",
            "diode_circuit_renderer",
            "Charge pump",
        ),

        "comparator": TopologyInfo(
            "comparator",
            "behavioral",
            "behavioral_renderer",
            "Comparator",
        ),
        "schmitt_trigger": TopologyInfo(
            "schmitt_trigger",
            "behavioral",
            "behavioral_renderer",
            "Schmitt trigger",
        ),
        "mixer": TopologyInfo(
            "mixer",
            "behavioral",
            "behavioral_renderer",
            "Mixer",
        ),
        "sample_and_hold": TopologyInfo(
            "sample_and_hold",
            "behavioral",
            "behavioral_renderer",
            "Sample and hold",
        ),
    }

    def detect_from_name(self, name: str) -> TopologyInfo:
        circuit_type = Path(name).stem.lower()

        if circuit_type in self.CIRCUIT_TOPOLOGY_MAP:
            return self.CIRCUIT_TOPOLOGY_MAP[circuit_type]

        return TopologyInfo(
            circuit_type=circuit_type,
            family="generic",
            renderer="generic_renderer",
            description="Generic unknown analog circuit",
        )

    def detect_from_path(self, path: str) -> TopologyInfo:
        return self.detect_from_name(Path(path).stem)

    def detect_from_parsed(self, parsed) -> TopologyInfo:
        component_types = [c.type.upper() for c in parsed.components]

        r_count = component_types.count("R")
        c_count = component_types.count("C")
        l_count = component_types.count("L")
        v_count = component_types.count("V")
        i_count = component_types.count("I")
        d_count = component_types.count("D")
        m_count = component_types.count("M")
        b_count = component_types.count("B")
        e_count = component_types.count("E")
        g_count = component_types.count("G")
        s_count = component_types.count("S")

        if r_count >= 1 and c_count >= 1 and v_count >= 1 and m_count == 0:
            return TopologyInfo(
                circuit_type="rc_network",
                family="rc_filter",
                renderer="rc_filter_renderer",
                description="Detected RC network",
            )

        if m_count >= 2 and i_count >= 1:
            return TopologyInfo(
                circuit_type="current_mirror_or_diffpair",
                family="current_mirror",
                renderer="current_mirror_renderer",
                description="Detected MOS current-source-like structure",
            )

        if m_count >= 2 and ("in_p" in self._all_nodes(parsed) or "in_n" in self._all_nodes(parsed)):
            return TopologyInfo(
                circuit_type="differential_structure",
                family="differential",
                renderer="differential_renderer",
                description="Detected differential MOS structure",
            )

        if l_count >= 1 and c_count >= 1:
            return TopologyInfo(
                circuit_type="lc_network",
                family="oscillator",
                renderer="oscillator_renderer",
                description="Detected LC network",
            )

        if d_count >= 1:
            return TopologyInfo(
                circuit_type="diode_network",
                family="diode_circuit",
                renderer="diode_circuit_renderer",
                description="Detected diode-based network",
            )

        if b_count >= 1 or e_count >= 1 or g_count >= 1 or s_count >= 1:
            return TopologyInfo(
                circuit_type="behavioral_or_macro",
                family="behavioral",
                renderer="behavioral_renderer",
                description="Detected behavioral or controlled-source macro-model",
            )

        return TopologyInfo(
            circuit_type="generic",
            family="generic",
            renderer="generic_renderer",
            description="Generic topology inferred from parsed netlist",
        )

    def supported_circuit_count(self) -> int:
        return len(self.CIRCUIT_TOPOLOGY_MAP)

    def supported_families(self) -> list[str]:
        return sorted({info.family for info in self.CIRCUIT_TOPOLOGY_MAP.values()})

    def circuits_by_family(self) -> dict[str, list[str]]:
        families: dict[str, list[str]] = {}

        for circuit, info in self.CIRCUIT_TOPOLOGY_MAP.items():
            families.setdefault(info.family, []).append(circuit)

        return families

    def validate_coverage(self) -> bool:
        return self.supported_circuit_count() == 35

    def _all_nodes(self, parsed) -> list[str]:
        nodes = []

        for c in parsed.components:
            for node in c.nodes:
                nodes.append(node.lower())

        return nodes