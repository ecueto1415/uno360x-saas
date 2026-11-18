"""Retire obsolete, pristine shared-PostgreSQL seeds; never customer databases.

Archive dumps are retained. Dry-run is the default. Apply requires matching
managed resources, a verified archive, strict factory-data checks and no users.
"""
import argparse
import collections
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from control.template_cache import CACHE, verified_cache
from deployment.pilot_adapter import PilotAdapter
from deployment.reserve_pool import BASE, Pool, ident, literal, profiles

SEED = re.compile(r'uno_tpl_[a-f0-9]{24}\Z')
STATE = BASE / 'seed-maintenance'


def referenced_fingerprints(pool):
    protected = set()
    for row in pool.store.db.execute("SELECT fingerprint FROM reserve_slots WHERE state!='retired'"):
        protected.add(row[0])
    control = Path('/var/lib/uno360x-saas/control/control.sqlite3')
    with sqlite3.connect('file:' + str(control) + '?mode=ro', uri=True) as db:
        for (snapshot,) in db.execute('SELECT snapshot FROM preparation_jobs'):
            value = json.loads(snapshot)
            if value.get('installation', {}).get('fingerprint'):
                protected.add(value['installation']['fingerprint'])
    return protected


def current_protection(pool, keep_previous):
    current = {p['fingerprint'] for _, p, _ in profiles()}
    protected = current | referenced_fingerprints(pool)
    manifests = {}
    history = collections.defaultdict(list)
    for file in (CACHE / 'ready').glob('*/manifest.json'):
        value = json.loads(file.read_text())
        profile = value.get('installation', {})
        fp = value.get('fingerprint', '')
        if not re.fullmatch('[a-f0-9]{64}', fp) or profile.get('fingerprint') != fp or value.get('pristine') is not True:
            continue
        name = 'uno_tpl_' + fp[:24]
        if name in manifests and manifests[name]['fingerprint'] != fp:
            raise RuntimeError('Ambiguous seed prefix')
        manifests[name] = value
        history[tuple(sorted(value.get('modules', [])))].append(value)
    # Preserve independently verified recent rollback versions of every plan.
    for versions in history.values():
        retained = set()
        for value in sorted(versions, key=lambda x: x['created'], reverse=True):
            fp = value['fingerprint']
            if fp in current or fp in retained:
                continue
            if len(retained) >= keep_previous:
                break
            if verified_cache(value['installation'], value['images']):
                retained.add(fp)
                protected.add(fp)
    return {'uno_tpl_' + fp[:24] for fp in protected}, manifests


def provisioning_busy():
    path = '/var/lib/uno360x-saas/control/control.sqlite3'
    with sqlite3.connect('file:' + path + '?mode=ro', uri=True, timeout=2) as db:
        return bool(db.execute("SELECT count(*) FROM preparation_jobs WHERE status IN ('queued','running')").fetchone()[0])


def seed_rows(pool):
    raw = pool.sql("""SELECT coalesce(json_agg(json_build_object(
        'name',d.datname,'oid',d.oid,'owner',r.rolname,'allow',d.datallowconn,
        'system_template',d.datistemplate,'size',pg_database_size(d.oid),
        'sessions',(SELECT count(*) FROM pg_stat_activity WHERE datid=d.oid),
        'other_role_dependencies',(SELECT count(*) FROM pg_shdepend
          WHERE refclassid='pg_authid'::regclass
          AND refobjid=(SELECT oid FROM pg_roles WHERE rolname='uno_seed_'||substring(d.datname from 9))
          AND dbid<>d.oid))), '[]'::json)
        FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba
        WHERE d.datname LIKE 'uno_tpl_%';""")
    return json.loads(raw)


def eligible(row, protected, manifests, min_age):
    name = row['name']
    if not SEED.fullmatch(name) or name in protected or name not in manifests:
        return False
    return (row['owner'] == 'postgres' and not row['allow']
            and not row['system_template'] and row['sessions'] == 0
            and row['other_role_dependencies'] == 0
            and manifests[name]['created'] < time.time() - min_age)


PRISTINE = """BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
DO $pristine$
DECLARE n bigint; t text;
BEGIN
 IF (SELECT value FROM ir_config_parameter WHERE key='database.uuid')
       IS DISTINCT FROM 'template-not-an-active-company' THEN
   RAISE EXCEPTION 'Not a sanitized factory seed';
 END IF;
 IF (SELECT count(*) FROM res_company)<>1 OR EXISTS(
     SELECT 1 FROM res_company c JOIN res_partner p ON p.id=c.partner_id
     WHERE c.name<>'UNO360X Plantilla' OR coalesce(p.vat,'')<>'') THEN
   RAISE EXCEPTION 'Company identity present';
 END IF;
 IF EXISTS(SELECT 1 FROM res_users WHERE coalesce(password,'')<>'' OR uno360x_account_id IS NOT NULL)
    OR EXISTS(SELECT 1 FROM ir_cron WHERE active) THEN
   RAISE EXCEPTION 'User credentials or active automation present';
 END IF;
 FOREACH t IN ARRAY ARRAY['uno360x_tenant_identity','ir_mail_server',
   'account_move','sale_order','purchase_order','pos_order','stock_picking',
   'stock_move','account_analytic_line','hr_contract','hr_leave','hr_expense',
   'hr_expense_sheet','uno360x_ecf_issue','uno360x_ecf_range'] LOOP
   IF to_regclass('public.'||t) IS NOT NULL THEN
     EXECUTE format('SELECT count(*) FROM %I',t) INTO n;
     IF n<>0 THEN RAISE EXCEPTION 'Factory has business rows in %',t; END IF;
   END IF;
 END LOOP;
 IF to_regclass('public.hr_employee') IS NOT NULL THEN
   EXECUTE 'SELECT count(*) FROM hr_employee WHERE active' INTO n;
   IF n<>0 THEN RAISE EXCEPTION 'Factory has active employees'; END IF;
 END IF;
END $pristine$;
COMMIT;
"""


def retire(pool, row, metadata):
    name = row['name']
    if not SEED.fullmatch(name):
        raise RuntimeError('Refusing nonseed database')
    if not verified_cache(metadata['installation'], metadata['images']):
        raise RuntimeError('Verified recovery archive is missing')
    role = 'uno_seed_' + name[8:]
    # No FORCE, session termination, DROP OWNED or customer identifiers.
    script = """SET lock_timeout='1s';
DO $guard$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_database d WHERE d.datname=%s
   AND d.oid=%d AND d.datdba=(SELECT oid FROM pg_roles WHERE rolname='postgres')
   AND NOT d.datallowconn AND NOT d.datistemplate)
   OR EXISTS(SELECT 1 FROM pg_stat_activity WHERE datid=%d) THEN
   RAISE EXCEPTION 'Seed state changed';
 END IF;
END $guard$;
ALTER DATABASE %s ALLOW_CONNECTIONS true;
\\connect %s
%s
\\connect postgres
ALTER DATABASE %s ALLOW_CONNECTIONS false;
DROP DATABASE %s;
DROP ROLE IF EXISTS %s;
SELECT 'SEED_RETIRED';
""" % (literal(name), int(row['oid']), int(row['oid']), ident(name), name,
       PRISTINE, ident(name), ident(name), ident(role))
    result = pool.sql(script, check=False)
    if result.returncode:
        # A failed pristine check must never leave a formerly closed seed open.
        exists = pool.sql('SELECT count(*) FROM pg_database WHERE datname=' + literal(name)) == '1'
        if exists:
            pool.sql('ALTER DATABASE ' + ident(name) + ' ALLOW_CONNECTIONS false;')
        raise RuntimeError('Seed retirement failed; database still exists=%s' % exists)
    if 'SEED_RETIRED' not in result.stdout:
        raise RuntimeError('Missing retirement receipt')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--keep-previous', type=int, default=2)
    parser.add_argument('--min-age-seconds', type=int, default=3600)
    parser.add_argument('--limit', type=int, default=600)
    args = parser.parse_args()
    if os.geteuid() == 0 or not 1 <= args.keep_previous <= 10 or not 1 <= args.limit <= 600 or args.min_age_seconds < 600:
        raise RuntimeError('Invalid maintenance policy or execution account')
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'maintenance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Seed maintenance already running')
            return
        with Pool(PilotAdapter()) as pool:
            pool.verify_server()
            with pool.builder_lock():
                protected, manifests = current_protection(pool, args.keep_previous)
                rows = seed_rows(pool)
                selected = sorted(
                    (r for r in rows if eligible(r, protected, manifests, args.min_age_seconds)),
                    key=lambda r: manifests[r['name']]['created'],
                )[:args.limit]
            report = {'created': time.time(), 'apply': args.apply,
                      'protected': sorted(protected), 'candidates': selected,
                      'candidate_bytes': sum(r['size'] for r in selected),
                      'deleted': [], 'deferred': [], 'errors': []}
            path = STATE / ('run-%d-%s.json' % (time.time_ns(), 'apply' if args.apply else 'plan'))
            def save():
                temp = path.with_suffix('.tmp')
                temp.write_text(json.dumps(report, indent=2))
                temp.replace(path)
            save()
            print(json.dumps({'plan': str(path), 'seeds': len(rows), 'candidates': len(selected),
                              'candidate_bytes': report['candidate_bytes'], 'protected_names': len(protected)}), flush=True)
            if not args.apply:
                return
            for index, row in enumerate(selected):
                if provisioning_busy():
                    report['deferred'].append({'name': row['name'], 'reason': 'Customer provisioning has priority'})
                    save()
                    break
                with pool.builder_lock():
                    # Re-evaluate protection after every short, exclusive operation.
                    if index % 25 == 0:
                        protected, _ = current_protection(pool, args.keep_previous)
                    protected.update('uno_tpl_' + fp[:24] for fp in referenced_fingerprints(pool))
                    if row['name'] in protected:
                        report['deferred'].append({'name': row['name'], 'reason': 'Now protected'})
                        save()
                        continue
                    try:
                        retire(pool, row, manifests[row['name']])
                    except Exception as error:
                        report['errors'].append({'name': row['name'], 'error': str(error)})
                        save()
                        raise
                report['deleted'].append({'name': row['name'], 'oid': row['oid'], 'size': row['size']})
                save()
                if len(report['deleted']) % 25 == 0:
                    print(json.dumps({'deleted': len(report['deleted'])}), flush=True)
                time.sleep(0.05)
            report['finished'] = time.time()
            report['reclaimed_database_bytes'] = sum(r['size'] for r in report['deleted'])
            save()
            print(json.dumps({'deleted': len(report['deleted']), 'deferred': len(report['deferred']),
                              'reclaimed_database_bytes': report['reclaimed_database_bytes'], 'report': str(path)}), flush=True)


if __name__ == '__main__':
    main()
