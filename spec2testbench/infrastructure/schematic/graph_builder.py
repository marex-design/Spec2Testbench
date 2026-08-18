# Fichier : spec2testbench/schematic/graph_builder.py

import os
import re
from typing import List, Dict, Tuple
import networkx as nx

# Importation de notre modèle graphique défini à l'étape précédente
try:
    from spec2testbench.schematic.symbol_models import GraphicComponent
except ImportError:
    # Fallback si le module n'est pas encore packagé globalement
    from symbol_models import GraphicComponent

class GraphBuilder:
    def __init__(self):
        self.graph = nx.Graph()
        self.components: List[GraphicComponent] = []

    def parse_netlist_file(self, file_path: str) -> List[GraphicComponent]:
        """
        Lit un fichier de netlist SPICE, ignore les commentaires/commandes,
        et extrait les instances de composants graphiques typés.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier de netlist est introuvable : {file_path}")

        parsed_components = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Ignorer les lignes vides, les commentaires SPICE (*) et les commandes (.model, .tran, etc.)
                if not line or line.startswith('*') or line.startswith('.'):
                    continue
                    
                # Nettoyer les commentaires en fin de ligne (séparés par un point-virgule ou double slash)
                line = line.split(';')[0].split('//')[0].strip()
                if not line:
                    continue

                # Découper la ligne par espaces
                tokens = line.split()
                if len(tokens) < 3:
                    continue

                comp_name = tokens[0]
                prefix = comp_name[0].upper()

                # --- 1. Gestion des MOSFETs (Ex: M1 drain gate source bulk model_name [W=... L=...]) ---
                if prefix == 'M':
                    if len(tokens) < 5:
                        continue  # Ligne mal formée pour un transistor
                    nets = {
                        "D": tokens[1],
                        "G": tokens[2],
                        "S": tokens[3],
                        "B": tokens[4]
                    }
                    # Détection automatique du type NFET/PFET basée sur le nom du modèle ou du composant
                    # Par convention, on cherche 'P' ou 'N' dans le nom du modèle (ex: NMOS, PMOS, nch, pch)
                    model_token = tokens[5].upper() if len(tokens) > 5 else ""
                    comp_type = "PFET" if ("P" in model_token or "P" in comp_name.upper()) else "NFET"
                    
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type=comp_type, nets=nets))

                # --- 2. Gestion des Résistances (Ex: R1 nodeA nodeB 10k) ---
                elif prefix == 'R':
                    nets = {
                        "1": tokens[1],
                        "2": tokens[2]
                    }
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type="RES", nets=nets))

                # --- 3. Gestion des Condensateurs (Ex: C1 nodeA nodeB 100n) ---
                elif prefix == 'C':
                    nets = {
                        "1": tokens[1],
                        "2": tokens[2]
                    }
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type="CAP", nets=nets))

                # --- 4. Gestion des Sources de Tension (Ex: VDD vdd 0 DC 5) ---
                elif prefix == 'V':
                    nets = {
                        "P": tokens[1],
                        "N": tokens[2]
                    }
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type="VSOURCE", nets=nets))

                # --- 5. Gestion des Sources de Courant (Ex: Iref vdd ref DC 100u) ---
                elif prefix == 'I':
                    nets = {
                        "P": tokens[1],
                        "N": tokens[2]
                    }
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type="ISOURCE", nets=nets))

        self.components = parsed_components
        return parsed_components

    def build_bipartite_graph(self, components: List[GraphicComponent]) -> nx.Graph:
        """
        Génère un graphe biparti NetworkX.
        Nœuds de type 1 : Les composants physiques (ex: 'M1', 'R1')
        Nœuds de type 2 : Les équipotentielles électriques / fils (ex: 'in', 'out', '0')
        Les arêtes stockent le nom de la broche ('pin') intermédiaire.
        """
        self.graph.clear()
        
        for comp in components:
            # Ajouter le nœud de composant avec ses caractéristiques structurelles
            self.graph.add_node(
                comp.name, 
                node_type="component", 
                comp_type=comp.comp_type, 
                instance=comp
            )
            
            for pin_name, net_name in comp.nets.items():
                # Ajouter le nœud de net s'il n'existe pas encore
                if not self.graph.has_node(net_name):
                    self.graph.add_node(net_name, node_type="net")
                
                # Relier le composant au net en enregistrant la broche cible
                self.graph.add_edge(comp.name, net_name, pin=pin_name)
                
        return self.graph

    def get_summary(self) -> str:
        """Retourne un résumé textuel de la topologie du graphe pour le debug."""
        comp_count = sum(1 for n, d in self.graph.nodes(data=True) if d.get('node_type') == 'component')
        net_count = sum(1 for n, d in self.graph.nodes(data=True) if d.get('node_type') == 'net')
        return f"Graphe Électrique : {comp_count} composants, {net_count} nets (équipotentielles)."