from spec2testbench.infrastructure.schematic.renderers.rc_filter_renderer import RCFilterRenderer
from spec2testbench.infrastructure.schematic.renderers.amplifier_renderer import AmplifierRenderer
from spec2testbench.infrastructure.schematic.renderers.current_mirror_renderer import CurrentMirrorRenderer
from spec2testbench.infrastructure.schematic.renderers.differential_renderer import DifferentialRenderer
from spec2testbench.infrastructure.schematic.renderers.oscillator_renderer import OscillatorRenderer
from spec2testbench.infrastructure.schematic.renderers.diode_circuit_renderer import DiodeCircuitRenderer
from spec2testbench.infrastructure.schematic.renderers.opamp_macro_renderer import OpampMacroRenderer
from spec2testbench.infrastructure.schematic.renderers.behavioral_renderer import BehavioralRenderer
from spec2testbench.infrastructure.schematic.renderers.generic_renderer import GenericRenderer


class RendererFactory:

    def __init__(self):
        self.renderers = {
            "rc_filter_renderer": RCFilterRenderer,
            "amplifier_renderer": AmplifierRenderer,
            "current_mirror_renderer": CurrentMirrorRenderer,
            "differential_renderer": DifferentialRenderer,
            "oscillator_renderer": OscillatorRenderer,
            "diode_circuit_renderer": DiodeCircuitRenderer,
            "opamp_macro_renderer": OpampMacroRenderer,
            "behavioral_renderer": BehavioralRenderer,
            "generic_renderer": GenericRenderer,
        }

    def create(self, renderer_name: str):
        renderer_class = self.renderers.get(renderer_name)

        if renderer_class is None:
            return GenericRenderer()

        return renderer_class()