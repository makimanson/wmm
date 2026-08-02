"""
Utilidades de bloqueo de archivos para escritura atómica.
Independiente del resto de WMM. Puede usarse desde cualquier módulo.
"""
import fcntl


def lock_file(f):
    """Bloquea el archivo f (debe estar abierto en modo escritura)."""
    fcntl.flock(f, fcntl.LOCK_EX)


def unlock_file(f):
    """Desbloquea el archivo f."""
    fcntl.flock(f, fcntl.LOCK_UN)
