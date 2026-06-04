"""
Módulo de plataforma para GNOME (Linux).
Contiene solo las implementaciones específicas de este entorno.
"""
# TODO: Implementar get_monitors usando GNOME Shell/Mutter
def get_monitors():
    # En GNOME, se podría usar la misma API de Gdk que en Cinnamon,
    # o bien consultar directamente a Mutter vía D-Bus.
    # Por ahora, delegamos en la implementación genérica de Linux (Gdk).
    from wmm_platform.linux import _generic_get_monitors
    return _generic_get_monitors()

def set_wallpaper(path, config_handler=None):
    # GNOME usa gsettings con esquema 'org.gnome.desktop.background'
    import os
    os.system(f"gsettings set org.gnome.desktop.background picture-uri 'file://{path}'")
