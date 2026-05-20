from abc import ABC, abstractmethod


class BaseRenderer(ABC):

    @abstractmethod
    def draw(self, netlist: str, output_path: str) -> str:
        pass