from spec2testbench.infrastructure.schematic.synthesis.graph_builder import GraphBuilder
from spec2testbench.infrastructure.schematic.synthesis.topology_matcher import TopologyMatcher
from spec2testbench.infrastructure.schematic.synthesis.constraint_engine import ConstraintEngine
from spec2testbench.infrastructure.schematic.synthesis.placement_solver import PlacementSolver
from spec2testbench.infrastructure.schematic.synthesis.autorouter import AutoRouter
from spec2testbench.infrastructure.schematic.synthesis.render_engine import RenderEngine


class SchematicSynthesizer:
    def synthesize(self, netlist: str, output_path: str, source_name: str | None = None) -> str:
        graph = GraphBuilder().build(netlist)
        graph.raw_netlist = netlist

        topology = TopologyMatcher().match(graph, source_name=source_name)

        constraints = ConstraintEngine().build_constraints(topology, graph)

        placement = PlacementSolver().solve(topology, graph, constraints)

        routes = AutoRouter().route(topology, graph, placement)

        return RenderEngine().render(
            topology=topology,
            graph=graph,
            placement=placement,
            routes=routes,
            output_path=output_path,
        )