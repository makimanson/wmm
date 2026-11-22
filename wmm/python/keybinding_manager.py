#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""Formulario común de atajos; el registro y la persistencia pertenecen al backend."""

import os
import sys

if __name__ == "__main__":
    # El launcher vive en /python; la capa de plataforma está en la raíz WMM.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from i18n import _

def _position_window_at_point(window, platform, x, y):
    """Centra la ventana sobre un punto sin salir del workarea."""
    workarea = platform.get_point_available_area(int(x), int(y))

    if workarea is not None:
        area_x = workarea["x"]
        area_y = workarea["y"]
        area_width = workarea["width"]
        area_height = workarea["height"]

    else:
        display = Gdk.Display.get_default()
        if display is None:
            return

        monitor = display.get_monitor_at_point(int(x), int(y))
        if monitor is None:
            return

        gdk_workarea = monitor.get_workarea()

        area_x = gdk_workarea.x
        area_y = gdk_workarea.y
        area_width = gdk_workarea.width
        area_height = gdk_workarea.height

    _, natural = window.get_preferred_size()
    default_width, default_height = window.get_default_size()

    width = max(natural.width, default_width)
    height = max(natural.height, default_height)

    target_x = int(x - width / 2)
    target_y = int(y - height / 2)

    target_x = max(area_x, min(target_x, area_x + area_width - width))
    target_y = max(area_y, min(target_y, area_y + area_height - height))

    # El gestor de ventanas puede comunicar primero una geometría
    # provisional centrada. Esperar a la posición solicitada evita
    # corregir una geometría transitoria y perder el evento definitivo.
    def _on_frame_configured(widget, _event):
        native = widget.get_window()
        if native is None:
            return False

        frame = native.get_frame_extents()

        # Esperar a que estén disponibles las decoraciones exteriores.
        if (frame.width <= native.get_width()
                and frame.height <= native.get_height()):
            return False

        # No desconectar mientras el marco siga en una posición provisional.
        if (frame.x, frame.y) != (target_x, target_y):
            return False

        final_x = max(area_x, min(frame.x, area_x + area_width - frame.width))
        final_y = max(area_y, min(frame.y, area_y + area_height - frame.height))

        # Una vez alcanzada la posición solicitada, aplicar una única
        # corrección contra la workarea y liberar el manejador.
        widget.disconnect(configure_handler)

        if (final_x, final_y) != (frame.x, frame.y):
            widget.move(int(final_x), int(final_y))

        return False

    configure_handler = window.connect("configure-event", _on_frame_configured)

    window.set_position(Gtk.WindowPosition.NONE)
    window.move(target_x, target_y)

def format_keybinding(shortcut):
    """Traduce la presentación sin modificar los nombres del JSON."""
    if shortcut is None:
        return ""
    labels = {"Control": "Ctrl", "Alt": "Alt", "Shift": _("Shift")}
    parts = [labels.get(name, name) for name in shortcut["modifiers"]]
    key = shortcut.get("key")
    if key:
        parts.append(key)
    return " + ".join(parts)

class KeybindingDialog(Gtk.Dialog):
    """Captura una combinación; validate devuelve sus datos canónicos o ValueError."""

    def __init__(self, action_label, validate, shortcut=None, *, apply=None):
        super().__init__(title="WMM " + _("Keyboard shortcut"))
        self.set_icon_name("input-keyboard")
        self.set_modal(True)
        self.set_keep_above(True)
        self.set_resizable(False)
        self.set_default_size(290, -1)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._validate = validate
        self._apply = apply
        self._applying = False
        self._applied = False
        self.shortcut = None
        self._held_key = None
        self._capture_intercepted = False

        # Reconocer otros modificadores permite que el backend los rechace;
        # nunca convertir silenciosamente Super + N en una simple N.
        self._modifier_masks = (
            ("Control", Gdk.ModifierType.CONTROL_MASK),
            ("Alt", Gdk.ModifierType.MOD1_MASK),
            ("Shift", Gdk.ModifierType.SHIFT_MASK),
            ("Super", Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.MOD4_MASK),
            ("Meta", Gdk.ModifierType.META_MASK),
            ("Hyper", Gdk.ModifierType.HYPER_MASK),
            ("AltGr", Gdk.ModifierType.MOD5_MASK),
        )
        self._modifier_keys = {
            "Control_L": "Control", "Control_R": "Control",
            "Alt_L": "Alt", "Alt_R": "Alt",
            "Shift_L": "Shift", "Shift_R": "Shift",
            "Super_L": "Super", "Super_R": "Super",
            "Meta_L": "Meta", "Meta_R": "Meta",
            "Hyper_L": "Hyper", "Hyper_R": "Hyper",
            "ISO_Level3_Shift": "AltGr",
        }

        content = self.get_content_area()
        content.set_spacing(10)
        content.set_border_width(12)

        # Mantener visible la configuración original durante toda la edición.
        # Las capturas posteriores no modifican este recordatorio.
        action_title = Gtk.Label(xalign=0)
        action_title.set_markup('<span weight="bold" size="larger">%s</span>' %
            GLib.markup_escape_text(action_label))
        content.pack_start(action_title, False, False, 0)

        current = format_keybinding(shortcut) or _("No shortcut assigned")
        current_label = Gtk.Label(
            label=_("Current combination") + ": " + current, xalign=0)
        current_label.set_line_wrap(True)
        content.pack_start(current_label, False, False, 0)

        # Agrupar la instrucción y los controles de captura en un marco.
        # Margen contenido para no aumentar innecesariamente el ancho.
        capture_frame = Gtk.Frame()
        capture_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        capture_content.set_border_width(6)
        capture_frame.add(capture_content)
        content.pack_start(capture_frame, False, False, 0)

        capture_content.pack_start(Gtk.Label(
            label=_("Press the desired key combination."), xalign=0),
            False, False, 0)

        # La captura y el botón Clear comparten fila para mantener
        # compacto el formulario. Sólo Aceptar aplica los cambios.
        capture_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        capture_row.set_halign(Gtk.Align.END)

        self.entry = Gtk.Entry()
        self.entry.get_style_context().add_class("wmm-entry-border")
        self.entry.set_width_chars(18)
        self.entry.set_editable(False)
        self.entry.set_placeholder_text(_("No shortcut assigned"))
        self.entry.connect("key-press-event", self._on_key_press)
        self.entry.connect("key-release-event", self._on_key_release)
        self.entry.connect("focus-out-event", self._on_capture_focus_out)
        self.entry.connect("button-press-event", self._on_capture_button_press)
        capture_row.pack_start(self.entry, False, False, 0)

        self.remove_button = Gtk.Button(label=_("Clear"))
        self.remove_button.set_margin_end(30)
        self.remove_button.set_sensitive(shortcut is not None)
        self.remove_button.connect("clicked", self._on_remove_clicked)
        capture_row.pack_start(self.remove_button, False, False, 0)
        capture_row.set_margin_bottom(4)
        capture_content.pack_start(capture_row, False, False, 0)

        self.message = Gtk.Label(xalign=0)
        self.message.set_line_wrap(True)
        content.pack_start(self.message, False, False, 0)

        cancel_button = self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        cancel_button.set_margin_end(8)
        self.add_button(_("OK"), Gtk.ResponseType.OK)
        self.set_response_sensitive(Gtk.ResponseType.OK, True)

        if shortcut is not None:
            self._show_candidate(shortcut)

        self.connect("response", self._on_response)
        self.connect("delete-event", self._on_delete_event)


    def _on_response(self, dialog, response):
        """Confirma la combinación o su retirada únicamente al aceptar."""
        if self._apply is None or self._applied:
            return
        if self._applying:
            self.stop_emission_by_name("response")
            return
        if response != Gtk.ResponseType.OK:
            return

        self.stop_emission_by_name("response")

        # Un campo vacío permite retirar el atajo; una captura
        # incompleta o inválida no debe confundirse con ese estado.
        if self.shortcut is None and self.entry.get_text():
            return

        self._begin_apply(response)

    def _on_remove_clicked(self, button):
        """Limpia la captura sin modificar el atajo registrado."""
        if not self._applying:
            self._clear_candidate()

    def _clear_candidate(self):
        """Deja la captura vacía y preparada para otra combinación."""
        self.shortcut = None
        self._held_key = None
        self._capture_intercepted = False
        self.entry.set_text("")
        self.message.set_text("")
        self.entry.set_sensitive(True)
        self.remove_button.set_sensitive(False)
        self.set_response_sensitive(Gtk.ResponseType.OK, True)
        self.set_response_sensitive(Gtk.ResponseType.CANCEL, True)
        self.entry.grab_focus()

    def _begin_apply(self, response):
        """Ejecuta el cambio mediante el backend sin bloquear GTK."""
        import threading
        from debug_logger import log_event

        # Sólo Aceptar llega aquí. None representa una captura vacía.
        shortcut = None
        if self.shortcut is not None:
            shortcut = {"key": self.shortcut["key"],
                "modifiers": list(self.shortcut["modifiers"])}
        self._applying = True
        self._held_key = None
        self.entry.set_sensitive(False)
        self.remove_button.set_sensitive(False)

        for button in (Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL):
            self.set_response_sensitive(button, False)

        self.message.set_text(_("Applying keyboard shortcut..."))

        def apply_change():
            error = None
            try:
                # El backend conserva el registro y la persistencia.
                # El hilo auxiliar nunca manipula controles GTK.
                self._apply(shortcut)
            except ValueError as exception:
                error = str(exception) or _("Could not apply the keyboard shortcut.")
            except Exception as exception:
                log_event(f"Error al aplicar el atajo: {exception}",
                    origin="KEYBINDING", level="ERROR", reason="SETTINGS")
                error = _("Could not apply the keyboard shortcut.")

            GLib.idle_add(self._finish_apply, response, error)

        try:
            threading.Thread(target=apply_change,
                name="WMM-KeybindingApply", daemon=True).start()
        except Exception as exception:
            log_event(f"No se pudo iniciar la aplicación del atajo: {exception}",
                origin="KEYBINDING", level="ERROR", reason="SETTINGS")
            self._finish_apply(response, _("Could not apply the keyboard shortcut."))

    def _finish_apply(self, response, error):
        """Recupera el formulario o cierra tras confirmar el cambio."""
        self._applying = False

        if error is not None:
            self.message.set_text(error)
            self.entry.set_sensitive(True)
            self.remove_button.set_sensitive(bool(self.entry.get_text()))

            # Vacío y combinación válida son estados confirmables.
            # Una captura incompleta o inválida no lo es.
            can_accept = self.shortcut is not None or not self.entry.get_text()
            self.set_response_sensitive(Gtk.ResponseType.OK, can_accept)
            self.set_response_sensitive(Gtk.ResponseType.CANCEL, True)
            self.entry.grab_focus()
        else:
            # El backend ya ha confirmado el único cambio: Aceptar.
            self._applied = True
            self.response(response)

        return GLib.SOURCE_REMOVE

    def _on_delete_event(self, widget, event):
        """Mantiene abierto el diálogo mientras el backend confirma un cambio."""
        return self._applying

    def _show_candidate(self, candidate):
        """La validación aquí es de formato; la disponibilidad se comprobará al aceptar."""

        # Sin tecla ni modificadores equivale a una captura vacía,
        # no a una combinación incompleta.
        if not candidate.get("key") and not candidate.get("modifiers"):
            self._clear_candidate()
            return

        self.shortcut = None
        self.entry.set_text(format_keybinding(candidate))

        # Clear sólo limpia la captura, sin modificar el atajo registrado.
        self.remove_button.set_sensitive(bool(self.entry.get_text()))
        self.set_response_sensitive(Gtk.ResponseType.OK, False)
        if not candidate.get("key"):
            self.message.set_text(_("Complete the key combination."))
            return
        try:
            canonical = self._validate(candidate)
        except ValueError:
            self.message.set_text(_("This key combination is not supported."))
            return
        self.shortcut = {"key": canonical["key"], "modifiers": list(canonical["modifiers"])}
        self.entry.set_text(format_keybinding(self.shortcut))
        self.message.set_text("")
        self.set_response_sensitive(Gtk.ResponseType.OK, True)

    def _event_modifiers(self, event, pressed=False):
        modifiers = [name for name, mask in self._modifier_masks if event.state & mask]
        modifier = self._modifier_keys.get(Gdk.keyval_name(event.keyval))
        if pressed and modifier and modifier not in modifiers:
            modifiers.append(modifier)
        if not pressed and modifier in modifiers:
            modifiers.remove(modifier)
        return [name for name, mask in self._modifier_masks if name in modifiers]

    def _on_key_press(self, widget, event):
        name = Gdk.keyval_name(event.keyval)
        if name == "Escape":
            self.response(Gtk.ResponseType.CANCEL)
            return True
        if name in ("Tab", "ISO_Left_Tab"):
            return False

        # Un PRESS recibido por GTK inicia una captura real. Si el intento
        # anterior fue interceptado por el sistema, deja de ser relevante.
        self._capture_intercepted = False

        modifiers = self._event_modifiers(event, pressed=True)
        if name in self._modifier_keys:
            key = self._held_key[1] if self._held_key is not None else None
        else:
            # Resolver la tecla sin Shift evita guardar "exclam" cuando el
            # usuario pulsa Ctrl + Shift + 1. Shift queda en los modificadores.
            keymap = Gdk.Keymap.get_for_display(self.get_display())
            translated = keymap.translate_keyboard_state(
                event.hardware_keycode, Gdk.ModifierType(0), event.group)
            if not translated[0]:
                self._show_candidate({"key": None, "modifiers": modifiers})
                return True
            key = Gdk.keyval_name(translated[1])
            if key and len(key) == 1 and key.isascii():
                key = key.upper()
            self._held_key = (event.hardware_keycode, key)
        self._show_candidate({"key": key, "modifiers": modifiers})
        return True

    def _on_key_release(self, widget, event):
        name = Gdk.keyval_name(event.keyval)

        # Si GTK recibe el RELEASE de una tecla normal sin haber recibido
        # antes su PRESS, el sistema ha interceptado esa combinación.
        if name not in self._modifier_keys and (self._held_key is None
                or self._held_key[0] != event.hardware_keycode):

            key = name
            if key and len(key) == 1 and key.isascii():
                key = key.upper()

            candidate = { "key": key, "modifiers": self._event_modifiers(event), }

            self.shortcut = None
            self._capture_intercepted = True
            self.entry.set_text(format_keybinding(candidate))
            self.message.set_text(_("This key combination is already in use."))
            self.remove_button.set_sensitive(True)
            self.set_response_sensitive(Gtk.ResponseType.OK, False)
            return True

        if self._held_key is not None and self._held_key[0] == event.hardware_keycode:
            self._held_key = None

        # Una combinación completa permanece visible después de soltarla.
        # Si el sistema interceptó el intento, conservar el aviso hasta que
        # el usuario inicie una nueva captura o pulse Clear.
        if (self.shortcut is None
                and not self._capture_intercepted
                and name in self._modifier_keys):
            self._show_candidate({ "key": None, "modifiers": self._event_modifiers(event), })

        return True

    def _on_capture_button_press(self, widget, event):
        """Permite enfocar la captura, pero impide seleccionar su texto."""
        widget.grab_focus()
        return True

    def _on_capture_focus_out(self, widget, event):
        self._held_key = None
        return False

def main():
    """Abre la captura común utilizando las capacidades del escritorio activo."""
    from config_handler import ConfigHandler
    from debug_logger import log_event
    from i18n import initialize
    from wmm_platform.core import PlatformManager

    platform = PlatformManager()

    anchor = None
    if len(sys.argv) == 3:
        try:
            anchor = (int(sys.argv[1]), int(sys.argv[2]))
        except ValueError:
            pass

    # Linux conserva su nombre de proceso; Windows identifica el formulario
    # antes de crear la ventana para mantener separadas ambas responsabilidades.
    if hasattr(platform, "set_process_name"):
        platform.set_process_name("WMM Keybinding")

    if hasattr(platform, "prepare_form_taskbar_identity"):
        platform.prepare_form_taskbar_identity("keybinding")

    initialize(platform)
    handler = ConfigHandler(cache_base_dir=platform.cache_dir, platform=platform)

    if hasattr(platform, "prepare_gtk_color_scheme"):
        platform.prepare_gtk_color_scheme()

    def request(payload):
        result = platform.request_keybindings(handler.data_dir, payload)
        if not result.get("ok"):
            raise RuntimeError(f"Petición de atajo rechazada: {result}")
        return result

    # Una segunda captura no debe retirar ni restaurar el registro de la primera.
    lock_path = os.path.join(handler.cache_dir, "keybinding_manager.lock")
    with open(lock_path, "a+") as lock_file:
        if not platform.try_lock_file(lock_file):
            log_event("Formulario de atajo ya abierto",
                origin="KEYBINDING", level="INFO", reason="SETTINGS")
            return

        dialog = None
        suspended = False
        committed = False
        previous = None
        try:
            previous = request({"action": "get"})["shortcut"]
            request({"action": "set", "shortcut": None})
            suspended = True
            dialog = KeybindingDialog(_("Next Background"), platform.validate_keybinding,
                previous, apply=lambda value: platform.apply_keybinding(handler, value))

            if anchor is not None:
                # Preparar las dimensiones de los hijos sin mapear la ventana.
                # Evita presentar primero el diálogo en la posición centrada.
                dialog.get_child().show_all()
                _position_window_at_point(dialog, platform, anchor[0], anchor[1])

            dialog.show_all()

            dialog.entry.grab_focus()

            if hasattr(platform, "present_window"):
                if hasattr(platform, "prepare_form_taskbar_identity"):
                    platform.present_window(dialog, form_name="keybinding")
                else:
                    platform.present_window(dialog)
            else:
                dialog.present()

            response = dialog.run()
            committed = response == Gtk.ResponseType.OK

        finally:
            try:
                if dialog is not None:
                    dialog.destroy()
            finally:
                try:
                    # Sólo Aceptar confirma registro y persistencia.
                    # Cancelar o un fallo restauran el registro original.
                    if suspended and not committed:
                        request({"action": "set", "shortcut": previous})
                finally:
                    platform.unlock_file(lock_file)

if __name__ == "__main__":
    from debug_logger import log_event

    try:
        main()
    except Exception as error:
        log_event(f"No se pudo configurar el atajo: {error}",
            origin="KEYBINDING", level="ERROR", reason="SETTINGS")
        sys.exit(1)
