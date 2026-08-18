# Cahier de Charge vs Etat Actuel

Date d'audit: 2026-06-10
Branche auditée: `dev-moanra`
Mode d'évaluation utilisé pour cette matrice: sans LLM pour la campagne benchmark

## Résumé

Le framework est déjà solide sur l'architecture générale, la CLI, la campagne `ngspice`, le registre des tests, et la génération de rapports. En revanche, il n'est pas encore entièrement conforme au cahier de charge sur le point le plus important pour le paper: transformer les `28 tests` du catalogue en `28 flux exécutables spécialisés` produisant chacun de manière uniforme un testbench, une simulation, une image, un verdict et un diagnostic.

## Matrice d'écart

| Exigence du cahier de charge | Etat actuel dans le dépôt | Manque restant | Priorité |
|---|---|---|---|
| Générer automatiquement 28 tests paramétrables à partir d'une spécification | Le dépôt expose bien `28` tests dans [supported_tests.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/domain/registry/supported_tests.py:1) | Les `28` tests ne sont pas encore `28 implémentations spécialisées` exécutables; l'exécution réelle repose surtout sur `6` catégories templates | `P0` |
| Organiser les tests en 6 catégories fonctionnelles | Conforme: `DC`, `AC`, `Transient`, `Spectral`, `Differential`, `PVT` sont présents dans le registre | Aucun manque structurel; il faut surtout compléter l'exécution détaillée par test | `P2` |
| Produire un script PySpice exécutable pour chaque test | La génération de testbench existe via [testbench_generator.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/infrastructure/testbench/testbench_generator.py:1) et la CLI `generate` dans [main.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/presentation/cli/main.py:147) | Les scripts sont générés par catégorie, pas encore par test précis du catalogue 1..28 | `P0` |
| Produire une image PNG par test (gain, step response, etc.) | Le plotting existe dans [waveform_plotter.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/infrastructure/waveform_checker/waveform_plotter.py:1) et les figures benchmark sont générées | Ce n'est pas encore uniformément branché dans le pipeline de vérification pour chaque test du catalogue | `P0` |
| Produire un verdict PASS/FAIL avec seuils extraits de la spécification | Conforme au niveau pipeline: [spec_checker.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/infrastructure/spec_checker/spec_checker.py:1) compare les métriques aux specs | Le verdict existe, mais pas encore sur 28 flux spécialisés bout-en-bout | `P1` |
| Produire un message de diagnostic multimodal (texte + image) destiné au LLM | Le support multimodal existe dans [waveform_checker.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/infrastructure/waveform_checker/waveform_checker.py:1) | En mode sans LLM, le diagnostic multimodal n'est pas systématiquement généré pour tous les tests; en pratique il manque l'uniformisation du flux image + diagnostic par test | `P1` |
| Test 1: Point de fonctionnement DC | Couvert partiellement par la catégorie `dc` et les métriques `vout_dc`, `idd` | Il manque une implémentation explicite des critères `VGS > VTH`, `VDS > VGS-VTH`, `VOUT ≈ VDD/2` | `P0` |
| Test 2: Courbe de transfert DC | Couvert partiellement via `.dc` et génération DC | Il manque un test dédié `vin -> vout`, analyse de linéarité et verdict spécifique | `P1` |
| Test 3: Recherche du point de polarisation optimal | Présent dans le registre | Pas d'implémentation spécialisée détectée | `P0` |
| Test 4: Consommation en courant / puissance | Partiellement couvert: extraction `idd`, `mean_current_a`, `power` | Il manque un flux standardisé avec seuils et rapport dédié par test | `P1` |
| Tests 5-10: bloc AC complet (gain, phase margin, UGF, CMRR, PSRR, Zin/Zout) | Gain AC partiellement couvert, `phase_margin`, `cmrr`, `psrr` existent dans l'extracteur | Pas de couverture bout-en-bout spécialisée et robuste pour toute la liste AC | `P0` |
| Tests 11-17: bloc transitoire complet | `step`, `sine`, `square`, oscillateur, comparateur sont partiellement représentés dans les catégories et l'extracteur | Il manque la spécialisation par test et plusieurs métriques dédiées comme overshoot, settling, startup, propagation `rise/fall` séparés | `P0` |
| Tests 18-21: bloc spectral complet | THD/FFT et quelques métriques existent | SFDR, précision oscillateur FFT, mixeur conversion gain ne sont pas encore démontrés proprement par flux dédiés | `P1` |
| Tests 22-25: bloc différentiel et spécifique | La catégorie `differential` existe et quelques heuristiques sont présentes | Plage de mode commun, erreur de phase, hystérésis, matching de miroir ne sont pas encore explicitement implémentés un par un | `P1` |
| Tests 26-28: PVT complet | La catégorie `pvt` existe dans le générateur et dans le registre | Il manque une vraie campagne PVT exécutable avec coins FF/SS/TT/FS/SF, températures et VDD ±10% produisant des métriques consolidées | `P0` |
| Workflow minimal `spec -> circuit -> netlist -> graph -> draw schematic` | Conforme partiellement: parsing netlist + rendu schématique existent via [netlist_parser.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/infrastructure/schematic/netlist_parser.py:1) et [connected_drawer.py](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/spec2testbench/infrastructure/schematic/connected_drawer.py:1) | Le flux est opérationnel en PNG, mais pas encore consolidé comme pipeline unique documenté de bout en bout | `P2` |
| Conversion PySpice -> netlist SPICE brute | Le framework sait générer du PySpice, et les netlists benchmark sont simulées | La chaîne inverse `PySpice object -> export SPICE -> parse -> schematic` n'est pas encore démontrée systématiquement | `P2` |
| Construction du graphe électrique avec nœuds et composants | Conforme en bonne partie | Le graphe existe mais il faut mieux le lier au discours expérimental et aux sorties utilisateurs | `P3` |
| Placement 2D automatique (spring layout / équivalent) | Plusieurs modules de placement existent dans `schematic/` et `infrastructure/schematic/` | Pas encore clairement validé comme fonctionnalité stabilisée dans le pipeline principal CLI | `P2` |
| Export vers LTSpice `.asc` | Non démontré dans le pipeline actuel | Fonctionnalité manquante ou incomplète | `P1` |
| Export vers KiCad `.kicad_sch` | Non démontré dans le pipeline actuel | Fonctionnalité manquante ou incomplète | `P1` |
| Rendu sans EDA avec Matplotlib/PNG | Conforme partiellement: rendu PNG disponible, benchmark et plotting headless fonctionnels | Il faut mieux unifier le rendu schématique et le rattacher au workflow officiel utilisateur | `P2` |
| Documentation exploitable pour validation humaine et multimodale | Les rapports, figures et schémas existent déjà en partie | Il manque un récit produit automatiquement par test, directement exploitable dans un paper | `P2` |
| Framework beginner-friendly | L'architecture, la CLI et les scripts de benchmark rendent le projet accessible | Il faut encore lisser les sorties, la doc et l'alignement exact avec le cahier pour vraiment démontrer l'aspect débutant | `P2` |
| Campagne expérimentale réelle sur un lot de netlists | Conforme: campagne `ngspice` sur `35` netlists effectuée, avec résumé dans [benchmark_summary.md](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/results/benchmark_summary.md:1) | Il manque maintenant le lien direct entre cette campagne et les 28 tests du cahier | `P0` |
| Métriques quantitatives pour la section évaluation | Conforme: [metrics.csv](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/results/metrics.csv:1), [metrics_stats.csv](/E:/my_organisation/Memoire%20Maruba/code/Spec2Testbench/results/metrics_stats.csv:1), figures et résumé benchmark sont présents | Il faut encore choisir et présenter les bonnes métriques selon les claims du paper | `P1` |

## Lecture rapide par priorité

### `P0` — indispensable avant de revendiquer une conformité forte

- Transformer le catalogue des `28 tests` en exécution plus spécialisée, au moins pour les cas majeurs du papier.
- Mettre en place un vrai flux `PVT` exécutable.
- Relier explicitement la campagne benchmark aux tests du cahier plutôt qu'à une campagne générique ngspice.
- Rendre uniformes les artefacts par test: `testbench + simulation + image + verdict + diagnostic`.

### `P1` — très important pour un paper crédible

- Compléter le bloc AC, spectral et différentiel test par test.
- Stabiliser les exports et les métriques spécialisées.
- Consolider les diagnostics multimodaux et les rapports orientés évaluation.

### `P2` — utile pour renforcer le positionnement et la finition

- Unifier le workflow schématique.
- Améliorer la doc utilisateur et la clarté beginner-friendly.
- Produire des sorties directement réutilisables dans le manuscrit.

### `P3` — amélioration secondaire

- Renforcer l'intégration fine des modules graphe/layout dans le pipeline principal.

## Ce qu'il faut finir avant le paper

Si l'objectif est de publier rapidement sans promettre trop large, l'ordre recommandé est:

1. Sélectionner un sous-ensemble représentatif des `28 tests` et les implémenter proprement bout-en-bout.
2. Ajouter une vraie campagne `PVT`.
3. Garantir pour ces tests les 5 artefacts: `script`, `simulation`, `image`, `verdict`, `diagnostic`.
4. Faire correspondre explicitement les résultats benchmark aux exigences du cahier dans la section évaluation.
5. Laisser les exports KiCad/LTSpice comme travail futur si le temps manque.

## Position honnête pour le manuscrit

La formulation la plus défendable aujourd'hui est:

"Le framework implémente déjà l'architecture cible, le registre normalisé de 28 tests, une campagne ngspice reproductible sur 35 netlists benchmark, ainsi qu'une chaîne de génération/analyse/rapport robuste. La conformité complète au cahier de charge reste partielle car tous les tests du catalogue ne sont pas encore réalisés comme flux spécialisés bout-en-bout."
