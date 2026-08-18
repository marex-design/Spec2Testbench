class ConstraintEngine:
    def build_constraints(self, topology, graph):
        family = topology.family

        if family == "rc_filter":
            return {
                "flow": "left_to_right",
                "input_side": "left",
                "output_side": "right",
                "ground_side": "bottom",
            }

        if family == "current_mirror":
            return {
                "symmetry": "horizontal",
                "reference_branch": "left",
                "output_branch": "right",
                "ground_side": "bottom",
            }

        if family == "differential":
            return {
                "symmetry": "vertical",
                "inputs": "left_right",
                "tail": "bottom_center",
                "loads": "top",
            }

        if family == "amplifier":
            return {
                "input_side": "left",
                "output_side": "right",
                "load_side": "top",
                "ground_side": "bottom",
            }

        if family == "oscillator":
            return {
                "feedback_loop": True,
                "output_side": "right",
            }

        if family == "diode":
            return {
                "input_side": "left",
                "output_side": "right",
                "rectifying_path": True,
            }

        if family == "opamp_macro":
            return {
                "macro_block": "opamp",
                "input_side": "left",
                "output_side": "right",
            }

        if family == "behavioral":
            return {
                "macro_block": "behavioral",
                "input_side": "left",
                "output_side": "right",
            }

        return {
            "generic": True,
        }