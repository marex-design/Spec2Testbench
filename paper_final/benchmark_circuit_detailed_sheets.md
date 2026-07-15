# ACP-28: fiches détaillées de reconstruction schématique

## Comment lire les fiches

Chaque schéma ASCII représente la connectivité de la netlist locale, pas un placement physique. Pour les MOS, l’ordre ngspice est `M drain gate source bulk modèle`. Les corps sont reliés à la source ou au rail indiqué dans la netlist. Les blocs `[OPAMP]` correspondent à la même macro transistorisée à cinq MOS utilisée dans `p09` et `p22` à `p28`; une fiche spécifique en donne la structure. Les résultats numériques de fonctionnement doivent provenir de `.OP`, `.AC`, `.DC` ou `.TRAN`; les formules proposées sont des calculs analytiques de contrôle.

## p01_amplifier — source-commune résistif

```text
       VDD=5 V
          |
     Rload=10 kOhm
          |
 Vout o---+---D M1 NMOS
                  G--- Vin (DC 1 V, AC 1 nV)
          0 V ----S,B
```

`M1` a `W/L=50` et le modèle `KP=100 uA/V2`, `VTO=0.5 V`. Dessiner un NMOS source-commune, la résistance de drain et les deux sources `Vdd` et `Vin`. Le calcul petit signal est `A_v=-g_m(Rload||r_o)`. Pour le continu, vérifier d’abord la région de fonctionnement puis résoudre `Vout=5-I_D*10 kOhm`; si `VDS<VGS-VTO`, employer l’équation de triode et non celle de saturation.

## p02_amplifier — chaîne de trois dispositifs avec étage central polarisé

```text
 VDD             VDD              VDD
  |               |                |
 R1              R2               R3
  |               |                |
 Drain1--D M1     Drain2--D M2     Vout--D M3
          G Vin            G Bias_M2      G Drain2
          S 0              S Drain1       S 0
                             |
                  V(Bias_M2)-V(Drain1)=2 V
```

La description du manifeste parle de trois étages source-commune, mais la netlist ne câble pas `M2` comme un source-commune classique: sa source est `Drain1` et une source idéale impose `VGS2=2 V`. Il faut donc reproduire cette source flottante sur le schéma. Le gain global doit être obtenu par linéarisation nodale, puis comparé au produit `A_{v1}A_{v2}A_{v3}`; ne pas attribuer automatiquement `-g_mR` aux trois dispositifs. Tous les résistors valent `10 kOhm`, tous les MOS ont `W/L=50`.

## p03_amplifier — suiveur de source

```text
 VDD=5 V -----D M1
                 G----- Vin (DC 1 V)
 Vout o----------S,B
   |
 Rload=10 kOhm
   |
  0 V
```

Le drain est commun à l’alimentation, l’entrée est sur la grille et la sortie sur la source. Calculer `Vout≈Vin-VGS` au repos et `A_v≈g_mR_X/(1+g_mR_X)` avec `R_X=Rload||r_o`. Le gain est positif et inférieur à l’unité dans le modèle usuel.

## p04_amplifier — grille-commune

```text
       VDD=5 V
          |
     Rload=10 kOhm
          |
 Vout o---D M1
          G------ Vbias=2 V
 Vin o----S,B     (DC 0.5 V, AC 1 nV)
  |
 source Vin vers 0 V
```

L’entrée doit être dessinée à la source, point essentiel de ce circuit. Les approximations sont `Rin≈1/g_m` et `A_v≈+g_m(Rload||r_o)`. Le calcul de polarisation part de `VGS=2-0.5=1.5 V`, puis doit vérifier la saturation avec la tension `Vout` obtenue. Dans la campagne nominale canonique, la simulation réussit mais le gain extrait ne satisfait pas le seuil; ce cas illustre que simulabilité et conformité sont distinctes.

## p05_amplifier — cascode NMOS

```text
       VDD=5 V
          |
     Rload=10 kOhm
          |
 Vout o---D M2
 Vbias=3--G
  Drain_M1-S,B
          |
          D M1
 Vin=1.5--G
        0-S,B
```

Dessiner les deux NMOS empilés: `M1` convertit la tension d’entrée en courant et `M2` maintient approximativement le drain de `M1`. Le calcul utile est `A_v≈-g_m1(Rload||r_out,cas)` avec `r_out,cas≈g_m2*r_o1*r_o2`. Contrôler la marge de tension: les deux transistors doivent simultanément conserver `VDS>=VOV`.

## p06_inverter — inverseur NMOS résistif

```text
 VDD=5 V
   |
 Rload=100 kOhm
   |
 Vout o---D M1
 Vin o----G
       0--S,B
```

Pour `Vin<VTO`, `M1` est bloqué et `Vout≈VDD`. Pour `Vin>VTO`, déterminer `Vout` par `I_R=(VDD-Vout)/Rload=I_D(Vin,Vout)`. Le seuil de transfert n’est pas celui d’un inverseur CMOS symétrique; il dépend fortement de `Rload`, de `KP` et de la région de `M1`.

## p07_inverter — inverseur CMOS

```text
             VDD=5 V
                |
             S,B M_P
 Vin o-----------G
 Vout o----------D
                D M_N
 Vin o-----------G
             S,B|
               0 V
```

Les deux grilles et les deux drains sont communs. Au point de commutation, poser `I_Dn=|I_Dp|`. Avec le modèle carré et les deux MOS en saturation, utiliser `sqrt(beta_n)(V_M-VTn)=sqrt(beta_p)(VDD-V_M-|VTp|)`, où `beta=KP*W/L`. Tracer ensuite `Vout(Vin)` et repérer `VIL`, `VIH`, `VOL`, `VOH` seulement si les courbes permettent de les définir.

## p08_currentmirror — source de courant NMOS polarisée

```text
 VDD=5 V
   |
 Rload=10 kOhm
   |
 Vout o---D M1
 Vbias=1--G
       0--S,B
```

La netlist contient un seul transistor: le dessin doit donc être nommé «source de courant NMOS commandée» et non «miroir de courant classique». En saturation, `I_D≈(KP/2)(W/L)(Vbias-VTO)^2`; avec les paramètres nominaux, cette formule idéale donne `0.25 mA`, à confirmer par `.OP` et par la contrainte de charge. La tension de conformité minimale idéale est `Vout,min≈Vbias-VTO=0.5 V`.

## p09_comparator — comparateur à macro-op-amp

```text
 Vin=3 V  --------(+)
                         [OPAMP]---- Vout
 Vref=2.5 V -------(-)

 Macro interne:
 VDD --- M4 diode PMOS ----+---- drain M1 (Voutp)
 VDD --- M5 miroir PMOS ---+---- drain M2 (Vout)
                            M1(G=Vinp)  M2(G=Vinn)
                                 \      /
                                  Source3
                                     |
                              M3(G=Vbias=1.5 V)
                                     |
                                    0 V
```

Le schéma principal peut utiliser un symbole de comparateur, mais une figure scientifique doit préciser que `[OPAMP]` est la sous-circulation locale à cinq MOS ci-dessus. La règle attendue est `Vout` haut pour `Vin>Vref` et bas pour `Vin<Vref`. La netlist n’applique qu’un niveau constant `Vin=3 V`; elle ne constitue donc pas, à elle seule, un balayage complet des deux états.

## p10_lowpass — filtre RC passe-bas

```text
 Vin o---R1=10 kOhm---+---o Vout
                      |
                   C1=10 nF
                      |
                     0 V
```

`H(s)=Vout/Vin=1/(1+sR1C1)`. La constante de temps vaut `100 us`, le pôle `omega_p=10 krad/s` et `f_c=1.5915 kHz`. À `f_c`, le module idéal vaut `1/sqrt(2)` et la phase `-45 deg`.

## p11_highpass — filtre RC passe-haut

```text
 Vin o---C1=10 nF---+---o Vout
                    |
                 R1=10 kOhm
                    |
                   0 V
```

`H(s)=sR1C1/(1+sR1C1)`. La constante de temps et la fréquence de coupure sont les mêmes que pour `p10`: `100 us` et `1.5915 kHz`. À basse fréquence, le condensateur bloque; à haute fréquence, `Vout/Vin` tend vers 1.

## p12_bandpass — cascade RC passive non tamponnée

```text
 Vin--C1=10 nF--o N1--R2=10 kOhm--o Vout
                 |                    |
              R1=10 kOhm          C2=10 nF
                 |                    |
                0 V                  0 V
```

Le premier sous-réseau est passe-haut et le second passe-bas, mais `R2-C2` charge `N1`. Il faut donc écrire les deux équations nodales, `sC1(Vin-V1)=V1/R1+(V1-Vout)/R2` et `(V1-Vout)/R2=sC2Vout`, puis résoudre `H(s)`. Avec `R1=R2=R` et `C1=C2=C`, on obtient `H(s)=sRC/[1+3sRC+(sRC)^2]`. La fréquence centrale géométrique reste `1/(2pi RC)=1.5915 kHz`, mais le gain maximal est inférieur à celui d’une cascade tamponnée.

## p13_bandstop — notch RLC

```text
 Vin o---R1=1 kOhm---+---o Vout
                     |
                  L1=10 mH
                     |
                   o N1
                     |
                  C1=10 nF
                     |
                    0 V
```

La branche `L1-C1` est série vers la masse; à la résonance, son impédance idéale devient nulle et annule la sortie. `H(s)=(s^2LC+1)/(s^2LC+sRC+1)`, `f0=15.915 kHz` et `Q=sqrt(L/C)/R=1`. Dessiner clairement que `Vout` est pris avant l’inductance, et non au noeud `N1`.

## p14_amplifier — deux étages compensés Miller

```text
                 VDD=5 V                 VDD=5 V
                    |                       |
                 S,B M2 PMOS             Rload=10 kOhm
 Vbias=2.5 V -------G                       |
 Vmid o-------------D              Vout o--+--D M3
   |                                          G-- Vmid
   +---|| Cmiller=1 pF --- Vout            0--S,B
   |
   D M1 NMOS
 Vin--G
 0---S,B
```

`M2` est une charge PMOS à grille polarisée, et non un miroir dans cette netlist. Estimer `A1≈-g_m1Rout1`, `A2≈-g_m3(Rload||r_o3)`, puis `A0≈A1A2`. La capacité Miller vue au premier noeud est approximativement `Cmiller(1-A2)`; le calcul précis du pôle exige les résistances de sortie au point `.OP`.

## p15_amplifier — charge PMOS diode-connectée

```text
 VDD=5 V
   |
 S,B M2 PMOS
   |
 G,D+------o Vout
   |
   D M1 NMOS
 Vin--G
 0---S,B
```

La grille et le drain de `M2` sont court-circuités à `Vout`. En petit signal, le PMOS diode-connecté présente environ `1/(g_mp+g_dsp)`. Le gain devient `A_v≈-g_mn/(g_mP+g_dsn+g_dsp)`. Le point de repos se calcule par égalité des courants NMOS et PMOS.

## p16_opamp — paire différentielle à miroir PMOS

```text
             VDD                         VDD
              |                           |
        M3 PMOS diode               M4 PMOS miroir
         G,D=Voutp ------------------G
              |                           |
 Voutp o------D M1                   D M2------o Vout
 Vinp --------G                         G-------- Vinn
               S,B------ Stail ------S,B
                              |
                         D Mtail
 Vbias=1 V --------------G
                         S,B
                          |
                         0 V
```

Le miroir `M3-M4` transforme le courant différentiel en sortie simple sur `Vout`; `Voutp` demeure aussi exposé mais est chargé par le transistor diode-connecté. Pour une petite excitation différentielle, chaque branche reçoit approximativement `+/-g_m*v_id/2`, et le miroir additionne les variations au noeud simple. Estimer `A_d≈g_mRout` puis vérifier la plage de mode commun et la saturation des cinq MOS.

## p17_currentmirror — miroir cascode NMOS

```text
                  VDD=5 V
                 /       \
      Iref=100 uA         R1=10 kOhm
           |                   |
        o Iref              o Iout
           |                   |
       D,G M2              D M4
           S o N1       G-----o Iref
           |                   S o N3
       D,G M1              D M3
           |              G-----o N1
          0 V                  |
                              0 V
```

Dans la branche de référence, `M1` fixe le niveau `N1` et `M2` est diode-connecté au noeud `Iref`. Ces tensions commandent respectivement `M3` et `M4`. Avec dispositifs appariés et saturation, `Iout≈Iref`; le cascode élève la résistance de sortie vers l’ordre de `g_mr_o^2`. La tension minimale de sortie doit être calculée en additionnant les tensions nécessaires aux deux NMOS empilés.

## p18_opamp — paire différentielle à charges résistives

```text
            VDD=5 V                  VDD=5 V
               |                        |
           R1=10 kOhm               R2=10 kOhm
               |                        |
 Vout o--------D M1                D M2--------o Drain2
 Vinp ----------G                    G---------- Vinn
                 S,B--- SourceDiff --S,B
                           |
                       D Mtail
 Vbias=1 V ------------G
                       S,B
                        |
                       0 V
```

Pour une entrée différentielle pure et une sortie simple, l’approximation est `A_d≈-(g_m/2)(10 kOhm||r_o)`. En sortie différentielle entre `Vout` et `Drain2`, le facteur `1/2` disparaît idéalement. Calculer aussi le mode commun maximal et minimal imposé par `Mtail`, `M1-M2` et les chutes dans les résistances.

## p19_mixer — cellule de Gilbert simplifiée

```text
             VDD                         VDD
              |                           |
          RL1=1 kOhm                 RL2=1 kOhm
              |                           |
          o Voutp                     o Voutn
          /      \                   /      \
 M3 G=Vlop      M4 G=Vlon   M5 G=Vlon      M6 G=Vlop
      S RFp_out      S RFn_out    S RFp_out      S RFn_out
             \          /             \          /
          M1 G=Vrfp                  M2 G=Vrfn
                 S------ SourceNode ------S
                              |
                         M7 G=Vbias
                              |
                             0 V
```

La paire `M1-M2` transforme la tension RF différentielle en courants; `M3-M6` les commute selon le signal LO; `RL1-RL2` reconvertissent en tension différentielle. Le modèle idéal donne `v_od proportional to g_m,RF*v_RF,d*q(v_LO,d)` et des produits de mélange à `fLO+fRF` et `|fLO-fRF|`. La netlist locale utilise toutefois des tensions constantes, pas des sinusoïdes RF/LO; un calcul fréquentiel complet exige des stimuli temporels explicitement définis.

## p20_opamp — amplificateur différentiel à deux étages

```text
 Première étape:                     Deuxième étape:
 VDD       VDD                       VDD
  |         |                         |
 M4        M5                        M7 PMOS (G=Vbias3)
 G=Vbias2  G=Vbias2                   |
  |         |                    Vout o---D M6 NMOS
 Voutp     Outn                       G------ Voutp
  | M1      | M2                     S,B----- 0 V
  G Vinp    G Vinn
   \        /
      Stail--M3(G=Vbias1)--0 V

 Branche auxiliaire: VDD--M8(G=Vbias3)--Nbias--Rb--0 V
```

Les charges `M4-M5` ont toutes deux une grille fixe `Vbias2`; elles ne forment pas un miroir. `M6-M7` constituent le second étage. Calculer `A0≈A1*A2` à partir des `g_m` et résistances de sortie obtenus au repos. La branche `M8-Rb` ne commande aucun autre transistor dans cette netlist; elle doit être dessinée séparément et ne pas être présentée comme un générateur de polarisation distribué.

## p21_opamp — télescopique cascode différentiel

```text
 VDD                   VDD
  |                      |
 M7 PMOS               M8 PMOS          G(M7,M8)=Vbias4
  | S5                   | S6
 M5 PMOS               M6 PMOS          G(M5,M6)=Vbias3
  |                      |
 Voutp                  Vout
  |                      |
 M3 NMOS               M4 NMOS          G(M3,M4)=Vbias2
  | N1                   | N2
 M1 NMOS               M2 NMOS          G=M1:Vinp, M2:Vinn
   \                    /
          S_tail
             |
       M9 NMOS (G=Vbias1)
             |
            0 V
```

Le signal traverse une pile de cinq niveaux entre les rails; le dessin doit donc rendre visible la contrainte de headroom. Le gain de premier ordre est `A_d≈g_m,in*Rout`, où `Rout` combine les résistances cascodées vues vers le haut et vers le bas. Pour le calcul continu, vérifier successivement la saturation de `M9`, `M1-M2`, `M3-M4`, `M5-M6` et `M7-M8`; la marge de sortie est plus informative qu’un gain isolé.

## p22_oscillator — oscillateur RC à déphasage

```text
 Vout--R1--o N1--R2--o N2--R3--o N3--Rin=1 Ohm--o Vinn
           |          |          |                      |
          C1         C2         C3                 Rf=330 kOhm
           |          |          |                      |
          Vref       Vref       Vref              Vout--+

 Vref=2.5 V ----(+) [OPAMP]
 Vinn ------------(-)        ---- Vout
```

Pour trois sections identiques non chargées, l’approximation classique est `f0≈1/(2piRCsqrt(6))=649.7 Hz` avec un gain inverseur minimal proche de 29. Ici, `Rin=1 Ohm` au lieu d’une valeur comparable aux `10 kOhm` du réseau charge fortement `N3`, tandis que `Rf/Rin=330000`; les formules classiques ne suffisent donc pas à prouver l’oscillation. Il faut vérifier en `.TRAN` le démarrage, l’amplitude non constante, le nombre de passages par zéro et la fréquence seulement après validation de l’oscillation.

## p23_oscillator — pont de Wien

```text
 Vout--R1=10 kOhm--C1=10 nF--o N2 ----(+) [OPAMP]---- Vout
                                  |
                         R2=10 kOhm || C2=10 nF
                                  |
                              Vref=2.5 V

 Vout--Rf1=21 kOhm--o Vinn ----(-)
                     |
                 Rf2=10 kOhm
                     |
                    Vref
```

Le pont de Wien fournit une phase nulle à `f0=1/(2piRC)=1.5915 kHz` et une atténuation idéale de `1/3`. L’amplificateur non inverseur est câblé à `1+21k/10k=3.1`, légèrement au-dessus de trois pour favoriser le démarrage. La netlist ne contient aucun mécanisme explicite de stabilisation d’amplitude; ne pas prétendre à une faible distorsion sans mesure transitoire et spectrale.

## p24_integrator — intégrateur inverseur

```text
 Vin--R1=10 kOhm--o Vinn ----(-) [OPAMP]----o Vout
                    |                         |
                    +----Cf=100 nF------------+
 Vref=2.5 V ----------------(+)
```

Autour de `Vref`, définir `v_i=Vin-Vref` et `v_o=Vout-Vref`. Alors `v_o(s)=-v_i(s)/(sR1Cf)` et `dv_o/dt=-v_i/(R1Cf)`, avec `R1Cf=1 ms`. Pour une entrée constante différente de `Vref`, la sortie rampe jusqu’à saturation; l’absence de résistance en parallèle avec `Cf` implique un gain continu idéal infini.

## p25_differentiator — différenciateur inverseur

```text
 Vin--C1=10 nF--o Ninv ----(-) [OPAMP]----o Vout
                  |                          |
                  +------Rf=10 kOhm----------+
                  |
               Rb=1 MOhm
                  |
             Vref=2.5 V ----(+)
```

Dans la bande où `Rb` ne domine pas, `v_o(s)=-sRfC1*v_i(s)` avec `RfC1=100 us`. La résistance `Rb` fournit un chemin continu vers `Vref`; l’impédance d’entrée exacte est `Zin=1/(sC1)` et la contre-réaction équivalente doit tenir compte de `Rf` et `Rb` par analyse nodale. Un différenciateur idéal amplifie le bruit haute fréquence; aucune limitation HF supplémentaire n’est câblée ici.

## p26_adder — sommateur inverseur référencé

```text
 Vin1--R1=10 kOhm--+
                    +--o Vsum ----(-) [OPAMP]----o Vout
 Vin2--R2=10 kOhm--+   |                           |
                       +------Rf=10 kOhm------------+
 Vref=2.5 V -----------------(+)
```

L’équation absolue est `Vout=Vref(1+Rf/R1+Rf/R2)-Rf*Vin1/R1-Rf*Vin2/R2`. Avec les trois résistances égales, `Vout=3Vref-Vin1-Vin2`. En variables centrées, `Vout-Vref=-(Vin1-Vref)-(Vin2-Vref)`, ce qui est la forme correcte à écrire pour ce montage alimenté autour de `Vref`.

## p27_subtractor — soustracteur référencé

```text
 Vin1--R1=10 kOhm--o Vinn ----(-) [OPAMP]----o Vout
                     |                           |
                     +------R2=10 kOhm-----------+

 Vin2--R3=10 kOhm--o Vinp ----(+)
                    |
                 R4=10 kOhm
                    |
               Vref=2.5 V
```

Avec les quatre résistances égales, `Vinp=(Vin2+Vref)/2` et l’équilibre idéal impose `Vout=Vin2+Vref-Vin1`. En variables centrées, `Vout-Vref=(Vin2-Vref)-(Vin1-Vref)`. Attention: les sources de la netlist sont connectées entre `Vin1`/`Vin2` et `Vref`; les tensions absolues des noeuds valent donc `Vref+3 V` et `Vref+4 V`, ce qui peut dépasser le rail de `5 V`. Le dessin doit montrer cette référence des sources si les valeurs DC sont reproduites.

## p28_schmitt — trigger de Schmitt non inverseur

```text
 Vin ----R1=10 kOhm----+
                        +----o Vp ----(+) [OPAMP]----o Vout
 Vout --R2=100 kOhm----+                              |
                        |                              |
 Vref --R3=10 kOhm-----+             (-)--------------+
                                      Vref=2.5 V
```

Au basculement idéal, `Vp=Vref`. La loi des noeuds donne `Vin,th=Vref+(Vref-Vout)/10`. Si la sortie bascule entre `0 V` et `5 V`, le seuil montant vaut `2.75 V`, le seuil descendant `2.25 V` et l’hystérésis `0.50 V`. Utiliser les niveaux de sortie réellement mesurés dans cette formule pour un calcul fidèle à la macro-op-amp, car ils peuvent différer des rails idéaux.

## Vérifications recommandées avant mise au propre

Pour chaque schéma, conserver les noms de noeuds de la netlist sous forme de petits labels; cela permet une comparaison directe avec les rapports ngspice. Pour chaque calcul MOS, relever dans `.OP` au minimum `VGS`, `VDS`, `ID` et, si ngspice les expose, `gm` et `gds`. Pour les filtres, comparer les fréquences analytiques aux courbes `.AC`. Pour les oscillateurs, établir d’abord l’existence d’une oscillation avant d’en extraire la fréquence. Pour les blocs à op-amp, distinguer l’équation idéale du comportement réel de la macro à cinq MOS.
