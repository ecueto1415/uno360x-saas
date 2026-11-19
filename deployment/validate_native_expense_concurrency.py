"""Concurrent capture in isolated native clone; removes only its own QA fixtures."""
from pathlib import Path
exec(Path(__file__).with_name('validate_native_expense_chat.py').read_text().split(
    'first=service._prepare')[0], globals())
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from odoo.modules.registry import Registry

env.cr.commit()
barrier = Barrier(2)


def create_parallel(index):
    with Registry(env.cr.dbname).cursor() as cr:
        actor = api.Environment(cr, 2, dict(admin.context))
        barrier.wait()
        try:
            result = actor['uno360x.expense.capture']._prepare(
                'simultanea.png', photo(str(index)), data)
            cr.commit()
            return {'status': result['status'], 'id': result['id']}
        except Exception as error:
            cr.rollback()
            return {'error': type(error).__name__, 'code': getattr(error, 'pgcode', None)}


with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(create_parallel, [1, 2]))
env.invalidate_all()
moves = admin['account.move'].search([
    ('company_id', '=', company.id), ('ref', '=', data['ncf'])])
assert len(moves) == 1, results
assert moves.state == 'draft'
assert sum(r.get('status') == 'draft' for r in results) == 1
print('NATIVE_CONCURRENT_TWO_REQUESTS', json.dumps(results), 'DRAFT_COUNT', len(moves))
moves.unlink()
partner.unlink()
env.cr.commit()
print('QA_CONCURRENCY_FIXTURES_REMOVED')
