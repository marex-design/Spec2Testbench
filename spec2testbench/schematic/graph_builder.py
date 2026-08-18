# Fichier : spec2testbench/schematic/graph_builder.py

import os
from typing import List, Dict, Tuple
import networkx as nx

# Importation sécurisée du modèle graphique interne
try:
    from spec2testbench.schematic.symbol_models import GraphicComponent
except ImportError:
    # Alternative pour l'exécution directe hors installation globale
    from symbol_models import GraphicComponent


class GraphBuilder:
    def __init__(self):
        self.graph = nx.Graph()
        self.components: List[GraphicComponent] = []

    def parse_netlist_file(self, file_path: str) -> List[GraphicComponent]:
        """
        Analyse une netlist SPICE (.cir / .sp) ligne par ligne, extrait la connectivité
        électrique des composants et renvoie une liste d'instances GraphicComponent typées.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier de netlist est introuvable : {file_path}")

        parsed_components = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Éliminer les lignes vides, commentaires purs (*) et commandes SPICE (.)
                if not line or line.startswith('*') or line.startswith('.'):
                    continue
                    
                # Nettoyer les commentaires inclus en fin de ligne (séparateurs ';' ou '//')
                line = line.split(';')[0].split('//')[0].strip()
                if not line:
                    continue

                # Découpage des arguments par espace
                tokens = line.split()
                if len(tokens) < 3:
                    continue

                comp_name = tokens[0]
                prefix = comp_name[0].upper()

                # --- 1. MOSFETs (Ex: M1 drain gate source bulk model_name [W=... L=...]) ---
                if prefix == 'M':
                    if len(tokens) < 5:
                        continue  # Ligne incomplète
                    nets = {
                        "D": tokens[1],
                        "G": tokens[2],
                        "S": tokens[3],
                        "B": tokens[4]
                    }
                    # Identification sémantique NFET vs PFET basée sur les mots-clés du modèle
                    model_token = tokens[5].upper() if len(tokens) > 5 else ""
                    comp_type = "PFET" if ("P" in model_token or "P" in comp_name.upper()) else "NFET"
                    
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type=comp_type, nets=nets))

                # --- 2. RÉSISTANCES (Ex: R1 nodeA nodeB 10k) ---
                elif prefix == 'R':
                    nets = {
                        "1": tokens[1],
                        "2": tokens[2]
                    }
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type="RES", nets=nets))

                # --- 3. CONDENSATEURS (Ex: C1 nodeA nodeB 100n) ---
                elif prefix == 'C':
                    nets = {
                        "1": tokens[1],
                        "2": tokens[2]
                    }
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type="CAP", nets=nets))

                # --- 4. SOURCES DE TENSION (Ex: VDD vdd 0 DC 5) ---
                elif prefix == 'V':
                    nets = {
                        "P": tokens[1],
                        "N": tokens[2]
                    }
                    parsed_components.append(GraphicComponent(name=comp_name, comp_type="VSOURCE", nets=nets))

                # --- 5. SOURCES DE COURANT (Ex: Iref vdd ref DC 100u) ---
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
        Génère un graphe d'interconnexion biparti NetworkX à partir des composants.
        - Un ensemble de nœuds représente les composants physiques (ex: 'M1').
        - Un autre ensemble représente les équipotentielles / nets (ex: 'out').
        - L'arête contient la métadonnée du nom de la broche cible ('pin').
        """
        self.graph.clear()
        
        for comp in components:
            # Enregistrement du nœud de composant avec son instance en attribut
            self.graph.add_node(
                comp.name, 
                node_type="component", 
                comp_type=comp.comp_type, 
                instance=comp
            )
            
            for pin_name, net_name in comp.nets.items():
                # Création à la volée du nœud de net si absent
                if not self.graph.has_node(net_name):
                    self.graph.add_node(net_name, node_type="net")
                
                # Connexion électrique : Composant <---> Net
                self.graph.add_edge(comp.name, net_name, pin=pin_name)
                
        return self.graph

    def get_summary(self) -> str:
        """Fournit un résumé structurel rapide du graphe généré (Utile pour le débogage)."""
        comp_count = sum(1 for n, d in self.graph.nodes(data=True) if d.get('node_type') == 'component')
        net_count = sum(1 for n, d in self.graph.nodes(data=True) if d.get('node_type') == 'net')
        return f"Graphe Électrique : {comp_count} composants détectés, {net_count} nets (équipotentielles)."