# Reproductibilité — exécution des benchmarks

Résumé rapide — ces commandes permettent de reproduire l'exécution des 35 netlists, d'extraire les métriques et de produire des rapports.

Prerequis système
- Python 3.10+ installé et accessible via `python`.
- `ngspice` installé et accessible dans le PATH (Windows: via Chocolatey `choco install ngspice`).

Commandes PowerShell (depuis la racine du dépôt)

1) Exécuter le script principal (créera `.venv`, installera les dépendances et lancera les étapes) :

```powershell
.\scripts\run_all.ps1
```

2) Si vous ne souhaitez pas que le script tente d'installer `ngspice` automatiquement :

```powershell
.\scripts\run_all.ps1 -SkipNgspiceInstall
```

Que fait le script
- crée `.venv` si absent
- active l'environnement virtuel
- `pip install -e .` pour installer `spec2testbench`
- installe `PySpice` (optionnel, utilisé pour parsing avancé)
- vérifie la présence de `ngspice` (propose `choco install ngspice` si Chocolatey présent)
- lance `scripts/check_35_netlists_ngspice.py` (génère `results/ngspice_logs/`)
- lance `scripts/aggregate_metrics.py` (génère `results/metrics.csv` via parsing `.raw`)
- lance `scripts/generate_coverage_matrix.py` (génère `results/coverage_matrix.csv`)

Fichiers produits
- `results/ngspice_logs/` : logs ngspice (.log)
- `results/raw/` : fichiers raw `.raw` produits par ngspice
- `results/metrics.csv` : métriques agrégées (amplitude_pp, frequency_hz, rise_time_s)
- `results/coverage_matrix.csv` : matrice de couverture tests/netlists

Conseils pour la préparation d'un article
- Inspectez `results/metrics.csv` et calculez les statistiques requises (mean/std/min/max) pour chaque métrique.
- Utilisez `matplotlib`/`pandas` pour produire tableaux et figures pour IEEE Access.

Exemple rapide en Python pour charger le CSV :

```python
import pandas as pd
df = pd.read_csv('results/metrics.csv')
print(df.describe())
```

Contact
- Si vous voulez, je peux :
  - générer automatiquement les statistiques et figures (histogrammes, boxplots) prêtes pour la publication ;
  - produire un notebook `results/analysis.ipynb` pour l'exploration interactive.
