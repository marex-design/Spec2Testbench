from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[3]
rows = list(csv.DictReader((ROOT / 'results' / 'metric_category_performance.csv').open()))
print('metric_category,extraction_success_rate,detection_recall')
for row in rows:
    print(f"{row['metric_category']},{row['extraction_success_rate']},{row['detection_recall']}")
