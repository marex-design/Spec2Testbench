# Spec2Testbench v0.5.0 — reconstruction du dernier checkpoint déterministe

## Statut

Cette archive est une **reconstruction contrôlée** du framework à partir de :

1. `Spec2Testbench_BASE_REBUILD.zip` fourni par l'utilisateur ;
2. `S2T_RECOVERY_ASSETS.zip` fourni par l'utilisateur ;
3. huit patches v0.5.0 récupérés ;
4. `apply_op_bias_support.zip` dont le script historique a une taille de 18 633 octets et un SHA-256 connu ;
5. les traces terminal et résultats scientifiques du dernier checkpoint.

Ce n'est **pas** une restauration byte-à-byte du dépôt Git local perdu. La branche locale historique `test` n'était pas poussée.

## Ce qui a été reconstruit

- package/CLI `spec2testbench` version 0.5.0 ;
- architecture déterministe Spec -> TestBench -> ngspice -> extraction -> verdict ;
- contrat ACP-28 v2 : 28 YAML, 64 critères obligatoires ;
- 47 critères déclarés exécutables et 17 explicitement `metadata_only`/`NOT_IMPLEMENTED` ;
- séparation stricte execution / evidence / compliance ;
- `Cov_metrics`, `Cov_circuits`, `Cov_analyses`, VCY et evaluation rate ;
- analyse OP, DC, AC, TRAN ;
- sources multimodes DC+AC ;
- parser MOS 4 terminaux + modèle + W/L ;
- backend ngspice natif avec WRDATA pour AC/DC/TRAN ;
- hydratation du sweep DC complet et traces de courant ;
- guard des transitoires incomplets ;
- extraction sémantique ACP (filtres, comparateur, inverter, miroir, oscillateur, intégrateur, Schmitt, etc.) ;
- probe auxiliaire OP-bias `minimum_device_drain_current_a = min(abs(Id))` ;
- planner/validator/compiler LLM minimal déterministe avec provider stub ;
- refus des nœuds halluciné/incompatibilités avant simulation ;
- mock désactivé par défaut pour les preuves scientifiques ;
- provenance et script de freeze SHA-256.

## Limite de validation locale

L'environnement de construction ChatGPT ne possède pas l'exécutable `ngspice`. Les tests Python/statics peuvent donc être exécutés ici, mais la campagne numérique ACP-28 réelle doit être revalidée dans l'Ubuntu WSL de l'utilisateur avec ngspice-42.

Le nombre de tests de cette reconstruction ne doit pas être confondu avec le fingerprint historique du dépôt perdu (`293 passed, 12 skipped, 5 deselected`). Ce nombre historique est conservé uniquement comme **cible de comparaison**, pas comme résultat inventé de cette archive reconstruite.

## Contrat ACP-28 reconstruit

- circuits : 28
- critères obligatoires : 64
- exécutables : 47
- non implémentés explicitement : 17

Les 11 critères OP-bias ont été promus à l'état exécutable : p01, p02, p03, p04, p05, p14, p15, p16, p18, p20, p21.

Les 17 critères volontairement non implémentés restent :

- `differential_gain_linear` ×4 ;
- `differential_minus_common_gain` ×4 ;
- `iref_replication_error_a` ×1 ;
- `mixer_if_down_magnitude_v` ×1 ;
- `mixer_if_up_magnitude_v` ×1 ;
- `differentiator_square_wave_score` ×1 ;
- `adder_vin1_effect` ×1 ;
- `adder_vin2_effect` ×1 ;
- `adder_effect_ratio` ×1 ;
- `adder_formula_error` ×1 ;
- `subtractor_formula_error` ×1.

## Installation WSL

```bash
cd ~/Spec2Testbench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ngspice --version
spec2testbench version
python -m pytest -q -m "not llm_live"
```

## Revalidation déterministe réelle

```bash
rm -rf results/acp28_opbias_final

spec2testbench acp-benchmark \
  --manifest benchmark/analogcoder_pro/acp28_manifest.yaml \
  --output results/acp28_opbias_final

cat results/acp28_opbias_final/summary.json
bash scripts/freeze_deterministic_baseline.sh results/acp28_opbias_final
```

## Fingerprint historique à comparer

Le dernier dépôt perdu avait produit :

| Mesure | Cible historique |
|---|---:|
| Circuits | 28 |
| Simulation SUCCESS | 26 |
| COMPLIANT | 16 |
| NONCOMPLIANT | 7 |
| NOT_EVALUATED | 5 |
| Evaluation rate | 82.14 % |
| Compliance / evaluated | 69.57 % |
| Verified Compliance Yield | 57.14 % |
| Cov_circuits | 85.71 % |
| Cov_metrics | 67.19 % |
| Cov_analyses | 69.23 % |

Critères historiques : PASS 36, FAIL 7, NOT_EVALUATED 4, NOT_IMPLEMENTED 17.

Ces nombres sont **des critères d'acceptation de la reconstruction**. Tant que la campagne réelle ngspice-42 n'a pas été relancée, ils ne sont pas présentés comme résultats mesurés de cette archive.

## Valeurs OP-bias historiques de contrôle

| Cas | Verdict | `min(abs(Id))` [A] |
|---|---|---:|
| p01 | PASS | 4.74403102e-4 |
| p02 | PASS | 3.10401297e-4 |
| p03 | PASS | 3.77171464e-5 |
| p04 | PASS | 4.40658573e-4 |
| p05 | PASS | 4.85676304e-4 |
| p14 | PASS | 1.25000005e-4 |
| p15 | PASS | 6.25000004e-4 |
| p16 | FAIL | 4.86355744e-12 |
| p18 | FAIL | 4.77726119e-12 |
| p20 | FAIL | 3.50999896e-12 |
| p21 | FAIL | 3.64778430e-13 |

Seuil : `> 1e-5 A`. Les quatre FAIL ne doivent pas être modifiés pour améliorer artificiellement le benchmark.

## Suite du mémoire

Une fois cette baseline revalidée, la prochaine phase est la comparaison : déterministe vs LLM direct vs hybride LLM + validation déterministe + ngspice, puis ablations/stabilité. Le LLM ne décide jamais le verdict scientifique et ne modifie ni le DUT ni les seuils.
