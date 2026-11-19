"""Bounded server telemetry, separate from authentication and customer data."""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import time

WEEK = 7 * 86400
RETENTION = 8 * 86400
METRICS = {
    'cpu': ('cpu', 'NULL', 'NULL'),
    'memory': ('100.0*memory_used/memory_total', 'memory_used', 'memory_total'),
    'disk': ('100.0*disk_used/disk_total', 'disk_used', 'disk_total'),
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def pair(used, total):
    if not finite(used) or not finite(total) or not 0 <= used <= total < 9e18 or total <= 0:
        return None, None
    return int(used), int(total)


def connect_writer(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=3)
    db.execute('''CREATE TABLE IF NOT EXISTS resource_samples (
      ts INTEGER PRIMARY KEY, cpu REAL, memory_used INTEGER, memory_total INTEGER,
      disk_used INTEGER, disk_total INTEGER, source TEXT NOT NULL)''')
    return db


def sample_values(server, timestamp, source='exporter'):
    if not finite(timestamp) or timestamp < 0:
        raise ValueError('Invalid sample timestamp')
    cpu = server.get('cpu_percent')
    cpu = float(cpu) if finite(cpu) and 0 <= cpu <= 100 else None
    memory = pair(server.get('memory_used'), server.get('memory_total'))
    disk = pair(server.get('disk_used'), server.get('disk_total'))
    return (int(timestamp), cpu, *memory, *disk, source)


def record_sample(path, server, timestamp, now=None):
    now = time.time() if now is None else now
    values = sample_values(server, timestamp)
    if not now - RETENTION <= values[0] <= now + 60:
        return False
    db = connect_writer(path)
    try:
        with db:
            db.execute('''INSERT INTO resource_samples VALUES (?,?,?,?,?,?,?)
              ON CONFLICT(ts) DO UPDATE SET cpu=excluded.cpu,
                memory_used=excluded.memory_used,memory_total=excluded.memory_total,
                disk_used=excluded.disk_used,disk_total=excluded.disk_total,source=excluded.source''', values)
            db.execute('DELETE FROM resource_samples WHERE ts<?', (int(now - RETENTION),))
    finally:
        db.close()
    return True


def import_sysstat(path, directory, memory_total, now=None):
    """Import measured CPU/available RAM only. No filesystem usage is inferred."""
    now = time.time() if now is None else now
    samples = {}
    for file in sorted(Path(directory).glob('sa[0-9][0-9]')):
        if file.stat().st_mtime < now - RETENTION:
            continue
        result = subprocess.run(['sadf', '-j', str(file), '--', '-u', '-r'],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            continue
        hosts = json.loads(result.stdout).get('sysstat', {}).get('hosts', [])
        for host in hosts:
            for item in host.get('statistics', []):
                stamp = item['timestamp']
                if stamp.get('tz') != 'UTC':
                    continue
                dt = datetime.datetime.fromisoformat(stamp['date'] + 'T' + stamp['time']).replace(tzinfo=datetime.timezone.utc)
                ts = int(dt.timestamp())
                if not now - WEEK <= ts <= now:
                    continue
                cpu = next((row for row in item.get('cpu-load', []) if row.get('cpu') == 'all'), None)
                server = {}
                if cpu:
                    server['cpu_percent'] = 100 - cpu['idle'] - cpu.get('iowait', 0) - cpu.get('steal', 0)
                memory = item.get('memory', {})
                pct = memory.get('memused-percent', 0)
                # Validate capacity against the historical used/percent pair.
                # Skip RAM if capacity changed or MemAvailable was not recorded.
                if pct > 0 and finite(memory.get('avail')) and memory_total > 0:
                    inferred = memory['memused'] * 1024 * 100 / pct
                    if abs(inferred - memory_total) / memory_total <= 0.005:
                        server.update(memory_total=memory_total,
                                      memory_used=memory_total - memory['avail'] * 1024)
                samples[ts] = sample_values(server, ts, 'sysstat')
    db = connect_writer(path)
    try:
        with db:
            db.executemany('INSERT OR IGNORE INTO resource_samples VALUES (?,?,?,?,?,?,?)', samples.values())
            db.execute('DELETE FROM resource_samples WHERE ts<?', (int(now - RETENTION),))
    finally:
        db.close()
    return len(samples)


def read_history(path, metric, now=None):
    if metric not in METRICS:
        raise ValueError('Unknown resource metric')
    now = int(time.time() if now is None else now)
    start = now - WEEK
    response = dict(metric=metric, start=start, end=now, bucket_seconds=3600,
                    points=[], summary=None, latest=None, available_from=None)
    path = Path(path)
    if not path.is_file():
        return response
    expr, used, total = METRICS[metric]
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        where = f'ts>=? AND ts<=? AND ({expr}) IS NOT NULL'
        args = (start, now)
        rows = db.execute(f'''SELECT (ts/3600)*3600 AS bucket,avg({expr}) AS value,
          min({expr}) AS low,max({expr}) AS high,count(*) AS samples,
          avg({used}) AS used,avg({total}) AS total
          FROM resource_samples WHERE {where} GROUP BY bucket ORDER BY bucket''', args)
        response['points'] = [dict(ts=max(start, row['bucket']), until=min(now, row['bucket'] + 3600),
                                   value=row['value'], low=row['low'], high=row['high'],
                                   samples=row['samples'], used=row['used'], total=row['total']) for row in rows]
        summary = db.execute(f'''SELECT min(ts) AS first,max(ts) AS last,count(*) AS samples,
          avg({expr}) AS average,min({expr}) AS low,max({expr}) AS high
          FROM resource_samples WHERE {where}''', args).fetchone()
        if summary['samples']:
            response['summary'] = dict(summary)
            response['available_from'] = summary['first']
            latest = db.execute(f'''SELECT ts,({expr}) AS value,{used} AS used,{total} AS total
              FROM resource_samples WHERE {where} ORDER BY ts DESC LIMIT 1''', args).fetchone()
            response['latest'] = dict(latest)
    finally:
        db.close()
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--import-sysstat', action='store_true')
    args = parser.parse_args()
    value = json.loads(Path(args.snapshot).read_text())
    imported = import_sysstat(args.database, '/var/log/sysstat', value['server']['memory_total']) if args.import_sysstat else 0
    record_sample(args.database, value['server'], value['generated'])
    print(json.dumps({'historical_samples_imported': imported,
                      'metrics': {key: read_history(args.database, key)['summary'] for key in METRICS}}))


if __name__ == '__main__':
    main()
