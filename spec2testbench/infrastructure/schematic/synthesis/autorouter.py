class AutoRouter:
    def route(self, topology, graph, placement):
        family = topology.family

        if family == "rc_filter":
            return [
                ("wire", "input_to_r"),
                ("symbol", "series_r"),
                ("wire", "r_to_out"),
                ("branch", "out_to_c_to_ground"),
            ]

        if family == "current_mirror":
            return [
                ("branch", "iref_to_ref"),
                ("symbol", "m1_diode_connected"),
                ("symbol", "m2_output"),
                ("wire", "shared_gate"),
                ("ground", "sources"),
            ]

        if family == "differential":
            return [
                ("symbol", "m1"),
                ("symbol", "m2"),
                ("wire", "sources_to_tail"),
                ("symbol", "tail_current"),
                ("symbol", "loads"),
            ]

        if family == "amplifier":
            return [
                ("symbol", "input"),
                ("symbol", "mos_core"),
                ("symbol", "load"),
                ("wire", "output"),
                ("ground", "source"),
            ]

        if family == "oscillator":
            return [
                ("symbol", "oscillator_core"),
                ("wire", "output"),
                ("loop", "feedback"),
            ]

        if family == "diode":
            return [
                ("symbol", "input"),
                ("symbol", "diode"),
                ("wire", "output"),
                ("branch", "load_to_ground"),
            ]

        if family == "opamp_macro":
            return [
                ("symbol", "opamp"),
                ("wire", "inputs"),
                ("wire", "output"),
            ]

        if family == "behavioral":
            return [
                ("symbol", "block"),
                ("wire", "input_output"),
            ]

        return [
            ("generic", "network_graph"),
        ]