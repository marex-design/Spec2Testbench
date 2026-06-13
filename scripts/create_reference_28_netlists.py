import csv
from pathlib import Path


OUT = Path("benchmark_reference_28")
OUT.mkdir(exist_ok=True)

MANIFEST = OUT / "manifest.csv"


NETLISTS = [
    (
        1,
        "Amplifier",
        "Common-source amplifier with resistive load",
        "common_source_resistive_load_amplifier.cir",
        """
* Common-source amplifier with resistive load
Vdd vdd 0 DC 5
Vin in 0 DC 1.5 AC 1 SIN(1.5 10m 1k)
Rd vdd out 10k
M1 out in 0 0 NMOS
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 10Meg
.tran 1u 5m
.end
""",
    ),
    (
        2,
        "Amplifier",
        "3-stage common-source amplifier with resistive loads",
        "three_stage_common_source_resistive_load_amplifier.cir",
        """
* Three-stage common-source resistive-load amplifier
Vdd vdd 0 DC 5
Vin in 0 DC 1.5 AC 1 SIN(1.5 5m 1k)
M1 n1 in 0 0 NMOS
R1 vdd n1 20k
M2 n2 n1 0 0 NMOS
R2 vdd n2 20k
M3 out n2 0 0 NMOS
R3 vdd out 20k
.model NMOS NMOS LEVEL=1 VTO=1 KP=0.8m
.op
.ac dec 100 10 10Meg
.tran 1u 5m
.end
""",
    ),
    (
        3,
        "Amplifier",
        "Common-drain amplifier with resistive load",
        "common_drain_resistive_load_amplifier.cir",
        """
* Common-drain amplifier with resistive load
Vdd vdd 0 DC 5
Vin in 0 DC 2 AC 1 SIN(2 10m 1k)
M1 vdd in out 0 NMOS
Rs out 0 2k
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 10Meg
.tran 1u 5m
.end
""",
    ),
    (
        4,
        "Amplifier",
        "Common-gate amplifier with resistive load",
        "common_gate_resistive_load_amplifier.cir",
        """
* Common-gate amplifier with resistive load
Vdd vdd 0 DC 5
Vin in 0 AC 1 SIN(0 10m 1k)
Vbias gate 0 DC 2
Rd vdd out 10k
M1 out gate in 0 NMOS
Rs in 0 1k
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 10Meg
.end
""",
    ),
    (
        5,
        "Amplifier",
        "Cascode amplifier with resistive load",
        "cascode_resistive_load_amplifier.cir",
        """
* Cascode amplifier with resistive load
Vdd vdd 0 DC 5
Vin in 0 DC 1.5 AC 1
Vbias cas 0 DC 2.5
Rd vdd out 10k
M1 n1 in 0 0 NMOS
M2 out cas n1 0 NMOS
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 10Meg
.end
""",
    ),
    (
        6,
        "Inverter",
        "NMOS inverter with resistive load",
        "nmos_resistive_load_inverter.cir",
        """
* NMOS inverter with resistive load
Vdd vdd 0 DC 5
Vin in 0 PULSE(0 5 0 1u 1u 1m 2m)
Rd vdd out 10k
M1 out in 0 0 NMOS
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.tran 1u 5m
.end
""",
    ),
    (
        7,
        "Inverter",
        "Logical inverter",
        "cmos_logical_inverter.cir",
        """
* CMOS logical inverter
Vdd vdd 0 DC 5
Vin in 0 PULSE(0 5 0 1n 1n 0.5u 1u)
Mp out in vdd vdd PMOS
Mn out in 0 0 NMOS
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.model PMOS PMOS LEVEL=1 VTO=-1 KP=0.5m
.op
.tran 1n 5u
.end
""",
    ),
    (
        8,
        "Current Mirror",
        "NMOS constant current source with resistive load",
        "nmos_constant_current_source_resistive_load.cir",
        """
* NMOS constant current source with resistive load
Vdd vdd 0 DC 5
Iref vdd ref DC 100u
M1 ref ref 0 0 NMOS
M2 out ref 0 0 NMOS
Rload vdd out 20k
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.dc Vdd 3 5 0.1
.end
""",
    ),
    (
        9,
        "Comparator",
        "Op-amp comparator",
        "opamp_comparator.cir",
        """
* Op-amp comparator
Vin_p inp 0 PULSE(0 2 0 1u 1u 1m 2m)
Vref inn 0 DC 1
Ecmp out 0 inp inn 1e6
Rload out 0 10k
.tran 1u 5m
.end
""",
    ),
    (
        10,
        "Filter",
        "Passive low-pass filter",
        "passive_lowpass_filter.cir",
        """
* Passive low-pass filter
Vin in 0 AC 1 SIN(0 1 1k)
R1 in out 1k
C1 out 0 159n
.ac dec 100 10 1Meg
.tran 1u 5m
.end
""",
    ),
    (
        11,
        "Filter",
        "Passive high-pass filter",
        "passive_highpass_filter.cir",
        """
* Passive high-pass filter
Vin in 0 AC 1 SIN(0 1 1k)
C1 in out 159n
R1 out 0 1k
.ac dec 100 10 1Meg
.tran 1u 5m
.end
""",
    ),
    (
        12,
        "Filter",
        "Passive band-pass filter",
        "passive_bandpass_filter.cir",
        """
* Passive band-pass filter
Vin in 0 AC 1
C1 in n1 159n
R1 n1 0 1k
R2 n1 out 1k
C2 out 0 159n
.ac dec 100 10 1Meg
.end
""",
    ),
    (
        13,
        "Filter",
        "Passive band-stop filter",
        "passive_bandstop_filter.cir",
        """
* Passive band-stop filter
Vin in 0 AC 1
R1 in n1 1k
R2 n1 out 1k
C1 n1 0 159n
C2 in n2 159n
C3 n2 out 159n
R3 n2 0 500
Rload out 0 100k
.ac dec 100 10 1Meg
.end
""",
    ),
    (
        14,
        "Amplifier",
        "Common-source amplifier with diode-connected load",
        "common_source_diode_connected_load_amplifier.cir",
        """
* Common-source amplifier with diode-connected load
Vdd vdd 0 DC 5
Vin in 0 DC 1.5 AC 1
M1 out in 0 0 NMOS
M2 out out vdd vdd PMOS
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.model PMOS PMOS LEVEL=1 VTO=-1 KP=0.5m
.op
.ac dec 100 10 10Meg
.end
""",
    ),
    (
        15,
        "Amplifier",
        "2-stage amplifier with Miller compensation",
        "two_stage_miller_compensated_amplifier.cir",
        """
* 2-stage amplifier with Miller compensation
Vdd vdd 0 DC 5
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
G1 n1 0 inp inn 1m
R1 n1 0 100k
G2 out 0 n1 0 10m
Rout out 0 10k
Cc n1 out 1p
Cl out 0 10p
.ac dec 100 10 100Meg
.tran 1u 5m
.end
""",
    ),
    (
        16,
        "Current Mirror",
        "Cascode current mirror",
        "cascode_current_mirror.cir",
        """
* Cascode current mirror
Vdd vdd 0 DC 5
Iref vdd ref DC 100u
Vbias bias 0 DC 2.5
M1 n1 ref 0 0 NMOS
M2 ref bias n1 0 NMOS
M3 n2 ref 0 0 NMOS
M4 out bias n2 0 NMOS
Rload vdd out 20k
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.end
""",
    ),
    (
        17,
        "Opamp",
        "Op-amp with active current mirror loads",
        "opamp_active_current_mirror_loads.cir",
        """
* Op-amp with active current mirror loads
Vdd vdd 0 DC 5
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
M1 n1 inp tail 0 NMOS
M2 out inn tail 0 NMOS
M3 n1 n1 vdd vdd PMOS
M4 out n1 vdd vdd PMOS
Itail tail 0 DC 200u
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.model PMOS PMOS LEVEL=1 VTO=-1 KP=0.5m
.op
.ac dec 100 10 100Meg
.end
""",
    ),
    (
        18,
        "Opamp",
        "Common-source op-amp with resistive loads",
        "common_source_resistive_load_opamp.cir",
        """
* Common-source op-amp with resistive loads
Vdd vdd 0 DC 5
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
M1 outp inp tail 0 NMOS
M2 outn inn tail 0 NMOS
R1 vdd outp 20k
R2 vdd outn 20k
Itail tail 0 DC 200u
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 100Meg
.end
""",
    ),
    (
        19,
        "Mixer",
        "Gilbert cell mixer",
        "gilbert_cell_mixer.cir",
        """
* Gilbert-cell-style mixer approximation
Vrf rf 0 SIN(0 0.1 10Meg)
Vlo lo 0 SIN(0 1 11Meg)
Bmix out 0 V = V(rf)*V(lo)
Rload out 0 50
.tran 1n 5u
.end
""",
    ),
    (
        20,
        "Opamp",
        "Cascode op-amp with cascode loads",
        "cascode_opamp_cascode_loads.cir",
        """
* Cascode op-amp with cascode loads
Vdd vdd 0 DC 5
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
Gm n1 0 inp inn 1m
Rcas n1 out 100k
Rload out 0 10k
Cdom out 0 5p
.ac dec 100 10 100Meg
.end
""",
    ),
    (
        21,
        "Opamp",
        "2-stage op-amp with active loads",
        "two_stage_opamp_active_loads.cir",
        """
* 2-stage op-amp with active loads
Vdd vdd 0 DC 5
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
G1 n1 0 inp inn 1m
R1 n1 0 100k
G2 out 0 n1 0 10m
Rload out 0 20k
Ccomp n1 out 1p
.ac dec 100 10 100Meg
.tran 1u 5m
.end
""",
    ),
    (
        22,
        "Oscillator",
        "Wien Bridge oscillator",
        "wien_bridge_oscillator.cir",
        """
* Wien Bridge oscillator approximation
Vdd vdd 0 DC 12
Bosc out 0 V = 2*sin(2*3.14159*1k*time)
R1 out n1 10k
C1 n1 0 15.9n
R2 n1 fb 10k
C2 fb out 15.9n
Rload out 0 100k
.tran 10u 20m
.end
""",
    ),
    (
        23,
        "Oscillator",
        "RC Shift oscillator",
        "rc_shift_oscillator.cir",
        """
* RC shift oscillator approximation
Bosc out 0 V = sin(2*3.14159*1k*time)
R1 out n1 10k
C1 n1 0 10n
R2 n1 n2 10k
C2 n2 0 10n
R3 n2 n3 10k
C3 n3 0 10n
Rload out 0 100k
.tran 10u 20m
.end
""",
    ),
    (
        24,
        "Integrator",
        "Op-amp integrator",
        "opamp_integrator.cir",
        """
* Op-amp integrator
Vin in 0 PULSE(0 1 0 1u 1u 1m 2m)
Rin in nminus 10k
Cfb out nminus 1u
Eop out 0 0 nminus 1e5
Rbias nminus 0 1Meg
.tran 10u 10m
.end
""",
    ),
    (
        25,
        "Differentiator",
        "Op-amp differentiator",
        "opamp_differentiator.cir",
        """
* Op-amp differentiator
Vin in 0 PULSE(0 1 0 1u 1u 1m 2m)
Cin in nminus 100n
Rf out nminus 10k
Eop out 0 0 nminus 1e5
Rbias nminus 0 1Meg
.tran 1u 5m
.end
""",
    ),
    (
        26,
        "Adder",
        "Op-amp adder",
        "opamp_adder.cir",
        """
* Op-amp adder
V1 in1 0 SIN(0 0.5 1k)
V2 in2 0 SIN(0 0.5 2k)
R1 in1 nminus 10k
R2 in2 nminus 10k
Rf out nminus 10k
Eop out 0 0 nminus 1e5
Rbias nminus 0 1Meg
.tran 10u 5m
.ac dec 100 10 100k
.end
""",
    ),
    (
        27,
        "Subtractor",
        "Op-amp subtractor",
        "opamp_subtractor.cir",
        """
* Op-amp subtractor
V1 in1 0 SIN(0 0.5 1k)
V2 in2 0 SIN(0 0.5 2k)
R1 in1 nminus 10k
R2 out nminus 10k
R3 in2 nplus 10k
R4 nplus 0 10k
Eop out 0 nplus nminus 1e5
.tran 10u 5m
.ac dec 100 10 100k
.end
""",
    ),
    (
        28,
        "Schmitt Trigger",
        "Non-inverting Schmitt trigger",
        "non_inverting_schmitt_trigger.cir",
        """
* Non-inverting Schmitt trigger
Vin in 0 PULSE(0 5 0 1u 1u 1m 2m)
R1 out nplus 100k
R2 nplus 0 100k
Eop out 0 in nplus 1e6
Rload out 0 10k
.tran 1u 5m
.end
""",
    ),
]


def main():
    with MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "family", "description", "filename"])
        for identifier, family, description, filename, content in NETLISTS:
            (OUT / filename).write_text(content.strip() + "\n", encoding="utf-8")
            writer.writerow([identifier, family, description, filename])

    print(f"Generated {len(NETLISTS)} reference netlists in {OUT}")
    print(f"Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
