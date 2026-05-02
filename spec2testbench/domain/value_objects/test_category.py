
"""
28 catégories de tests pour la vérification de circuits analogiques.
Basé sur le testbench analogique standard de l'industrie.
"""

from enum import Enum
from typing import List, Set


class TestCategory(Enum):
    """
    Catégories de tests organisées en 6 groupes fonctionnels.
    
    Groupe 1: DC Tests (4)     - Point de repos, transfert, polarisation, consommation
    Groupe 2: AC Tests (6)     - Gain, bande, phase, CMRR, PSRR, impédances
    Groupe 3: Transient (6)    - Slew rate, établissement, réponse échelon/carré
    Groupe 4: Spectral (4)     - FFT, THD, SFDR, bruit de phase
    Groupe 5: Differential (4) - Plage mode commun, gain diff, hystérésis, appariement
    Groupe 6: PVT (3)          - Corners, température, alimentation
    """

    # =========================================================
    # GROUPE 1: DC TESTS (4) - Comportement statique
    # =========================================================
    
    DC_OPERATING_POINT = "dc_operating_point"
    """
    Vérifie le point de fonctionnement DC.
    - Vérifie VGS > VTH pour chaque MOSFET
    - Vérifie VDS > VGS - VTH (région saturation)
    - Vérifie VOUT ≈ VDD/2 pour les amplis simple-ended
    """
    
    DC_TRANSFER = "dc_transfer"
    """
    Courbe de transfert DC - VOUT en fonction de VIN.
    - Détermine la plage de fonctionnement linéaire
    - Identifie les points de basculement
    - Mesure le gain DC
    """
    
    DC_BIAS_SEARCH = "dc_bias_search"
    """
    Recherche multi-résolution du point de polarisation optimal.
    - Balayage grossier (20 points sur [0.25VDD, 0.75VDD])
    - Balayage moyen (200 points, ±10%)
    - Balayage fin (2000 points, ±2%)
    - Objectif: VOUT le plus proche de VDD/2
    """
    
    DC_POWER_CONSUMPTION = "dc_power"
    """
    Mesure de la consommation de courant statique.
    - IDD au repos (quiescent current)
    - Calcul P = VDD × IDD
    - Vérifie P < P_MAX spécifiée
    """

    # =========================================================
    # GROUPE 2: AC TESTS (6) - Comportement fréquentiel petit signal
    # =========================================================
    
    AC_GAIN_BANDWIDTH = "ac_gain_bw"
    """
    Gain en boucle ouverte en fonction de la fréquence.
    - Mesure le gain DC (ADC)
    - Détermine la bande passante à -3dB
    - Calcule le produit gain-bande (GBW)
    """
    
    AC_PHASE_MARGIN = "ac_phase_margin"
    """
    Marge de phase et marge de gain.
    - Marge de phase à GBW (doit être > 45° pour stabilité)
    - Marge de gain à -180° de phase
    - Critique pour les amplificateurs en boucle fermée
    """
    
    AC_GAIN_BANDWIDTH_PRODUCT = "ac_gbp"
    """
    Produit Gain-Bande (GBW = Gain × Bande passante)
    - Figure de mérite pour amplificateurs
    - GBW = gm / (2π × CL)
    """
    
    AC_CMRR = "ac_cmrr"
    """
    Taux de Rejection du Mode Commun.
    - CMRR = |Ad| / |Acm|
    - Mesure la capacité à rejeter les signaux communs
    - Typiquement 60-100 dB pour ampli diff
    """
    
    AC_PSRR = "ac_psrr"
    """
    Taux de Rejection de l'Alimentation.
    - PSRR = variation VOUT / variation VDD
    - Critique pour les circuits sensibles au bruit d'alimentation
    """
    
    AC_IMPEDANCES = "ac_impedances"
    """
    Impédances d'entrée et de sortie.
    - Zin en fonction de la fréquence
    - Zout en fonction de la fréquence
    """

    # =========================================================
    # GROUPE 3: TRANSIENT TESTS (6) - Comportement temporel grand signal
    # =========================================================
    
    TRAN_SLEW_RATE = "tran_slew_rate"
    """
    Slew rate - vitesse de balayage maximale.
    - SR = dVOUT/dt (max)
    - Limité par le courant de polarisation
    - Important pour les grandes excursions
    """
    
    TRAN_SETTLING_TIME = "tran_settling_time"
    """
    Temps d'établissement.
    - Temps pour atteindre 1% ou 0.1% de la valeur finale
    - Critique pour les convertisseurs et buffers
    """
    
    TRAN_OVERSHOOT = "tran_overshoot"
    """
    Dépassement et oscillations transitoires.
    - Dépassement en pourcentage
    - Oscillations parasites (ringing)
    - Indicateur de stabilité en transitoire
    """
    
    TRAN_SINUSOIDAL = "tran_sinusoidal"
    """
    Réponse à un signal sinusoïdal.
    - Vérifie la distorsion en grand signal
    - Mesure l'atténuation et le déphasage
    """
    
    TRAN_SQUARE_WAVE = "tran_square_wave"
    """
    Réponse à un signal carré.
    - Temps de montée (rise time)
    - Temps de descente (fall time)
    - Test de stress pour les circuits rapides
    """
    
    TRAN_STEP_RESPONSE = "tran_step"
    """
    Réponse indicielle (échelon).
    - Changement brusque VIN = 0 → VDD
    - Caractérise la réponse naturelle du circuit
    """

    # =========================================================
    # GROUPE 4: SPECTRAL TESTS (4) - Analyse fréquentielle grand signal
    # =========================================================
    
    SPECTRAL_FFT = "spectral_fft"
    """
    Analyse FFT du signal de sortie.
    - Identifie toutes les raies spectrales
    - Détecte les harmoniques et intermodulations
    """
    
    SPECTRAL_THD = "spectral_thd"
    """
    Distorsion Harmonique Totale.
    - THD = sqrt(H2² + H3² + ...) / H1
    - Exprime la pureté du signal de sortie
    """
    
    SPECTRAL_SFDR = "spectral_sfdr"
    """
    Plage Dynamique Sans Signaux Parasites.
    - SFDR = H1 / max(spur)
    - Important pour les convertisseurs
    """
    
    SPECTRAL_PHASE_NOISE = "spectral_phase_noise"
    """
    Bruit de phase (spécifique aux oscillateurs).
    - Mesuré en dBc/Hz à offset donné
    - Critique pour les VCO et PLL
    """

    # =========================================================
    # GROUPE 5: DIFFERENTIAL TESTS (4) - Comportement différentiel
    # =========================================================
    
    DIFF_INPUT_RANGE = "diff_input_range"
    """
    Plage de tension d'entrée en mode commun.
    - ICMR = [VCM_min, VCM_max]
    - Où le circuit reste en région de fonctionnement
    """
    
    DIFF_GAIN_PHASE = "diff_gain_phase"
    """
    Gain différentiel et erreur de phase.
    - Ad = (Vout+ - Vout-) / (Vin+ - Vin-)
    - Erreur de phase entre entrée et sortie
    """
    
    DIFF_HYSTERESIS = "diff_hysteresis"
    """
    Hystérésis du trigger de Schmitt.
    - Vt+ (seuil montant)
    - Vt- (seuil descendant)
    - Hystérésis = Vt+ - Vt-
    """
    
    DIFF_MATCHING = "diff_matching"
    """
    Appariement des miroirs de courant.
    - ΔI / I entre branches miroir
    - Critique pour la précision des circuits analogiques
    """

    # =========================================================
    # GROUPE 6: PVT TESTS (3) - Robustesse procédé-tension-température
    # =========================================================
    
    PVT_PROCESS_CORNERS = "pvt_process"
    """
    Coins de procédé de fabrication.
    - TT (Typical-Typical)
    - FF (Fast-Fast) - transistors rapides
    - SS (Slow-Slow) - transistors lents
    - FS (Fast-Slow) - NMOS rapide, PMOS lent
    - SF (Slow-Fast) - NMOS lent, PMOS rapide
    """
    
    PVT_TEMPERATURE = "pvt_temperature"
    """
    Balayage en température.
    - Militaire: -55°C, 25°C, 125°C
    - Industriel: -40°C, 25°C, 85°C
    - Commercial: 0°C, 25°C, 70°C
    """
    
    PVT_SUPPLY_VARIATION = "pvt_supply"
    """
    Variation de tension d'alimentation.
    - Nominal: ±5% ou ±10%
    - Vérifie la robustesse du circuit
    """

    # =========================================================
    # MÉTHODES DE CLASSE - Regroupement par catégories
    # =========================================================
    
    @classmethod
    def all_categories(cls) -> List["TestCategory"]:
        """Retourne les 28 catégories de tests."""
        return list(cls)
    
    @classmethod
    def dc_tests(cls) -> List["TestCategory"]:
        """Retourne les 4 tests DC."""
        return [
            cls.DC_OPERATING_POINT,
            cls.DC_TRANSFER,
            cls.DC_BIAS_SEARCH,
            cls.DC_POWER_CONSUMPTION,
        ]
    
    @classmethod
    def ac_tests(cls) -> List["TestCategory"]:
        """Retourne les 6 tests AC."""
        return [
            cls.AC_GAIN_BANDWIDTH,
            cls.AC_PHASE_MARGIN,
            cls.AC_GAIN_BANDWIDTH_PRODUCT,
            cls.AC_CMRR,
            cls.AC_PSRR,
            cls.AC_IMPEDANCES,
        ]
    
    @classmethod
    def transient_tests(cls) -> List["TestCategory"]:
        """Retourne les 6 tests transitoires."""
        return [
            cls.TRAN_SLEW_RATE,
            cls.TRAN_SETTLING_TIME,
            cls.TRAN_OVERSHOOT,
            cls.TRAN_SINUSOIDAL,
            cls.TRAN_SQUARE_WAVE,
            cls.TRAN_STEP_RESPONSE,
        ]
    
    @classmethod
    def spectral_tests(cls) -> List["TestCategory"]:
        """Retourne les 4 tests spectraux."""
        return [
            cls.SPECTRAL_FFT,
            cls.SPECTRAL_THD,
            cls.SPECTRAL_SFDR,
            cls.SPECTRAL_PHASE_NOISE,
        ]
    
    @classmethod
    def differential_tests(cls) -> List["TestCategory"]:
        """Retourne les 4 tests différentiels."""
        return [
            cls.DIFF_INPUT_RANGE,
            cls.DIFF_GAIN_PHASE,
            cls.DIFF_HYSTERESIS,
            cls.DIFF_MATCHING,
        ]
    
    @classmethod
    def pvt_tests(cls) -> List["TestCategory"]:
        """Retourne les 3 tests PVT."""
        return [
            cls.PVT_PROCESS_CORNERS,
            cls.PVT_TEMPERATURE,
            cls.PVT_SUPPLY_VARIATION,
        ]
    
    # =========================================================
    # MÉTHODES D'INSTANCE
    # =========================================================
    
    @property
    def group_name(self) -> str:
        """Nom du groupe fonctionnel."""
        groups = {
            # DC
            self.DC_OPERATING_POINT: "DC Tests",
            self.DC_TRANSFER: "DC Tests",
            self.DC_BIAS_SEARCH: "DC Tests",
            self.DC_POWER_CONSUMPTION: "DC Tests",
            # AC
            self.AC_GAIN_BANDWIDTH: "AC Tests",
            self.AC_PHASE_MARGIN: "AC Tests",
            self.AC_GAIN_BANDWIDTH_PRODUCT: "AC Tests",
            self.AC_CMRR: "AC Tests",
            self.AC_PSRR: "AC Tests",
            self.AC_IMPEDANCES: "AC Tests",
            # Transient
            self.TRAN_SLEW_RATE: "Transient Tests",
            self.TRAN_SETTLING_TIME: "Transient Tests",
            self.TRAN_OVERSHOOT: "Transient Tests",
            self.TRAN_SINUSOIDAL: "Transient Tests",
            self.TRAN_SQUARE_WAVE: "Transient Tests",
            self.TRAN_STEP_RESPONSE: "Transient Tests",
            # Spectral
            self.SPECTRAL_FFT: "Spectral Tests",
            self.SPECTRAL_THD: "Spectral Tests",
            self.SPECTRAL_SFDR: "Spectral Tests",
            self.SPECTRAL_PHASE_NOISE: "Spectral Tests",
            # Differential
            self.DIFF_INPUT_RANGE: "Differential Tests",
            self.DIFF_GAIN_PHASE: "Differential Tests",
            self.DIFF_HYSTERESIS: "Differential Tests",
            self.DIFF_MATCHING: "Differential Tests",
            # PVT
            self.PVT_PROCESS_CORNERS: "PVT Tests",
            self.PVT_TEMPERATURE: "PVT Tests",
            self.PVT_SUPPLY_VARIATION: "PVT Tests",
        }
        return groups.get(self, "Other Tests")
    
    @property
    def requires_simulation(self) -> bool:
        """True si ce test nécessite une simulation SPICE."""
        # Tous les tests nécessitent une simulation sauf éventuellement certains
        return True
    
    @property
    def requires_multimodal_analysis(self) -> bool:
        """True si ce test bénéficie de l'analyse MLLM sur images."""
        multimodal_tests = {
            self.TRAN_SLEW_RATE,
            self.TRAN_SETTLING_TIME,
            self.TRAN_OVERSHOOT,
            self.TRAN_SINUSOIDAL,
            self.TRAN_SQUARE_WAVE,
            self.TRAN_STEP_RESPONSE,
            self.SPECTRAL_FFT,
            self.DIFF_HYSTERESIS,
        }
        return self in multimodal_tests
    
    @property
    def display_name_fr(self) -> str:
        """Nom français pour documentation."""
        names = {
            # DC
            self.DC_OPERATING_POINT: "Point de fonctionnement DC",
            self.DC_TRANSFER: "Courbe de transfert DC",
            self.DC_BIAS_SEARCH: "Recherche du point de polarisation",
            self.DC_POWER_CONSUMPTION: "Consommation de courant",
            # AC
            self.AC_GAIN_BANDWIDTH: "Gain en boucle ouverte",
            self.AC_PHASE_MARGIN: "Marge de phase",
            self.AC_GAIN_BANDWIDTH_PRODUCT: "Produit gain-bande",
            self.AC_CMRR: "Taux de réjection du mode commun",
            self.AC_PSRR: "Taux de réjection de l'alimentation",
            self.AC_IMPEDANCES: "Impédances d'entrée/sortie",
            # Transient
            self.TRAN_SLEW_RATE: "Slew rate",
            self.TRAN_SETTLING_TIME: "Temps d'établissement",
            self.TRAN_OVERSHOOT: "Dépassement",
            self.TRAN_SINUSOIDAL: "Réponse sinusoïdale",
            self.TRAN_SQUARE_WAVE: "Réponse au signal carré",
            self.TRAN_STEP_RESPONSE: "Réponse indicielle",
            # Spectral
            self.SPECTRAL_FFT: "Analyse FFT",
            self.SPECTRAL_THD: "Distorsion harmonique totale",
            self.SPECTRAL_SFDR: "Plage dynamique sans parasites",
            self.SPECTRAL_PHASE_NOISE: "Bruit de phase",
            # Differential
            self.DIFF_INPUT_RANGE: "Plage de tension d'entrée",
            self.DIFF_GAIN_PHASE: "Gain différentiel",
            self.DIFF_HYSTERESIS: "Hystérésis",
            self.DIFF_MATCHING: "Appariement des miroirs",
            # PVT
            self.PVT_PROCESS_CORNERS: "Coins de procédé",
            self.PVT_TEMPERATURE: "Balayage température",
            self.PVT_SUPPLY_VARIATION: "Variation d'alimentation",
        }
        return names.get(self, self.value)
    
    @classmethod
    def from_group(cls, group: str) -> List["TestCategory"]:
        """Retourne les tests d'un groupe spécifique."""
        group_map = {
            "dc": cls.dc_tests(),
            "ac": cls.ac_tests(),
            "transient": cls.transient_tests(),
            "spectral": cls.spectral_tests(),
            "differential": cls.differential_tests(),
            "pvt": cls.pvt_tests(),
        }
        return group_map.get(group.lower(), [])