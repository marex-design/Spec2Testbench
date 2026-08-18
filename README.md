# Spec2Testbench v0.5.0 — reconstruction contrôlée

> Cette archive reconstruit le dernier checkpoint déterministe connu. Voir `README_RECONSTRUCTION.md` et `RECONSTRUCTION_PROVENANCE.json` avant toute campagne scientifique. Le mode mock est désactivé par défaut pour les preuves.

# Spec2TestBench

framework de vérification et de génération automatique de testbenches SPICE basé sur des spécifications YAML et des modèles LLM.

---

# Fonctionnalités

- Vérification automatique de circuits SPICE
- Génération de testbenches PySpice
- Diagnostic de formes d’onde
- Intégration LLM 
- Simulation ngspice sous WSL/Linux
- Architecture Logicielle Clean Architecture

---

# Architecture

```text
┌─────────────────────────────────────────────┐
│           PRESENTATION LAYER                │
│         (CLI, Rapports Markdown)            │
├─────────────────────────────────────────────┤
│           APPLICATION LAYER                 │
│         (Use Cases, Pipeline)               │
├─────────────────────────────────────────────┤
│              DOMAIN LAYER                   │
│     (Entities, Value Objects, Interfaces)   │
├─────────────────────────────────────────────┤
│          INFRASTRUCTURE LAYER               │
│      (LLM, SPICE, Checkers, Simulator)      │
└─────────────────────────────────────────────┘
```

---

# Flux de données

1. **Spécification YAML** → `Specification Entity`
2. **TestBenchGen** → `TestBench Entity (PySpice)`
3. **Simulateur WSL/ngspice** → Résultats SPICE
4. **SpecChecker** → Verdicts PASS/FAIL
5. **Rapport** → Markdown / JSON / Console

---

# Installation

```bash
# Cloner le dépôt
git clone https://github.com/marex-design/Spec2Testbench.git

cd Spec2Testbench

# Installer le package
pip install -e .

# Configurer les clés API  
cp .env.example .env
```

Éditer ensuite le fichier `.env` avec vos clés API.

---

# Commandes disponibles

| Commande | Description |
|---|---|
| `spec2testbench verify` | Vérifier un circuit |
| `spec2testbench generate` | Générer un testbench |
| `spec2testbench diagnose` | Diagnostiquer une forme d’onde |
| `spec2testbench draw` | Dessiner le schéma à partir d'un netlist SPICE |
| `spec2testbench config` | Voir la configuration |
| `spec2testbench providers` | Voir les fournisseurs LLM |

---

# Exemples d'utilisation

## Vérifier un amplificateur

```bash
spec2testbench verify \
  --specs examples/amplifier_spec.yaml \
  --netlist netlists/amplifier.cir
```

## Générer un testbench

```bash
spec2testbench generate \
  --specs examples/test_opamp.yaml \
  --output my_testbench.py
```

## Diagnostiquer une forme d’onde

```bash
spec2testbench diagnose \
  --waveform plot.png \
  --provider deepseek
```

## Dessiner le schéma d'un circuit

```bash
spec2testbench draw \
  --netlist netlists/amplifier.cir \
  --output schematic.png
```

Cette commande lit le netlist SPICE et dessine un schéma qui reflète
réellement les composants, les nœuds et les connexions du fichier.
Des netlists différents produisent des schémas différents.

---

# Structure du projet

```text
Spec2Testbench/
│
├── netlists/
│   ├── amplifier.cir
│   ├── differential_amp.cir
│   ├── lowpass_filter.cir
│   ├── ring_oscillator.cir
│   └── current_mirror.cir
│
├── docs/
│   ├── architecture.md
│   └── user_guide.md
│
├── scripts/
│   ├── setup_environment.sh
│   ├── run_tests.sh
│   └── clean_cache.sh
│
├── examples/
│   ├── test_opamp.yaml
│   ├── amplifier_spec.yaml
│   └── filter_spec.yaml
│
└── tests/
```

---

# Résultats

-  ... types de circuits testés
-  ... générations de testbench réussies (100%)
-  30 tests unitaires validés
-  Simulation avec ngspice (WSL/Linux)

---

# Technologies utilisées

- Python
- PySpice
- ngspice
- YAML
- WSL/Linux
- LLM APIs

---

# Licence

MIT License

---



**Exaucé K. Maruba** \
**exauce.kambale@unikin.ac.cd** \
***Université de Kinshasa***
***Faculté Polytechnique / Génie électrique et Informatique*** \
***Option Electronique*** 

