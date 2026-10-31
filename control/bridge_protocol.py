"""Load the single shared, pure-Python protocol implementation (no Odoo import)."""
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'addons/uno360x_auth_bridge/protocol.py'
spec=importlib.util.spec_from_file_location('uno360x_bridge_protocol',path)
protocol=importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
mint=protocol.mint
verify=protocol.verify
