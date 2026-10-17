"""Robust data study using a declared source CSV."""
import csv
import random
import statistics

def resample(inputs, *, seed):
    with open(inputs['path'],newline='',encoding='utf8') as f:
        rows=list(csv.DictReader(f))
    vals=[float(r['observation']) for r in rows]
    rng=random.Random(seed)
    resampled=[rng.choice(vals) for _ in range(len(vals))]
    if inputs['method']=='median':
        value=statistics.median(resampled)
    else:
        value=statistics.fmean(resampled)
    return {'estimate':float(value),'n':len(resampled)}
