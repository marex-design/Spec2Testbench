import subprocess
from pathlib import Path
import csv
import sys
import math
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import traceback
from spec2testbench.domain.registry import circuit_kb


NETLIST_DIR = Path("benchmark_netlists")
OUT_RAW_DIR = Path("results/raw")
OUT_RAW_DIR.mkdir(parents=True, exist_ok=True)
PREPARED_NETLIST_DIR = Path("results/prepared_netlists")
PREPARED_NETLIST_DIR.mkdir(parents=True, exist_ok=True)
NGSPICE_LOG_DIR = Path("results/ngspice_logs")
NGSPICE_LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = Path("results/metrics.csv")

# optional overrides: results/node_override.csv with columns circuit,preferred_out_node
NODE_OVERRIDE_CSV = Path('results/node_override.csv')
NODE_OVERRIDES = {}
if NODE_OVERRIDE_CSV.exists():
    try:
        with NODE_OVERRIDE_CSV.open('r', encoding='utf-8') as f:
            import csv as _csv
            rdr = _csv.DictReader(f)
            for row in rdr:
                c = row.get('circuit')
                n = row.get('preferred_out_node') or row.get('suggested_node')
                if c and n:
                    NODE_OVERRIDES[c] = n
    except Exception:
        NODE_OVERRIDES = {}


def run_ngspice_with_raw(netlist: Path, raw_path: Path, log_path: Path):
    cmd = ["ngspice", "-b", "-r", str(raw_path), str(netlist)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    return result


def _strip_final_end(text: str) -> str:
    return re.sub(r"\n\.end\s*$", "", text.strip(), flags=re.IGNORECASE)


def prepare_netlist_for_campaign(netlist: Path) -> tuple[Path, dict]:
    text = netlist.read_text(errors="ignore")
    lower = text.lower()
    notes = []

    has_ac = ".ac" in lower
    has_tran = ".tran" in lower
    has_op = re.search(r"^\s*\.op\b", text, re.IGNORECASE | re.MULTILINE) is not None
    has_dc = re.search(r"^\s*\.dc\b", text, re.IGNORECASE | re.MULTILINE) is not None
    has_any_analysis = has_ac or has_tran or has_op or has_dc

    has_ac_source = re.search(r"^\s*[vi]\w*\s+\S+\s+\S+.*\bac\b", text, re.IGNORECASE | re.MULTILINE) is not None
    has_time_source = any(token in lower for token in ("sin(", "pulse(", "pwl(", "exp("))

    prepared = _strip_final_end(text)

    if not has_any_analysis:
        prepared += "\n.op"
        notes.append("injected_op")

    if has_ac_source and not has_ac:
        prepared += "\n.ac dec 100 10 100Meg"
        notes.append("injected_ac")

    if has_time_source and not has_tran:
        prepared += "\n.tran 1u 5m"
        notes.append("injected_tran")

    prepared += "\n.end\n"

    prepared_path = PREPARED_NETLIST_DIR / netlist.name
    prepared_path.write_text(prepared, encoding="utf-8")

    return prepared_path, {
        "prepared_netlist": str(prepared_path),
        "preparation_notes": ";".join(notes),
        "injected_analyses": sum(1 for note in notes if note.startswith("injected_")),
    }


def parse_raw(raw_path: Path):
    try:
        if not raw_path.exists():
            return None, "raw file missing"
        text = raw_path.read_text(errors='ignore')
        if not text.lstrip().startswith('Title:'):
            return None, "unsupported raw format"

        lines = text.splitlines()
        plot_starts = [i for i, line in enumerate(lines) if line.startswith('Plotname:')]
        if not plot_starts:
            return None, "missing Plotname"

        plot_starts.append(len(lines))
        plots = {}

        def parse_value(raw_value: str, variable_name: str):
            raw_value = raw_value.strip()
            if ',' in raw_value:
                try:
                    real_str, imag_str = raw_value.split(',', 1)
                    real = float(real_str)
                    imag = float(imag_str)
                    if variable_name.lower() == 'frequency':
                        return real
                    return math.hypot(real, imag)
                except Exception:
                    return float('nan')
            try:
                return float(raw_value)
            except Exception:
                return float('nan')

        for idx in range(len(plot_starts) - 1):
            start = plot_starts[idx]
            end = plot_starts[idx + 1]
            section = lines[start:end]
            plotname = section[0].split(':', 1)[1].strip()

            nvars = None
            npoints = None
            vars_list = []
            values_idx = None

            for i, line in enumerate(section):
                lower = line.lower().strip()
                if lower.startswith('no. variables'):
                    nvars = int(line.split(':', 1)[1].strip())
                elif lower.startswith('no. points'):
                    npoints = int(line.split(':', 1)[1].strip())
                elif lower == 'variables:':
                    j = i + 1
                    while j < len(section):
                        current = section[j].strip()
                        if not current:
                            j += 1
                            continue
                        if current.lower() == 'values:':
                            break
                        tokens = current.split()
                        if len(tokens) >= 2 and tokens[0].isdigit():
                            vars_list.append(tokens[1])
                        j += 1
                elif lower == 'values:':
                    values_idx = i + 1
                    break

            if not vars_list or values_idx is None or not nvars:
                continue

            data_cols = {name: [] for name in vars_list}
            i = values_idx
            points_read = 0
            while i < len(section) and (npoints is None or points_read < npoints):
                line = section[i]
                if not line.strip():
                    i += 1
                    continue

                match = re.match(r'^\s*(\d+)\s+(.+?)\s*$', line)
                if not match:
                    i += 1
                    continue

                data_cols[vars_list[0]].append(parse_value(match.group(2), vars_list[0]))
                i += 1

                for var_index in range(1, len(vars_list)):
                    if i >= len(section):
                        break
                    data_cols[vars_list[var_index]].append(parse_value(section[i].strip(), vars_list[var_index]))
                    i += 1

                points_read += 1

            plots[plotname.lower()] = {name: np.array(values) for name, values in data_cols.items()}

        if not plots:
            return None, "no plots parsed"

        first_plot = next(iter(plots.values()))
        combined = dict(first_plot)
        combined["__plots__"] = plots
        return combined, None
    except Exception as e2:
        return None, f"raw parse fallback error: {e2}"


def analyze_tran(data: dict):
    # find time variable
    time_key = None
    for k in data.keys():
        if 'time' in k.lower():
            time_key = k
            break
    if time_key is None:
        return {}, "no time"

    time = data[time_key]
    # pick best voltage signal (largest std deviation)
    volt_keys = [k for k in data.keys() if k.lower().startswith('v') or 'v(' in k.lower()]
    if not volt_keys:
        return {}, "no voltage"

    best = max(volt_keys, key=lambda k: float(np.std(data[k])))
    v = data[best]

    if len(time) < 2:
        return {}, "insufficient samples"

    dt = np.mean(np.diff(time))
    # amplitude peak-to-peak
    amp_pp = float(np.max(v) - np.min(v))

    # frequency via FFT
    try:
        # detrend
        v_detr = v - np.mean(v)
        N = len(v_detr)
        yf = np.fft.rfft(v_detr)
        xf = np.fft.rfftfreq(N, dt)
        idx = np.argmax(np.abs(yf[1:])) + 1 if len(yf) > 1 else 0
        freq = float(xf[idx]) if xf.size > 0 else float('nan')
    except Exception:
        freq = float('nan')

    # rise time 10%-90% (first rising edge)
    try:
        v_min = np.min(v)
        v_max = np.max(v)
        v10 = v_min + 0.1 * (v_max - v_min)
        v90 = v_min + 0.9 * (v_max - v_min)
        # find indices where crosses
        above10 = np.where(v >= v10)[0]
        above90 = np.where(v >= v90)[0]
        if above10.size and above90.size:
            t10 = time[above10[0]]
            # find first index after t10 where >= v90
            after = above90[above90 >= above10[0]]
            if after.size:
                t90 = time[after[0]]
                rise_time = float(t90 - t10)
            else:
                rise_time = float('nan')
        else:
            rise_time = float('nan')
    except Exception:
        rise_time = float('nan')

    return {
        'signal': best,
        'amplitude_pp': amp_pp,
        'frequency_hz': freq,
        'rise_time_s': rise_time
    }, None


def extract_metrics_by_type(data: dict, stem: str, netlist_text: str):
    """Extract metrics using circuit knowledge and analysis type detection.

    Robust, normalized implementation: returns (metrics_dict, parse_err, circ_type).
    """
    kb = circuit_kb.classify_from_stem(stem)
    circ_type = kb['type'] if kb else circuit_kb.heuristic_classify(netlist_text)
    plots = data.get('__plots__', {}) if isinstance(data, dict) else {}

    def normalize_dataset(dataset):
        norm = {}
        for key, value in dataset.items():
            if key == '__plots__':
                continue
            try:
                arr = np.array(value)
                if arr.ndim == 0:
                    arr = np.atleast_1d(arr)
                norm[key] = arr
            except Exception:
                norm[key] = np.array([])
        return norm

    flat_data = normalize_dataset(data)
    plot_data = {name: normalize_dataset(dataset) for name, dataset in plots.items()}

    ac_data = next((dataset for name, dataset in plot_data.items() if 'ac analysis' in name), None)
    tran_data = next((dataset for name, dataset in plot_data.items() if 'transient analysis' in name), None)
    op_data = next((dataset for name, dataset in plot_data.items() if 'operating point' in name or 'dc transfer' in name), None)

    if ac_data is None and any('frequency' in key.lower() for key in flat_data.keys()):
        ac_data = flat_data
    if tran_data is None and any('time' in key.lower() for key in flat_data.keys()):
        tran_data = flat_data
    if op_data is None and ac_data is None and tran_data is None:
        op_data = flat_data

    def choose_node(role: str, dataset: dict | None):
        if not dataset:
            return None, 'none'
        try:
            if role == 'out' and stem in NODE_OVERRIDES:
                override = NODE_OVERRIDES.get(stem)
                if override and override in dataset:
                    return override, 'override'
        except Exception:
            pass

        if kb and 'nodes' in kb and role in kb['nodes']:
            for name in kb['nodes'].get(role, []):
                for key in dataset.keys():
                    if name.lower() in key.lower():
                        return key, 'kb'

        patterns = {
            'out': ['v(vout)', 'v(out)', 'out', 'vout', 'vo'],
            'in': ['v(vin)', 'v(in)', 'v(inp)', 'in', 'vin', 'vi']
        }
        for pattern in patterns.get(role, []):
            for key in dataset.keys():
                if pattern in key.lower():
                    return key, 'pattern'

        volt_keys = [key for key in dataset.keys() if key.lower().startswith('v') or 'v(' in key.lower()]
        if not volt_keys:
            return None, 'none'
        try:
            ordered = sorted(volt_keys, key=lambda key: float(np.nanstd(np.abs(dataset[key]))), reverse=True)
            node = ordered[0] if role == 'out' else (ordered[1] if len(ordered) > 1 else ordered[0])
            return node, 'stddev'
        except Exception:
            return volt_keys[0], 'stddev'

    ac_out, ac_out_reason = choose_node('out', ac_data or op_data or tran_data)
    ac_in, ac_in_reason = choose_node('in', ac_data or op_data or tran_data)
    tran_out, tran_out_reason = choose_node('out', tran_data or ac_data or op_data)
    tran_in, tran_in_reason = choose_node('in', tran_data or ac_data or op_data)
    op_out, op_out_reason = choose_node('out', op_data or ac_data or tran_data)
    op_in, op_in_reason = choose_node('in', op_data or ac_data or tran_data)

    metrics = {}
    parse_err = ''

    try:
        if op_data is not None:
            if op_out and op_out in op_data and op_data[op_out].size >= 1:
                try:
                    metrics['vout_dc'] = float(np.real(np.atleast_1d(op_data[op_out])[0]))
                except Exception:
                    metrics['vout_dc'] = float('nan')

            cur_keys = [key for key in op_data.keys() if key.lower().startswith('i') or 'i(' in key.lower()]
            if cur_keys:
                try:
                    metrics['mean_current_a'] = float(np.mean([float(np.real(np.atleast_1d(op_data[key])[0])) for key in cur_keys]))
                except Exception:
                    metrics['mean_current_a'] = float('nan')
                supply_match = re.search(
                    r"^(V[\w$]+)\s+(\S+)\s+(\S+)\s+DC\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
                    netlist_text,
                    re.IGNORECASE | re.MULTILINE,
                )
                if supply_match:
                    try:
                        supply_value = float(supply_match.group(4))
                        metrics['quiescent_power_w'] = abs(metrics['mean_current_a']) * supply_value
                    except Exception:
                        pass

        if ac_data is not None and circ_type in ('filter', 'amplifier', 'mixer', 'reference', 'bandgap'):
            freq_key = next((key for key in ac_data.keys() if key.lower() == 'frequency'), None)
            freq_arr = np.atleast_1d(ac_data[freq_key]) if freq_key else None

            if ac_out and freq_arr is not None and ac_out in ac_data:
                vout = np.abs(np.atleast_1d(ac_data[ac_out]))
                vin = np.abs(np.atleast_1d(ac_data[ac_in])) if ac_in and ac_in in ac_data else None

                L = min(len(freq_arr), len(vout), len(vin) if vin is not None else len(vout))
                if L > 0:
                    freq = np.array(np.real(freq_arr[:L]), dtype=float)
                    vout = vout[:L]
                    vin = vin[:L] if vin is not None else None

                    with np.errstate(divide='ignore', invalid='ignore'):
                        if vin is not None and np.any(vin != 0):
                            gain = vout / (vin + 1e-30)
                        else:
                            gain = vout
                        gain_db = 20 * np.log10(np.maximum(np.abs(gain), 1e-30))

                    valid = np.where(np.isfinite(gain_db))[0]
                    metrics['gain_db_at_dc'] = float(gain_db[valid[0]]) if valid.size else float('nan')
                    try:
                        unity_candidates = np.where(gain_db <= 0)[0]
                        if unity_candidates.size:
                            ugf_idx = int(unity_candidates[0])
                            metrics['ugbw_hz'] = float(freq[ugf_idx])
                            phase_deg = np.degrees(np.angle(gain))
                            if ugf_idx < len(phase_deg):
                                metrics['phase_margin_deg'] = float(max(0.0, min(180.0, 180.0 + phase_deg[ugf_idx])))
                    except Exception:
                        pass

                    try:
                        peak_idx = int(np.nanargmax(gain_db))
                        peak_db = float(gain_db[peak_idx])
                        metrics['gain_db_peak'] = peak_db

                        kind = 'lowpass'
                        if 'band' in stem.lower():
                            kind = 'bandpass'
                        elif 'high' in stem.lower():
                            kind = 'highpass'

                        if kind == 'bandpass':
                            target_db = peak_db - 3.0
                        else:
                            target_db = metrics.get('gain_db_at_dc', peak_db) - 3.0

                        left_idx = None
                        for i in range(peak_idx, -1, -1):
                            if gain_db[i] <= target_db:
                                left_idx = i
                                break
                        right_idx = None
                        for i in range(peak_idx, len(gain_db)):
                            if gain_db[i] <= target_db:
                                right_idx = i
                                break

                        if left_idx is not None and right_idx is not None:
                            metrics['center_frequency'] = float(freq[peak_idx])
                            metrics['bandwidth'] = float(freq[right_idx] - freq[left_idx])
                            metrics['cutoff_frequency'] = float(freq[right_idx])
                        elif right_idx is not None:
                            metrics['cutoff_frequency'] = float(freq[right_idx])
                        else:
                            metrics['cutoff_frequency'] = float('nan')
                    except Exception:
                        pass

                    try:
                        finite_gain = gain_db[np.isfinite(gain_db)]
                        if finite_gain.size:
                            gain_span = float(np.nanmax(finite_gain) - np.nanmin(finite_gain))
                            conf = max(0.2, min(1.0, 0.4 + min(gain_span, 40.0) / 50.0))
                        else:
                            conf = 0.0
                        metrics['ac_confidence'] = float(conf)
                    except Exception:
                        metrics['ac_confidence'] = 0.0

        if tran_data is not None:
            time_key = next((key for key in tran_data.keys() if 'time' in key.lower()), None)
            t = tran_data[time_key] if time_key else None

            if circ_type in ('oscillator', 'vco') and tran_out and tran_out in tran_data and t is not None:
                try:
                    v = np.real(tran_data[tran_out])
                    dt = float(np.mean(np.diff(t)))
                    N = len(v)
                    yf = np.fft.rfft((v - np.mean(v)) * np.hanning(N))
                    xf = np.fft.rfftfreq(N, dt)
                    mags = np.abs(yf)
                    mags[0] = 0
                    idx = int(np.argmax(mags))
                    metrics['frequency_hz'] = float(xf[idx]) if xf.size > idx else float('nan')
                    metrics['amplitude_pp'] = float(np.max(v) - np.min(v))
                    harmonics = []
                    for order in range(1, 6):
                        target_freq = order * metrics['frequency_hz']
                        harmonic_idx = int(np.argmin(np.abs(xf - target_freq)))
                        harmonics.append(float(mags[harmonic_idx]) if harmonic_idx < len(mags) else 0.0)
                    if harmonics and harmonics[0] > 0:
                        metrics['thd_percent'] = float(100.0 * np.sqrt(sum(h ** 2 for h in harmonics[1:])) / harmonics[0])
                except Exception:
                    metrics['frequency_hz'] = float('nan')
                    metrics['amplitude_pp'] = float('nan')

            if circ_type == 'comparator' and tran_out and t is not None and tran_in and tran_in in tran_data and tran_out in tran_data:
                try:
                    vin = np.real(tran_data[tran_in])
                    vout = np.real(tran_data[tran_out])
                    vin_mid = 0.5 * (np.nanmin(vin) + np.nanmax(vin))
                    vout_mid = 0.5 * (np.nanmin(vout) + np.nanmax(vout))
                    in_edges = np.where(np.diff((vin >= vin_mid).astype(int)) != 0)[0]
                    out_edges = np.where(np.diff((vout >= vout_mid).astype(int)) != 0)[0]
                    if in_edges.size and out_edges.size:
                        metrics['propagation_delay_s'] = float(t[out_edges[0]] - t[in_edges[0]])
                except Exception:
                    pass

            if tran_out and t is not None and circ_type not in ('oscillator', 'vco'):
                try:
                    v = np.real(tran_data[tran_out])
                    metrics['amplitude_pp'] = float(np.max(v) - np.min(v))
                except Exception:
                    metrics['amplitude_pp'] = float('nan')

                try:
                    dt = float(np.mean(np.diff(t)))
                    N = len(v)
                    yf = np.fft.rfft((v - np.mean(v)) * np.hanning(N))
                    xf = np.fft.rfftfreq(N, dt)
                    mags = np.abs(yf)
                    mags[0] = 0
                    idx = int(np.argmax(mags)) if mags.size else 0
                    freq = float(xf[idx]) if xf.size > idx else float('nan')
                    metrics['frequency_hz'] = freq if np.isfinite(freq) and 0 < freq <= 1e11 else float('nan')
                    if idx > 0 and idx < len(mags) and mags[idx] > 0:
                        harmonics = []
                        for order in range(1, 6):
                            target_freq = order * freq
                            harmonic_idx = int(np.argmin(np.abs(xf - target_freq)))
                            harmonics.append(float(mags[harmonic_idx]) if harmonic_idx < len(mags) else 0.0)
                        metrics['thd_percent'] = float(100.0 * np.sqrt(sum(h ** 2 for h in harmonics[1:])) / harmonics[0])
                except Exception:
                    metrics['frequency_hz'] = float('nan')

                try:
                    v_min = np.nanmin(v)
                    v_max = np.nanmax(v)
                    v10 = v_min + 0.1 * (v_max - v_min)
                    v90 = v_min + 0.9 * (v_max - v_min)
                    above10 = np.where(v >= v10)[0]
                    above90 = np.where(v >= v90)[0]
                    if above10.size and above90.size:
                        after = above90[above90 >= above10[0]]
                        metrics['rise_time_s'] = float(t[after[0]] - t[above10[0]]) if after.size else float('nan')
                    else:
                        metrics['rise_time_s'] = float('nan')
                except Exception:
                    metrics['rise_time_s'] = float('nan')

        if circ_type == 'current_source':
            current_data = op_data or ac_data or tran_data or flat_data
            cur_keys = [key for key in current_data.keys() if key.lower().startswith('i') or 'i(' in key.lower()]
            if cur_keys:
                try:
                    vals = np.array([np.nanmean(np.abs(current_data[key])) if current_data[key].size else np.nan for key in cur_keys], dtype=float)
                    metrics['mean_current_a'] = float(np.nanmean(vals))
                    metrics['std_current_a'] = float(np.nanstd(vals))
                except Exception:
                    pass

    except Exception as e:
        parse_err = str(e)

    warnings = []
    score = 1.0

    selected_out = tran_out if tran_data is not None else (ac_out if ac_data is not None else op_out)
    selected_in = tran_in if tran_data is not None else (ac_in if ac_data is not None else op_in)
    selected_out_reason = tran_out_reason if tran_data is not None else (ac_out_reason if ac_data is not None else op_out_reason)
    selected_in_reason = tran_in_reason if tran_data is not None else (ac_in_reason if ac_data is not None else op_in_reason)
    metrics['preferred_out_node'] = selected_out or ''
    metrics['preferred_in_node'] = selected_in or ''
    metrics['node_selection_reason_out'] = selected_out_reason
    metrics['node_selection_reason_in'] = selected_in_reason

    try:
        expects_frequency = circ_type in ('oscillator', 'vco', 'comparator', 'rectifier', 'detector', 'sah', 'charge_pump')
        f = metrics.get('frequency_hz')
        if expects_frequency:
            if f is None or (isinstance(f, float) and (math.isnan(f) or f <= 0)):
                warnings.append('freq_invalid')
                score -= 0.5
            elif f > 1e9:
                warnings.append('freq_too_high')
                score -= 0.3
    except Exception:
        pass

    try:
        amp = metrics.get('amplitude_pp')
        if amp is not None and not (isinstance(amp, str) and amp == ''):
            if isinstance(amp, (int, float)) and not math.isnan(amp) and abs(amp) > 1e3:
                warnings.append('amplitude_unrealistic')
                score -= 0.3
    except Exception:
        pass

    try:
        cur = metrics.get('mean_current_a')
        if cur is not None and not (isinstance(cur, str) and cur == ''):
            if isinstance(cur, (int, float)) and not math.isnan(cur) and abs(cur) > 1.0:
                warnings.append('current_unrealistic')
                score -= 0.3
    except Exception:
        pass

    try:
        ac_conf = metrics.get('ac_confidence')
        if ac_conf is not None and isinstance(ac_conf, (int, float)) and ac_conf < 0.2:
            warnings.append('ac_low_confidence')
            score -= 0.2
    except Exception:
        pass

    try:
        g = metrics.get('gain_db_peak')
        if g is not None and isinstance(g, (int, float)) and not math.isnan(g) and abs(g) > 200:
            warnings.append('gain_unrealistic')
            score -= 0.2
    except Exception:
        pass

    score = max(0.0, min(1.0, score))
    metrics['plausibility_score'] = float(score)
    metrics['plausibility_warnings'] = ';'.join(warnings)

    return metrics, parse_err, circ_type


def main():
    rows = []
    for netlist in sorted(NETLIST_DIR.glob('*.cir')):
        stem = netlist.stem
        netlist_text = netlist.read_text(errors='ignore')
        prepared_netlist, prep_meta = prepare_netlist_for_campaign(netlist)
        raw_file = OUT_RAW_DIR / f"{stem}.raw"
        log_file = NGSPICE_LOG_DIR / f"{stem}.log"
        print(f"Running: {netlist.name}")
        res = run_ngspice_with_raw(prepared_netlist, raw_file, log_file)
        logs = (res.stdout or '') + '\n' + (res.stderr or '')
        success = res.returncode == 0 and 'error' not in logs.lower()
        data, err = parse_raw(raw_file)
        metrics = {}
        parse_err = ''
        circ_type = ''
        if data is not None:
            try:
                try:
                    metrics, parse_err, circ_type = extract_metrics_by_type(data, stem, netlist_text)
                except Exception:
                    parse_err = traceback.format_exc()
            except Exception as e:
                parse_err = str(e)
        else:
            parse_err = err or 'no data'

        rows.append({
            'circuit': stem,
            'circuit_type': circ_type,
            'success': success,
            'ngspice_returncode': res.returncode,
            'raw_exists': raw_file.exists(),
            'log_path': str(log_file),
            'prepared_netlist': prep_meta['prepared_netlist'],
            'preparation_notes': prep_meta['preparation_notes'],
            'injected_analyses': prep_meta['injected_analyses'],
            'parse_error': parse_err,
            'signal': metrics.get('signal', ''),
            'amplitude_pp': metrics.get('amplitude_pp', ''),
            'frequency_hz': metrics.get('frequency_hz', ''),
            'rise_time_s': metrics.get('rise_time_s', ''),
            'dc_gain_db': metrics.get('gain_db_at_dc', metrics.get('dc_gain_db', '')),
            'gain_db_peak': metrics.get('gain_db_peak', ''),
            'gain_db_at_dc': metrics.get('gain_db_at_dc', ''),
            'center_frequency': metrics.get('center_frequency', ''),
            'bandwidth': metrics.get('bandwidth', ''),
            'cutoff_frequency': metrics.get('cutoff_frequency', ''),
            'ac_confidence': metrics.get('ac_confidence', ''),
            'mean_current_a': metrics.get('mean_current_a', ''),
            'std_current_a': metrics.get('std_current_a', ''),
            'vout_dc': metrics.get('vout_dc', ''),
            'propagation_delay_s': metrics.get('propagation_delay_s', ''),
            'peak_mag': metrics.get('peak_mag', ''),
            'preferred_out_node': metrics.get('preferred_out_node', ''),
            'preferred_in_node': metrics.get('preferred_in_node', ''),
            'node_selection_reason_out': metrics.get('node_selection_reason_out', ''),
            'node_selection_reason_in': metrics.get('node_selection_reason_in', ''),
            'plausibility_score': metrics.get('plausibility_score', ''),
            'plausibility_warnings': metrics.get('plausibility_warnings', ''),
        })

    # write CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'circuit','circuit_type','success','ngspice_returncode','raw_exists','log_path','prepared_netlist',
            'preparation_notes','injected_analyses','parse_error','signal','amplitude_pp','frequency_hz','rise_time_s',
            'dc_gain_db','gain_db_peak','gain_db_at_dc','center_frequency','bandwidth','cutoff_frequency','ac_confidence',
            'mean_current_a','std_current_a','vout_dc','propagation_delay_s','peak_mag',
            'preferred_out_node','preferred_in_node','node_selection_reason_out','node_selection_reason_in',
            'plausibility_score','plausibility_warnings'
        ])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Metrics aggregated: {OUT_CSV}")


if __name__ == '__main__':
    main()
