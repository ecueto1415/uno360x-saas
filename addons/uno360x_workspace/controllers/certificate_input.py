"""Read a certificate password from a text file in memory."""
import re


def certificate_password(contents):
    if not contents or len(contents) > 8192:
        raise ValueError('El archivo de credenciales debe pesar hasta 8 KB.')
    if contents.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = contents.decode('utf-16')
    else:
        text = contents.decode('utf-8-sig')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    matches = []
    for line in lines:
        entry = re.fullmatch(
            r'(?:clave(?: del certificado)?|contraseña(?: del certificado)?|password|pin)\s*[:=]\s*(.+)',
            line, flags=re.IGNORECASE,
        )
        if entry:
            matches.append(entry.group(1))
    if len(matches) == 1:
        password = matches[0]
    elif not matches and len(lines) == 1 and not re.match(r'^[\w ]+\s*[:=]', lines[0]):
        password = lines[0]
    else:
        raise ValueError('No se identificó una clave única en el archivo. Adjunta el archivo original del certificado.')
    if len(password) > 1024 or any(ord(character) < 32 for character in password):
        raise ValueError('La clave del certificado tiene un formato inválido.')
    return password
