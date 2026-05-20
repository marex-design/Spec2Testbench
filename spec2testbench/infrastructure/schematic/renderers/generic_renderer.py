from spec2testbench.infrastructure.schematic.renderers.base_renderer import BaseRenderer
from spec2testbench.infrastructure.schematic.graph.networkx_drawer import draw_networkx_graph


class GenericRenderer(BaseRenderer):

    def draw(self, netlist: str, output_path: str) -> str:
        return draw_networkx_graph(netlist, output_path)