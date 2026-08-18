"""Propose des corrections automatiques de sélection de nœuds pour entrées à faible plausibilité.

Lit `results/metrics.csv`, filtre par `plausibility_score` faible, parse les raw
associés et propose un nœud alternatif basé sur stddev ou KB. Écrit `results/node_corrections.csv`.
"""
import csv
import math
from pathlib import Path
import numpy as np
import traceback

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from scripts import aggregate_metrics as ag
from spec2testbench.domain.registry import circuit_kb

METRICS_CSV = Path('results/metrics.csv')
RAW_DIR = Path('results/raw')
OUT_CSV = Path('results/node_corrections.csv')

THRESHOLD = 0.5


def estimate_plausibility_from_signal(data, node, time_key=None):
    score = 1.0
    warnings = []
    try:
        v = np.atleast_1d(data[node]).astype(float)
    except Exception:
        return 0.0, 'no_data'
    # amplitude
    try:
        amp = float(np.nanmax(v) - np.nanmin(v))
        if math.isnan(amp) or amp <= 0:
            warnings.append('amp_invalid'); score -= 0.5
        elif amp > 1e3:
            warnings.append('amplitude_unrealistic'); score -= 0.3
    except Exception:
        warnings.append('amp_error'); score -= 0.5
    # frequency
    f = float('nan')
    if time_key and time_key in data:
        try:
            t = np.atleast_1d(data[time_key]).astype(float)
            dt = float(np.mean(np.diff(t)))
            N = len(v)
            if N > 4 and dt > 0:
                yf = np.fft.rfft((v - np.mean(v)) * np.hanning(N))
                xf = np.fft.rfftfreq(N, dt)
                mags = np.abs(yf)
                mags[0] = 0
                idx = int(np.argmax(mags))
                f = float(xf[idx]) if xf.size > idx else float('nan')
                if math.isnan(f) or f <= 0:
                    warnings.append('freq_invalid'); score -= 0.5
                elif f > 1e9:
                    warnings.append('freq_too_high'); score -= 0.3
        except Exception:
            warnings.append('freq_error'); score -= 0.5

    score = max(0.0, min(1.0, score))
    return score, ';'.join(warnings)


def main():
    if not METRICS_CSV.exists():
        print('No metrics.csv found. Run aggregate_metrics.py first.')
        return

    rows = []
    with METRICS_CSV.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    suggestions = []
    for r in rows:
        try:
            score = float(r.get('plausibility_score') or 1.0)
        except Exception:
            score = 1.0
        if score >= THRESHOLD:
            continue
        stem = r['circuit']
        raw_path = RAW_DIR / f"{stem}.raw"
        if not raw_path.exists():
            continue
        data, err = ag.parse_raw(raw_path)
        if data is None:
            continue

        # find time key if present
        time_key = next((k for k in data.keys() if 'time' in k.lower()), None)

        preferred = r.get('preferred_out_node') or ''

        volt_keys = [k for k in data.keys() if k.lower().startswith('v') or 'v(' in k.lower()]
        # exclude bias nets
        blacklist = ['vdd', 'vss', 'gnd', '0']
        volt_keys = [k for k in volt_keys if not any(b in k.lower() for b in blacklist)]
        if not volt_keys:
            continue

        stds = {}
        for k in volt_keys:
            try:
                stds[k] = float(np.nanstd(np.atleast_1d(data[k]).astype(float)))
            except Exception:
                stds[k] = 0.0

        # candidate by stddev
        best_std = max(stds, key=stds.get)

        # candidate by KB
        kb = circuit_kb.classify_from_stem(stem)
        kb_candidate = None
        if kb and 'nodes' in kb:
            for name in kb['nodes'].get('out', []):
                for k in volt_keys:
                    if name.lower() in k.lower():
                        kb_candidate = k
                        break
                if kb_candidate:
                    break

        # pick suggestion: prefer kb_candidate if exists and differs, else best_std if differs
        suggestion = None
        reason = ''
        if kb_candidate and kb_candidate != preferred:
            suggestion = kb_candidate; reason = 'kb_match'
        elif best_std != preferred:
            suggestion = best_std; reason = 'stddev_higher'

        if not suggestion:
            continue

        new_score, warnings = estimate_plausibility_from_signal(data, suggestion, time_key=time_key)

        suggestions.append({
            'circuit': stem,
            'current_node': preferred,
            'suggested_node': suggestion,
            'reason': reason,
            'old_plausibility_score': score,
            'new_estimated_score': new_score,
            'warnings': warnings,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
        if suggestions:
            writer = csv.DictWriter(f, fieldnames=list(suggestions[0].keys()))
            writer.writeheader()
            for s in suggestions:
                writer.writerow(s)
    print(f'Suggestions written: {OUT_CSV} ({len(suggestions)} entries)')


if __name__ == '__main__':
    main()
