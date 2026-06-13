"""Génère `results/node_override.csv` à partir de `results/node_corrections.csv`.
Filtre les suggestions manifestement invalides (contenants ':' ou 'Variables').
"""
import csv
from pathlib import Path

IN = Path('results/node_corrections.csv')
OUT = Path('results/node_override.csv')

if not IN.exists():
    print('No node_corrections.csv found.')
    raise SystemExit(1)

rows = []
with IN.open('r', encoding='utf-8') as f:
    r = csv.DictReader(f)
    for row in r:
        s = row.get('suggested_node','').strip()
        if not s:
            continue
        if ':' in s or 'variables' in s.lower():
            continue
        rows.append({'circuit': row.get('circuit',''), 'preferred_out_node': s})

if not rows:
    print('No valid overrides found.')
    raise SystemExit(0)

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['circuit','preferred_out_node'])
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f'Wrote {len(rows)} overrides to {OUT}')
