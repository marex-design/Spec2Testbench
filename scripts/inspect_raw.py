from pathlib import Path
p=Path('results/raw/lowpass_filter.raw')
print('exists',p.exists())
if p.exists():
    b=p.read_bytes()[:200]
    print('len',len(b))
    print(b)
