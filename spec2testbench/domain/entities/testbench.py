# spec2testbench/domain/entities/testbench.py

"""
TestBench Entity - Représente un plan de test exécutable.
Produit par le module TestBenchGen, consommé par le simulateur.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class AnalysisType(Enum):
    """Types d'analyse SPICE supportés."""
    DC = "dc"
    AC = "ac"
    TRANSIENT = "tran"
    NOISE = "noise"
    DISTORTION = "disto"
    SENSITIVITY = "sens"
    TRANSFER_FUNCTION = "tf"
    FOURIER = "fourier"
    MONTE_CARLO = "mc"
    PVT = "pvt"  # Process, Voltage, Temperature


class SweepType(Enum):
    """Types de balayage pour les analyses AC et DC."""
    LINEAR = "lin"
    DECADE = "dec"
    OCTAVE = "oct"


@dataclass
class Stimulus:
    """
    Stimulus d'entrée pour la simulation.
    
    Exemple:
        Stimulus(
            name="vin",
            type="sin",
            parameters={"amplitude": 1, "frequency": 1e6, "offset": 0}
        )
    """
    
    name: str
    """Nom du stimulus (ex: 'vin', 'vclk')"""
    
    type: str
    """Type: 'dc', 'ac', 'pulse', 'sin', 'pwl', 'exp', 'sffm'"""
    
    parameters: Dict[str, Any] = field(default_factory=dict)
    """Paramètres spécifiques au type de stimulus"""
    
    node_positive: str = "1"
    """Noeud positif (par défaut: '1')"""
    
    node_negative: str = "0"
    """Noeud négatif (par défaut: '0')"""
    
    def to_pyspice(self) -> str:
        """
        Convertit le stimulus en code PySpice.
        
        Returns:
            Code Python/PySpice pour créer ce stimulus
        """
        if self.type == "dc":
            return f"circuit.V('{self.name}', '{self.node_positive}', '{self.node_negative}', dc_value={self.parameters.get('value', 0)})"
        
        elif self.type == "ac":
            mag = self.parameters.get('magnitude', 1)
            phase = self.parameters.get('phase', 0)
            return f"circuit.V('{self.name}', '{self.node_positive}', '{self.node_negative}', ac={mag})"
        
        elif self.type == "pulse":
            v1 = self.parameters.get('v1', 0)
            v2 = self.parameters.get('v2', 5)
            td = self.parameters.get('delay', 0)
            tr = self.parameters.get('rise', '1n')
            tf = self.parameters.get('fall', '1n')
            pw = self.parameters.get('width', '1u')
            period = self.parameters.get('period', '2u')
            return f"circuit.PulseVoltageSource('{self.name}', '{self.node_positive}', '{self.node_negative}', initial_value={v1}, pulsed_value={v2}, delay_time={td}, rise_time={tr}, fall_time={tf}, pulse_width={pw}, period={period})"
        
        elif self.type == "sin":
            offset = self.parameters.get('offset', 0)
            amplitude = self.parameters.get('amplitude', 1)
            frequency = self.parameters.get('frequency', 1e6)
            return f"circuit.SinusoidalVoltageSource('{self.name}', '{self.node_positive}', '{self.node_negative}', offset={offset}, amplitude={amplitude}, frequency={frequency})"
        
        elif self.type == "pwl":
            # PWL: list of (time, value) pairs
            points = self.parameters.get('points', [])
            if not points:
                return f"circuit.V('{self.name}', '{self.node_positive}', '{self.node_negative}')"
            
            pwl_str = ", ".join([f"({t}, {v})" for t, v in points])
            return f"circuit.PieceWiseLinearVoltageSource('{self.name}', '{self.node_positive}', '{self.node_negative}', values=[{pwl_str}])"
        
        else:
            # Default: simple DC voltage source
            return f"circuit.V('{self.name}', '{self.node_positive}', '{self.node_negative}', {self.parameters.get('value', 0)})"
    
    def to_spice(self) -> str:
        """
        Convertit le stimulus en format SPICE classique.
        
        Returns:
            Ligne SPICE pour ce stimulus
        """
        if self.type == "dc":
            return f"V{self.name} {self.node_positive} {self.node_negative} {self.parameters.get('value', 0)}"
        
        elif self.type == "ac":
            mag = self.parameters.get('magnitude', 1)
            return f"V{self.name} {self.node_positive} {self.node_negative} AC {mag}"
        
        elif self.type == "pulse":
            v1 = self.parameters.get('v1', 0)
            v2 = self.parameters.get('v2', 5)
            td = self.parameters.get('delay', 0)
            tr = self.parameters.get('rise', '1N')
            tf = self.parameters.get('fall', '1N')
            pw = self.parameters.get('width', '1U')
            period = self.parameters.get('period', '2U')
            return f"V{self.name} {self.node_positive} {self.node_negative} PULSE({v1} {v2} {td} {tr} {tf} {pw} {period})"
        
        elif self.type == "sin":
            offset = self.parameters.get('offset', 0)
            amplitude = self.parameters.get('amplitude', 1)
            frequency = self.parameters.get('frequency', 1e6)
            return f"V{self.name} {self.node_positive} {self.node_negative} SIN({offset} {amplitude} {frequency})"
        
        else:
            return f"V{self.name} {self.node_positive} {self.node_negative} {self.parameters.get('value', 0)}"


@dataclass
class AnalysisConfig:
    """
    Configuration d'une analyse SPICE.
    
    Exemple:
        AnalysisConfig(
            type=AnalysisType.AC,
            parameters={
                "sweep_type": "dec",
                "points_per_decade": 10,
                "start_freq": 1,
                "stop_freq": 1e9
            }
        )
    """
    
    type: AnalysisType
    """Type d'analyse (DC, AC, TRANSIENT, etc.)"""
    
    parameters: Dict[str, Any] = field(default_factory=dict)
    """Paramètres spécifiques à l'analyse"""
    
    def to_pyspice(self) -> str:
        """
        Convertit l'analyse en code PySpice.
        
        Returns:
            Code Python/PySpice pour exécuter cette analyse
        """
        if self.type == AnalysisType.DC:
            source = self.parameters.get('source', 'VIN')
            start = self.parameters.get('start', 0)
            stop = self.parameters.get('stop', 5)
            step = self.parameters.get('step', 0.01)
            return f"analysis = simulator.dc({source}=({start}, {stop}, {step}))"
        
        elif self.type == AnalysisType.AC:
            sweep = self.parameters.get('sweep_type', 'dec')
            npd = self.parameters.get('points_per_decade', 10)
            fstart = self.parameters.get('start_freq', 1)
            fstop = self.parameters.get('stop_freq', 1e9)
            return f"analysis = simulator.ac({sweep}, {npd}, {fstart}, {fstop})"
        
        elif self.type == AnalysisType.TRANSIENT:
            step = self.parameters.get('step_time', '1n')
            stop = self.parameters.get('end_time', '100n')
            start = self.parameters.get('start_time', 0)
            uic = self.parameters.get('use_initial_conditions', False)
            uic_str = ", uic=True" if uic else ""
            return f"analysis = simulator.transient(step_time={step}, end_time={stop}, start_time={start}{uic_str})"
        
        elif self.type == AnalysisType.NOISE:
            output = self.parameters.get('output', 'Vout')
            source = self.parameters.get('input_source', 'VIN')
            points = self.parameters.get('points_per_summary', 10)
            return f"analysis = simulator.noise(output={output}, input_source={source}, points_per_summary={points})"
        
        elif self.type == AnalysisType.PVT:
            # PVT est un cas spécial - simulation à plusieurs corners/températures
            corners = self.parameters.get('corners', ['TT'])
            temps = self.parameters.get('temperatures', [27])
            return f"# PVT Analysis: corners={corners}, temps={temps}"
        
        else:
            return f"# Analysis {self.type.value} not yet implemented"
    
    def to_spice(self) -> str:
        """
        Convertit l'analyse en commande SPICE.
        
        Returns:
            Ligne de commande SPICE
        """
        if self.type == AnalysisType.DC:
            source = self.parameters.get('source', 'VIN')
            start = self.parameters.get('start', 0)
            stop = self.parameters.get('stop', 5)
            step = self.parameters.get('step', 0.01)
            return f".DC {source} {start} {stop} {step}"
        
        elif self.type == AnalysisType.AC:
            sweep = self.parameters.get('sweep_type', 'DEC')
            npd = self.parameters.get('points_per_decade', 10)
            fstart = self.parameters.get('start_freq', 1)
            fstop = self.parameters.get('stop_freq', 1E9)
            return f".AC {sweep} {npd} {fstart} {fstop}"
        
        elif self.type == AnalysisType.TRANSIENT:
            step = self.parameters.get('step_time', '1N')
            stop = self.parameters.get('end_time', '100N')
            start = self.parameters.get('start_time', 0)
            uic = " UIC" if self.parameters.get('use_initial_conditions', False) else ""
            return f".TRAN {step} {stop} {start}{uic}"
        
        elif self.type == AnalysisType.NOISE:
            output = self.parameters.get('output', 'VOUT')
            source = self.parameters.get('input_source', 'VIN')
            points = self.parameters.get('points_per_summary', 10)
            return f".NOISE {output} {source} {points}"
        
        else:
            return f"* Analysis {self.type.value} not yet implemented"


@dataclass
class Measurement:
    """
    Mesure à extraire des résultats de simulation.
    
    Exemple:
        Measurement(
            name="dc_gain",
            expression="20*log10(Vout/Vin)",
            expected_min=60,
            expected_max=None,
            unit="dB"
        )
    """
    
    name: str
    """Nom de la mesure (ex: 'dc_gain', 'bandwidth')"""
    
    expression: str
    """Expression mathématique pour calculer la mesure"""
    
    expected_min: Optional[float] = None
    """Valeur minimale attendue"""
    
    expected_max: Optional[float] = None
    """Valeur maximale attendue"""
    
    unit: str = ""
    """Unité de la mesure (dB, V, A, Hz, etc.)"""
    
    node: Optional[str] = None
    """Noeud où prendre la mesure (si applicable)"""
    
    def to_assertion(self) -> str:
        """
        Convertit la mesure en assertion Python.
        
        Returns:
            Code Python pour vérifier cette mesure
        """
        code_lines = [f"def check_{self.name}(results):"]
        code_lines.append(f'    """Vérifie {self.name} ({self.unit})."""')
        code_lines.append(f"    measured = results.get('{self.name}')")
        code_lines.append(f"    if measured is None:")
        code_lines.append(f"        return False, f'{{self.name}} non trouvé dans les résultats'")
        
        if self.expected_min is not None:
            code_lines.append(f"    if measured < {self.expected_min}:")
            code_lines.append(f"        return False, f'{{self.name}} = {{measured}} < {self.expected_min} {self.unit}'")
        
        if self.expected_max is not None:
            code_lines.append(f"    if measured > {self.expected_max}:")
            code_lines.append(f"        return False, f'{{self.name}} = {{measured}} > {self.expected_max} {self.unit}'")
        
        code_lines.append(f"    return True, f'{{self.name}} = {{measured}} {self.unit}'")
        
        return "\n".join(code_lines)
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire."""
        return {
            "name": self.name,
            "expression": self.expression,
            "expected_min": self.expected_min,
            "expected_max": self.expected_max,
            "unit": self.unit,
            "node": self.node,
        }


@dataclass
class TestBench:
    """
    TestBench Entity - Plan de test complet pour un circuit.
    
    Cette entité est le produit du module TestBenchGen.
    Elle contient tout ce qui est nécessaire pour:
    1. Configurer les stimuli d'entrée
    2. Exécuter les analyses SPICE
    3. Extraire et vérifier les mesures
    
    Exemple:
        tb = TestBench(
            name="test_opamp_ac",
            category="ac",
            circuit_name="two_stage_opamp",
            stimuli=[
                Stimulus(name="vin", type="ac", parameters={"magnitude": 1})
            ],
            analyses=[
                AnalysisConfig(type=AnalysisType.AC, parameters={"start_freq": 1, "stop_freq": 1e9})
            ],
            measurements=[
                Measurement(name="dc_gain", expression="20*log10(Vout/Vin)", expected_min=60, unit="dB")
            ]
        )
    """
    
    # =========================================================
    # CHAMPS OBLIGATOIRES
    # =========================================================
    
    name: str
    """Nom du testbench"""
    
    category: str
    """Catégorie: 'dc', 'ac', 'transient', 'pvt', 'spectral', 'differential'"""
    
    # =========================================================
    # RÉFÉRENCE AU CIRCUIT
    # =========================================================
    
    circuit_name: str = ""
    """Nom du circuit à tester"""
    
    netlist_path: Optional[str] = None
    """Chemin vers le fichier netlist SPICE"""
    
    # =========================================================
    # CONFIGURATION DU TEST
    # =========================================================
    
    stimuli: List[Stimulus] = field(default_factory=list)
    """Stimuli d'entrée à appliquer"""
    
    analyses: List[AnalysisConfig] = field(default_factory=list)
    """Analyses SPICE à exécuter"""
    
    measurements: List[Measurement] = field(default_factory=list)
    """Mesures à extraire et vérifier"""
    
    # =========================================================
    # CODE GÉNÉRÉ
    # =========================================================
    
    pyspice_code: str = ""
    """Code PySpice généré (optionnel, peut être généré à la demande)"""
    
    # =========================================================
    # MÉTADONNÉES
    # =========================================================
    
    description: str = ""
    """Description du test"""
    
    temperature: float = 27.0
    """Température de simulation (°C)"""
    
    # =========================================================
    # MÉTHODES DE GÉNÉRATION DE CODE
    # =========================================================
    
    def generate_pyspice_code(self) -> str:
        """
        Génère le code PySpice complet pour ce testbench.
        
        Returns:
            Code Python exécutable avec PySpice
        """
        lines = [
            "# Auto-generated by Spec2TestBench - TestBenchGen",
            f"# TestBench: {self.name}",
            f"# Category: {self.category}",
            f"# Circuit: {self.circuit_name}",
            "",
            "from PySpice.Spice.Netlist import Circuit",
            "from PySpice.Unit import *",
            "import numpy as np",
            "import matplotlib.pyplot as plt",
            "",
        ]
        
        # Construction du circuit
        if self.netlist_path:
            lines.append(f"# Load netlist from: {self.netlist_path}")
            lines.append("def create_circuit():")
            lines.append(f"    circuit = Circuit('{self.circuit_name}')")
            lines.append(f"    # TODO: Include netlist file: {self.netlist_path}")
            lines.append("    return circuit")
        else:
            lines.append("def create_circuit():")
            lines.append(f"    circuit = Circuit('{self.circuit_name}')")
            
            # Ajouter les stimuli
            for stimulus in self.stimuli:
                lines.append(f"    {stimulus.to_pyspice()}")
            
            lines.append("    return circuit")
        
        lines.append("")
        lines.append("def run_simulation():")
        lines.append("    circuit = create_circuit()")
        lines.append("    simulator = circuit.simulator()")
        lines.append(f"    simulator.temperature = {self.temperature}")
        lines.append("")
        
        # Exécuter les analyses
        results = {}
        for i, analysis in enumerate(self.analyses):
            result_var = f"analysis_{i}"
            lines.append(f"    {result_var} = {analysis.to_pyspice()}")
            results[f"analysis_{i}"] = result_var
        
        lines.append("")
        lines.append("    # Extract measurements")
        lines.append("    results = {}")
        
        for measurement in self.measurements:
            lines.append(f"    # {measurement.name}: {measurement.expression}")
            lines.append(f"    results['{measurement.name}'] = None  # TODO: extract from simulation")
        
        lines.append("")
        lines.append("    return results")
        lines.append("")
        lines.append("if __name__ == '__main__':")
        lines.append("    results = run_simulation()")
        lines.append("    print('Simulation completed')")
        lines.append("    for name, value in results.items():")
        lines.append("        if value is not None:")
        lines.append("            print(f'{name}: {value}')")
        
        self.pyspice_code = "\n".join(lines)
        return self.pyspice_code
    
    def generate_spice_deck(self) -> str:
        """
        Génère le deck SPICE classique.
        
        Returns:
            Fichier SPICE (.spice) traditionnel
        """
        lines = [
            f"* TestBench: {self.name}",
            f"* Category: {self.category}",
            f"* Circuit: {self.circuit_name}",
            "",
        ]
        
        # Titre
        lines.append(f"{self.circuit_name or 'TestCircuit'}")
        
        # Inclure le netlist
        if self.netlist_path:
            lines.append(f".INCLUDE {self.netlist_path}")
        
        # Ajouter les stimuli
        for stimulus in self.stimuli:
            lines.append(stimulus.to_spice())
        
        # Analyses
        for analysis in self.analyses:
            lines.append(analysis.to_spice())
        
        # Mesures (en format SPICE)
        for measurement in self.measurements:
            if measurement.node:
                lines.append(f".MEASURE {measurement.name} FIND {measurement.expression}")
        
        lines.append(".END")
        
        return "\n".join(lines)
    
    # =========================================================
    # MÉTHODES DE VALIDATION
    # =========================================================
    
    def validate(self) -> tuple:
        """
        Valide que le testbench est cohérent.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Vérifier le nom
        if not self.name:
            errors.append("Le nom du testbench ne peut pas être vide")
        
        # Vérifier la catégorie
        valid_categories = ['dc', 'ac', 'transient', 'pvt', 'spectral', 'differential']
        if self.category not in valid_categories:
            errors.append(f"Catégorie invalide: {self.category}. Doit être {valid_categories}")
        
        # Vérifier qu'il y a au moins une analyse
        if not self.analyses:
            errors.append("Aucune analyse spécifiée")
        
        # Vérifier les stimuli
        for i, stimulus in enumerate(self.stimuli):
            if not stimulus.name:
                errors.append(f"Stimulus {i}: nom vide")
            if stimulus.type not in ['dc', 'ac', 'pulse', 'sin', 'pwl', 'exp', 'sffm']:
                errors.append(f"Stimulus {i}: type inconnu '{stimulus.type}'")
        
        return (len(errors) == 0, errors)
    
    def is_valid(self) -> bool:
        """Version simplifiée de validate."""
        is_valid, _ = self.validate()
        return is_valid
    
    # =========================================================
    # MÉTHODES DE CONVERSION
    # =========================================================
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour JSON."""
        return {
            "name": self.name,
            "category": self.category,
            "circuit_name": self.circuit_name,
            "netlist_path": self.netlist_path,
            "stimuli": [{"name": s.name, "type": s.type, "parameters": s.parameters} for s in self.stimuli],
            "analyses": [{"type": a.type.value, "parameters": a.parameters} for a in self.analyses],
            "measurements": [m.to_dict() for m in self.measurements],
            "description": self.description,
            "temperature": self.temperature,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TestBench":
        """Crée un TestBench depuis un dictionnaire."""
        stimuli = [
            Stimulus(
                name=s.get("name", f"stim_{i}"),
                type=s.get("type", "dc"),
                parameters=s.get("parameters", {}),
                node_positive=s.get("node_positive", "1"),
                node_negative=s.get("node_negative", "0"),
            )
            for i, s in enumerate(data.get("stimuli", []))
        ]
        
        analyses = [
            AnalysisConfig(
                type=AnalysisType(a.get("type", "dc")),
                parameters=a.get("parameters", {}),
            )
            for a in data.get("analyses", [])
        ]
        
        measurements = [
            Measurement(
                name=m.get("name", f"meas_{i}"),
                expression=m.get("expression", ""),
                expected_min=m.get("expected_min"),
                expected_max=m.get("expected_max"),
                unit=m.get("unit", ""),
                node=m.get("node"),
            )
            for i, m in enumerate(data.get("measurements", []))
        ]
        
        return cls(
            name=data.get("name", "unnamed_testbench"),
            category=data.get("category", "dc"),
            circuit_name=data.get("circuit_name", ""),
            netlist_path=data.get("netlist_path"),
            stimuli=stimuli,
            analyses=analyses,
            measurements=measurements,
            description=data.get("description", ""),
            temperature=data.get("temperature", 27.0),
        )
    
    # =========================================================
    # REPRÉSENTATIONS
    # =========================================================
    
    def __str__(self) -> str:
        return f"TestBench({self.name}, {self.category}, {len(self.measurements)} measurements)"
    
    def __repr__(self) -> str:
        return f"TestBench(name='{self.name}', category='{self.category}')"