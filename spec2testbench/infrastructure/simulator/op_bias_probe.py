from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json, re, subprocess
import numpy as np

@dataclass(frozen=True)
class OpBiasProbeResult:
    value: float | None
    devices: tuple[str, ...]
    currents_a: tuple[float, ...]
    status: str
    reason: str | None
    metadata_path: str | None

ANALYSIS_RE = re.compile(r"^\s*\.(?:op|dc|ac|tran|four|noise|tf|sens|print|plot|measure|meas)\b", re.I)

def needs_op_bias_probe(testbench: Any) -> bool:
    md=getattr(testbench,"metadata",{}) or {}
    required={str(x).lower() for x in md.get("required_metrics",[])}
    return "minimum_device_drain_current_a" in required or any(
        getattr(m,"name","").lower()=="minimum_device_drain_current_a" for m in getattr(testbench,"measurements",[]) or []
    )

def _strip_control_sections_and_end(deck_text: str, *, strip_analyses: bool=False) -> str:
    kept=[]; in_control=False
    for raw in deck_text.splitlines():
        token=raw.strip().lower()
        if token==".control": in_control=True; continue
        if in_control:
            if token==".endc": in_control=False
            continue
        if token==".end": continue
        if strip_analyses and ANALYSIS_RE.match(raw): continue
        kept.append(raw)
    return "\n".join(kept).rstrip()+"\n"

def extract_mos_device_names_from_runnable(deck_text: str) -> list[str]:
    names=[]
    for raw in deck_text.splitlines():
        line=raw.strip()
        if not line or line.startswith(("*",".","+")): continue
        token=line.split()[0].lower()
        # flattened hierarchical MOS names include m.x...; ordinary MOS start m.
        if token.startswith("m") and token not in names:
            parts=line.split()
            if len(parts)>=6: names.append(token)
    return names

def run_op_bias_probe(*, ngspice_path: str, executed_deck_path: Path, artifact_dir: Path, timeout_seconds: float) -> OpBiasProbeResult:
    probe_dir=Path(artifact_dir)/"op_bias_probe"; probe_dir.mkdir(parents=True,exist_ok=True)
    metadata_path=probe_dir/"op_bias_metadata.json"
    def finish(value=None,devices=(),currents=(),status="NOT_EVALUATED",reason=None,extra=None):
        payload={"metric":"minimum_device_drain_current_a","status":status,"reason":reason,"value":value,
                 "devices":list(devices),"currents_a":list(currents),"executed_deck":str(executed_deck_path)}
        if extra: payload.update(extra)
        metadata_path.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")
        return OpBiasProbeResult(value,tuple(devices),tuple(currents),status,reason,str(metadata_path))
    try: source=Path(executed_deck_path).read_text(encoding="utf-8",errors="replace")
    except OSError as exc: return finish(reason=f"DECK_READ_FAILED:{exc}")
    base=_strip_control_sections_and_end(source,strip_analyses=True)
    expanded_path=(probe_dir/"expanded_runnable.ckt").resolve()
    discovery_path=(probe_dir/"discover_mos.ckt").resolve()

    # Fast, deterministic path for ordinary top-level MOS decks (all ACP-28
    # OP-bias cases use explicit M devices).  This avoids making a successful
    # proof depend on ngspice's human-oriented `listing runnable` command.
    devices=extract_mos_device_names_from_runnable(base)
    expanded_text=base
    expanded_path.write_text(expanded_text,encoding="utf-8")

    # Fallback for hierarchical/subcircuit decks: ask ngspice for its runnable
    # flattened listing.  IMPORTANT: pass an absolute deck path because cwd is
    # changed for subprocess execution; a relative path would otherwise be
    # resolved twice (the exact cause of LISTING_RUNNABLE_FAILED on Ubuntu).
    if not devices:
        discovery_path.write_text(base+"\n.control\nlisting runnable\nquit\n.endc\n.END\n",encoding="utf-8")
        try:
            run=subprocess.run([str(ngspice_path),"-b",str(discovery_path)],cwd=str(Path(executed_deck_path).parent.resolve()),capture_output=True,text=True,timeout=timeout_seconds,check=False)
        except (OSError,subprocess.TimeoutExpired) as exc: return finish(reason=f"LISTING_RUN_FAILED:{exc}")
        (probe_dir/"discover_stdout.txt").write_text(run.stdout or "",encoding="utf-8")
        (probe_dir/"discover_stderr.txt").write_text(run.stderr or "",encoding="utf-8")
        if run.returncode!=0:
            return finish(reason="LISTING_RUNNABLE_FAILED",extra={"discovery_returncode":run.returncode})
        expanded_text=run.stdout or ""
        expanded_path.write_text(expanded_text,encoding="utf-8")
        devices=extract_mos_device_names_from_runnable(expanded_text)

    if not devices: return finish(reason="NO_MOS_DEVICES_FOUND")
    vectors=[f"@{d}[id]" for d in devices]
    opdeck=(probe_dir/"op_bias.ckt").resolve()
    # Historical final fix: run OP on original circuit, not on listing text.
    expanded_base=base

    # Use one wrdata file per MOS current.  ngspice can emit different column
    # layouts for multi-vector wrdata (depending on wr_singlescale/version).
    # A single-vector file is unambiguous: its final numeric field is Id.
    value_files=[]
    wr_lines=[]
    for idx,(dev,vec) in enumerate(zip(devices,vectors)):
        vf=(probe_dir/f"op_bias_{idx:02d}_{re.sub(r'[^A-Za-z0-9_.-]+','_',dev)}.dat").resolve()
        value_files.append(vf)
        wr_lines.append(f"wrdata {vf} {vec}")

    opdeck.write_text(
        expanded_base+"\n.control\nset filetype=ascii\nset wr_singlescale\n"+
        "save "+" ".join(vectors)+"\nop\n"+
        "\n".join(wr_lines)+"\nquit\n.endc\n.END\n",
        encoding="utf-8"
    )
    try:
        op=subprocess.run([str(ngspice_path),"-b",str(opdeck)],cwd=str(probe_dir.resolve()),capture_output=True,text=True,timeout=timeout_seconds,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc: return finish(reason=f"OP_RUN_FAILED:{exc}",devices=devices)
    (probe_dir/"op_stdout.txt").write_text(op.stdout or "",encoding="utf-8"); (probe_dir/"op_stderr.txt").write_text(op.stderr or "",encoding="utf-8")
    err=((op.stderr or "")+"\n"+(op.stdout or "")).lower()
    if op.returncode!=0 or any(x in err for x in ("no such device","no such vector","no convergence","fatal")):
        return finish(reason="OP_DEVICE_CURRENT_EXTRACTION_FAILED",devices=devices,extra={"op_returncode":op.returncode})

    currents=[]
    for dev,vf in zip(devices,value_files):
        if not vf.is_file():
            return finish(reason=f"OP_DEVICE_CURRENT_FILE_MISSING:{dev}",devices=devices,extra={"op_returncode":op.returncode})
        try:
            arr=np.asarray(np.loadtxt(vf,dtype=float),dtype=float).reshape(-1)
        except (OSError,ValueError) as exc:
            return finish(reason=f"OP_WRDATA_PARSE_FAILED:{dev}:{exc}",devices=devices)
        arr=arr[np.isfinite(arr)]
        if arr.size==0:
            return finish(reason=f"OP_WRDATA_EMPTY:{dev}",devices=devices)
        currents.append(float(arr[-1]))

    raw=np.asarray(currents,dtype=float)
    value=float(np.min(np.abs(raw)))
    # Preserve a compact aggregate artifact for provenance/debugging.
    values=(probe_dir/"op_bias.dat").resolve()
    values.write_text("\n".join(f"{d} {i:.17g}" for d,i in zip(devices,currents))+"\n",encoding="utf-8")
    return finish(value=value,devices=devices,currents=currents,status="SUCCESS",extra={"aggregation":"min(abs(Id))","device_parameter":"id","op_values_file":str(values),"per_device_value_files":[str(x) for x in value_files],"expanded_runnable":str(expanded_path)})
