"""Produce reviewable candidates; never mutate the live paths directly."""
from pathlib import Path
import argparse


def patch(name, source):
    marker = '# UNO360X expense photo chat v1'
    if marker in source:
        return source
    if name == 'agente_jenifer.py':
        anchor = "def commerce_tools():\n    string={'type':'string'}\n    return ["
        replacement = """def commerce_tools():
    # UNO360X expense photo chat v1
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('jenifer_expense_tools',Path(__file__).with_name('expense_bridge.py'))
    expense=importlib.util.module_from_spec(spec);spec.loader.exec_module(expense)
    string={'type':'string'}
    return expense.definitions() + ["""
    elif name == 'comercio_jenifer.py':
        anchor = "    def execute(self, name, args):\n"
        replacement = """    def execute(self, name, args):
        # UNO360X expense photo chat v1
        if name in {'leer_factura_gasto', 'preparar_gasto_desde_foto'}:
            import importlib.util
            spec=importlib.util.spec_from_file_location('jenifer_expense_dispatch',Path(__file__).with_name('expense_bridge.py'))
            expense=importlib.util.module_from_spec(spec);spec.loader.exec_module(expense)
            return expense.execute(self, name, args)
"""
    elif name == 'worker.py':
        anchor = "        if name in {'consultar_nomina','preparar_nomina'"
        replacement = """        # UNO360X expense photo chat v1
        if name in {'leer_factura_gasto','preparar_gasto_desde_foto','consultar_nomina','preparar_nomina'"""
    else:
        raise ValueError(name)
    if source.count(anchor) != 1:
        raise ValueError('Source changed: inspect '+name)
    candidate = source.replace(anchor, replacement, 1)
    compile(candidate, name, 'exec')
    return candidate


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source'); parser.add_argument('output')
    args = parser.parse_args()
    target = Path(args.output); target.mkdir(parents=True, exist_ok=True)
    for name in ['agente_jenifer.py', 'comercio_jenifer.py', 'worker.py']:
        (target/name).write_text(patch(name, (Path(args.source)/name).read_text()))
    print('CANDIDATES_READY')
