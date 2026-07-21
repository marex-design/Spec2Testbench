# Deterministic Divergence ref_fp2_p01_amplifier

Date: 2026-07-21

- Root cause: `WRONG_TESTBENCH`
- Historical evaluation outcome: `TRUE_ACCEPT`
- Replay evaluation outcome: `FALSE_REJECT`
- Historical backend: `NGSPICE_MEASURE`
- Replay backend: `NGSPICE_MEASURE`
- Historical value: `-31.88738224966965`
- Replay value: `-600.0`
- Threshold / operator: `>= -35.0`

Trace:

- Manifest: `experiments\llm_deepseek\frozen_manifest.yaml`
- Specification: `experiments\frozen_pilot_v2\ref_fp2_p01_amplifier\specification.yaml`
- Netlist: `benchmark\analogcoder_pro\p01_amplifier.cir`
- Native measurement source: `C:\Users\Admin\AppData\Local\Temp\spec2tb_native_kku9v32e\measures.txt`
- Checker decision: `FAIL`
- Ground-truth mapping: `GROUND_TRUTH_COMPLIANT -> FALSE_REJECT`
- Aggregation: `FAIL`

Generated testbench:

```spice
* TestBench: frozen_p01_amplifier_gain_full_testbench
* Category: full
* Circuit: frozen_p01_amplifier_gain

frozen_p01_amplifier_gain
.INCLUDE E:\my_organisation\Memoire Maruba\code\Spec2Testbench\benchmark\analogcoder_pro\p01_amplifier.cir
Vvin Vin 0 2.5
Vvin Vin 0 AC 1
Vvin Vin 0 PULSE(1.25 3.75 0 1n 1n 10u 20u)
.OP
.AC dec 10 1 1000000000.0
.TRAN 1n 50u 0
.END
```

ngspice command:

```text
C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice_con.exe -b -r C:\Users\Admin\AppData\Local\Temp\tmpnzw96wb5.raw C:\Users\Admin\AppData\Local\Temp\tmpnzw96wb5.cir
```

stdout:

```text
Note: No compatibility mode selected!


Circuit: * testbench: frozen_p01_amplifier_gain_full_testbench

ASCII raw file "C:\Users\Admin\AppData\Local\Temp\tmpnzw96wb5.raw"
Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

No. of Data Columns : 6  

No. of Data Rows : 91
No. of Data Columns : 5  

No. of Data Rows : 1
No. of Data Columns : 6  

Initial Transient Solution
--------------------------

Node                                   Voltage
----                                   -------
vdd                                          5
vin                                       1.25
vout                                  0.143183
vin#branch                                   0
vdd#branch                        -0.000485682

 Reference value :  2.47420e-05

No. of Data Rows : 50040

Total analysis time (seconds) = 0.475

Total elapsed time (seconds) = 0.490 

Total DRAM available = 8075.586 MB.
DRAM currently available =  909.496 MB.
Maximum ngspice program size =    9.031 MB.
Current ngspice program size =    9.027 MB.
```

stderr:

```text
Note: vin: dc value used for op instead of transient time=0 value.
```
