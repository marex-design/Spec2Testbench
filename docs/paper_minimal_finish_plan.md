# Plan Minimal de Finition pour le Paper

Date: 2026-06-10
Objectif: rendre le framework publiable sans chercher à implémenter complètement les 28 tests avant soumission.

## Principe

Pour le paper, il n'est pas nécessaire de terminer les `28` tests d'un coup. Il faut surtout démontrer:

- une chaîne complète `specification -> testbench -> simulation -> métriques -> verdict -> rapport`
- une couverture représentative de plusieurs familles de vérification analogique
- une campagne expérimentale reproductible
- une narration honnête sur ce qui est déjà implémenté et ce qui reste futur

Le bon compromis est d'implémenter proprement `10 tests` couvrant `5` familles de comportements:

- DC
- AC
- Transient
- Spectral
- PVT

Ce sous-ensemble est suffisant pour soutenir un article de type framework/prototype si la méthodologie et les résultats sont solides.

## Les 10 tests prioritaires

### 1. DC Operating Point

- Catégorie: DC
- Pourquoi: indispensable pour montrer la vérification de base d'un circuit analogique
- Ce qu'il faut sortir: `Vout`, courants d'alimentation, validation d'un point nominal

### 2. Quiescent Current / Power

- Catégorie: DC
- Pourquoi: facile à mesurer, très parlant pour l'évaluation
- Ce qu'il faut sortir: `IDD`, puissance statique, verdict par seuil

### 3. Open-Loop / Small-Signal Gain

- Catégorie: AC
- Pourquoi: test canonique pour amplificateurs, OTA, op-amps, LNA
- Ce qu'il faut sortir: gain basse fréquence ou gain nominal, courbe de Bode

### 4. -3 dB Bandwidth / Cutoff Frequency

- Catégorie: AC
- Pourquoi: complète naturellement le test de gain
- Ce qu'il faut sortir: fréquence de coupure ou bande passante

### 5. Unity Gain Frequency ou Gain Peak Stable

- Catégorie: AC
- Pourquoi: très utile pour op-amps et deux étages, bon signal scientifique
- Ce qu'il faut sortir: `UGF` si applicable, sinon méta-règle “not applicable”

### 6. Step Response

- Catégorie: Transient
- Pourquoi: relie directement spec temporelle et comportement observable
- Ce qu'il faut sortir: forme d'onde, temps de montée, settling si possible

### 7. Comparator Propagation Delay

- Catégorie: Transient
- Pourquoi: donne un cas non-linéaire simple, différent d'un amplificateur
- Ce qu'il faut sortir: délai entrée/sortie montant ou moyen

### 8. Oscillator Startup / Frequency

- Catégorie: Transient + Spectral léger
- Pourquoi: montre qu'on ne couvre pas seulement des amplificateurs
- Ce qu'il faut sortir: fréquence oscillée, amplitude, démarrage observé

### 9. FFT / THD

- Catégorie: Spectral
- Pourquoi: apporte une vraie dimension “analog verification” plus riche
- Ce qu'il faut sortir: spectre, estimation THD, verdict

### 10. PVT Sweep Minimal

- Catégorie: PVT
- Pourquoi: indispensable pour justifier la robustesse du framework
- Ce qu'il faut sortir: variation d'au moins une métrique sur tension et température, même si les corners process restent simplifiés

## Pourquoi ces 10 tests

Ce choix couvre:

- les mesures statiques
- la réponse fréquentielle
- la réponse temporelle
- le spectral
- la robustesse paramétrique

Il couvre aussi plusieurs topologies déjà présentes dans le benchmark:

- amplificateurs simples
- op-amps
- comparateurs / schmitt
- oscillateurs
- filtres

Avec ce noyau, tu peux raisonnablement écrire que le framework “implements a representative subset of the standardized verification suite” sans surpromettre la totalité des 28 cas.

## Ce qu'il ne faut pas essayer de finir avant le paper

À repousser en “future work” si le temps est limité:

- CMRR complet
- PSRR complet
- impédance d'entrée / sortie robuste
- SFDR
- mixer conversion gain complet
- Schmitt hysteresis complet
- current mirror matching complet
- export KiCad
- export LTSpice `.asc`

Ce sont de bonnes fonctionnalités, mais elles coûtent plus cher en temps de validation que ce qu'elles rapportent pour une première soumission.

## Plan d'exécution recommandé

### Phase 1. Stabiliser le noyau expérimental

- Utiliser la campagne benchmark actuelle comme base expérimentale
- Verrouiller les 10 tests prioritaires dans le pipeline
- Générer pour chacun:
  - un testbench
  - une simulation
  - une image
  - une extraction de métrique
  - un verdict

### Phase 2. Choisir 6 à 10 circuits démonstrateurs

- `common_source_amplifier`
- `source_follower`
- `operational_amplifier`
- `two_stage_opamp`
- `comparator`
- `schmitt_trigger`
- `ring_oscillator`
- `lowpass_filter`
- `highpass_filter`
- `current_mirror` ou `voltage_reference`

Le but n'est pas d'exécuter tous les tests sur tous les circuits, mais de montrer une matrice crédible circuit/test.

### Phase 3. Produire les tableaux du paper

- Tableau 1: tests implémentés dans la version évaluée
- Tableau 2: circuits benchmark utilisés
- Tableau 3: taux de succès de génération/simulation/extraction
- Tableau 4: exemples de métriques extraites

### Phase 4. Positionner honnêtement la contribution

Formulation recommandée:

“Rather than claiming complete implementation of all 28 standardized analog verification tests, the evaluated prototype implements and validates a representative 10-test subset spanning DC, AC, transient, spectral, and PVT analyses.”

## Priorité pratique

### P0

- DC operating point
- quiescent current / power
- open-loop gain
- cutoff / bandwidth
- step response
- comparator delay
- oscillator frequency
- FFT / THD
- minimal PVT

### P1

- unity gain frequency
- settling time plus robuste
- rapport standardisé par test

### P2

- extension progressive aux autres tests du catalogue

## Message clé pour le paper

Le paper sera plus fort si tu défends:

- un framework reproductible
- un sous-ensemble représentatif bien exécuté
- une campagne expérimentale propre

plutôt que:

- une promesse de couverture totale des 28 tests sans validation homogène

## Sortie attendue après ce plan

Si ce plan est suivi, tu pourras soutenir dans le manuscrit:

- un pipeline complet sans LLM pour l'exécution benchmark
- un registre standardisé de 28 tests
- une implémentation évaluée de 10 tests représentatifs
- une campagne ngspice reproductible sur 35 netlists
- une base extensible pour compléter le reste du catalogue
