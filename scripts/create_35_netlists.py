from pathlib import Path

OUT = Path("benchmark_netlists")
OUT.mkdir(exist_ok=True)

netlists = {
"lowpass_filter.cir": """
* RC Low-Pass Filter
Vin in 0 AC 1 SIN(0 1 1k)
R1 in out 1k
C1 out 0 159n
.ac dec 100 10 1Meg
.tran 1u 5m
.end
""",

"highpass_filter.cir": """
* RC High-Pass Filter
Vin in 0 AC 1 SIN(0 1 1k)
C1 in out 159n
R1 out 0 1k
.ac dec 100 10 1Meg
.tran 1u 5m
.end
""",

"bandpass_filter.cir": """
* Passive RC Band-Pass Filter
Vin in 0 AC 1
C1 in n1 159n
R1 n1 0 1k
R2 n1 out 1k
C2 out 0 159n
.ac dec 100 10 1Meg
.end
""",

"notch_filter.cir": """
* Simple Twin-T Notch Approximation
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

"rc_integrator.cir": """
* RC Integrator
Vin in 0 PULSE(0 1 0 1u 1u 1m 2m)
R1 in out 10k
C1 out 0 1u
.tran 10u 10m
.end
""",

"rc_differentiator.cir": """
* RC Differentiator
Vin in 0 PULSE(0 1 0 1u 1u 1m 2m)
C1 in out 100n
R1 out 0 1k
.tran 1u 5m
.end
""",

"common_source_amplifier.cir": """
* NMOS Common Source Amplifier
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

"common_drain_amplifier.cir": """
* Source Follower
Vdd vdd 0 DC 5
Vin in 0 DC 2 AC 1 SIN(2 10m 1k)
Rd vdd d 1
M1 d in out 0 NMOS
Rs out 0 2k
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 10Meg
.end
""",

"common_gate_amplifier.cir": """
* Common Gate Amplifier
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

"differential_amplifier.cir": """
* NMOS Differential Amplifier
Vdd vdd 0 DC 5
V1 in_p 0 DC 1.5 AC 0.5
V2 in_n 0 DC 1.5 AC -0.5
M1 out_p in_p tail 0 NMOS
M2 out_n in_n tail 0 NMOS
R1 vdd out_p 10k
R2 vdd out_n 10k
Itail tail 0 DC 500u
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 10Meg
.end
""",

"operational_amplifier.cir": """
* Simplified Voltage-Controlled Op-Amp
Vdd vdd 0 DC 15
Vss vss 0 DC -15
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
Eop out 0 inp inn 100000
Rout out vout 100
Cdom vout 0 10p
Rload vout 0 10k
.ac dec 100 1 100Meg
.tran 1u 5m
.end
""",

"current_mirror.cir": """
* NMOS Current Mirror
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

"cascode_current_mirror.cir": """
* Cascode Current Mirror
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

"widlar_current_source.cir": """
* Widlar Current Source Approximation
Vdd vdd 0 DC 5
Iref vdd ref DC 100u
M1 ref ref 0 0 NMOS
M2 out ref n1 0 NMOS
Rs n1 0 1k
Rload vdd out 20k
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.end
""",

"bandgap_reference.cir": """
* Simplified Bandgap-Like Reference
Vdd vdd 0 DC 5
D1 n1 0 DIODE
D2 n2 0 DIODE
R1 vdd n1 10k
R2 vdd n2 20k
R3 n1 vref 5k
R4 n2 vref 5k
.model DIODE D IS=1e-14
.op
.dc temp -40 125 5
.end
""",

"voltage_reference.cir": """
* Zener Voltage Reference Approximation
Vin in 0 DC 10
R1 in vref 1k
D1 0 vref ZD
Rload vref 0 10k
.model ZD D BV=5.1 IBV=1m
.op
.dc Vin 5 12 0.5
.end
""",

"comparator.cir": """
* Ideal Comparator
Vin_p inp 0 PULSE(0 2 0 1u 1u 1m 2m)
Vref inn 0 DC 1
Ecmp out 0 inp inn 1e6
Rload out 0 10k
.tran 1u 5m
.end
""",

"schmitt_trigger.cir": """
* Simplified Schmitt Trigger
Vin in 0 PULSE(0 5 0 1u 1u 1m 2m)
E1 out 0 VALUE = { V(in) > 2.5 ? 5 : 0 }
Rload out 0 10k
.tran 1u 5m
.end
""",

"ring_oscillator.cir": """
* 3-Stage Ring Oscillator
Vdd vdd 0 DC 5
X1 n1 n2 vdd 0 inv
X2 n2 n3 vdd 0 inv
X3 n3 n1 vdd 0 inv
.ic v(n1)=0 v(n2)=5 v(n3)=0
.subckt inv in out vdd gnd
Mp out in vdd vdd PMOS W=10u L=1u
Mn out in gnd gnd NMOS W=5u L=1u
.ends inv
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.model PMOS PMOS LEVEL=1 VTO=-1 KP=0.5m
.tran 1n 1u
.end
""",

"lc_oscillator.cir": """
* LC Tank Oscillator Approximation
Vinit n1 0 PULSE(0 1 0 1n 1n 10n 20n)
L1 n1 out 10u
C1 out 0 100p
Rloss out 0 10k
.tran 1n 10u
.end
""",

"relaxation_oscillator.cir": """
* RC Relaxation Oscillator Approximation
Vdd vdd 0 DC 5
R1 vdd cap 10k
C1 cap 0 100n
Ecmp out 0 VALUE = { V(cap) > 2.5 ? 0 : 5 }
Rfb out cap 100k
.tran 10u 20m
.end
""",

"mixer.cir": """
* Simple Multiplicative Mixer Approximation
Vrf rf 0 SIN(0 0.1 10Meg)
Vlo lo 0 SIN(0 1 11Meg)
Bmix out 0 V = V(rf)*V(lo)
Rload out 0 50
.tran 1n 5u
.end
""",

"rectifier.cir": """
* Half-Wave Rectifier
Vin in 0 SIN(0 5 1k)
D1 in out DIODE
Rload out 0 1k
.model DIODE D IS=1e-14
.tran 10u 10m
.end
""",

"peak_detector.cir": """
* Peak Detector
Vin in 0 SIN(0 5 1k)
D1 in out DIODE
C1 out 0 10u
Rload out 0 100k
.model DIODE D IS=1e-14
.tran 10u 20m
.end
""",

"sample_and_hold.cir": """
* Sample and Hold Approximation
Vin in 0 SIN(0 1 1k)
Vclk clk 0 PULSE(0 5 0 1u 1u 0.2m 1m)
S1 in out clk 0 SW
Chold out 0 1n
Rload out 0 1Meg
.model SW SW RON=10 ROFF=1Meg VON=2 VOFF=1
.tran 1u 5m
.end
""",

"charge_pump.cir": """
* Simple Diode Charge Pump
Vin in 0 PULSE(0 5 0 1n 1n 1u 2u)
C1 in n1 100n
D1 n1 out DIODE
D2 0 n1 DIODE
C2 out 0 100n
Rload out 0 10k
.model DIODE D IS=1e-14
.tran 10n 100u
.end
""",

"lna.cir": """
* Simplified Low Noise Amplifier
Vdd vdd 0 DC 3.3
Vin in 0 AC 1 SIN(0 1m 1Meg)
Lg in gate 10n
M1 out gate 0 0 NMOS
Ld vdd out 100n
Rload out 0 1k
.model NMOS NMOS LEVEL=1 VTO=0.7 KP=5m
.op
.ac dec 100 1k 1Gig
.end
""",

"vco.cir": """
* Voltage Controlled Oscillator Approximation
Vctrl ctrl 0 DC 1
Bosc out 0 V = sin(2*3.14159*(1e6+1e6*V(ctrl))*time)
Rload out 0 1k
.tran 10n 20u
.end
""",

"ota.cir": """
* Simplified OTA
Vdd vdd 0 DC 5
Vin_p inp 0 DC 1.5 AC 0.5
Vin_n inn 0 DC 1.5 AC -0.5
Gm out 0 inp inn 1m
Rout out 0 100k
Cl out 0 10p
.ac dec 100 10 100Meg
.tran 1u 5m
.end
""",

"folded_cascode_opamp.cir": """
* Simplified Folded Cascode Op-Amp Macro
Vdd vdd 0 DC 5
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
Gm n1 0 inp inn 1m
Rcas n1 out 100k
Cdom out 0 5p
Rload out 0 10k
.ac dec 100 10 100Meg
.end
""",

"two_stage_opamp.cir": """
* Simplified Two-Stage Op-Amp
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

"instrumentation_amplifier.cir": """
* Simplified Instrumentation Amplifier
Vin_p inp 0 AC 0.5
Vin_n inn 0 AC -0.5
E1 n1 0 inp inn 10
E2 out 0 n1 0 10
Rload out 0 10k
.ac dec 100 10 10Meg
.end
""",

"active_load_amplifier.cir": """
* Common Source Amplifier with Active Load
Vdd vdd 0 DC 5
Vin in 0 DC 1.5 AC 1
M1 out in 0 0 NMOS
M2 out bias vdd vdd PMOS
Vbias bias 0 DC 3.5
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.model PMOS PMOS LEVEL=1 VTO=-1 KP=0.5m
.op
.ac dec 100 10 10Meg
.end
""",

"source_follower.cir": """
* Source Follower
Vdd vdd 0 DC 5
Vin in 0 DC 2 AC 1
M1 vdd in out 0 NMOS
Rs out 0 2k
.model NMOS NMOS LEVEL=1 VTO=1 KP=1m
.op
.ac dec 100 10 10Meg
.end
""",

"transimpedance_amplifier.cir": """
* Transimpedance Amplifier Macro
Iin in 0 AC 1u SIN(0 1u 1k)
Rfb out in 100k
Eop out 0 0 in 1e5
Cfb out in 1p
Rload out 0 10k
.ac dec 100 10 100Meg
.end
"""
}

for filename, content in netlists.items():
    path = OUT / filename
    path.write_text(content.strip() + "\n", encoding="utf-8")

print(f"Generated {len(netlists)} netlists in {OUT}/")