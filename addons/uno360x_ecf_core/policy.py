"""Transmission remains unavailable until a separately validated adapter exists."""
def transmit(*args, **kwargs):
    raise RuntimeError('Emisión fiscal no habilitada. Este paquete solo prepara y comprueba localmente.')
