import subprocess
from pathlib import Path

NETLIST_DIR = Path("benchmark_netlists")
RESULTS_DIR = Path("results/ngspice_logs")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

passed = 0
failed = 0

for netlist in sorted(NETLIST_DIR.glob("*.cir")):
    log_file = RESULTS_DIR / f"{netlist.stem}.log"

    cmd = ["ngspice", "-b", "-o", str(log_file), str(netlist)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    log_text = log_file.read_text(errors="ignore") if log_file.exists() else ""

    fatal_patterns = [
        "fatal error",
        "syntax error",
        "unknown parameter",
        "unknown subckt",
        "run simulation(s) aborted",
        "mismatch of .subckt",
    ]

    success_patterns = [
    "total analysis time",
    "total elapsed time",
    "device",
    "resistor models",
    "mos1:",
    ]

    has_fatal = any(p in log_text.lower() for p in fatal_patterns)
    has_success = any(p in log_text.lower() for p in success_patterns)

    ok = (result.returncode == 0 or has_success) and not has_fatal

    if ok:
        passed += 1
        status = "PASS"
    else:
        failed += 1
        status = "FAIL"

    print(f"{status}: {netlist.name}")

print()
print(f"Total: {passed + failed}")
print(f"PASS: {passed}")
print(f"FAIL: {failed}")