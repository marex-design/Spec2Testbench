
- **`simple_drawer.py`** : réécrit pour parser réellement le netlist
  via `NetlistParser` et utiliser **SchemDraw** comme moteur de
  rendu. Chaque composant SPICE est traduit dans son symbole approprié
  (Resistor, Capacitor, Inductor, SourceV, SourceI, Diode, NFet, PFet,
  BjtNpn). Les terminaux de chaque composant sont annotés avec leur
  nom de nœud. Un panneau récapitulatif liste tous les nets et leur
  nombre de broches.

- **`netlist_parser.py`** : réécrit avec la grammaire standard SPICE.
  Le nombre de nœuds par lettre d'élément est connu et fixe :
  - R, C, L, V, I, D : 2 nœuds
  - M (MOSFET)       : 4 nœuds + modèle
  - Q (BJT)          : 3 nœuds + modèle
  - J (JFET)         : 3 nœuds + modèle
  Plus de classification heuristique douteuse.

- **`presentation/cli/main.py`** : ajout de la commande
  `spec2testbench draw --netlist <fichier.cir> --output <png>`.

- **`setup.py`** : ajout de `schemdraw>=0.19` aux dépendances.

- **Fichiers supprimés** (code mort jamais appelé) :
  - `matplotlib_drawer.py`
  - `drawer.py`
  - `layout.py`

- **Nouveau dossier `netlists/`** avec cinq exemples utilisables pour
  tester la commande `draw` :
  - `amplifier.cir`
  - `differential_amp.cir`
  - `lowpass_filter.cir`
  - `ring_oscillator.cir`
  - `current_mirror.cir`

### Test de non-régression
Les commandes `verify`, `generate`, `diagnose`, `config`, `providers`,
`version` continuent de fonctionner exactement comme avant.

### Vérification du correctif
```bash
spec2testbench draw --netlist netlists/amplifier.cir       --output amp.png
spec2testbench draw --netlist netlists/differential_amp.cir --output diff.png
spec2testbench draw --netlist netlists/lowpass_filter.cir   --output filt.png
spec2testbench draw --netlist netlists/ring_oscillator.cir  --output ring.png
spec2testbench draw --netlist netlists/current_mirror.cir   --output mirror.png
```

