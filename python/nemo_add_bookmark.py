#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WMM Applet - Cinnamon Edition
----------------------------
nemo_add_bookmark.py – Añade una imagen a favoritos desde Nemo.
"""

import sys
import os
import subprocess
import gettext

# Asegurar la importación del módulo vecino
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_handler import ConfigHandler
from PIL import Image

# ==========================================================
# Traducciones
# ==========================================================

# Captura de traducibles
_ = gettext.gettext
# Ruta estándar de traducciones para extensiones de Cinnamon
# locale_dir = os.path.expanduser('~/.local/share/locale')
# Usar el dominio 'wmm-applet@maki'
# gettext.bindtextdomain('wmm-applet@maki', locale_dir)

# Función de traducción personalizada: busca primero en el sistema, luego en nuestro dominio
def _(text):
    translated = gettext.dgettext('cinnamon', text)
    if translated != text:
        return translated
    return gettext.dgettext('wmm-applet@maki', text)

def main():
    #Testeo de rutas
    import datetime
    with open("/tmp/wmm_nemo_debug.log", "a") as f:
        f.write(f"{datetime.datetime.now()}: sys.argv = {sys.argv}\n")
        f.write(f"{datetime.datetime.now()}: CWD = {os.getcwd()}\n")

    if len(sys.argv) < 2:
        print("Uso: nemo_add_bookmark.py <ruta_imagen>")
        sys.exit(1)

    # Reconstruir la ruta si Nemo la ha fragmentado por espacios
    if len(sys.argv) > 2:
        sys.argv = [sys.argv[0], ' '.join(sys.argv[1:])]

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        sys.exit(1)

    ch = ConfigHandler()

    # Obtener dimensiones y orientación
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            orient = "h" if w >= h else "v"
    except Exception as e:
        ch._send_notification(_("Error adding to favorites"),
                              _("Could not process image:") + "\n" + e,
                              level="error")
        sys.exit(1)

    entry = [image_path, w, h, orient]

    # Verificar duplicados
    current_list = ch.load_json("bookmarks_single")
    existing_paths = [item[0] for item in current_list]
    if image_path in existing_paths:
        ch._send_notification(_("Add to favorites"),
                              _("Image is already in favorites."),
                              level="info")
        return

    # Añadir y guardar
    current_list.append(entry)
    ch.save_json("bookmarks_single", current_list)
    ch.refresh_history_metadata()

    try:
        ch.save_json("commands", {"action": "bookmark_added", "name": os.path.basename(image_path)})
        subprocess.run(["pkill", "-USR1", "-f", "main.py"])
    except Exception as e:
        print(f" [AVISO] No se pudo notificar al motor: {e}")

if __name__ == "__main__":
    main()
