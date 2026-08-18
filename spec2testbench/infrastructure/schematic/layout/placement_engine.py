class PlacementEngine:

    def place_lowpass(self):
        return {
            "Vin": (-6, 0),
            "R1": (-1, 0),
            "out": (4, 0),
            "C1": (4, -3),
            "0": (4, -6),
        }