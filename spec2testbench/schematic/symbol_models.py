# Fichier : spec2testbench/schematic/symbol_models.py

from typing import Dict, Tuple, List
from dataclasses import dataclass

# Dictionnaire de référence des positions relatives des broches (Offsets)
# On considère l'ancrage central du symbole à (0.0, 0.0)
SYMBOL_PIN_MAPS = {
    "NFET": {
        "G": (-1.0, 0.0),   # Grille à gauche
        "D": (0.0, 1.0),    # Drain en haut
        "S": (0.0, -1.0),   # Source en bas
        "B": (0.0, -1.0)    # Substrat connecté à la source par défaut
    },
    "PFET": {
        "G": (-1.0, 0.0),   # Grille à gauche
        "D": (0.0, -1.0),   # Drain en bas (lecture d'un PMOS classique)
        "S": (0.0, 1.0),    # Source en haut
        "B": (0.0, 1.0)     # Substrat connecté à la source
    },
    "RES": {
        "1": (0.0, 1.0),    # Broche 1 en haut
        "2": (0.0, -1.0)    # Broche 2 en bas
    },
    "CAP": {
        "1": (0.0, 1.0),    # Broche 1 en haut
        "2": (0.0, -1.0)    # Broche 2 en bas
    },
    "VSOURCE": {
        "P": (0.0, 1.0),    # Borne positive en haut
        "N": (0.0, -1.0)    # Borne négative en bas
    },
    "ISOURCE": {
        "P": (0.0, 1.0),    # Sortie du courant (flèche vers le haut)
        "N": (0.0, -1.0)    # Entrée du courant
    }
}

@dataclass
class GraphicComponent:
    name: str                       # Identifiant unique (ex: "M1", "R1", "Vinput")
    comp_type: str                  # Type de composant (ex: "NFET", "PFET", "RES", etc.)
    nets: Dict[str, str]            # Dictionnaire de connectivité : {"Nom_Broche": "Nom_Net"}
    
    # Coordonnées et orientation calculées plus tard par le Placement Solver
    position: Tuple[float, float] = (0.0, 0.0)
    rotation: int = 0               # Valeurs autorisées : 0, 90, 180, 270 degrés

    def get_pin_grid_coords(self) -> Dict[str, Tuple[float, float]]:
        """
        Calcule et retourne les coordonnées absolues (X, Y) sur le schéma 
        pour chaque broche du composant, en appliquant la rotation discrète.
        """
        pins = SYMBOL_PIN_MAPS.get(self.comp_type, {})
        abs_pins = {}
        
        for pin_name, (rx, ry) in pins.items():
            # Application d'une matrice de rotation 2D standard pour les angles multiples de 90°
            if self.rotation == 0:
                tx, ty = rx, ry
            elif self.rotation == 90:
                tx, ty = -ry, rx
            elif self.rotation == 180:
                tx, ty = -rx, -ry
            elif self.rotation == 270:
                tx, ty = ry, -rx
            else:
                tx, ty = rx, ry  # Par défaut pas de rotation si valeur invalide
            
            # Position finale absolue = Centre du composant + Offset avec rotation
            abs_pins[pin_name] = (self.position[0] + tx, self.position[1] + ty)
            
        return abs_pins

    def get_bounding_box(self) -> Tuple[float, float, float, float]:
        """
        Retourne la boîte de délimitation (min_x, min_y, max_x, max_y) du composant.
        Utile pour que l'autorouteur considère le composant comme un obstacle géométrique.
        """
        # Taille standard par défaut de 2x2 unités centrée sur la position du composant
        return (
            self.position[0] - 1.0, 
            self.position[1] - 1.0, 
            self.position[0] + 1.0, 
            self.position[1] + 1.0
        )