try:
    from .simple_drawer import netlist_to_schematic
except ModuleNotFoundError as exc:
    if exc.name != "schemdraw":
        raise

    def netlist_to_schematic(*args, **kwargs):
        raise ModuleNotFoundError(
            "schemdraw is required for netlist_to_schematic(). "
            "Install the optional schematic rendering dependency to use it."
        ) from exc

from .publication_renderer import PublicationSchematicGenerator, PublicationSchematicResult

__all__ = [
    "netlist_to_schematic",
    "PublicationSchematicGenerator",
    "PublicationSchematicResult",
]
