"""Numerical integration of a sample: ordinary Python code, not a TEVIEW plugin."""
import csv
import json
from pathlib import Path

with Path('measurements.csv').open(newline='', encoding='utf-8') as stream:
    samples = [(float(row['x']), float(row['y'])) for row in csv.DictReader(stream)]
assert len(samples) >= 2 and all(b[0] > a[0] for a,b in zip(samples,samples[1:]))
area = sum((b[0]-a[0]) * (b[1]+a[1])/2 for a,b in zip(samples,samples[1:]))
# This sample is x^2 on [0,1], which has known integral 1/3.
error = abs(area - 1/3)
Path('metrics.json').write_text(json.dumps({'integral':area, 'error':error, 'samples':len(samples)}),encoding='utf8')
print(f'Integral: {area:.7f}; absolute error: {error:.7f}')
