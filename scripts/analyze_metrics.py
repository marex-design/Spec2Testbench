"""Analyse `results/metrics.csv` — calcule statistiques et produit figures.

Usage:
    python scripts/analyze_metrics.py

Sorties:
    - results/metrics_stats.csv
    - results/figures/*.png
"""
from pathlib import Path
import csv
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statistics

ROOT = Path(__file__).resolve().parents[1]
METRICS_CSV = ROOT / 'results' / 'metrics.csv'
OUT_DIR = ROOT / 'results'
FIG_DIR = OUT_DIR / 'figures'
FIG_DIR.mkdir(parents=True, exist_ok=True)

METRICS = ['amplitude_pp', 'frequency_hz', 'rise_time_s', 'gain_db_at_dc', 'cutoff_frequency', 'plausibility_score']


def read_csv(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} missing")
    rows = []
    with path.open(encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def to_float(x):
    try:
        if x is None or x == '':
            return math.nan
        return float(x)
    except Exception:
        return math.nan


def compute_stats(values: list):
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return None
    arr = np.array(vals)
    return {
        'count': int(len(vals)),
        'mean': float(np.mean(arr)),
        'std': float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        'min': float(np.min(arr)),
        '25%': float(np.percentile(arr, 25)),
        '50%': float(np.median(arr)),
        '75%': float(np.percentile(arr, 75)),
        'max': float(np.max(arr)),
    }


def save_stats_csv(stats_dict, out_path: Path):
    keys = ['metric','count','mean','std','min','25%','50%','75%','max']
    with out_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(keys)
        for metric, s in stats_dict.items():
            if s is None:
                writer.writerow([metric,'0','','','','','','',''])
            else:
                writer.writerow([metric, s['count'], s['mean'], s['std'], s['min'], s['25%'], s['50%'], s['75%'], s['max']])


def plot_hist_box(values, metric, figdir: Path):
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return
    arr = np.array(vals)

    # Histogram
    plt.figure(figsize=(6,4))
    try:
        if metric == 'frequency_hz':
            plt.xscale('log')
        plt.hist(arr, bins=30, color='#2b8cbe', edgecolor='black')
        plt.title(f'Histogram: {metric}')
        plt.xlabel(metric)
        plt.ylabel('count')
        plt.tight_layout()
        plt.savefig(figdir / f'hist_{metric}.png', dpi=200)
        plt.close()
    except Exception as e:
        print('hist plot error', metric, e)

    # Boxplot
    plt.figure(figsize=(4,3))
    try:
        plt.boxplot(arr, vert=False)
        plt.title(f'Boxplot: {metric}')
        plt.xlabel(metric)
        plt.tight_layout()
        plt.savefig(figdir / f'box_{metric}.png', dpi=200)
        plt.close()
    except Exception as e:
        print('box plot error', metric, e)


def main():
    rows = read_csv(METRICS_CSV)
    stats = {}
    for metric in METRICS:
        vals = [to_float(r.get(metric, '')) for r in rows]
        s = compute_stats(vals)
        stats[metric] = s
        plot_hist_box(vals, metric, FIG_DIR)

    out_stats = OUT_DIR / 'metrics_stats.csv'
    save_stats_csv(stats, out_stats)
    print('Saved stats:', out_stats)
    print('Saved figures in:', FIG_DIR)


if __name__ == '__main__':
    main()
