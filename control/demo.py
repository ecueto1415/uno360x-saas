"""Run with python -m control.demo. Uses disposable, fictional data only."""
import json
import tempfile
from pathlib import Path

from control.registry import Registry
from control.provisioning import SimulatedProvisioner, build_plan


def main():
    with tempfile.TemporaryDirectory(prefix='uno360x-simulation-') as directory:
        root = Path(directory)
        registry = Registry(root / 'registry.sqlite3')
        provisioner = SimulatedProvisioner(root / 'simulation.sqlite3', registry)
        try:
            alfa = registry.reserve('empresa-alfa', ['jenifer_ai'], 'demo-alfa')
            beta = registry.reserve('empresa-beta', ['payroll_hr', 'projects_services'], 'demo-beta')
            failed = provisioner.run(alfa['hostname'], fail_at='configuration')
            resumed = provisioner.run(alfa['hostname'])
            other = provisioner.run(beta['hostname'])
            print(json.dumps({'mode': 'simulation', 'alfa_plan': build_plan(registry, alfa['hostname']),
                              'failure': failed, 'resumed': resumed, 'beta': other},
                             indent=2, ensure_ascii=False))
        finally:
            provisioner.close()
            registry.close()


if __name__ == '__main__':
    main()
