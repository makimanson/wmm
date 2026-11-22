#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

image_engine.py – Motor gráfico para la generación del lienzo maestro.
=============================
Renderiza el fondo de pantalla componiendo las imágenes seleccionadas
sobre un lienzo único, aplicando modos de aspecto, efectos visuales
y fondos de relleno.
"""

# ==========================================================
# IMPORTS DE LIBRERÍA ESTÁNDAR
# ==========================================================
import os
import io
import math
import hashlib
import json
import warnings
import threading

from functools import wraps

# ==========================================================
# IMPORTS DE TERCEROS
# ==========================================================
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageOps

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from monitor_manager import get_spanned_reference_hash, get_total_canvas_geometry
from debug_logger import log_event
from exif_cache import read_exif
from i18n import _

# ==========================================================
# DIAGNÓSTICO PILLOW: RUTA DE LA IMAGEN POR HILO
# ==========================================================
_pillow_warning_path = threading.local()
_previous_showwarning = warnings.showwarning


def _wmm_show_pillow_warning(message, category, filename, lineno, file=None, line=None):
    """Registrar el aviso EXIF identificado sin afectar a otros warnings."""
    img_path = getattr(_pillow_warning_path, "path", None)

    if (img_path and issubclass(category, UserWarning)
            and str(message) == "Truncated File Read"
            and filename.replace("\\", "/").endswith("/PIL/TiffImagePlugin.py")):
        log_event(f"Pillow: {message} | Imagen: {img_path}",
            origin="IMG_ENG", level="WARN", reason="LIBRARY")
        return

    _previous_showwarning(message, category, filename, lineno, file=file, line=line)


def _track_pillow_image(func):
    """Asociar los avisos de Pillow al original procesado por cada hilo."""
    @wraps(func)
    def wrapped(path, *args, **kwargs):
        previous = getattr(_pillow_warning_path, "path", None)
        _pillow_warning_path.path = path
        try:
            return func(path, *args, **kwargs)
        finally:
            _pillow_warning_path.path = previous
    return wrapped


# Capturar cada aparición de este aviso, no sólo la primera.
# El resto de categorías conserva su tratamiento habitual.
warnings.filterwarnings("always", message=r"^Truncated File Read$",
    category=UserWarning, module=r"^PIL\.TiffImagePlugin$")
warnings.showwarning = _wmm_show_pillow_warning


class ImageEngine:
    def __init__(self, config_handler, monitor_manager):
        """
        Motor gráfico para la generación del lienzo maestro.
        """
        self.ch = config_handler
        self.mm = monitor_manager
        self.master_path = self.ch.master_canvas

    @staticmethod
    def _build_metadata_lines(img_path, entry, selected_fields, field_groups):
        """Construye las líneas EXIF seleccionadas, sin intervenir en el dibujo."""
        if not isinstance(img_path, str) or not isinstance(selected_fields, (list, tuple, set)):
            return []

        selected = set(selected_fields)
        entry = entry if isinstance(entry, dict) else {}
        lines = []

        for group, fields in field_groups:
            values = []
            for key, label in fields:
                if key not in selected:
                    continue

                if key == "filename":
                    filename = os.path.basename(img_path.replace("\\", "/"))
                    value = os.path.splitext(filename)[0]
                elif key == "directory":
                    value = os.path.dirname(img_path)
                else:
                    family, field = key.split(".", 1)
                    family_data = entry.get(family, {})
                    value = family_data.get(field) if isinstance(family_data, dict) else None

                if value is None:
                    continue

                # Abreviaturas traducibles; las unidades SI permanecen como símbolos.
                if key == "GPSInfo.AltitudeMeters" and isinstance(value, (int, float)):
                    value = f"{_('Alt.')} {value:g} m"
                elif key == "Geolocation.distance_km" and isinstance(value, (int, float)):
                    value = f"{_('Dist.')} {value:.2f} km"
                else:
                    value = str(value).strip()

                if not value:
                    continue

                if group == "Image":
                    field_label = group if key == "filename" else label
                    lines.append(f"{_(field_label)}: {value}")
                else:
                    values.append(value)

            if group != "Image" and values:
                lines.append(f"{_(group)}: {' · '.join(values)}")

        return lines

    def _load_metadata_lines(self, selection, settings=None):
        """
        Prepara las líneas EXIF de las imágenes seleccionadas.

        Consulta settings.json y lee exif_cache.json una sola vez por
        composición. No modifica las imágenes ni las cachés.
        """
        if settings is None:
            settings = self.ch.load_json("settings").get("global", {})

        if not settings.get("exif_metadata_enabled", False):
            return {}

        selected = settings.get("exif_metadata_fields", [])
        if not isinstance(selected, list) or not selected:
            return {}

        # Descartar fondos de color y evitar procesar dos veces una misma ruta.
        paths = {path for path in selection.values() if isinstance(path, str)}
        if not paths:
            return {}

        # Una caché ausente no impide mostrar el nombre del archivo.
        cache_path = os.path.join(self.ch.data_dir, "exif_cache.json")
        try:
            with open(cache_path, "r", encoding="utf-8") as file:
                cache = json.load(file)
        except (OSError, ValueError):
            cache = {}

        if not isinstance(cache, dict):
            cache = {}

        # Las imágenes internas de demostración no pertenecen a Sources
        # ni a exif_cache.json. Sus metadatos se leen directamente.
        demos_dir = os.path.normcase(os.path.abspath(
            os.path.join(self.ch.app_root, "screenshots")))

        lines_by_path = {}
        for path in paths:
            entry = cache.get(path)

            if (not isinstance(entry, dict) and
                    os.path.normcase(os.path.dirname(os.path.abspath(path))) == demos_dir):
                try:
                    entry = read_exif(path)
                except (OSError, ValueError, TypeError, SyntaxError) as error:
                    log_event(f"Error leyendo metadatos demo de {os.path.basename(path)}: {error}",
                        origin="IMG_ENG", level="WARN", reason="LIBRARY")
                    entry = {}

            lines_by_path[path] = self._build_metadata_lines(
                path, entry, selected,
                self.ch.METADATA_FIELD_GROUPS)

        return lines_by_path

    @staticmethod
    def _draw_metadata_block(image, lines, position, font_name,
        margin_x, margin_y, area=None, opacity=67):
        """
        Compone los metadatos con PangoCairo sobre una imagen PIL.

        La posición determina también la alineación del texto.
        area limita la composición a una región visible del lienzo.
        """
        if not lines:
            return image

        import cairo
        import gi
        gi.require_foreign("cairo")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo

        left, top, right, bottom = area or (0, 0, *image.size)
        padding, spacing = 14, 6
        max_width = right - left - 2 * (margin_x + padding)

        if max_width <= 0:
            return image

        # Preparar y medir el texto con la tipografía seleccionada en GTK.
        measure_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        layout = PangoCairo.create_layout(cairo.Context(measure_surface))
        layout.set_font_description(
            Pango.FontDescription.from_string(font_name or "Sans 12"))
        layout.set_text("\n".join(lines), -1)
        layout.set_spacing(spacing * Pango.SCALE)

        natural_width, _ = layout.get_pixel_size()
        text_width = min(natural_width, max_width)

        # Ajustar las líneas excepcionalmente largas sin crear saltos.
        layout.set_width(text_width * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_auto_dir(False)

        align_right = position in ("top_right", "bottom_right")
        align_bottom = position in ("bottom_left", "bottom_right")

        layout.set_alignment(
            Pango.Alignment.RIGHT if align_right else Pango.Alignment.LEFT)

        _, text_height = layout.get_pixel_size()
        block_width = text_width + 2 * padding
        block_height = text_height + 2 * padding

        if block_height > bottom - top - 2 * margin_y:
            return image

        x = right - margin_x - block_width if align_right else left + margin_x
        y = bottom - margin_y - block_height if align_bottom else top + margin_y

        # Rasterizar únicamente el rectángulo de los metadatos.
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, block_width, block_height)
        ctx = cairo.Context(surface)

        radius = 8

        ctx.new_sub_path()
        ctx.arc(block_width - radius, radius, radius, -math.pi / 2, 0)
        ctx.arc(block_width - radius, block_height - radius,
                radius, 0, math.pi / 2)
        ctx.arc(radius, block_height - radius,
                radius, math.pi / 2, math.pi)
        ctx.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        ctx.close_path()

        ctx.set_source_rgba(0, 0, 0, max(0, min(100, opacity)) / 100)
        ctx.fill()

        ctx.move_to(padding, padding)
        ctx.set_source_rgb(1, 1, 1)
        PangoCairo.show_layout(ctx, layout)

        # Transferir el resultado a PIL respetando el alfa premultiplicado.
        surface.flush()
        overlay = Image.frombytes(
            "RGBA", (block_width, block_height),
            bytes(surface.get_data()), "raw", "BGRa")

        image.paste(overlay, (x, y), overlay.getchannel("A"))
        return image

    @staticmethod
    def _create_color_surface(width, height, color_mode, solid_color, gradient_h, gradient_v):
        """
        Crea una superficie PIL del tamaño indicado según el modo de color.
        color_mode: 'solid_color', 'gradient_h' o 'gradient_v'
        solid_color: string hex (ej. '#000000')
        gradient_h, gradient_v: listas de dos strings hex (ej. ['#000000', '#FFFFFF'])
        """
        surface = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(surface)

        if color_mode == 'solid_color' or color_mode == 'solid':
            draw.rectangle([(0, 0), (width, height)], fill=solid_color)

        elif color_mode in ('gradient_h', 'gradient_v', 'gradient_horizontal', 'gradient_vertical'):
            start_hex = gradient_h[0] if 'h' in color_mode else gradient_v[0]
            end_hex = gradient_h[1] if 'h' in color_mode else gradient_v[1]
            start_rgb = ImageEngine._hex_to_rgb(start_hex)
            end_rgb = ImageEngine._hex_to_rgb(end_hex)

            if 'h' in color_mode:
                # Degradado horizontal suave: dibujar en 1px de alto y escalar
                gradient_surface = Image.new('RGB', (width, 1))
                draw_grad = ImageDraw.Draw(gradient_surface)
                for x in range(width):
                    ratio = x / width
                    r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
                    g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
                    b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
                    draw_grad.point((x, 0), fill=(r, g, b))
                del draw_grad
                surface = gradient_surface.resize((width, height), Image.Resampling.BILINEAR)

            else:  # vertical
                gradient_surface = Image.new('RGB', (1, height))
                draw_grad = ImageDraw.Draw(gradient_surface)
                for y in range(height):
                    ratio = y / height
                    r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
                    g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
                    b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
                    draw_grad.point((0, y), fill=(r, g, b))
                del draw_grad
                surface = gradient_surface.resize((width, height), Image.Resampling.BILINEAR)

        del draw
        return surface

    @staticmethod
    def _hex_to_rgb(hex_str):
        """Convierte un color hexadecimal (#RRGGBB) a tupla RGB."""
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    @_track_pillow_image
    def _open_image_safe(path):
        """Abre la imagen respetando la orientación EXIF y la transparencia P."""
        img = Image.open(path)
        try:
            try:
                orientation = img.getexif().get(274)
            except (OSError, ValueError, TypeError, SyntaxError):
                orientation = None

            # Transformar únicamente imágenes con una orientación EXIF pendiente.
            if orientation in (2, 3, 4, 5, 6, 7, 8):
                corrected = ImageOps.exif_transpose(img)
                img.close()
                img = corrected

            # Conservar el tratamiento existente de imágenes indexadas.
            if img.mode == 'P' and 'transparency' in img.info:
                converted = img.convert('RGBA')
                img.close()
                img = converted

            return img

        except Exception:
            img.close()
            raise

    def _process_single_image(self, selection, monitors_map, spanned_enabled,
                             solid_color, color_mode, gradient_h, gradient_v,
                             wallpaper_effect_scope, wallpaper_mode, image_effect):
        """
        Procesa las imágenes de selection y devuelve un diccionario
        {hash: PIL.Image} con cada imagen ya procesada para su monitor.

        Esta función contiene TODA la lógica de procesamiento:
        - Modo spanned (real): la misma imagen se procesa para cada monitor
          con sus dimensiones, creando una imagen continua.
        - Modo normal: cada monitor tiene su propia imagen.
        - Colores sólidos y degradados.
        - Modos de aspecto (fit, zoom, stretched).
        - Efectos de imagen (sepia, bw, none).
        - Fondo de relleno (blur o color).
        """
        processed_images = {}

        # Preparar los metadatos una sola vez por composición.
        metadata_settings = self.ch.load_json("settings").get("global", {})
        metadata_lines = self._load_metadata_lines(selection, metadata_settings)
        metadata_font = metadata_settings.get("exif_metadata_font", "Sans 12")
        metadata_position = metadata_settings.get("exif_metadata_position", "top_left")
        metadata_opacity = metadata_settings.get("exif_metadata_background_opacity", 67)
        metadata_margin_x = metadata_settings.get("exif_metadata_margin_x", 64)
        metadata_margin_y = metadata_settings.get("exif_metadata_margin_y", 42)

        if spanned_enabled:
            # --- Spanned: usar la imagen que ya viene en selection (build_selection ya decidió cuál es) ---
            if not selection:
                log_event("Selection vacía para spanned",
                    origin="IMG_ENG", level="ERROR", reason="LIBRARY")
                return {}

            # 1. Tomar la primera imagen de selection (sin más lógica)
            img_path = next(iter(selection.values()))
            image_valid = True
            # 2. Calcular el tamaño total del canvas
            canvas_w = max(mon['x'] + mon['width'] for mon in monitors_map.values())
            canvas_h = max(mon['y'] + mon['height'] for mon in monitors_map.values())

            # 3. Procesar la imagen UNA SOLA VEZ para el canvas completo
            if isinstance(img_path, tuple) and img_path[0] == "color":
                _, cm, sc, gh, gv = img_path
                canvas_image = self._create_color_surface(canvas_w, canvas_h, cm, sc, gh, gv)
            else:
                try:
                    with self._open_image_safe(img_path) as img:
                        if wallpaper_mode == "fit":
                            canvas_image = self.apply_fit(
                                img, canvas_w, canvas_h,
                                wallpaper_effect_scope=wallpaper_effect_scope,
                                solid_color=solid_color,
                                gradient_h=gradient_h,
                                gradient_v=gradient_v,
                                color_mode=color_mode,
                                image_effect=image_effect
                            )
                        elif wallpaper_mode == "zoom":
                            canvas_image = self.apply_zoom(img, canvas_w, canvas_h, image_effect=image_effect)
                        elif wallpaper_mode == "stretched":
                            canvas_image = self.apply_stretched(img, canvas_w, canvas_h, image_effect=image_effect)
                        else:
                            canvas_image = self.apply_fit(
                                img, canvas_w, canvas_h,
                                wallpaper_effect_scope=wallpaper_effect_scope,
                                solid_color=solid_color,
                                gradient_h=gradient_h,
                                gradient_v=gradient_v,
                                color_mode=color_mode,
                                image_effect=image_effect
                            )
                except Exception as e:
                    image_valid = False
                    log_event(f"Error procesando imagen base para spanned: {e}",
                        origin="IMG_ENG", level="ERROR", reason="LIBRARY")
                    canvas_image = self._create_color_surface(canvas_w, canvas_h,
                        color_mode, solid_color, gradient_h, gradient_v)

            # Un único bloque EXIF sobre la composición panorámica.
            if image_valid and isinstance(img_path, str):
                lines = metadata_lines.get(img_path)
                if lines:
                    # Buscar la esquina visible más cercana a la elegida.
                    right = metadata_position.endswith("right")
                    bottom = metadata_position.startswith("bottom")
                    corner_x = canvas_w if right else 0
                    corner_y = canvas_h if bottom else 0

                    monitor = min(monitors_map.values(), key=lambda mon: (
                        ((mon["x"] + mon["width"] if right else mon["x"]) - corner_x) ** 2 +
                        ((mon["y"] + mon["height"] if bottom else mon["y"]) - corner_y) ** 2
                    ))

                    area = (
                        monitor["x"], monitor["y"],
                        monitor["x"] + monitor["width"],
                        monitor["y"] + monitor["height"]
                    )

                    try:
                        self._draw_metadata_block(canvas_image, lines, metadata_position, metadata_font,
                            metadata_margin_x, metadata_margin_y, area=area, opacity=metadata_opacity)
                    except Exception as error:
                        log_event(f"Error dibujando metadatos Spanned: {error}",
                            origin="IMG_ENG", level="WARN", reason="LIBRARY")

            # 4. Recortar fragmentos para cada monitor
            for m_hash, mon in monitors_map.items():
                box = (mon['x'], mon['y'], mon['x'] + mon['width'], mon['y'] + mon['height'])
                fragment = canvas_image.crop(box)
                processed_images[m_hash] = fragment

        else:
            # --- Modo normal: cada monitor tiene su propia imagen ---
            for m_hash, img_path in selection.items():
                if m_hash not in monitors_map:
                    continue
                mon = monitors_map[m_hash]
                target_w = mon['width']
                target_h = mon['height']

                image_valid = True

                if isinstance(img_path, tuple) and img_path[0] == "color":
                    _, cm, sc, gh, gv = img_path
                    processed = self._create_color_surface(target_w, target_h, cm, sc, gh, gv)
                else:
                    try:
                        with self._open_image_safe(img_path) as img:
                            if wallpaper_mode == "fit":
                                processed = self.apply_fit(
                                    img, target_w, target_h,
                                    wallpaper_effect_scope=wallpaper_effect_scope,
                                    solid_color=solid_color,
                                    gradient_h=gradient_h,
                                    gradient_v=gradient_v,
                                    color_mode=color_mode,
                                    image_effect=image_effect
                                )
                            elif wallpaper_mode == "zoom":
                                processed = self.apply_zoom(img, target_w, target_h, image_effect=image_effect)
                            elif wallpaper_mode == "stretched":
                                processed = self.apply_stretched(img, target_w, target_h, image_effect=image_effect)
                            else:
                                processed = self.apply_fit(
                                    img, target_w, target_h,
                                    wallpaper_effect_scope=wallpaper_effect_scope,
                                    solid_color=solid_color,
                                    gradient_h=gradient_h,
                                    gradient_v=gradient_v,
                                    color_mode=color_mode,
                                    image_effect=image_effect
                                )
                    except Exception as e:
                        image_valid = False
                        log_event(f"Error procesando imagen para {m_hash}: {e}",
                            origin="IMG_ENG", level="ERROR", reason="LIBRARY")
                        processed = self._create_color_surface(target_w, target_h,
                            color_mode, solid_color, gradient_h, gradient_v)

                # Dibujar los metadatos sobre la imagen terminada.
                if image_valid and isinstance(img_path, str):
                    lines = metadata_lines.get(img_path)
                    if lines:
                        try:
                            self._draw_metadata_block(processed, lines, metadata_position, metadata_font,
                                metadata_margin_x, metadata_margin_y, opacity=metadata_opacity)
                        except Exception as error:
                            log_event(f"Error dibujando metadatos: {error}",
                                origin="IMG_ENG", level="WARN", reason="LIBRARY")

                processed_images[m_hash] = processed

        log_event(f"Imágenes procesadas: {len(processed_images)}",
            origin="IMG_ENG", level="DEBUG", reason="LIBRARY")
        return processed_images

    # --- NUEVOS MÉTODOS ESTÁTICOS DE PROCESAMIENTO DE IMÁGENES ---

    @staticmethod
    @_track_pillow_image
    def process_image(path):
        """
        Clasifica la orientación visual priorizando EXIF.
        Verifica primero el archivo y consulta después sus metadatos,
        sin decodificar ni modificar sus píxeles.
        Retorna (orient, w, h) o (None, 0, 0) si falla.
        """
        try:
            # Pillow exige verificar inmediatamente después de abrir.
            with Image.open(path) as img:
                img.verify()

            # La verificación invalida el objeto: reabrir para consultar EXIF.
            with Image.open(path) as img:
                w, h = img.size
                try:
                    exif_orientation = img.getexif().get(274)
                except (OSError, ValueError, TypeError, SyntaxError):
                    exif_orientation = None

            if exif_orientation in (5, 6, 7, 8):
                w, h = h, w

            orientation = "h" if w >= h else "v"
            return orientation, w, h

        except Exception as e:
            ext = os.path.splitext(path)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'):
                log_event(f"Error físico/corrupción en: {os.path.basename(path)} -> {e}", origin="IMG_ENG", level="ERROR", reason="LIBRARY")
            return None, 0, 0

    @staticmethod
    @_track_pillow_image
    def generate_thumbnail(img_path, max_height, max_width, thumb_dir=None):
        """
        Genera una miniatura proporcional de la imagen en formato JPEG.

        Args:
            img_path (str): Ruta absoluta de la imagen original.
            max_height (int): Altura máxima de la miniatura.
            max_width (int): Anchura máxima de la miniatura.
            thumb_dir (str): Directorio donde se almacenará la miniatura.
                             Debe ser proporcionado por el llamante.

        Returns:
            str: Ruta de la miniatura generada, o cadena vacía si falla.
        """
        if thumb_dir is None:
            raise ValueError("thumb_dir es obligatorio para generar miniaturas.")

        os.makedirs(thumb_dir, exist_ok=True)

        m = hashlib.md5(img_path.encode()).hexdigest()
        thumb_path = os.path.join(thumb_dir, f"{m}.jpg")
        if not os.path.exists(thumb_path):
            try:
                with ImageEngine._open_image_safe(img_path) as img:
                    if img.mode == 'P':
                        img = img.convert('RGB')
                    elif img.mode == 'RGBA':
                        canvas = Image.new("RGB", img.size, (0, 0, 0))
                        canvas.paste(img, mask=img.split()[3])
                        img = canvas
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                    w, h = img.size
                    ratio = w / h
                    new_h = max_height
                    new_w = int(new_h * ratio)
                    if new_w > max_width:
                        new_w = max_width
                        new_h = int(new_w / ratio)
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    img.save(thumb_path, "JPEG", quality=75)
            except Exception as e:
                log_event(f"Error generando miniatura para {os.path.basename(img_path)}: {e}",
                    origin="IMG_ENG", level="WARN", reason="LIBRARY")
                return ""
        return thumb_path

    @staticmethod
    def generate_composite_thumbnail(img_path, target_w, target_h, thumb_dir=None,
        wallpaper_effect_scope="blur", solid_color="#000000", gradient_h=None,
        gradient_v=None, color_mode="solid_color", image_effect="none"):
        """
        Genera una miniatura compuesta (blur de fondo + imagen centrada)
        para que ocupe exactamente target_w × target_h sin deformar la imagen real.
        Utiliza _render_image_with_blur para la composición.

        Args:
            img_path (str): Ruta absoluta de la imagen original.
            target_w (int): Anchura deseada de la miniatura compuesta.
            target_h (int): Altura deseada de la miniatura compuesta.
            thumb_dir (str): Directorio donde se almacenará la miniatura.
                             Debe ser proporcionado por el llamante.

        Returns:
            str or None: Ruta de la miniatura compuesta, o None si falla.
        """
        if thumb_dir is None:
            raise ValueError("thumb_dir es obligatorio para generar miniaturas compuestas.")

        if isinstance(img_path, tuple) and img_path[0] == "color":
            # miniatura de color o degradado
            _, color_mode, solid_color, gradient_h, gradient_v = img_path
            composite = ImageEngine._create_color_surface(
                target_w, target_h, color_mode, solid_color, gradient_h, gradient_v
            )
            # Guardar igual que una miniatura normal
            m = hashlib.md5(f"{color_mode}_{solid_color}_{gradient_h}_{gradient_v}_{target_w}x{target_h}_blur_color".encode()).hexdigest()
            blurred_path = os.path.join(thumb_dir, f"blur_{m}.png")
            composite.save(blurred_path, "PNG")
            return blurred_path

        os.makedirs(thumb_dir, exist_ok=True)

        m = hashlib.md5(f"{img_path}_{target_w}x{target_h}_{wallpaper_effect_scope}_{solid_color}_{gradient_h}_{gradient_v}_{color_mode}_blur".encode()).hexdigest()
        blurred_path = os.path.join(thumb_dir, f"blur_{m}.jpg")
        if os.path.exists(blurred_path):
            return blurred_path

        try:
            img = ImageEngine._open_image_safe(img_path).convert('RGB')
            composite = ImageEngine.apply_fit(
                img, target_w, target_h,
                wallpaper_effect_scope=wallpaper_effect_scope,
                solid_color=solid_color,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                color_mode=color_mode,
                image_effect=image_effect
            )
            composite.save(blurred_path, "JPEG", quality=85)
            return blurred_path
        except Exception as e:
            log_event(f"Error generando blurred thumbnail: {e}",
                origin="IMG_ENG", level="WARN", reason="LIBRARY")
            return None

    @staticmethod
    def _calculate_fit_size(img_w, img_h, target_w, target_h):
        """
        Calcula el tamaño de una imagen para encajar completamente dentro
        del área destino manteniendo su proporción.
        """
        img_ratio = img_w / img_h
        target_ratio = target_w / target_h

        if img_ratio > target_ratio:
            new_w = target_w
            new_h = math.ceil(target_w / img_ratio)
        else:
            new_h = target_h
            new_w = math.ceil(target_h * img_ratio)

        new_w = min(new_w, target_w)
        new_h = min(new_h, target_h)

        return new_w, new_h

    @staticmethod
    def _calculate_cover_size(img_w, img_h, target_w, target_h):
        """
        Calcula el tamaño de una imagen para cubrir completamente
        el área destino manteniendo su proporción.
        """
        img_ratio = img_w / img_h
        target_ratio = target_w / target_h

        if img_ratio > target_ratio:
            new_h = target_h
            new_w = int(target_h * img_ratio)
        else:
            new_w = target_w
            new_h = int(target_w / img_ratio)

        return new_w, new_h

    @staticmethod
    def _create_blur_background(img, target_w, target_h):
        """
        Genera una capa de fondo desenfocada a partir de la propia imagen.
        Se escala para cubrir completamente el área destino y se aplica un filtro gaussiano.
        Devuelve la imagen desenfocada y su posición de pegado (bg_x, bg_y).
        """
        img_w, img_h = img.size
        bg_w, bg_h = ImageEngine._calculate_cover_size(img_w, img_h, target_w, target_h)

        bg_img = img.resize((bg_w, bg_h), Image.Resampling.NEAREST)
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=40))

        bg_x = (target_w - bg_w) // 2
        bg_y = (target_h - bg_h) // 2
        return bg_img, bg_x, bg_y

    # ==========================================================
    # MODOS DE ASPECTO (estáticos + distribuidor)
    # ==========================================================

    @staticmethod
    def apply_fit(img, target_w, target_h, wallpaper_effect_scope="blur",
        solid_color="#000000", gradient_h=None, gradient_v=None,
        color_mode="solid_color", image_effect="none"):
        """
        Ajusta la imagen para que quepa dentro del rectángulo destino manteniendo la proporción.
        Los huecos se rellenan según wallpaper_effect_scope: "blur" o "color".
        Si la imagen llena exactamente el contenedor, no se genera capa de fondo.
        """
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Aplicar efecto de imagen (sepia, bw, none) a la imagen original
        img_effected = ImageEngine.apply_image_effect(img, image_effect)

        img_w, img_h = img_effected.size

        # Calcular dimensiones de la imagen nítida (manteniendo proporción)
        new_w, new_h = ImageEngine._calculate_fit_size(img_w, img_h, target_w, target_h)

        # Determinar si hay huecos (la imagen no llena completamente)
        has_gaps = (new_w < target_w) or (new_h < target_h)

        container = Image.new('RGB', (target_w, target_h), (0, 0, 0))

        if has_gaps:
            # --- Pintar capa de fondo solo si hay huecos ---
            if wallpaper_effect_scope == "blur":
                bg_img, bg_x, bg_y = ImageEngine._create_blur_background(img_effected, target_w, target_h)
                container.paste(bg_img, (bg_x, bg_y))
            elif wallpaper_effect_scope == "color":
                if color_mode == "solid_color":
                    bg_surface = Image.new('RGB', (target_w, target_h), solid_color)
                elif color_mode in ("gradient_h", "gradient_v"):
                    bg_surface = ImageEngine._create_color_surface(
                        target_w, target_h, color_mode, solid_color,
                        gradient_h or ["#000000", "#8D9797"],
                        gradient_v or ["#000000", "#8D9797"]
                    )
                else:
                    bg_surface = Image.new('RGB', (target_w, target_h), solid_color)
                container.paste(bg_surface, (0, 0))

        # --- Pegar siempre la imagen nítida encima ---
        img_fit = img_effected.resize((new_w, new_h), Image.Resampling.LANCZOS)
        fit_x = (target_w - new_w) // 2
        fit_y = (target_h - new_h) // 2
        container.paste(img_fit, (fit_x, fit_y))

        return container

    @staticmethod
    def apply_zoom(img, target_w, target_h, image_effect="none"):
        """
        Escala la imagen para llenar completamente el rectángulo destino,
        manteniendo la proporción y recortando el excedente.
        """
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img = ImageEngine.apply_image_effect(img, image_effect)
        img_w, img_h = img.size
        new_w, new_h = ImageEngine._calculate_cover_size(img_w, img_h, target_w, target_h)

        img_scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        right = left + target_w
        bottom = top + target_h
        img_cropped = img_scaled.crop((left, top, right, bottom))

        return img_cropped

    @staticmethod
    def apply_stretched(img, target_w, target_h, image_effect="none"):
        """
        Escala la imagen para que ocupe exactamente el rectángulo destino,
        sin mantener la proporción (la imagen se deforma si es necesario).
        """
        if img.mode != 'RGB':
            img = img.convert('RGB')
        # Aplicar el efecto de imagen (fuera del condicional para que siempre se ejecute)
        img = ImageEngine.apply_image_effect(img, image_effect)

        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    @staticmethod
    def apply_image_effect(img, effect, intensity=100):
        """
        Aplica un efecto visual a la imagen.
        effect: "none", "sepia", "bw"
        intensity: 0-100, controla la intensidad del efecto.
        Devuelve una nueva imagen PIL con el efecto aplicado.
        """
        if effect == "none" or effect is None:
            return img
        elif effect == "bw":
            bw_img = img.convert('L').convert('RGB')
            if intensity < 100:
                return Image.blend(img, bw_img, intensity / 100.0)
            return bw_img
        elif effect == "sepia":
            # Fórmula de sepia genuino optimizada con NumPy
            original = img.copy() if intensity < 100 else None
            arr = np.array(img, dtype=np.float64)
            sepia = np.empty(arr.shape, dtype=np.uint8)

            sepia[:,:,0] = np.clip(0.393*arr[:,:,0] + 0.769*arr[:,:,1] + 0.189*arr[:,:,2], 0, 255)
            sepia[:,:,1] = np.clip(0.349*arr[:,:,0] + 0.686*arr[:,:,1] + 0.168*arr[:,:,2], 0, 255)
            sepia[:,:,2] = np.clip(0.272*arr[:,:,0] + 0.534*arr[:,:,1] + 0.131*arr[:,:,2], 0, 255)

            sepia_img = Image.fromarray(sepia)

            if intensity < 100:
                return Image.blend(original, sepia_img, intensity / 100.0)
            return sepia_img
        else:
            return img

    @staticmethod
    def _process_preview_image(img, target_w, target_h, mode,
        wallpaper_effect_scope="blur", solid_color="#000000", gradient_h=None,
        gradient_v=None, color_mode="solid_color", image_effect="none"):
        """
        Procesa una imagen para preview reduciendo primero a la geometría
        necesaria y aplicando después los efectos visuales.
        """
        if img.mode != 'RGB':
            img = img.convert('RGB')

        img_w, img_h = img.size

        if mode == "zoom":
            new_w, new_h = ImageEngine._calculate_cover_size(img_w, img_h, target_w, target_h)

            img_scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            right = left + target_w
            bottom = top + target_h

            img_cropped = img_scaled.crop((left, top, right, bottom))

            return ImageEngine.apply_image_effect(img_cropped, image_effect)

        if mode == "stretched":
            img_scaled = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            return ImageEngine.apply_image_effect(img_scaled, image_effect)

        # FIT y fallback
        new_w, new_h = ImageEngine._calculate_fit_size(img_w, img_h, target_w, target_h)
        has_gaps = (new_w < target_w) or (new_h < target_h)

        container = Image.new('RGB', (target_w, target_h), (0, 0, 0))

        if has_gaps:
            if wallpaper_effect_scope == "blur":
                bg_w, bg_h = ImageEngine._calculate_cover_size(img_w, img_h, target_w, target_h)
                bg_img = img.resize((bg_w, bg_h), Image.Resampling.NEAREST)
                bg_img = ImageEngine.apply_image_effect(bg_img, image_effect)
                bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=40))

                bg_x = (target_w - bg_w) // 2
                bg_y = (target_h - bg_h) // 2
                container.paste(bg_img, (bg_x, bg_y))

            elif wallpaper_effect_scope == "color":
                bg_surface = ImageEngine._create_color_surface(
                    target_w, target_h,
                    color_mode, solid_color,
                    gradient_h, gradient_v
                )
                container.paste(bg_surface, (0, 0))

        img_fit = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        img_fit = ImageEngine.apply_image_effect(img_fit, image_effect)

        fit_x = (target_w - new_w) // 2
        fit_y = (target_h - new_h) // 2
        container.paste(img_fit, (fit_x, fit_y))

        return container

    def apply_spanned(self, img_path, canvas_w, canvas_h, mode,
        color_mode="blur", solid_color="#000000", gradient_h=None,
        gradient_v=None, wallpaper_effect_scope="blur", image_effect="none"):
        """
        Aplica el modo real (mode) al canvas completo definido por
        canvas_w y canvas_h (obtenidos previamente de MonitorManager).

        Args:
            img_path (str):       Ruta de la imagen maestra.
            canvas_w (int):       Ancho del canvas total (bounding box real o escalado).
            canvas_h (int):       Alto del canvas total.
            mode (str):           Modo real a aplicar: "fit", "zoom", "stretched".
            color_mode (str):     Modo de color para relleno (solo si mode == "fit").
            solid_color (str):    Color hexadecimal (solo si color_mode == "solid_color").
            gradient_h (list):    Degradado horizontal [inicio, fin] (solo si color_mode == "gradient_h").
            gradient_v (list):    Degradado vertical [inicio, fin] (solo si color_mode == "gradient_v").

        Returns:
            tuple: (ruta del thumbnail maestro, imagen PIL procesada).
                   La imagen PIL es None si se reutiliza la caché.
                   Devuelve None si falla.
        """
        if canvas_w <= 0 or canvas_h <= 0:
            return None

        thumb_dir = self.ch.thumbnails_dir
        os.makedirs(thumb_dir, exist_ok=True)
        m = hashlib.md5(f"{img_path}_{canvas_w}x{canvas_h}_spanned_{mode}_{wallpaper_effect_scope}_{image_effect}_{color_mode}_{solid_color}_{gradient_h}_{gradient_v}".encode()).hexdigest()
        output_path = os.path.join(thumb_dir, f"spanned_{m}.jpg")

        if os.path.exists(output_path):
            return output_path, None

        with ImageEngine._open_image_safe(img_path) as img:
            processed = ImageEngine._process_preview_image(
                img, canvas_w, canvas_h,
                mode=mode,
                wallpaper_effect_scope=wallpaper_effect_scope,
                solid_color=solid_color,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                color_mode=color_mode,
                image_effect=image_effect
            )

        processed.save(output_path, "JPEG", quality=85)
        return output_path, processed

    def paint_monitors_thumbnails(self, fixed_widget, layout_data, img_source,
        wallpaper_mode, spanned_enabled, color_tuple, wallpaper_effect_scope="blur",
        image_effect="none", layout_info=None, spanned_source_hash=None):
        """
        Pinta las miniaturas dentro de los EventBox existentes en fixed_widget.
        NO añade nuevos widgets si ya existe uno (modifica el existente).
        """
        if spanned_enabled:
            # --- MODO DISTRIBUIDO (SPANNED) ---

            # 1. Calcular el bounding box del layout escalado
            canvas_min_x = min(d['x'] for d in layout_data)
            canvas_min_y = min(d['y'] for d in layout_data)
            canvas_w = max(d['x'] + d['w'] for d in layout_data) - canvas_min_x
            canvas_h = max(d['y'] + d['h'] for d in layout_data) - canvas_min_y

            if canvas_w <= 0 or canvas_h <= 0:
                return

            # 2. Preferir el origen de la imagen Spanned realmente aplicada.
            #    Puede proceder de cualquier monitor mediante Drag & Drop.
            spanned_hash = get_spanned_reference_hash(layout_info) if layout_info else None
            master_path = None

            if spanned_source_hash in img_source:
                entry = img_source[spanned_source_hash]

                if isinstance(entry, dict):
                    path = entry.get("path", "")
                    active = entry.get("active", True)
                else:
                    path = entry if entry else ""
                    active = True

                if active and path and os.path.exists(path):
                    master_path = path

            # Sin un origen válido, conservar la prioridad histórica
            # del monitor de referencia y los fallbacks existentes.
            if not master_path and spanned_hash:
                entry = img_source.get(spanned_hash, {})

                if isinstance(entry, dict):
                    path = entry.get("path", "")
                    active = entry.get("active", True)
                else:
                    path = entry if entry else ""
                    active = True

                if active and path and os.path.exists(path):
                    master_path = path

            # En activación reactiva, el monitor de referencia puede no tener
            # imagen válida y ImageSelectionEngine haber reutilizado la de otro
            # monitor compatible. Reproducir exactamente ese desempate.
            if not master_path and layout_info:
                physical_w, physical_h = get_total_canvas_geometry(layout_info)
                canvas_orientation = "horizontal" if physical_w >= physical_h else "vertical"
                compatible_hashes = []

                for m_hash, info in layout_info.items():
                    if m_hash == spanned_hash:
                        continue

                    monitor_orientation = info.get("orientation")
                    if monitor_orientation not in ("horizontal", "vertical"):
                        monitor_orientation = "horizontal" if info.get("width", 0) >= info.get("height", 0) else "vertical"

                    if monitor_orientation == canvas_orientation:
                        compatible_hashes.append(m_hash)

                for m_hash in sorted(compatible_hashes):
                    entry = img_source.get(m_hash, {})

                    if isinstance(entry, dict):
                        path = entry.get("path", "")
                        active = entry.get("active", True)
                    else:
                        path = entry if entry else ""
                        active = True

                    if active and path and os.path.exists(path):
                        master_path = path
                        break

            # Fallback defensivo: usar la primera imagen activa disponible.
            if not master_path:
                for entry in img_source.values():
                    if isinstance(entry, dict):
                        path = entry.get("path", "")
                        active = entry.get("active", True)
                    else:
                        path = entry if entry else ""
                        active = True

                    if active and path and os.path.exists(path):
                        master_path = path
                        break

            if not master_path:
                # Sin imagen maestra: limpiar todos los EventBox.
                for eb in fixed_widget.get_children():
                    if isinstance(eb, Gtk.EventBox):
                        child = eb.get_child()
                        if child is not None:
                            eb.remove(child)
                return

            # 3. Generar el thumbnail maestro spanned usando apply_spanned
            spanned_result = self.apply_spanned(
                master_path, canvas_w, canvas_h, mode=wallpaper_mode,
                color_mode=color_tuple[1], solid_color=color_tuple[2],
                gradient_h=color_tuple[3], gradient_v=color_tuple[4],
                wallpaper_effect_scope=wallpaper_effect_scope,
                image_effect=image_effect
            )
            if not spanned_result:
                return

            spanned_thumb, processed = spanned_result

            # 4. Usar la imagen en memoria si acaba de generarse;
            #    cargar el thumbnail solo si procede de caché.
            if processed is not None:
                full_pixbuf = self._pil_to_pixbuf(processed)
            else:
                full_pixbuf = GdkPixbuf.Pixbuf.new_from_file(spanned_thumb)

            # 5. Recortar la porción correspondiente a cada monitor
            for eb in fixed_widget.get_children():
                if not isinstance(eb, Gtk.EventBox):
                    continue
                m_hash = getattr(eb, 'm_hash', None)
                if not m_hash:
                    continue
                monitor_data = next((d for d in layout_data if d['hash'] == m_hash), None)
                if not monitor_data:
                    continue
                x, y, w, h = monitor_data['x'], monitor_data['y'], monitor_data['w'], monitor_data['h']
                rel_x = x - canvas_min_x
                rel_y = y - canvas_min_y
                inner_w = w - 2
                inner_h = h - 2
                if rel_x + 2 >= 0 and rel_y + 2 >= 0 and inner_w > 0 and inner_h > 0:
                    subpixbuf = full_pixbuf.new_subpixbuf(rel_x + 2, rel_y + 2, inner_w, inner_h)
                    child = eb.get_child()
                    if child is None:
                        child = Gtk.Image()
                        eb.add(child)
                    if not child.get_style_context().has_class("monitor-image"):
                        child.get_style_context().add_class("monitor-image")
                    child.set_from_pixbuf(subpixbuf)
                    child.queue_resize()
                    child.show()
        else:
            # Modo fit
            for eb in fixed_widget.get_children():
                if not isinstance(eb, Gtk.EventBox):
                    continue
                m_hash = getattr(eb, 'm_hash', None)
                if not m_hash:
                    continue
                monitor_data = next((d for d in layout_data if d['hash'] == m_hash), None)
                if not monitor_data:
                    continue
                w, h = monitor_data['w'], monitor_data['h']
                entry = img_source.get(m_hash, {})
                if not isinstance(entry, dict):
                    entry = {"path": entry if entry else "", "active": True}
                active = entry.get("active", True)

                # Hijo actual del EventBox (puede ser marcador de posición)
                child = eb.get_child()
                if not active:
                    inner_w = w - 2
                    inner_h = h - 2
                    color_surface = ImageEngine._create_color_surface(
                        inner_w, inner_h, color_tuple[1], color_tuple[2], color_tuple[3], color_tuple[4]
                    )
                    pixbuf = self._pil_to_pixbuf(color_surface)
                    if pixbuf:
                        if child is None:
                            child = Gtk.Image()
                            eb.add(child)
                        if not child.get_style_context().has_class("monitor-image"):
                            child.get_style_context().add_class("monitor-image")
                        child.set_from_pixbuf(pixbuf)
                        child.queue_resize()
                        child.show()
                elif entry.get("path"):
                    img_path = entry["path"]
                    inner_w = w - 2
                    inner_h = h - 2

                    thumb_dir = self.ch.thumbnails_dir
                    os.makedirs(thumb_dir, exist_ok=True)
                    intensity = 100  # Valor temporal hasta implementar el slider
                    m = hashlib.md5(f"{img_path}_{inner_w}x{inner_h}_{wallpaper_mode}_{wallpaper_effect_scope}_{image_effect}_{intensity}_{color_tuple[1]}_{color_tuple[2]}_{color_tuple[3]}_{color_tuple[4]}".encode()).hexdigest()
                    blurred_path = os.path.join(thumb_dir, f"blur_{m}.jpg")

                    if os.path.exists(blurred_path):
                        if child is None:
                            child = Gtk.Image()
                            eb.add(child)
                        if not child.get_style_context().has_class("monitor-image"):
                            child.get_style_context().add_class("monitor-image")
                        child.set_from_file(blurred_path)
                        child.queue_resize()
                        child.show()
                        continue

                    with ImageEngine._open_image_safe(img_path) as img_obj:
                        processed = ImageEngine._process_preview_image(
                            img_obj, inner_w, inner_h,
                            mode=wallpaper_mode,
                            wallpaper_effect_scope=wallpaper_effect_scope,
                            solid_color=color_tuple[2],
                            gradient_h=color_tuple[3],
                            gradient_v=color_tuple[4],
                            color_mode=color_tuple[1],
                            image_effect=image_effect
                        )
                    # Guardar miniatura con dimensiones reducidas
                    processed.save(blurred_path, "JPEG", quality=85)
                    pixbuf = self._pil_to_pixbuf(processed)

                    if child is None:
                        child = Gtk.Image()
                        eb.add(child)
                    if not child.get_style_context().has_class("monitor-image"):
                        child.get_style_context().add_class("monitor-image")
                    child.set_from_pixbuf(pixbuf)
                    child.queue_resize()
                    child.show()
                else:
                    # Monitor activo sin imagen: dejar vacío (eliminar cualquier hijo existente)
                    if child is not None:
                        eb.remove(child)

        fixed_widget.queue_draw()

    def _pil_to_pixbuf(self, pil_image):
        """Convierte una imagen PIL directamente a GdkPixbuf.Pixbuf en memoria."""
        if pil_image.mode not in ('RGB', 'RGBA'):
            pil_image = pil_image.convert('RGB')

        width, height = pil_image.size
        has_alpha = pil_image.mode == 'RGBA'
        channels = 4 if has_alpha else 3
        pixels = GLib.Bytes.new(pil_image.tobytes())

        return GdkPixbuf.Pixbuf.new_from_bytes(pixels, GdkPixbuf.Colorspace.RGB,
            has_alpha, 8, width, height, width * channels)
