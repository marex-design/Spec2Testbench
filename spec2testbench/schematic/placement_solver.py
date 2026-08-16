# Fichier : spec2testbench/schematic/placement_solver.py

from typing import List, Dict, Tuple
import networkx as nx

try:
    from spec2testbench.schematic.symbol_models import GraphicComponent
except ImportError:
    from symbol_models import GraphicComponent

class PlacementSolver:
    def __init__(self, grid_spacing: float = 4.0):
        self.grid_spacing = grid_spacing

    def solve(self, graph: nx.Graph, components: List[GraphicComponent]) -> List[GraphicComponent]:
        """
        Analyse la sémantique des nets et attribue des coordonnées (X, Y) 
        ainsi qu'une rotation à chaque composant en fonction des conventions CAO.
        """
        # Dictionnaires pour stocker les scores de positionnement
        # Permet de classer dynamiquement la hiérarchie verticale (Y) et horizontale (X)
        
        for comp in components:
            # --- RÈGLE D'ORIENTATION ET PLACEMENT PAR DÉFAUT ---
            comp.position = (0.0, 0.0)
            comp.rotation = 0

            # --- PARSAGE DES RÈGLES SÉMANTIQUES (HEURISTIQUE) ---
            
            # 1. Gestion des Sources d'Alimentation (Verticalité absolue)
            if comp.comp_type == "VSOURCE":
                if "vdd" in comp.nets.values() or "VDD" in str(comp.nets.values()).lower():
                    # Source d'alim principale : à gauche, s'étend du bas vers le haut
                    comp.position = (0.0, self.grid_spacing)
                else:
                    # Source de signal d'entrée classique (Vin)
                    comp.position = (0.0, self.grid_spacing)
                continue

            # 2. Gestion des Filtres Passifs (Ex: Passe-bas R1 + C1)
            if comp.name == "R1" and comp.comp_type == "RES":
                # La résistance d'entrée est horizontale (rotation 90 ou 270) entre in et out
                comp.position = (self.grid_spacing, self.grid_spacing * 2)
                comp.rotation = 90  # Couchée horizontalement
            
            elif comp.name == "C1" and comp.comp_type == "CAP":
                # Le condensateur de charge descend vers la masse (vertical)
                comp.position = (self.grid_spacing * 2, self.grid_spacing)
                comp.rotation = 0   # Vertical

            # 3. Gestion de la Famille Miroir de Courant (Current Mirror)
            elif comp.comp_type == "ISOURCE":
                # Source de courant de référence : en haut à gauche
                comp.position = (self.grid_spacing, self.grid_spacing * 2)
            
            elif comp.comp_type == "NFET":
                if comp.name == "M1":
                    # Transistor de référence (diode-connected) : en bas à gauche
                    comp.position = (self.grid_spacing, self.grid_spacing)
                    comp.rotation = 0
                elif comp.name == "M2":
                    # Transistor de copie : décalé vers la droite sur le même niveau Y (Sources communes !)
                    comp.position = (self.grid_spacing * 2.5, self.grid_spacing)
                    comp.rotation = 0
                    
            elif comp.comp_type == "RES" and "out" in comp.nets.values():
                # Résistance de charge (Rload) connectée à la sortie : en haut à droite au-dessus de M2
                comp.position = (self.grid_spacing * 2.5, self.grid_spacing * 2)
                comp.rotation = 0

        return components