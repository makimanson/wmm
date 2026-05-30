#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WMM Applet - Cinnamon Edition
----------------------------
nemo_send_to_monitor.py – Acción "Enviar a monitor" desde Nemo.

Recibe la ruta de una imagen, muestra un diálogo con los monitores activos
y asigna la imagen al monitor seleccionado.
"""

import sys
import os
import subprocess
import time
import signal

# Asegurar que podemos importar el módulo vecino
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_handler import ConfigHandler


def main():
    if len(sys.argv) < 2:
        print("Uso: nemo_send_to_monitor.py <ruta_imagen>")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        sys.exit(1)

    # --- Control de instancia única ---
    ch = ConfigHandler()
    pid_path = os.path.join(ch.cache_dir, "pid_send_to_monitor.pid")
    os.makedirs(os.path.dirname(pid_path), exist_ok=True)

    if os.path.exists(pid_path):
        try:
            with open(pid_path, "r") as f:
                old_pid = int(f.read().strip())
            # Solo matar si es un proceso diferente (no nosotros)
            if old_pid != os.getpid():
                subprocess.run(["pkill", "-P", str(old_pid)], check=False)  # Matar hijos del proceso antiguo
                time.sleep(0.2)
        except (OSError, ValueError, FileNotFoundError):
            pass
        # Limpiar el PID antiguo pase lo que pase
        try:
            os.remove(pid_path)
        except FileNotFoundError:
            pass

    # Escribir nuestro PID actual
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))

    try:
        # Leer monitores activos
        vault = ch.load_json("vault")
        active = vault.get("active_session", {})
        geometry = ch.load_json("geometry")
        monitors = geometry.get("monitors", {})
        mfg_map = ch.get_mfg_map()

        # Construir lista para zenity y un mapa de vuelta
        zenity_opts = []
        label_to_hash = {}
        for m_hash, entry in active.items():
            if isinstance(entry, dict) and not entry.get("active", True):
                continue
            info = monitors.get(m_hash, {})
            conn = info.get("connector", "?")
            mfg_code = info.get("manufacturer", "")
            mfg_name = mfg_map.get(mfg_code, mfg_code)

            # Leer pulgadas desde geometry.json (ya calculadas por el motor)
            inches = info.get("inches", 0)
            size_str = f" ({inches}\")" if inches > 0 else ""

            # Construir etiqueta base
            if mfg_name and mfg_name != conn:
                label = f"{conn}:{mfg_name}{size_str}"
            else:
                label = f"{conn}{size_str}"

            # Indicar monitor principal
            if info.get("primary", False):
                label += " (Primary)"

            zenity_opts.append(label)
            label_to_hash[label] = m_hash

        if not zenity_opts:
            ch._send_notification(
                "WMM: No monitors",
                "No active monitors found.",
                level="warn"
            )
            sys.exit(1)

        # Mostrar diálogo con zenity
        zenity = subprocess.run(
            [
                "zenity", "--list",
                "--title=Send to Monitor",
                "--text=Select a monitor:",
                "--column=Monitor",
                "--width=250", "--height=250"
            ] + zenity_opts,
            capture_output=True,
            text=True
        )
        selected = zenity.stdout.strip()
        if not selected:
            sys.exit(0)  # Usuario canceló

        m_hash = label_to_hash.get(selected)
        if not m_hash:
            sys.exit(1)

        # Actualizar el vault
        entry = active.get(m_hash, {})
        if isinstance(entry, str):
            entry = {"path": entry, "active": True}
        entry["path"] = image_path
        vault["active_session"][m_hash] = entry
        ch.save_json("vault", vault)

        # Notificar al motor con apply_manual_selection (no force_rotation)
        ch.save_json("commands", {"action": "apply_manual_selection"})
        subprocess.run(["pkill", "-USR1", "-f", "main.py"])

        # Notificación de confirmación
        name = os.path.basename(image_path)
        ch._send_notification(
            "WMM: Image sent",
            f"Image '{name}' assigned to monitor {m_hash[:8]}.",
            level="info"
        )

    finally:
        if os.path.exists(pid_path):
            try:
                os.remove(pid_path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
