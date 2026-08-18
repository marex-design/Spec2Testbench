from dataclasses import dataclass
from pathlib import Path


@dataclass
class TopologyMatch:
    name: str
    family: str


class TopologyMatcher:
    def match(self, graph, source_name: str | None = None) -> TopologyMatch:
        if source_name:
            name = Path(source_name).stem.lower()

            if name in {
                "lowpass_filter",
                "highpass_filter",
                "bandpass_filter",
                "notch_filter",
                "rc_integrator",
                "rc_differentiator",
            }:
                return TopologyMatch(name, "rc_filter")

            if name in {
                "current_mirror",
                "cascode_current_mirror",
                "widlar_current_source",
            }:
                return TopologyMatch(name, "current_mirror")

            if name in {
                "differential_amplifier",
                "ota",
                "folded_cascode_opamp",
                "two_stage_opamp",
                "instrumentation_amplifier",
            }:
                return TopologyMatch(name, "differential")

            if name in {
                "common_source_amplifier",
                "common_drain_amplifier",
                "common_gate_amplifier",
                "source_follower",
                "lna",
                "active_load_amplifier",
            }:
                return TopologyMatch(name, "amplifier")

            if name in {
                "ring_oscillator",
                "lc_oscillator",
                "relaxation_oscillator",
                "vco",
            }:
                return TopologyMatch(name, "oscillator")

            if name in {
                "rectifier",
                "peak_detector",
                "voltage_reference",
                "bandgap_reference",
                "charge_pump",
            }:
                return TopologyMatch(name, "diode")

            if name in {
                "comparator",
                "schmitt_trigger",
                "mixer",
                "sample_and_hold",
            }:
                return TopologyMatch(name, "behavioral")

            if name in {
                "operational_amplifier",
                "transimpedance_amplifier",
            }:
                return TopologyMatch(name, "opamp_macro")

        r = len(graph.by_kind("R"))
        c = len(graph.by_kind("C"))
        l = len(graph.by_kind("L"))
        d = len(graph.by_kind("D"))
        m = len(graph.by_kind("M"))
        b = len(graph.by_kind("B"))
        e = len(graph.by_kind("E"))
        g = len(graph.by_kind("G"))

        if r >= 1 and c >= 1 and m == 0 and d == 0:
            return TopologyMatch("rc_network", "rc_filter")

        if m >= 2 and len(graph.by_kind("I")) >= 1:
            return TopologyMatch("mos_current_or_diff", "current_mirror")

        if l >= 1 and c >= 1:
            return TopologyMatch("lc_network", "oscillator")

        if d >= 1:
            return TopologyMatch("diode_network", "diode")

        if b >= 1 or e >= 1 or g >= 1:
            return TopologyMatch("behavioral_macro", "behavioral")

        return TopologyMatch("generic", "generic")