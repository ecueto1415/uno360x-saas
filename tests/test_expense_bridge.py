import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

path = Path(__file__).resolve().parents[1] / 'integrations/jenifer/expense_bridge.py'
spec = importlib.util.spec_from_file_location('expense_bridge', path)
bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def setup_bridge(self):
        from hashlib import sha256
        class Service:
            def _read(self, name, raw):
                return {'sha256': sha256(raw).hexdigest(), 'texto_ocr': 'FICTICIO'}
            def _prepare(self, name, raw, data):
                return {'status': 'draft', 'data': data}
        class Commerce:
            def __init__(self):
                self.env = {'uno360x.expense.capture': Service()}
                self.attachments = {'archivo_1': ('foto.png', b'fictional')}
                self.lookups = set()
            def execute(self, name, args):
                return 'prior-tool'
        agent = SimpleNamespace(commerce_tools=lambda: [{'name': 'old'}])
        bridge.install(agent, Commerce)
        bridge.install(agent, Commerce)
        return agent, Commerce

    def test_definitions_once_and_prior_tools_preserved(self):
        agent, Commerce = self.setup_bridge()
        self.assertEqual(len(agent.commerce_tools()), 3)
        self.assertEqual(Commerce().execute('old', {}), 'prior-tool')

    def test_read_required_and_shared_lookup_survives_new_service(self):
        _, Commerce = self.setup_bridge()
        first = Commerce()
        args = {'archivo_id': 'archivo_1', 'datos_json': '{"ncf":"B0100000001"}'}
        with self.assertRaises(ValueError):
            first.execute('preparar_gasto_desde_foto', args)
        first.execute('leer_factura_gasto', {'archivo_id': 'archivo_1'})
        second = Commerce()
        second.lookups = first.lookups
        self.assertEqual(second.execute('preparar_gasto_desde_foto', args)['status'], 'draft')
        third = Commerce()
        with self.assertRaises(ValueError):
            third.execute('preparar_gasto_desde_foto', args)

    def test_missing_attachment_and_bad_json(self):
        _, Commerce = self.setup_bridge()
        service = Commerce()
        with self.assertRaises(ValueError):
            service.execute('leer_factura_gasto', {'archivo_id': 'archivo_99'})
        service.execute('leer_factura_gasto', {'archivo_id': 'archivo_1'})
        for value in ('[]', 'no json'):
            with self.assertRaises(ValueError):
                service.execute('preparar_gasto_desde_foto',
                    {'archivo_id': 'archivo_1', 'datos_json': value})


if __name__ == '__main__':
    unittest.main()
