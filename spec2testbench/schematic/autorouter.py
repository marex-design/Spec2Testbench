# Fichier : spec2testbench/schematic/autorouter.py

from typing import List, Dict, Tuple, Set

try:
    from spec2testbench.schematic.symbol_models import GraphicComponent
except ImportError:
    from symbol_models import GraphicComponent

class Autorouter:
    def __init__(self):
        self.segments: Dict[str, List[Tuple[Tuple[float, float], Tuple[float, float]]]] = {}

    def route_circuit(self, components: List[GraphicComponent]) -> Dict[str, List[Tuple[Tuple[float, float], Tuple[float, float]]]]:
        """
        Calcule les segments de fils orthogonaux pour relier toutes les broches
        partageant le même signal (Net).
        Retourne un dictionnaire : { "nom_du_net": [((x1, y1), (x2, y2)), ...] }
        """
        self.segments = {}
        
        # 1. Cartographier toutes les broches physiques par Net
        net_to_pins: Dict[str, List[Tuple[float, float]]] = {}
        
        for comp in components:
            pin_coords = comp.get_pin_grid_coords()
            for pin_name, net_name in comp.nets.items():
                # On ne route pas le substrat (B) s'il est implicitement lié à la source (S) au même endroit
                if pin_name == "B":
                    continue
                if net_name not in net_to_pins:
                    net_to_pins[net_name] = []
                net_to_pins[net_name].append(pin_coords[pin_name])

        # 2. Générer le routage Manhattan pour chaque Net
        for net_name, pins in net_to_pins.items():
            if len(pins) < 2:
                continue
            
            self.segments[net_name] = []
            
            # Stratégie de l'arbre de connexion minimum simplifié (Séquentiel)
            # On prend le premier point comme ancrage, et on y connecte les autres de façon orthogonale
            anchor = pins[0]
            
            for target in pins[1:]:
                # Si les points ne sont pas alignés, on crée un coude à angle droit (L-routing)
                if anchor[0] != target[0] and anchor[1] != target[1]:
                    # Point de virage intermédiaire (Manhattan)
                    corner = (target[0], anchor[1])
                    self.segments[net_name].append((anchor, corner))
                    self.segments[net_name].append((corner, target))
                else:
                    # Ligne droite directe
                    self.segments[net_name].append((anchor, target))
                    
        return self.segments