"""Offline 2D TEVIEW run visualizer. No physics is computed in this module.

The viewer renders numerical samples written by `tev simulate` and the saved
compiled model. It does not change a run's recorded evidence artifacts.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from teview_visual_template import VIEWER_TEMPLATE


class VisualError(ValueError):
    """Malformed, oversized, or unsupported run for visualization."""


def _json_escaped(value):
    """Return safely embeddable JSON for an HTML <script> context."""
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            .replace('&', '\\u0026').replace('<', '\\u003c')
            .replace('>', '\\u003e').replace('\u2028', '\\u2028')
            .replace('\u2029', '\\u2029'))


def render_scene(run_folder, output=None):
    """Render a standalone HTML playback file from a TEVIEW physics run.

    It reads model.json, measurements.csv, report.json and does not modify any
    of those files. Reports are simulations, not proof of scientific validity.
    """
    folder = Path(run_folder).resolve()
    if not folder.is_dir():
        raise VisualError(f'Missing simulation directory: {folder}')
    try:
        model_path, csv_path, report_path = (folder / p for p in
            ('model.json', 'measurements.csv', 'report.json'))
        if any(not p.is_file() for p in (model_path, csv_path, report_path)):
            raise VisualError('A simulated scene needs model.json, measurements.csv and report.json')
        if model_path.stat().st_size > 5_000_000 or report_path.stat().st_size > 5_000_000:
            raise VisualError('Model or report is too large to visualize')
        if csv_path.stat().st_size > 20_000_000:
            raise VisualError('Measurements file exceeds 20 MB viewer limit')
        model = json.loads(model_path.read_text(encoding='utf-8'))
        report = json.loads(report_path.read_text(encoding='utf-8'))
        with csv_path.open('r', newline='', encoding='utf-8') as handle:
            rows_csv = csv.DictReader(handle)
            keys = rows_csv.fieldnames
            if not keys or 'time' not in keys or len(keys) > 400:
                raise VisualError('Missing time column or too many numeric columns')
            if len(set(keys)) != len(keys):
                raise VisualError('Duplicate measurement columns')
            rows = []
            for item in rows_csv:
                if len(rows) >= 20001:
                    raise VisualError('Viewer supports at most 20,000 samples')
                if None in item or any(v is None or not v.strip() for v in item.values()):
                    raise VisualError('Malformed or incomplete measurement row')
                row = {key: float(value) for key, value in item.items()}
                if not all(math.isfinite(value) for value in row.values()):
                    raise VisualError('Measurements must contain finite numbers')
                if rows and row['time'] <= rows[-1]['time']:
                    raise VisualError('Sample times must increase strictly')
                rows.append(row)
        if not rows:
            raise VisualError('Simulation has no measurement samples')
        if not isinstance(model, dict) or not isinstance(model.get('components'), dict):
            raise VisualError('Invalid compiled scene model')
        if not isinstance(report, dict) or not isinstance(report.get('title'), str):
            raise VisualError('Invalid simulation report')
        payload = {'title': report['title'], 'model': model,
                   'columns': keys, 'rows': [[row[key] for key in keys] for row in rows],
                   'status': report.get('status', 'unknown')}
        page = VIEWER_TEMPLATE.replace('"__TEVIEW_DATA_PLACEHOLDER__"', _json_escaped(payload))
        dest = Path(output).resolve() if output else folder / 'viewer.html'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding='utf-8')
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VisualError(f'Cannot read simulation files: {exc}') from exc
    return {'viewer': str(dest), 'samples': len(rows), 'components': len(model['components']),
            'status': 'generated_from_saved_simulation'}
