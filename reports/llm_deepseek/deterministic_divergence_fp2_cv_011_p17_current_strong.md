# Deterministic Divergence fp2_cv_011_p17_current_strong

Date: 2026-07-21

- Root cause: `WRONG_OPERATOR`
- Historical evaluation outcome: `TRUE_DETECTION`
- Replay evaluation outcome: `FALSE_ACCEPT`
- Historical backend: `NGSPICE_MEASURE`
- Replay backend: `NGSPICE_MEASURE`
- Historical value: `1.999999910259551e-09`
- Replay value: `0.0003025000012599995`
- Threshold / operator: `range None`

Trace:

- Manifest: `experiments\llm_deepseek\frozen_manifest.yaml`
- Specification: `experiments\frozen_pilot_v2\fp2_cv_011_p17_current\strong\specification.yaml`
- Netlist: `experiments\frozen_pilot_v2\fp2_cv_011_p17_current\strong\netlist.cir`
- Native measurement source: `C:\Users\Admin\AppData\Local\Temp\spec2tb_native_iqc54ei4\measures.txt`
- Checker decision: `PASS`
- Ground-truth mapping: `GROUND_TRUTH_NONCOMPLIANT -> FALSE_ACCEPT`
- Aggregation: `PASS`

Generated testbench:

```spice
* TestBench: frozen_p17_currentmirror_current_full_testbench
* Category: full
* Circuit: frozen_p17_currentmirror_current

frozen_p17_currentmirror_current
.INCLUDE E:\my_organisation\Memoire Maruba\code\Spec2Testbench\experiments\frozen_pilot_v2\fp2_cv_011_p17_current\strong\netlist.cir
Vvin Iref 0 PULSE(1.25 3.75 0 1n 1n 10u 20u)
.DC vdd 5.0 5.0 0.05
.TRAN 1n 50u 0
.END
```

ngspice command:

```text
C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice_con.exe -b -r C:\Users\Admin\AppData\Local\Temp\tmp_x1xu6o0.raw C:\Users\Admin\AppData\Local\Temp\tmp_x1xu6o0.cir
```

stdout:

```text
Note: No compatibility mode selected!


Circuit: * testbench: frozen_p17_currentmirror_current_full_testbench

ASCII raw file "C:\Users\Admin\AppData\Local\Temp\tmp_x1xu6o0.raw"
Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

No. of Data Columns : 8  

No. of Data Rows : 1
No. of Data Columns : 8  

Initial Transient Solution
--------------------------

Node                                   Voltage
----                                   -------
vdd                                          5
iref                                      1.25
n1                                       0.625
n3                                         2.5
iout                                         5
vvin#branch                          -6.35e-13
vdd#branch                           -2.51e-12

 Reference value :  8.41196e-06
 Reference value :  1.65750e-05
 Reference value :  2.77620e-05
 Reference value :  3.97860e-05

No. of Data Rows : 50040

Total analysis time (seconds) = 1.177

Total elapsed time (seconds) = 1.206 

Total DRAM available = 8075.586 MB.
DRAM currently available =  386.402 MB.
Maximum ngspice program size =    9.035 MB.
Current ngspice program size =    9.031 MB.
```

stderr:

```text
Note: vvin: dc value used for op instead of transient time=0 value.
```
