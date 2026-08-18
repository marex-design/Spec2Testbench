# Fichier : spec2testbench/schematic/render_engine.py

import os
import schemdraw
import schemdraw.elements as elm
import matplotlib.pyplot as plt

class RenderEngine:
    def __init__(self):
        """
        Moteur de rendu graphique procédural et sémantique pour l'automatisation
        des benchmarks de schémas du framework Spec2Testbench.
        """
        pass

    def _ensure_dir(self, path: str):
        """Garantit la création du dossier de destination s'il est inexistant."""
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

    def parse_netlist_to_dict(self, netlist_path: str) -> dict:
        """
        Analyse le fichier .cir et extrait les instances de composants
        triées par types pour permettre un placement topologique intelligent.
        """
        components = {'V': [], 'R': [], 'C': [], 'L': [], 'M': [], 'I': []}
        if not os.path.exists(netlist_path):
            return components

        with open(netlist_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Ignorer les commentaires, les lignes vides et les directives SPICE
                if not line or line.startswith('*') or line.startswith('.'):
                    continue
                tokens = line.split()
                if len(tokens) < 4:
                    continue
                
                name = tokens[0].upper()
                comp_type = name[0]
                if comp_type in components:
                    components[comp_type].append({
                        'name': name,
                        'n1': tokens[1],
                        'n2': tokens[2],
                        'n3': tokens[3] if len(tokens) > 4 and comp_type == 'M' else None,
                        'value': tokens[3] if comp_type != 'M' else (tokens[4] if len(tokens) > 4 else '')
                    })
        return components

    def draw_from_netlist(self, netlist_path: str, output_path: str):
        """
        Point d'entrée principal automatique. Analyse le nom du benchmark, 
        parse sa netlist et aiguille vers la meilleure stratégie de routage.
        """
        filename = os.path.basename(netlist_path).lower()
        
        # 1. Court-circuiter vers les profiles d'or rédigés ou spécifiques
        if "lowpass_filter" in filename:
            return self.draw_lowpass(output_path)
        elif "cascode_current_mirror" in filename:
            return self.draw_cascode_current_mirror(output_path)
        elif "current_mirror" in filename:
            return self.draw_current_mirror(output_path)
        elif "differential_amplifier" in filename:
            return self.draw_differential_amplifier(output_path)

        # 2. Récupération des données structurelles de la netlist
        circuit_data = self.parse_netlist_to_dict(netlist_path)

        # 3. Stratégie pour la famille des Amplificateurs Monotubulaires/Monocanaux
        if any(amp_tag in filename for amp_tag in ["common_source", "common_gate", "common_drain", "source_follower"]):
            return self.draw_single_stage_amplifier(circuit_data, filename, output_path)

        # 4. Stratégie pour la famille des Filtres Passifs et Réseaux RLC en Cascade
        if any(filt_tag in filename for filt_tag in ["filter", "differentiator", "integrator"]):
            return self.draw_filter_chain(circuit_data, output_path)

        # 5. Routine Fallback de secours (linéaire) si le circuit n'est pas encore classifié
        return self._draw_fallback_linear(circuit_data, output_path)


    # =========================================================================
    # STRATÉGIE 1 : FILTRES PASSIFS EN CASCADE (Passe-haut, Bande, Intégrateur...)
    # =========================================================================
    def draw_lowpass(self, output_path: str):
        """Génère le schéma de référence doré pour le filtre passe-bas."""
        d = schemdraw.Drawing()
        Vin = d.add(elm.SourceV().up().label('Vin', loc='left', ofst=0.2))
        d.add(elm.Ground().at(Vin.start))
        d.add(elm.Line().right().at(Vin.end).length(1.0))
        R1 = d.add(elm.Resistor().right().label('R1', loc='top'))
        d.add(elm.Line().right().length(1.0))
        C1 = d.add(elm.Capacitor().down().label('C1', loc='right'))
        d.add(elm.Ground().at(C1.end))
        d.add(elm.Line().right().at(C1.start).length(1.0).label('out', loc='right'))
        
        self._ensure_dir(output_path)
        d.save(output_path)
        plt.close('all')
        print(f" -> [OK] Filtre passe-bas sauvé : {output_path}")

    def draw_filter_chain(self, data: dict, output_path: str):
        """Génère dynamiquement les autres filtres (R, L, C) sous forme d'échelle propre."""
        d = schemdraw.Drawing()
        
        v_src = data['V'][0]['name'] if data['V'] else 'Vin'
        Vin = d.add(elm.SourceV().up().label(v_src, loc='left', ofst=0.2))
        d.add(elm.Ground().at(Vin.start))
        
        curr_pos = Vin.end
        
        for r in data['R']:
            d.add(elm.Line().right().at(curr_pos).length(0.75))
            res = d.add(elm.Resistor().right().label(f"{r['name']}\n{r['value']}", loc='top'))
            curr_pos = res.end
            
        for l in data['L']:
            d.add(elm.Line().right().at(curr_pos).length(0.75))
            ind = d.add(elm.Inductor().right().label(f"{l['name']}\n{l['value']}", loc='top'))
            curr_pos = ind.end
            
        for c in data['C']:
            d.add(elm.Capacitor().down().at(curr_pos).label(f"{c['name']}\n{c['value']}", loc='right', ofst=0.2))
            d.add(elm.Ground())
            
        d.add(elm.Line().right().at(curr_pos).length(1.0).label('Out', loc='right'))
        
        self._ensure_dir(output_path)
        d.save(output_path)
        plt.close('all')
        print(f" -> [OK] Filtre en cascade généré : {output_path}")


    # =========================================================================
    # STRATÉGIE 2 : MIROIRS DE COURANT
    # =========================================================================
    def draw_current_mirror(self, output_path: str):
        """Génère le schéma doré pour le miroir de courant élémentaire."""
        d = schemdraw.Drawing()
        Vdd = d.add(elm.SourceV().up().label('Vdd', loc='left', ofst=0.2))
        d.add(elm.Ground().at(Vdd.start))
        
        x_start, y_rail = Vdd.end.x, Vdd.end.y
        d.add(elm.Line().right().at((x_start, y_rail)).length(8.0))
        
        # Branche gauche
        pt_iref = (x_start + 3.0, y_rail)
        Iref = d.add(elm.SourceI().down().at(pt_iref).label('Iref', loc='left', ofst=0.3))
        M1 = d.add(elm.NFet(bulk=True).anchor('drain').at(Iref.end).label('M1', loc='right', ofst=0.3))
        d.add(elm.Ground().at(M1.source))
        
        d.add(elm.Line().left().at(M1.drain).length(0.75))
        d.add(elm.Line().down().toy(M1.gate))
        d.add(elm.Line().right().to(M1.gate))
        
        # Branche droite
        pt_rload = (x_start + 6.5, y_rail)
        Rload = d.add(elm.Resistor().down().at(pt_rload).label('Rload', loc='left', ofst=0.3))
        M2 = d.add(elm.NFet(bulk=True).anchor('drain').at(Rload.end).label('M2', loc='right', ofst=0.3))
        d.add(elm.Ground().at(M2.source))
        
        d.add(elm.Line().at(M1.gate).to(M2.gate).color('black'))

        self._ensure_dir(output_path)
        d.save(output_path)
        plt.close('all')
        print(f" -> [OK] Miroir de courant sauvé : {output_path}")

    def draw_cascode_current_mirror(self, output_path: str):
        """Génère le schéma structurel empilé d'un miroir de courant Cascode."""
        d = schemdraw.Drawing()
        Vdd = d.add(elm.SourceV().up().label('Vdd', loc='left', ofst=0.2))
        d.add(elm.Ground().at(Vdd.start))
        
        x_start, y_rail = Vdd.end.x, Vdd.end.y
        d.add(elm.Line().right().at((x_start, y_rail)).length(8.0))
        
        # 1. Branche de référence (Gauche)
        pt_iref = (x_start + 3.0, y_rail)
        Iref = d.add(elm.SourceI().down().at(pt_iref).label('Iref', loc='left', ofst=0.3))
        M1 = d.add(elm.NFet(bulk=True).anchor('drain').at(Iref.end).label('M1', loc='right', ofst=0.3))
        M3 = d.add(elm.NFet(bulk=True).anchor('drain').at(M1.source).label('M3', loc='right', ofst=0.3))
        d.add(elm.Ground().at(M3.source))
        
        d.add(elm.Line().left().at(M1.drain).length(0.5))
        d.add(elm.Line().down().toy(M1.gate))
        d.add(elm.Line().right().to(M1.gate))
        
        d.add(elm.Line().left().at(M3.drain).length(0.5))
        d.add(elm.Line().down().toy(M3.gate))
        d.add(elm.Line().right().to(M3.gate))
        
        # 2. Branche de copie (Droite)
        pt_output = (x_start + 6.5, y_rail)
        out_line = d.add(elm.Line().down().at(pt_output).length(1.0).label('Out', loc='top'))
        M2 = d.add(elm.NFet(bulk=True).anchor('drain').at(out_line.end).label('M2', loc='right', ofst=0.3))
        M4 = d.add(elm.NFet(bulk=True).anchor('drain').at(M2.source).label('M4', loc='right', ofst=0.3))
        d.add(elm.Ground().at(M4.source))
        
        # Connexions horizontales Gate-to-Gate
        d.add(elm.Line().at(M1.gate).to(M2.gate).color('black'))
        d.add(elm.Line().at(M3.gate).to(M4.gate).color('black'))
        
        self._ensure_dir(output_path)
        d.save(output_path)
        plt.close('all')
        print(f" -> [OK] Miroir Cascode enregistré : {output_path}")


    # =========================================================================
    # STRATÉGIE 3 : STRUCTURES À TRANSISTORS SIMPLES (Common Source, Gate, Drain)
    # =========================================================================
    def draw_single_stage_amplifier(self, data: dict, filename: str, output_path: str):
        """Génère un profil CAO vertical standardisé pour les amplificateurs monocanaux."""
        d = schemdraw.Drawing()
        
        if not data['M']:
            return self._draw_fallback_linear(data, output_path)
        M_info = data['M'][0]

        Vdd = d.add(elm.SourceV().up().label('Vdd', loc='left', ofst=0.2))
        d.add(elm.Ground().at(Vdd.start))
        
        x_start = Vdd.end.x
        y_rail = Vdd.end.y
        d.add(elm.Line().right().at((x_start, y_rail)).length(4.5))

        pt_load = (x_start + 3.0, y_rail)
        R_load = next((r for r in data['R'] if 'vdd' in r['n1'].lower() or 'vdd' in r['n2'].lower()), None)
        
        if R_load:
            load_el = d.add(elm.Resistor().down().at(pt_load).label(f"{R_load['name']}\n{R_load['value']}", loc='left', ofst=0.2))
            M1 = d.add(elm.NFet(bulk=True).anchor('drain').at(load_el.end).label(M_info['name'], loc='right', ofst=0.3))
        else:
            M1 = d.add(elm.NFet(bulk=True).at((x_start + 3.0, y_rail - 2.5)).label(M_info['name'], loc='right', ofst=0.3))

        d.add(elm.Ground().at(M1.source))

        if "common_source" in filename or "source_follower" in filename:
            d.add(elm.Line().left().at(M1.gate).length(1.0).label('In', loc='left'))
        elif "common_gate" in filename:
            d.add(elm.Ground().at(M1.gate))
            d.add(elm.Line().left().at(M1.source).length(1.0).label('In', loc='left'))

        out_node = M1.source if "source_follower" in filename else M1.drain
        d.add(elm.Line().right().at(out_node).length(1.2).label('Out', loc='right'))

        self._ensure_dir(output_path)
        d.save(output_path)
        plt.close('all')
        print(f" -> [OK] Amplificateur monocanal standardisé : {output_path}")


    # =========================================================================
    # STRATÉGIE 4 : AMPLIFICATEUR DIFFÉRENTIEL (Paire Symétrique)
    # =========================================================================
    def draw_differential_amplifier(self, output_path: str):
        """Génère un schéma structurel symétrique pour l'étage différentiel."""
        d = schemdraw.Drawing()
        
        x_center = 4.0
        x_left = 2.0
        x_right = 6.0
        y_vdd = 6.0
        
        # Source d'alimentation principale (Vdd) à gauche
        Vdd = d.add(elm.SourceV().up().at((0.0, 2.0)).label('Vdd', loc='left'))
        d.add(elm.Ground().at(Vdd.start))
        
        # Rail horizontal Vdd haute tension
        d.add(elm.Line().at((0.0, y_vdd)).to((x_right + 1.0, y_vdd)))
        
        # Source de courant de queue commune (Tail current)
        tail_source = d.add(elm.SourceI().down().at((x_center, 2.0)).label('Itail', loc='right'))
        d.add(elm.Ground().at(tail_source.end))
        
        # Interconnexion des sources vers la gauche et la droite
        d.add(elm.Line().at(tail_source.start).to((x_left, 2.0)))
        d.add(elm.Line().at(tail_source.start).to((x_right, 2.0)))
        
        # Paire de transistors NMOS d'entrée
        M1 = d.add(elm.NFet(bulk=True).anchor('source').at((x_left, 2.0)).label('M1', loc='left', ofst=0.3))
        M2 = d.add(elm.NFet(bulk=True).anchor('source').at((x_right, 2.0)).flip().label('M2', loc='right', ofst=0.3))
        
        # Entrées différentielles sur les grilles
        d.add(elm.Line().left().at(M1.gate).length(0.75).label('In1', loc='left'))
        d.add(elm.Line().right().at(M2.gate).length(0.75).label('In2', loc='right'))
        
        # Résistances de charge supérieures (R1 et R2) descendues depuis le Vdd
        R1 = d.add(elm.Resistor().down().at((x_left, y_vdd)).toy(M1.drain).label('R1', loc='left'))
        d.add(elm.Line().at(R1.end).to(M1.drain))
        
        R2 = d.add(elm.Resistor().down().at((x_right, y_vdd)).toy(M2.drain).label('R2', loc='right'))
        d.add(elm.Line().at(R2.end).to(M2.drain))
        
        # Prises de tension de sortie sur les drains
        d.add(elm.Line().right().at(M1.drain).length(0.5).label('Out1', loc='top'))
        d.add(elm.Line().left().at(M2.drain).length(0.5).label('Out2', loc='top'))
        
        self._ensure_dir(output_path)
        d.save(output_path)
        plt.close('all')
        print(f" -> [OK] Amplificateur Différentiel structuré avec succès : {output_path}")


    # =========================================================================
    # STRATÉGIE DE RECOURS (FALLBACK)
    # =========================================================================
    def _draw_fallback_linear(self, data: dict, output_path: str):
        """Dessine une ligne topologique simple de manière sécurisée pour éviter les crashs."""
        d = schemdraw.Drawing()
        
        for k, items in data.items():
            for item in items:
                if k == 'V' or k == 'I': 
                    d.add(elm.SourceV().up().label(item['name']))
                elif k == 'R' or k == 'L': 
                    d.add(elm.Resistor().right().label(item['name']))
                elif k == 'C': 
                    cap = d.add(elm.Capacitor().down().label(item['name']))
                    d.add(elm.Ground().at(cap.end))
                elif k == 'M': 
                    d.add(elm.NFet().right().label(item['name'], loc='right'))
                    
        self._ensure_dir(output_path)
        d.save(output_path)
        plt.close('all')
        print(f" -> [!] Rendu linéaire de secours appliqué sans erreur pour : {os.path.basename(output_path)}")