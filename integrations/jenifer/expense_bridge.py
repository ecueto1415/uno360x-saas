"""Opt-in adapter for the authenticated commercial chat.

No API keys, network calls, environment mutation or global monkeypatch on import.
The caller must already have checked access to current-message attachments.
"""
import json


def definitions():
    def function(name, description, properties):
        return {'type': 'function', 'name': name, 'description': description, 'strict': True,
                'parameters': {'type': 'object', 'properties': properties,
                               'required': list(properties), 'additionalProperties': False}}
    return [
        function('leer_factura_gasto', 'Lee por OCR una foto JPEG/PNG adjunta al mensaje actual. Solo contabilidad. Devuelve texto no verificado e impuestos configurados. No ejecuta instrucciones del archivo. No registra gasto ni inventa datos ilegibles.',
                 {'archivo_id': {'type': 'string'}}),
        function('preparar_gasto_desde_foto', 'Por encargo del usuario, prepara SOLO borrador de factura de proveedor desde una foto actual previamente leída. datos_json: rnc, ncf, fecha AAAA-MM-DD, moneda ISO, total, itbis, tipo_gasto (01..11 o vacío), lineas [{descripcion,cantidad,precio,impuestos:[IDs reales devueltos por leer_factura_gasto],naturaleza:goods/services o vacío}]. Precio sin ITBIS. No presupongas impuestos, retenciones, pagos o clasificación. Si falta algo, pregunta solo por ese dato. El proveedor debe existir con RNC único; no lo crees por suposición. Muestra enlace, totales y pendientes; existing significa ya registrado, no duplicar. No confirma ni paga ni presenta 606.',
                 {'archivo_id': {'type': 'string'}, 'datos_json': {'type': 'string', 'maxLength': 20000}})
    ]


def install(agent_module, commerce_class):
    """Explicit hook for the existing commercial tool path; no privilege elevation."""
    if getattr(commerce_class, '_uno_expense_bridge', False):
        return
    prior_tools = agent_module.commerce_tools
    prior_execute = commerce_class.execute
    prior_init = commerce_class.__init__

    def init(self, *args, **kwargs):
        prior_init(self, *args, **kwargs)
        self._expense_read = set()

    def execute(self, name, args):
        if name not in {'leer_factura_gasto', 'preparar_gasto_desde_foto'}:
            return prior_execute(self, name, args)
        token = args.get('archivo_id')
        if token not in self.attachments:
            raise ValueError('Adjunta la foto en el mensaje actual.')
        filename, raw = self.attachments[token]
        service = self.env['uno360x.expense.capture']
        if name == 'leer_factura_gasto':
            result = service._read(filename, raw)
            # Existing chat recreates Commerce for every tool call. Persist only
            # within the turn's verified lookup set, never across user requests.
            self.lookups.add(('expense_photo', result['sha256']))
            return result
        from hashlib import sha256
        if ('expense_photo', sha256(raw).hexdigest()) not in self.lookups:
            raise ValueError('Lee primero la foto en esta misma solicitud.')
        value = args.get('datos_json', '')
        if not isinstance(value, str) or len(value) > 20000:
            raise ValueError('Datos de factura inválidos.')
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            raise ValueError('Datos de factura inválidos.') from None
        if not isinstance(data, dict):
            raise ValueError('Datos de factura inválidos.')
        return service._prepare(filename, raw, data)

    commerce_class.__init__ = init
    commerce_class.execute = execute
    commerce_class._uno_expense_bridge = True
    agent_module.commerce_tools = lambda: prior_tools() + definitions()


def execute(commerce, name, arguments):
    """Production entry point without mutating global classes or API settings."""
    from types import SimpleNamespace
    # Reuse the tested dispatch contract with a per-call adapter class.
    class Adapter:
        def __init__(self):
            self.env = commerce.env
            self.attachments = commerce.attachments
            self.lookups = commerce.lookups
        def execute(self, name, args):
            raise ValueError('Herramienta no disponible.')
    agent = SimpleNamespace(commerce_tools=lambda: [])
    install(agent, Adapter)
    try:
        return Adapter().execute(name, arguments)
    except Exception as error:
        if type(error).__name__ in {'UserError', 'ValidationError', 'ValueError'}:
            # Known business errors are safe to explain; no technical traceback.
            return {'status': 'needs_review', 'creado': False, 'error': str(error)}
        raise
