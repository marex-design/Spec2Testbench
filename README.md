# Spec2Testbench v0.5.0

**Framework hybride LLM–SPICE pour la génération de testbenches et la vérification de conformité des circuits analogiques**

>
> Avant toute nouvelle campagne scientifique, consulter `README_RECONSTRUCTION.md`, `RECONSTRUCTION_PROVENANCE.json` et `REPRO.md`.
>
> Le mode mock n'est pas destiné à la production de preuves scientifiques. Les expériences finales doivent utiliser un simulateur SPICE réel.

---

## Présentation

**Spec2Testbench** est un framework Python conçu pour automatiser une partie du processus de vérification des circuits analogiques à partir de spécifications structurées.

Le framework relie principalement :

```text
Spécification YAML
        ↓
Analyse de la spécification
        ↓
Plan de vérification
        ↓
Génération du testbench
        ↓
Simulation SPICE
        ↓
Extraction des métriques
        ↓
Vérification des exigences
        ↓
Verdict et rapport
```

Spec2Testbench combine des mécanismes **déterministes** avec une assistance optionnelle par **Large Language Model (LLM)**.

Le principe général du framework est le suivant :

> **Le LLM peut proposer ou assister le plan de vérification, SPICE produit les mesures électriques, et la logique déterministe décide de la conformité.**

---

# Fonctionnalités

Spec2Testbench fournit notamment :

* vérification automatique de circuits SPICE à partir de spécifications YAML ;
* génération automatique de testbenches ;
* simulation avec `ngspice` sous Linux/WSL ;
* extraction automatique de métriques électriques ;
* comparaison des métriques avec les exigences de la spécification ;
* génération de verdicts de conformité ;
* génération de rapports ;
* diagnostic de formes d'onde ;
* génération de schémas à partir de netlists SPICE ;
* intégration optionnelle de modèles LLM ;
* planification de tests assistée par LLM ;
* validation déterministe des propositions générées par le LLM ;
* prise en charge de campagnes expérimentales et de benchmarks ;
* conservation d'artefacts permettant la reproductibilité des expériences.

---

# Principe de fonctionnement

Une vérification Spec2Testbench repose sur deux entrées principales :

1. une **spécification YAML** décrivant les exigences ;
2. une **netlist SPICE** représentant le circuit sous test.

Le framework construit ensuite un processus de vérification permettant d'obtenir des métriques électriques et de les comparer aux seuils définis dans la spécification.

```text
          ┌────────────────────┐
          │ Spécification YAML │
          └──────────┬─────────┘
                     │
                     ▼
          ┌────────────────────┐
          │ Plan de vérification│
          └──────────┬─────────┘
                     │
                     ▼
          ┌────────────────────┐
          │ Validation du plan │
          └──────────┬─────────┘
                     │
                     ▼
          ┌────────────────────┐
          │ Testbench SPICE    │
          └──────────┬─────────┘
                     │
                     ▼
          ┌────────────────────┐
          │      ngspice       │
          └──────────┬─────────┘
                     │
                     ▼
          ┌────────────────────┐
          │ Mesures électriques│
          └──────────┬─────────┘
                     │
                     ▼
          ┌────────────────────┐
          │ Vérification       │
          │ déterministe       │
          └──────────┬─────────┘
                     │
                     ▼
          ┌────────────────────┐
          │ Verdict + preuves  │
          └────────────────────┘
```

---

# Modes de fonctionnement

## 1. Vérification déterministe

Le mode déterministe exécute la chaîne de vérification sans dépendre d'un LLM.

Il est particulièrement utile pour :

* les tests de régression ;
* les campagnes reproductibles ;
* les benchmarks ;
* la génération de preuves scientifiques ;
* les circuits dont le plan de vérification est déjà connu.

Exemple :

```bash
spec2testbench verify \
  --specs examples/amplifier_spec.yaml \
  --netlist netlists/amplifier.cir \
  --no-llm
```

---

## 2. Mode assisté par LLM

Le framework peut également utiliser un LLM pour assister certaines tâches de planification.

Selon le workflow utilisé, le modèle peut notamment aider à :

* interpréter une spécification ;
* identifier les rôles fonctionnels de certains nœuds ;
* proposer une analyse SPICE ;
* proposer un stimulus ;
* proposer une stratégie de mesure ;
* corriger certains problèmes dans un plan de test.

Les propositions générées par le modèle doivent néanmoins être validées avant leur exécution.

Le LLM ne remplace ni le simulateur SPICE ni le mécanisme déterministe de décision.

---

# Architecture logicielle

Spec2Testbench suit une organisation inspirée de la **Clean Architecture**.

```text
┌─────────────────────────────────────────────┐
│             PRESENTATION LAYER              │
│                                             │
│          CLI, rapports, interfaces          │
├─────────────────────────────────────────────┤
│             APPLICATION LAYER               │
│                                             │
│      Cas d'utilisation et orchestration     │
├─────────────────────────────────────────────┤
│                DOMAIN LAYER                 │
│                                             │
│ Entités, spécifications, plans, interfaces  │
├─────────────────────────────────────────────┤
│            INFRASTRUCTURE LAYER             │
│                                             │
│   SPICE, LLM, extracteurs, générateurs      │
└─────────────────────────────────────────────┘
```

Cette séparation permet de distinguer :

* la logique métier de vérification ;
* l'orchestration des workflows ;
* les interfaces utilisateur ;
* les dépendances externes comme `ngspice` et les fournisseurs LLM.

Une description plus détaillée est disponible dans :

```text
docs/
```

---

# Flux de données

Le flux principal peut être résumé comme suit :

1. **Spécification YAML**
   Chargement et validation des exigences du circuit.

2. **Netlist du DUT**
   Lecture du circuit sous test.

3. **Plan de vérification**
   Association entre exigences, analyses SPICE et métriques.

4. **Validation**
   Vérification de la cohérence du plan avant simulation.

5. **Génération du testbench**
   Construction du circuit de test et des commandes nécessaires.

6. **Simulation SPICE**
   Exécution avec `ngspice`.

7. **Extraction des métriques**
   Lecture des résultats issus de la simulation.

8. **Vérification des critères**
   Comparaison entre mesures et exigences.

9. **Verdict**
   Production du statut correspondant à chaque critère.

10. **Rapport et artefacts**
    Conservation des résultats nécessaires à l'analyse et à la reproductibilité.

---

# Installation

## Prérequis

L'environnement recommandé est :

* Ubuntu ou une distribution Linux compatible ;
* WSL2 sous Windows ;
* Python 3 ;
* `pip` ;
* `venv` ;
* Git ;
* `ngspice`.

---

## 1. Installer ngspice

Sous Ubuntu :

```bash
sudo apt update
sudo apt install ngspice
```

Vérifier l'installation :

```bash
ngspice --version
```

---

## 2. Cloner le dépôt

```bash
git clone https://github.com/marex-design/Spec2Testbench.git
cd Spec2Testbench
```

---

## 3. Créer l'environnement virtuel

```bash
python3 -m venv .venv
```

Activer l'environnement :

```bash
source .venv/bin/activate
```

Le terminal doit ensuite afficher quelque chose de similaire à :

```text
(.venv) user@machine:~/Spec2Testbench$
```

---

## 4. Mettre à jour pip

```bash
python -m pip install --upgrade pip
```

---

## 5. Installer Spec2Testbench

Pour une installation locale en mode développement :

```bash
python -m pip install -e .
```

Si les dépendances de développement sont définies dans le projet :

```bash
python -m pip install -e ".[dev]"
```

---

## 6. Vérifier l'installation

```bash
spec2testbench --help
```

Puis :

```bash
spec2testbench version
```

---

# Configuration des fournisseurs LLM

L'utilisation d'un LLM est optionnelle.

Lorsque le workflow sélectionné nécessite un fournisseur externe, les clés API doivent être configurées dans les variables d'environnement ou dans la configuration prévue par le projet.

Si un fichier d'exemple est disponible :

```bash
cp .env.example .env
```

Puis éditer :

```text
.env
```

Les clés API ne doivent jamais être ajoutées au dépôt Git.

Pour consulter les fournisseurs disponibles :

```bash
spec2testbench providers
```

Pour consulter la configuration courante :

```bash
spec2testbench config
```

---

# Commandes principales

Les commandes disponibles dépendent de la version installée.

La liste exacte peut toujours être obtenue avec :

```bash
spec2testbench --help
```

Les commandes principales comprennent notamment :

| Commande                   | Description                                       |
| -------------------------- | ------------------------------------------------- |
| `spec2testbench verify`    | Vérifier un circuit à partir d'une spécification  |
| `spec2testbench generate`  | Générer un testbench                              |
| `spec2testbench diagnose`  | Diagnostiquer une forme d'onde ou un comportement |
| `spec2testbench draw`      | Générer un schéma à partir d'une netlist SPICE    |
| `spec2testbench config`    | Afficher la configuration                         |
| `spec2testbench providers` | Afficher les fournisseurs LLM disponibles         |
| `spec2testbench version`   | Afficher la version du framework                  |

Certaines versions du framework proposent également des commandes dédiées :

* à la planification LLM ;
* à la vérification hybride ;
* aux mécanismes de réparation ;
* aux campagnes de benchmark.

Utiliser :

```bash
spec2testbench --help
```

pour obtenir la liste correspondant exactement au code installé.

---

# Exemples d'utilisation

## Vérifier un circuit

```bash
spec2testbench verify \
  --specs examples/amplifier_spec.yaml \
  --netlist netlists/amplifier.cir
```

---

## Vérifier sans LLM

```bash
spec2testbench verify \
  --specs examples/amplifier_spec.yaml \
  --netlist netlists/amplifier.cir \
  --no-llm
```

---

## Générer un testbench

```bash
spec2testbench generate \
  --specs examples/test_opamp.yaml \
  --output my_testbench.py
```

---

## Diagnostiquer une forme d'onde

```bash
spec2testbench diagnose \
  --waveform plot.png \
  --provider deepseek
```

---

## Dessiner le schéma d'un circuit

```bash
spec2testbench draw \
  --netlist netlists/amplifier.cir \
  --output schematic.png
```

La commande `draw` analyse la netlist SPICE puis produit une représentation graphique du circuit à partir des composants, nœuds et connexions détectés.

Le résultat dépend directement de la structure de la netlist fournie.

---

# Spécifications YAML

Les exigences de vérification sont décrites dans des fichiers YAML.

Une spécification peut contenir notamment :

* l'identifiant du circuit ;
* son type ;
* les ports d'entrée et de sortie ;
* les conditions de fonctionnement ;
* les analyses requises ;
* les métriques à mesurer ;
* les unités ;
* les seuils ;
* les opérateurs de comparaison.

Exemple simplifié :

```yaml
case_id: amplifier_example
name: amplifier
circuit_type: amplifier

ports:
  input:
    - Vin
  output:
    - Vout

functional_requirements:
  - id: REQ_GAIN
    metric: gain_db
    operator: ">="
    threshold: 20
    unit: dB
```

Le format réellement accepté dépend du schéma de spécification utilisé par la version du framework.

Consulter la documentation présente dans :

```text
docs/
```

et les exemples présents dans :

```text
examples/
benchmark/
spec/
```

---

# Verdicts de vérification

Un point important de Spec2Testbench est la distinction entre :

* le succès de la simulation ;
* la disponibilité d'une mesure ;
* la conformité électrique du circuit.

Une simulation SPICE réussie ne signifie donc pas automatiquement que le circuit est conforme.

Schématiquement :

```text
Simulation
    │
    ├── erreur d'exécution
    │
    └── exécution réussie
             │
             ├── métrique non disponible
             │
             └── métrique disponible
                      │
                      ├── exigence satisfaite
                      └── exigence violée
```

Cette distinction permet d'éviter de transformer artificiellement une mesure absente en valeur numérique ou en verdict positif.

---

# Benchmark et campagnes expérimentales

Le dépôt contient plusieurs répertoires associés aux circuits de référence, aux campagnes scientifiques et aux résultats expérimentaux.

On trouve notamment :

```text
benchmark/
benchmark_analogcoder_pro_28/
benchmark_netlists/
benchmark_reference_28/
scientific_evidence/
results/
reports/
```

Ces répertoires ne remplissent pas tous le même rôle.

Ils peuvent contenir :

* des netlists de référence ;
* des spécifications ;
* des manifestes de benchmark ;
* des sorties expérimentales ;
* des rapports ;
* des preuves gelées ;
* des artefacts de reproductibilité.

Les résultats d'une campagne particulière ne doivent pas être considérés comme des propriétés permanentes du framework.

---

# Reproductibilité scientifique

Les expériences utilisées comme preuves doivent permettre d'identifier autant que possible :

```text
spécification
netlist du DUT
plan de vérification
testbench exécuté
version du code
version de ngspice
sorties SPICE
mesures extraites
verdicts
configuration expérimentale
empreintes ou hashes des artefacts
```

Les principaux documents relatifs à la reconstruction et à la reproductibilité sont :

```text
README_RECONSTRUCTION.md
RECONSTRUCTION_PROVENANCE.json
RECONSTRUCTION_FILE_MANIFEST.json
REPRO.md
scientific_evidence/
```

Les répertoires ordinaires comme `output/`, `results/` ou `waveforms/` peuvent contenir des exécutions locales et ne doivent pas automatiquement être assimilés à des preuves scientifiques gelées.

---

# Structure actuelle du projet

La reconstruction actuelle contient notamment :

```text
Spec2Testbench/
│
├── README.md
├── CHANGELOG.md
├── REPRO.md
│
├── README_RECONSTRUCTION.md
├── RECONSTRUCTION_FILE_MANIFEST.json
├── RECONSTRUCTION_PROVENANCE.json
│
├── pyproject.toml
├── setup.py
├── pytest.ini
│
├── spec2testbench/
│   └── code source principal du framework
│
├── tests/
│   └── tests automatisés
│
├── docs/
│   └── documentation
│
├── examples/
│   └── exemples d'utilisation et de spécifications
│
├── benchmark/
│   └── benchmark principal et spécifications associées
│
├── benchmark_analogcoder_pro_28/
├── benchmark_reference_28/
├── benchmark_netlists/
│
├── scientific_evidence/
│   └── preuves et résultats scientifiques gelés
│
├── results/
├── reports/
├── output/
│
├── netlist/
├── netlists/
├── testbenches/
│
├── waveforms/
├── waveforms_test/
│
├── scripts/
├── recovery/
├── spec/
│
└── analogcoder/
```

Certains dossiers sont conservés pour :

* la compatibilité avec des versions antérieures ;
* la reproductibilité des expériences ;
* la reconstruction du dépôt ;
* la conservation des données utilisées dans les campagnes scientifiques.

Ils ne correspondent donc pas nécessairement tous au chemin d'exécution principal du logiciel.

---

# Tests

Pour lancer la suite de tests :

```bash
python -m pytest -q
```

Ou :

```bash
pytest -q
```

Il est recommandé de lancer les tests dans l'environnement virtuel :

```text
(.venv)
```

avant toute modification importante du framework ou toute nouvelle campagne expérimentale.

---

# Technologies utilisées

Le projet utilise principalement :

* **Python**
* **SPICE**
* **ngspice**
* **PySpice**
* **YAML**
* **Pydantic**
* **Typer**
* **Linux / Ubuntu**
* **WSL**
* **LLM APIs**

D'autres bibliothèques peuvent être utilisées selon les composants et workflows activés.

---

# Périmètre scientifique

Spec2Testbench est un **prototype de recherche**.

L'objectif principal est d'étudier et d'implémenter une chaîne automatisée :

```text
exigence
   ↓
test
   ↓
simulation
   ↓
mesure
   ↓
verdict
   ↓
preuve
```

Le framework ne doit pas être présenté comme un outil industriel complet de sign-off analogique.

La version actuelle ne prétend notamment pas remplacer les workflows industriels couvrant systématiquement :

* les PDK ;
* les corners PVT ;
* le mismatch ;
* les simulations Monte-Carlo ;
* les parasites post-layout ;
* les mesures silicium ;
* la qualification industrielle.

---

# Documentation

La documentation complémentaire se trouve dans :

```text
docs/
```

Les documents importants de reproductibilité se trouvent également dans :

```text
REPRO.md
README_RECONSTRUCTION.md
RECONSTRUCTION_PROVENANCE.json
scientific_evidence/
```

---

# État du projet

Spec2Testbench est un projet de recherche en développement.

La version `v0.5.0` de cette archive doit être considérée dans le contexte de la **reconstruction contrôlée du dépôt**.

Avant de publier de nouveaux résultats scientifiques, il est recommandé de :

1. vérifier l'environnement Python ;
2. vérifier la version de `ngspice` ;
3. exécuter les tests automatisés ;
4. identifier précisément le commit utilisé ;
5. conserver les spécifications et netlists d'entrée ;
6. conserver les artefacts générés ;
7. distinguer les résultats locaux des preuves scientifiques gelées.

---

# Licence

MIT License

---

## Auteur

**Exaucé K. Maruba**
Université de Kinshasa
Faculté Polytechnique
Génie électrique et Informatique
Option Électronique

**Contact :** [exauce.kambale@unikin.ac.cd](mailto:exauce.kambale@unikin.ac.cd)
