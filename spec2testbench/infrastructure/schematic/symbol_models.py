# Fichier à créer : spec2testbench/schematic/symbol_models.py

from typing import Dict, Tuple, List
from dataclasses import dataclass
import schemdraw.elements as elm

# 1. Définition des "Empreintes" Visuelles
# Ces dictionnaires définissent l'emplacement des broches nommées
# par rapport à l'ancrage central (0,0) du symbole Schemdraw.

SYMBOL_PIN_MAPS = {
    "NFET": {
        "G": (-1.0, 0.0),   # Grille à gauche
        "D": (0.0, 1.0),    # Drain en haut
        "S": (0.0, -1.0),   # Source en bas
        "B": (0.0, -1.0)    # Substrat couplé source par défaut
    },
    "PFET": {
        "G": (-1.0, 0.0),
        "D": (0.0, -1.0),   # Drain en bas (lecture standard PMOS)
        "S": (0.0, 1.0),    # Source en haut
        "B": (0.0, 1.0)
    },
    "RES": {
        "1": (0.0, 1.0),
        "2": (0.0, -1.0)
    },
    "CAP": {
        "1": (0.0, 1.0),
        "2": (0.0, -1.0)
    },
    "VSOURCE": {
        "P": (0.0, 1.0),    # Plus en haut
        "N": (0.0, -1.0)    # Moins en bas
    },
    "ISOURCE": {
        "P": (0.0, 1.0),    # Flèche pointe vers le haut
        "N": (0.0, -1.0)
    }
}

# 2. Classe de Données d'Instance de Composant
# Elle combine l'empreinte visuelle avec sa position absolue
# et ses connexions électriques réelles.

@dataclass
class GraphicComponent:
    name: str                       # ex: "M1", "RD"
    comp_type: str                  # ex: "NFET", "RES"
    nets: Dict[str, str]            # ex: {"G": "in", "D": "out", "S": "0"}
    
    # Données calculées par le futur Moteur de Placement
    position: Tuple[float, float] = (0.0, 0.0)
    rotation: int = 0               # Rotation discrète (0, 90, 180, 270)

    def get_pin_grid_coords(self) -> Dict[str, Tuple[float, float]]:
        """Calcule les coordonnées absolues (X, Y) sur la grille pour chaque broche."""
        pins = SYMBOL_PIN_MAPS.get(self.comp_type, {})
        abs_pins = {}
        
        # Application d'une matrice de rotation discrète
        for pin_name, (rx, ry) in pins.items():
            if self.rotation == 0:   tx, ty = rx, ry
            elif self.rotation == 90:  tx, ty = -ry, rx
            elif self.rotation == 180: tx, ty = -rx, -ry
            elif self.rotation == 270: tx, ty = ry, -rx
            else: tx, ty = rx, ry
            
            abs_pins[pin_name] = (self.position[0] + tx, self.position[1] + ty)
        return abs_pins

    def get_bounding_box(self) -> Tuple[float, float, float, float]:
        """Retourne la boîte de délimitation (min_x, min_y, max_x, max_y) pour le routeur."""
        # Pour simplifier initialement, on prend une boîte de 2x2 centrée.
        # Un moteur final lirait l'empreinte réelle du symbole schemdraw.
        return (self.position[0] - 1.0, self.position[1] - 1.0, 
                self.position[0] + 1.0, self.position[1] + 1.0)