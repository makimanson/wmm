"""
Módulo de plataforma para KDE Plasma (Linux).
Contiene solo las implementaciones específicas de este entorno.
"""
# TODO: Implementar get_monitors usando KWin/KDE API
def get_monitors():
    # En KDE, se podría usar PyKDE o consultar a KWin vía D-Bus.
    # Por ahora, delegamos en la implementación genérica de Linux (Gdk).
    from wmm_platform.linux import _generic_get_monitors
    return _generic_get_monitors()

def set_wallpaper(path, config_handler=None):
    # KDE Plasma usa un script propio para cambiar el fondo
    import subprocess
    subprocess.run([
        "plasma-apply-wallpaperimage",
        path
    ], check=False)
