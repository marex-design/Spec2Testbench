# Benchmark Test Naming Convention

Ce document fige la convention canonique des 28 tests du framework pour le benchmark `AnalogCoderPro-28`.

## Principes

- Le nom interne d'un test reste en `snake_case`.
- La famille du test est portee separement: `DC`, `AC`, `Transient`, `Spectral`, `Differential`, `PVT`.
- Le nom normalise recommande pour les tableaux, runners, rapports et campagnes est `family.test_name`, avec une famille en minuscules.
- Les metriques attendues restent des quantites physiques en `snake_case`, avec unite explicite dans la spec YAML.
- Une spec peut viser un ou plusieurs tests, mais chaque objectif doit pouvoir etre rattache sans ambiguite a un test canonique de cette liste.

## Format recommande

- Identifiant canonique du test: `test_name`
- Nom normalise affiche: `family.test_name`
- Exemple: `ac.phase_margin`, `transient.step_response`, `pvt.temperature_sweep`

## Tableau canonique des 28 tests

| Test | Famille | But | Metriques attendues | Nom normalise recommande |
| --- | --- | --- | --- | --- |
| `operating_point` | `DC` | Verifier le point de repos DC du noeud de sortie ou d'un noeud critique. | `operating_point`, `vout_dc`, tension(s) de bias | `dc.operating_point` |
| `dc_transfer` | `DC` | Balayer une entree en DC pour caracteriser la loi entree-sortie. | `vout_dc`, pente locale, plage lineaire, seuil de bascule | `dc.dc_transfer` |
| `bias_point_search` | `DC` | Trouver une polarisation valide respectant une zone de fonctionnement cible. | `operating_point`, tensions/courants de bias, marge de saturation | `dc.bias_point_search` |
| `quiescent_current` | `DC` | Mesurer la consommation au repos. | `quiescent_current`, `idd`, `iq`, `power` | `dc.quiescent_current` |
| `open_loop_gain` | `AC` | Mesurer le gain petit-signal en boucle ouverte ou equivalent. | `dc_gain`, `dc_gain_db`, `low_frequency_gain_db` | `ac.open_loop_gain` |
| `phase_margin` | `AC` | Evaluer la stabilite en boucle fermee via la marge de phase. | `phase_margin`, `phase_margin_deg` | `ac.phase_margin` |
| `unity_gain_frequency` | `AC` | Mesurer la frequence d'unite ou le GBW. | `unity_gain_frequency`, `ugbw`, `gbw`, `unity_gain_bandwidth` | `ac.unity_gain_frequency` |
| `cmrr` | `AC` | Mesurer la rejection du mode commun. | `cmrr`, `cmrr_db`, `common_mode_gain` | `ac.cmrr` |
| `psrr` | `AC` | Mesurer la rejection des perturbations d'alimentation. | `psrr`, `psrr_db` | `ac.psrr` |
| `input_output_impedance` | `AC` | Caracteriser l'impedance d'entree et/ou de sortie. | `input_impedance`, `output_impedance`, `zin`, `zout` | `ac.input_output_impedance` |
| `step_response` | `Transient` | Observer la reponse temporelle a un echelon. | `rise_time`, `fall_time`, `settling_time`, `overshoot`, `undershoot` | `transient.step_response` |
| `sine_response` | `Transient` | Verifier la reponse temporelle a une excitation sinusoidale. | `amplitude_gain`, `phase_shift`, `output_amplitude`, `slew_rate` | `transient.sine_response` |
| `square_response` | `Transient` | Verifier la reponse a un signal carre et les non-idealites dynamiques. | `rise_time`, `fall_time`, `propagation_delay`, `overshoot`, `ringing` | `transient.square_response` |
| `oscillator_startup` | `Transient` | Confirmer le demarrage de l'oscillation dans le temps. | `startup_time`, `startup_amplitude`, `oscillation_detected`, `frequency_hz` | `transient.oscillator_startup` |
| `integrator_ramp` | `Transient` | Verifier qu'un integrateur produit une rampe conforme. | `slope`, `ramp_linearity`, `output_swing`, `integration_error` | `transient.integrator_ramp` |
| `differentiator_impulse` | `Transient` | Verifier qu'un differentiator reagit par impulsion/pic a une transition rapide. | `peak_amplitude`, `pulse_width`, `derivative_gain`, `settling_time` | `transient.differentiator_impulse` |
| `comparator_delay` | `Transient` | Mesurer le retard de decision d'un comparateur. | `comparator_delay`, `propagation_delay`, `delay`, `response_time` | `transient.comparator_delay` |
| `fft_thd` | `Spectral` | Evaluer la distorsion harmonique totale par FFT. | `thd_percent`, `thd_db`, `fundamental_frequency` | `spectral.fft_thd` |
| `sfdr` | `Spectral` | Mesurer la dynamique sans raie parasite dominante. | `sfdr`, `sfdr_db`, `spur_frequency` | `spectral.sfdr` |
| `oscillator_frequency` | `Spectral` | Mesurer la frequence dominante d'un oscillateur. | `oscillator_frequency`, `frequency_hz`, `fundamental_frequency` | `spectral.oscillator_frequency` |
| `mixer_conversion_gain` | `Spectral` | Mesurer le gain ou la perte de conversion d'un mixer. | `conversion_gain_db`, `if_frequency`, `rf_to_if_gain` | `spectral.mixer_conversion_gain` |
| `common_mode_input_range` | `Differential` | Determiner la plage d'entree en mode commun admissible. | `input_common_mode_range`, `vicm_min`, `vicm_max` | `differential.common_mode_input_range` |
| `differential_gain_phase` | `Differential` | Caracteriser gain et phase en mode differentiel. | `differential_gain`, `differential_gain_db`, `phase_shift`, `common_mode_gain` | `differential.differential_gain_phase` |
| `schmitt_hysteresis` | `Differential` | Mesurer la largeur d'hysteresis et les seuils d'un trigger de Schmitt. | `hysteresis_width`, `schmitt_hysteresis`, `vih`, `vil` | `differential.schmitt_hysteresis` |
| `current_mirror_matching` | `Differential` | Evaluer l'erreur de copie et l'appariement d'un miroir de courant. | `current_ratio`, `matching_error_percent`, `output_current`, `reference_current` | `differential.current_mirror_matching` |
| `process_corners` | `PVT` | Verifier la robustesse sur coins de procede. | `corner_pass_count`, `worst_case_metric`, variations par coin | `pvt.process_corners` |
| `temperature_sweep` | `PVT` | Verifier la derive de performance avec la temperature. | `temperature_coefficient`, `metric_vs_temperature`, `worst_temp_value` | `pvt.temperature_sweep` |
| `supply_variation` | `PVT` | Verifier la sensibilite aux variations d'alimentation. | `line_regulation`, `psrr`, `metric_vs_supply`, `worst_supply_value` | `pvt.supply_variation` |

## Convention d'ecriture dans les specs YAML

- Le champ `test_categories` decrit les familles sollicitees: `dc`, `ac`, `transient`, `spectral`, `differential`, `pvt`.
- Les `performance_targets` decrivent les metriques physiques, pas les noms de familles.
- Quand un meme circuit a plusieurs objectifs, il est recommande de garder une correspondance lisible entre metrique et test canonique.

Exemple minimal:

```yaml
name: analogcoder_pro_p16_opamp
circuit_type: opamp
test_categories:
  - ac
performance_targets:
  phase_margin:
    min: 60
    unit: deg
  unity_gain_frequency:
    min: 1.0e6
    unit: Hz
```

Interpretation recommandee:

- `phase_margin` se rattache a `ac.phase_margin`
- `unity_gain_frequency` se rattache a `ac.unity_gain_frequency`

## Recommandation de contribution framework

Pour garder une convention stable dans tout le projet:

- conserver `SUPPORTED_TESTS` comme source canonique des 28 noms internes;
- afficher partout le format `family.test_name`;
- nommer les metriques YAML avec le vocabulaire physique normalise deja reconnu par l'extracteur;
- eviter les alias dans les specs utilisateur quand le nom canonique existe deja.

Cette convention permet d'aligner specs, extraction, verdicts et tableaux de benchmark sans ambiguite.
