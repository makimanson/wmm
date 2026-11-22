#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""WMM - Consulta, caché y descarga de fondos online.

Las funciones de búsqueda y las reglas de seguridad específicas pertenecen
al bloque de su proveedor. Sólo se comparten mecanismos realmente comunes.
Las operaciones de red son bloqueantes y se ejecutan fuera del hilo GTK.
"""

import json
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import math
import threading
import time
import urllib.error

from collections import deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from PIL import Image
from debug_logger import log_event

# ==========================================================
# INFRAESTRUCTURA COMÚN
# ==========================================================
# Límites de transferencia globales; cada proveedor conserva sus
# propias reglas de URL, formato, caché y descarga.
USER_AGENT = "WMM-Manager/2.0"
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
MAX_ORIGINAL_BYTES = 128 * 1024 * 1024

class OnlineProviderRateLimited(RuntimeError):
    """El proveedor o su cuota local impiden nuevas solicitudes."""

def _publish_online_thumbnail(content, target):
    """Publica una miniatura de forma atómica.

    La validación de URL y los límites de descarga pertenecen al proveedor.
    """
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", dir=os.path.dirname(target), delete=False) as output:
            temporary = output.name
            output.write(content)

        os.replace(temporary, target)

    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

    return target

def _read_online_api_key(path):
    """Lee una clave API desde su archivo, sin almacenarla en WMM."""
    try:
        with open(path, "r", encoding="utf-8-sig") as key_file:
            key = key_file.read().strip()
    except (OSError, UnicodeError) as error:
        raise RuntimeError(
            "No se pudo leer el archivo de clave API"
        ) from error

    if not key or "\n" in key or "\r" in key:
        raise ValueError("El archivo de clave API no contiene una clave válida")

    return key

def _resolve_online_api_key(provider, api_key_files):
    """Resuelve la clave personal del proveedor; None si no está configurada."""
    if not isinstance(api_key_files, dict):
        return None

    path = api_key_files.get(provider)
    if not path:
        return None

    if not isinstance(path, str):
        raise ValueError(f"Ruta de clave API inválida: {provider}")

    return _read_online_api_key(path)

# ==========================================================
# PROVEEDOR: WALLHAVEN
# ==========================================================
API_URL = "https://wallhaven.cc/api/v1/search"

# Margen preventivo respecto a las 45 llamadas API/min publicadas.
# Las transferencias de imágenes no consumen este contador.
_WALLHAVEN_API_LIMIT = 40
_WALLHAVEN_API_WINDOW = 60
_wallhaven_api_calls = deque()
_wallhaven_blocked_until = 0.0
_wallhaven_lock = threading.Lock()

def _wallhaven_page_url(item):
    """Devuelve la página informativa, nunca la URL del original."""
    image_id = item.get("id")
    url = item.get("url")

    if (not isinstance(image_id, str)
            or not re.fullmatch(r"[A-Za-z0-9]{6}", image_id)
            or not isinstance(url, str)):
        return None

    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None

    if (parsed.scheme != "https"
            or parsed.netloc != "wallhaven.cc"
            or parsed.path != f"/w/{image_id}"
            or parsed.query or parsed.fragment):
        return None

    return url

def _wallhaven_retry_delay(value):
    """Interpreta Retry-After en segundos o como fecha HTTP."""
    if value:
        try:
            return max(1, int(value))
        except (ValueError, TypeError):
            try:
                deadline = parsedate_to_datetime(value)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
                return max(1, math.ceil(seconds))
            except (ValueError, TypeError, OverflowError):
                pass

    # Política conservadora propia cuando Wallhaven no comunica plazo.
    return 60


def _wallhaven_open(request, timeout, *, api=False):
    """Centraliza la cuota API y las restricciones HTTP de Wallhaven."""
    global _wallhaven_blocked_until

    with _wallhaven_lock:
        now = time.monotonic()

        # Un 429 en cualquiera de sus servidores protege el proveedor completo.
        if now < _wallhaven_blocked_until:
            remaining = math.ceil(_wallhaven_blocked_until - now)
            raise OnlineProviderRateLimited(
                f"Wallhaven temporalmente limitado: {remaining} s")

        if api:
            while (_wallhaven_api_calls
                    and now - _wallhaven_api_calls[0] >= _WALLHAVEN_API_WINDOW):
                _wallhaven_api_calls.popleft()

            if len(_wallhaven_api_calls) >= _WALLHAVEN_API_LIMIT:
                remaining = math.ceil(
                    _WALLHAVEN_API_WINDOW - (now - _wallhaven_api_calls[0]))
                raise OnlineProviderRateLimited(
                    f"Cuota preventiva de API Wallhaven alcanzada: {remaining} s")

            # Contabilizar antes de iniciar la solicitud evita carreras.
            _wallhaven_api_calls.append(now)

    try:
        return urllib.request.urlopen(request, timeout=timeout)

    except urllib.error.HTTPError as error:
        if error.code != 429:
            raise

        delay = _wallhaven_retry_delay(error.headers.get("Retry-After"))

        with _wallhaven_lock:
            _wallhaven_blocked_until = max(
                _wallhaven_blocked_until, time.monotonic() + delay)

        raise OnlineProviderRateLimited(
            f"Wallhaven ha limitado las solicitudes: {delay} s") from error

# Búsqueda, filtros y normalización de los resultados.
def search_wallhaven(text, orientation="any", aspect="any", page=1, api_key=None):
    """
    Consulta una página pública o autenticada de Wallhaven.

    Devuelve resultados normalizados y metadatos de paginación.
    Las operaciones de red deben ejecutarse fuera del hilo GTK.
    """
    params = {
        "q": text.strip(),
        "purity": "100",
        "sorting": "relevance" if text.strip() else "date_added",
        "page": page,
    }

    if aspect != "any":
        width, height = map(int, aspect.split(":"))

        # Una proporción horizontal se invierte cuando el usuario
        # solicita expresamente imágenes verticales.
        if orientation == "vertical" and width > height:
            width, height = height, width

        params["ratios"] = f"{width}x{height}"

    url = API_URL + "?" + urllib.parse.urlencode(params)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    if api_key:
        headers["X-API-Key"] = api_key

    request = urllib.request.Request(url, headers=headers)

    with _wallhaven_open(request, timeout=15, api=True) as response:
        payload = json.load(response)

    results = []

    for item in payload.get("data", []):
        width = int(item.get("dimension_x", 0))
        height = int(item.get("dimension_y", 0))

        if width <= 0 or height <= 0:
            continue

        if orientation == "horizontal" and width <= height:
            continue

        if orientation == "vertical" and height <= width:
            continue

        image_id = item.get("id", "")
        thumbs = item.get("thumbs", {})
        thumbnail_url = thumbs.get("small", "")
        preferred_url = thumbs.get("original", "")

        if not re.fullmatch(r"[A-Za-z0-9]{6}", image_id):
            continue

        # La URL procede de una API externa: únicamente aceptamos
        # miniaturas HTTPS servidas por el dominio previsto.
        parsed = urllib.parse.urlsplit(thumbnail_url)
        if parsed.scheme != "https" or parsed.hostname != "th.wallhaven.cc":
            continue

        # La alternativa es opcional; una URL no válida conserva small.
        try:
            preferred = urllib.parse.urlsplit(preferred_url)
            if preferred.scheme != "https" or preferred.netloc != "th.wallhaven.cc":
                preferred_url = ""
        except (TypeError, ValueError):
            preferred_url = ""

        # Conservar la URL del original para su descarga posterior.
        # Una URL inválida no debe impedir mostrar la miniatura.
        original_url = item.get("path", "")
        try:
            original = urllib.parse.urlsplit(original_url)
            if original.scheme != "https" or original.netloc != "w.wallhaven.cc":
                original_url = ""
        except (TypeError, ValueError):
            original_url = ""

        results.append({
            "id": image_id,
            "provider": "wallhaven",
            "url": item.get("url", ""),
            "thumbnail_url": thumbnail_url,
            "thumbnail_preferred_url": preferred_url,
            "original_url": original_url,
            "width": width,
            "height": height,
        })

    return results, payload.get("meta", {})


# Caché de miniaturas del proveedor.
def cache_wallhaven_thumbnail(item, cache_dir):
    """Prefiere la miniatura original; small permanece como respaldo."""
    target_dir = os.path.join(cache_dir, "online", "wallhaven")
    os.makedirs(target_dir, exist_ok=True)

    image_id = item["id"]
    variants = []

    preferred_url = item.get("thumbnail_preferred_url")
    if preferred_url:
        variants.append((preferred_url, os.path.join(target_dir, f"{image_id}-original.jpg")))

    variants.append((item["thumbnail_url"], os.path.join(target_dir, f"{image_id}.jpg")))

    for index, (url, target) in enumerate(variants):
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            return target

        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with _wallhaven_open(request, timeout=15) as response:
                content = response.read(MAX_THUMBNAIL_BYTES + 1)

            if not content or len(content) > MAX_THUMBNAIL_BYTES:
                raise ValueError(f"Miniatura inválida o demasiado grande: {image_id}")

            # Mantener la publicación atómica, sin conversión ni verificación Pillow.
            return _publish_online_thumbnail(content, target)

        except OnlineProviderRateLimited:
            raise  # Respetar el bloqueo del proveedor; no insistir con más peticiones.
        except (OSError, ValueError):
            if index == len(variants) - 1:
                raise

def _wallhaven_original_filename(item):
    """Valida la identidad de Wallhaven y devuelve su nombre canónico."""
    image_id = item.get("id", "")
    original_url = item.get("original_url", "")

    if (item.get("provider") != "wallhaven"
            or not re.fullmatch(r"[A-Za-z0-9]{6}", image_id)):
        raise ValueError("Resultado Wallhaven inválido")

    try:
        parsed = urllib.parse.urlsplit(original_url)
    except (TypeError, ValueError) as error:
        raise ValueError("URL de imagen original inválida") from error

    extension = os.path.splitext(parsed.path)[1].lower()
    if (parsed.scheme != "https" or parsed.netloc != "w.wallhaven.cc"
            or extension not in (".jpg", ".jpeg", ".png")):
        raise ValueError("URL de imagen original no admitida")

    return f"wallhaven-{image_id}{extension}"

# Descarga de originales con verificación, temporal y progreso por bytes.
def download_wallhaven_original(item, destination_dir, on_progress=None):
    """Descarga el original de Wallhaven al directorio indicado.

    Operación bloqueante: debe ejecutarse fuera del hilo GTK.
    No registra la imagen en Sources ni sincroniza la biblioteca.
    """
    original_url = item.get("original_url", "")
    filename = _wallhaven_original_filename(item)
    extension = os.path.splitext(filename)[1].lower()

    if not destination_dir or not os.path.isdir(destination_dir):
        raise ValueError("Directorio de destino Online no disponible")

    # El identificador del proveedor permite reconocer descargas repetidas.
    target = os.path.join(destination_dir, filename)

    if os.path.exists(target):
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            return target
        raise FileExistsError(f"El destino ya existe y no es válido: {target}")

    request = urllib.request.Request(original_url, headers={ "User-Agent": USER_AGENT, })

    temporary = None
    try:
        with _wallhaven_open(request, timeout=30) as response:
            # Comprobar también el destino efectivo de una redirección.
            final_url = urllib.parse.urlsplit(response.geturl())
            if final_url.scheme != "https" or final_url.netloc != "w.wallhaven.cc":
                raise ValueError("Redirección fuera del servidor de originales")

            # El temporal no tiene extensión de imagen para evitar que
            # una sincronización lo incorpore antes de completarse.
            with tempfile.NamedTemporaryFile(
                    mode="wb", dir=destination_dir,
                    prefix=".wmm-online-", suffix=".part",
                    delete=False) as output:
                temporary = output.name
                total = 0

                # El tamaño puede ser desconocido si el servidor no lo anuncia.
                content_length = response.headers.get("Content-Length")
                expected_bytes = (int(content_length)
                    if content_length and content_length.isdecimal()
                    else None)

                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break

                    total += len(chunk)
                    if total > MAX_ORIGINAL_BYTES:
                        raise ValueError("La imagen supera el tamaño máximo permitido")

                    output.write(chunk)
                    if on_progress is not None:
                        on_progress(total, expected_bytes)

        if total == 0:
            raise ValueError("El servidor devolvió un archivo vacío")

        # Verificar el formato sin modificar ni recomprimir el original.
        with Image.open(temporary) as image:
            expected = "PNG" if extension == ".png" else "JPEG"
            if image.format != expected:
                raise ValueError("El contenido no coincide con el formato original")
            image.verify()

        # No sustituir una descarga que ya hubiera quedado registrada.
        if os.path.exists(target):
            if os.path.isfile(target) and os.path.getsize(target) > 0:
                return target
            raise FileExistsError(f"El destino ya existe y no es válido: {target}")

        os.replace(temporary, target)
        temporary = None
        return target

    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

# ==========================================================
# PROVEEDOR: ALPHA CODERS
# ==========================================================
_ALPHACODERS_API_URL = "https://api.alphacoders.com/4.0"
_ALPHACODERS_KEY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "wmm_platform", "shell", "common", "wmm-alphacoders.key"
)

def _alphacoders_default_key():
    """Lee la clave pública predeterminada de Alpha Coders."""
    return _read_online_api_key(_ALPHACODERS_KEY_FILE)

def _alphacoders_image_url_valid(url):
    """Acepta únicamente imágenes HTTPS de los servidores de Alpha Coders."""
    if not isinstance(url, str):
        return False

    try:
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.port is None
            and parsed.username is None
            and re.fullmatch(
                r"images\d*\.alphacoders\.com", parsed.hostname or ""
            ) is not None
        )
    except ValueError:
        return False

def search_alphacoders(text, orientation="any", aspect="any", page=1, api_key=None):
    """Consulta una página de Alpha Coders y normaliza sus fondos.

    Una búsqueda vacía utiliza /contents; una búsqueda con texto utiliza
    /search. La API no devuelve last_page: una página completa permite
    solicitar la siguiente, sin realizar consultas anticipadas.
    """
    if not isinstance(page, int) or not 1 <= page <= 200:
        raise ValueError("Página Alpha Coders fuera del intervalo permitido")

    term = text.strip()

    if len(term) > 128:
        raise ValueError("Alpha Coders admite búsquedas de hasta 128 caracteres")

    params = {
        "auth": api_key if api_key is not None else _alphacoders_default_key(),
        "content_type": "wallpaper",
        "page": page,
    }

    endpoint = "search" if term else "contents"
    if term:
        params["term"] = term
    else:
        params["sort"] = "newest"

    # La API utiliza intervalos numéricos para las proporciones.
    # Una pequeña tolerancia contempla resoluciones equivalentes.
    requested_ratio = None
    if aspect != "any":
        width_ratio, height_ratio = map(int, aspect.split(":"))
        requested_ratio = width_ratio / height_ratio
        params["min_ratio"] = f"{requested_ratio - 0.01:.4f}"
        params["max_ratio"] = f"{requested_ratio + 0.01:.4f}"

    url = (f"{_ALPHACODERS_API_URL}/{endpoint}?"
           f"{urllib.parse.urlencode(params)}")

    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise OnlineProviderRateLimited(
                "Alpha Coders ha alcanzado su límite de solicitudes"
            ) from None
        detail = error.read(512).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Alpha Coders: error HTTP {error.code}: {detail}") from None

    if not isinstance(payload, dict) or payload.get("success") is not True:
        error_code = (payload.get("error", "respuesta inválida")
                      if isinstance(payload, dict) else "respuesta inválida")
        raise RuntimeError(f"Alpha Coders: {error_code}")

    contents = payload.get("contents")
    if not isinstance(contents, list):
        raise ValueError("Alpha Coders devolvió una lista de resultados inválida")

    results = []

    for content in contents:
        if not isinstance(content, dict):
            continue

        if content.get("content_type") != "wallpaper":
            continue

        try:
            width = int(content.get("width", 0))
            height = int(content.get("height", 0))
        except (TypeError, ValueError):
            continue

        if width <= 0 or height <= 0:
            continue

        if orientation == "horizontal" and width <= height:
            continue
        if orientation == "vertical" and height <= width:
            continue

        if (requested_ratio is not None
                and abs(width / height - requested_ratio) > 0.01):
            continue

        image_id = str(content.get("content_id", ""))
        thumbnail_url = content.get("thumb", "")
        original_url = content.get("src", "")

        if not image_id.isdecimal():
            continue

        if (not _alphacoders_image_url_valid(thumbnail_url)
                or not _alphacoders_image_url_valid(original_url)):
            continue

        results.append({
            "id": image_id,
            "provider": "alphacoders",
            "url": content.get("url_page", ""),
            "thumbnail_url": thumbnail_url,
            "original_url": original_url,
            "width": width,
            "height": height,
        })

    # Alpha Coders no publica last_page. No anticipamos la página siguiente:
    # sólo la habilitamos cuando la actual llega al máximo de 30 elementos.
    last_page = page + 1 if len(contents) == 30 and page < 200 else page

    return results, {
        "current_page": page,
        "last_page": last_page,
    }

# Caché de miniaturas del proveedor.
def cache_alphacoders_thumbnail(item, cache_dir):
    """Descarga una miniatura de Alpha Coders, sin descargar el original."""
    target_dir = os.path.join(cache_dir, "online", "alphacoders")
    os.makedirs(target_dir, exist_ok=True)

    image_id = item["id"]
    thumbnail_url = item["thumbnail_url"]
    extension = os.path.splitext(urllib.parse.urlsplit(thumbnail_url).path)[1].lower()
    target = os.path.join(target_dir, f"{image_id}{extension}")

    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return target

    request = urllib.request.Request(thumbnail_url, headers={
        "User-Agent": USER_AGENT,
    })

    with urllib.request.urlopen(request, timeout=15) as response:
        content = response.read(MAX_THUMBNAIL_BYTES + 1)

    if not content or len(content) > MAX_THUMBNAIL_BYTES:
        raise ValueError(f"Miniatura inválida o demasiado grande: {image_id}")

    # Publicación atómica, sin conversión ni verificación Pillow.
    return _publish_online_thumbnail(content, target)

def _alphacoders_original_filename(item):
    """Valida la identidad de Alpha Coders y devuelve su nombre canónico."""
    image_id = item.get("id", "")
    original_url = item.get("original_url", "")

    if (item.get("provider") != "alphacoders"
            or not re.fullmatch(r"[0-9]+", image_id)):
        raise ValueError("Resultado Alpha Coders inválido")

    if not _alphacoders_image_url_valid(original_url):
        raise ValueError("URL de imagen original inválida")

    extension = os.path.splitext(
        urllib.parse.urlsplit(original_url).path)[1].lower()

    if extension not in (".jpg", ".jpeg", ".png"):
        raise ValueError("Formato de imagen original no admitido")

    return f"alphacoders-{image_id}{extension}"

# Descarga de originales con verificación, temporal y progreso por bytes.
def download_alphacoders_original(item, destination_dir, on_progress=None):
    """Descarga el original de Alpha Coders al directorio indicado.

    Operación bloqueante: debe ejecutarse fuera del hilo GTK.
    No registra la imagen en Sources ni sincroniza la biblioteca.
    """
    original_url = item.get("original_url", "")
    filename = _alphacoders_original_filename(item)
    extension = os.path.splitext(filename)[1].lower()

    if not destination_dir or not os.path.isdir(destination_dir):
        raise ValueError("Directorio de destino Online no disponible")

    target = os.path.join(destination_dir, filename)

    if os.path.exists(target):
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            return target
        raise FileExistsError(f"El destino ya existe y no es válido: {target}")

    request = urllib.request.Request(original_url, headers={
        "User-Agent": USER_AGENT,
    })

    temporary = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if not _alphacoders_image_url_valid(response.geturl()):
                raise ValueError("Redirección fuera del servidor de originales")

            with tempfile.NamedTemporaryFile(
                    mode="wb", dir=destination_dir,
                    prefix=".wmm-online-", suffix=".part",
                    delete=False) as output:
                temporary = output.name
                total = 0

                content_length = response.headers.get("Content-Length")
                expected_bytes = (int(content_length)
                    if content_length and content_length.isdecimal()
                    else None)

                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break

                    total += len(chunk)
                    if total > MAX_ORIGINAL_BYTES:
                        raise ValueError("La imagen supera el tamaño máximo permitido")

                    output.write(chunk)
                    if on_progress is not None:
                        on_progress(total, expected_bytes)

        if total == 0:
            raise ValueError("El servidor devolvió un archivo vacío")

        # Verificar sin modificar ni recomprimir el original.
        with Image.open(temporary) as image:
            expected = "PNG" if extension == ".png" else "JPEG"
            if image.format != expected:
                raise ValueError("El contenido no coincide con el formato original")
            image.verify()

        if os.path.exists(target):
            if os.path.isfile(target) and os.path.getsize(target) > 0:
                return target
            raise FileExistsError(f"El destino ya existe y no es válido: {target}")

        os.replace(temporary, target)
        temporary = None
        return target

    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

def _alphacoders_page_url(item):
    """Devuelve la página informativa, nunca la URL del original."""
    image_id = item.get("id")
    url = item.get("url")

    if (item.get("provider") != "alphacoders"
            or not isinstance(image_id, str)
            or not re.fullmatch(r"[0-9]+", image_id)
            or not isinstance(url, str)):
        return None

    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None

    # La API proporciona la URL de la página; validamos su destino
    # y estructura sin exigir que su ID coincida con content_id.
    if (parsed.scheme != "https"
            or parsed.netloc != "wall.alphacoders.com"
            or parsed.path != "/big.php"
            or not re.fullmatch(r"i=[0-9]+", parsed.query)
            or parsed.fragment):
        return None

    return url

# ==========================================================
# INTERFAZ COMÚN PARA LA VISTA ONLINE
# ==========================================================

# Las funciones específicas anteriores conservan la autoridad sobre cada API.
# Este registro desacopla la vista GTK de cada implementación.
# Sólo se registran proveedores operativos.
_ONLINE_PROVIDERS = {
    "wallhaven": {
        "name": "Wallhaven",
        "website": "https://wallhaven.cc/",
        "logo": "wallhaven.png",
        "search": search_wallhaven,
        "cache": cache_wallhaven_thumbnail,
        "download": download_wallhaven_original,
        "filename": _wallhaven_original_filename,
        "page": _wallhaven_page_url,
    },
    "alphacoders": {
        "name": "Alpha Coders",
        "website": "https://wall.alphacoders.com/",
        "logo": "alpha_coders.png",
        "search": search_alphacoders,
        "cache": cache_alphacoders_thumbnail,
        "download": download_alphacoders_original,
        "filename": _alphacoders_original_filename,
        "page": _alphacoders_page_url,
    },
}

def get_online_providers():
    """Devuelve los identificadores y nombres que ofrece el selector Online."""
    return [(key, entry["name"]) for key, entry in _ONLINE_PROVIDERS.items()]

def get_online_provider_identity(provider):
    """Publica la identidad del proveedor sin exponer su implementación."""
    entry = _ONLINE_PROVIDERS.get(provider)
    if entry is None:
        return None

    return {
        "name": entry["name"],
        "website": entry.get("website"),
        "logo": entry.get("logo"),
    }

def read_online_api_key(path):
    """Expone al Panel la lectura validada, sin duplicar su lógica."""
    return _read_online_api_key(path)

def online_provider_available(provider):
    """Una búsqueda conjunta sólo utiliza proveedores con buscador real."""
    return provider == "any" or bool(_ONLINE_PROVIDERS.get(provider, {}).get("search"))

def get_online_source_page(item):
    """Consulta al proveedor una página informativa validada."""
    if not isinstance(item, dict):
        return None

    entry = _ONLINE_PROVIDERS.get(item.get("provider"), {})
    resolver = entry.get("page")
    return resolver(item) if resolver else None

def search_wallpapers(text, orientation, aspect, provider, cache_dir,
    on_result, on_error, is_cancelled=None, page=1, api_key_files=None,
    provider_pages=None):
    """Busca y guarda miniaturas remotas sin conocer GTK.

    Publica cada resultado cuando su miniatura está en caché para conservar
    la presentación progresiva. Los callbacks se ejecutan en el hilo llamante;
    la vista es responsable de pasar sus cambios visuales a GLib.idle_add.

    Devuelve los datos de cierre que ya consume OnlineSection, o None si la
    búsqueda quedó sustituida o falló su único proveedor seleccionado.
    """
    if not online_provider_available(provider):
        raise ValueError(f"Proveedor Online no disponible: {provider}")

    targets = (provider,)
    if provider == "any":
        targets = tuple(key for key, entry in _ONLINE_PROVIDERS.items()
            if entry["search"] and (provider_pages is None or key in provider_pages))

    total = 0
    failures = 0
    failed_searches = 0
    last_error = None
    next_page = None
    # Any conserva exclusivamente las páginas pendientes de cada proveedor.
    next_pages = {}

    for source in targets:
        if is_cancelled is not None and is_cancelled():
            return None

        entry = _ONLINE_PROVIDERS[source]
        source_page = provider_pages[source] if provider_pages is not None else page

        try:
            api_key = _resolve_online_api_key(source, api_key_files)
            results, meta = entry["search"](
                text, orientation, aspect, page=source_page, api_key=api_key)
        except Exception as error:
            failed_searches += 1

            # Un fallo no consume la página pendiente de ese proveedor.
            if provider == "any":
                next_pages[source] = source_page

            # Una página adicional nunca debe borrar la galería existente.
            on_error(entry["name"], str(error),
                provider == "any" or page > 1)
            if provider != "any":
                return None
            continue

        # Cada proveedor conserva su cursor. Las búsquedas individuales
        # mantienen el contrato original de una única página siguiente.
        if isinstance(meta, dict):
            try:
                current_page = int(meta.get("current_page", source_page))
                last_page = int(meta.get("last_page", current_page))
                if current_page == source_page and last_page > current_page:
                    if provider == "any":
                        next_pages[source] = current_page + 1
                    else:
                        next_page = current_page + 1
            except (TypeError, ValueError):
                pass

        total += len(results)

        for item in results:
            if is_cancelled is not None and is_cancelled():
                return None

            try:
                path = entry["cache"](item, cache_dir)

            except OnlineProviderRateLimited as error:
                failures += 1
                last_error = f"{entry['name']} {item['id']}: {error}"
                on_error(entry["name"], str(error), True)

                # No insistir con las demás miniaturas de este proveedor.
                # En Any, otros proveedores independientes podrán continuar.
                break

            except Exception as error:
                failures += 1
                last_error = f"{entry['name']} {item['id']}: {error}"
                continue

            # La disponibilidad de Download depende de la implementación
            # real del proveedor, no de una condición de marca en GTK.
            item["provider_name"] = entry["name"]
            item["downloadable"] = entry["download"] is not None
            on_result(item, path)

    # Un fallo completo al ampliar resultados no consume la página pendiente.
    if page > 1 and failed_searches == len(targets):
        return None

    if provider == "any":
        next_page = next_pages or None

    name = "Any" if provider == "any" else _ONLINE_PROVIDERS[provider]["name"]
    return name, total, failures, last_error, failed_searches == len(targets), next_page

def get_online_original_filename(item):
    """Consulta al proveedor el nombre reconocible de su original."""
    entry = _ONLINE_PROVIDERS.get(item.get("provider"), {})
    filename = entry.get("filename")
    return filename(item) if filename else None

def download_online_original(item, destination_dir, on_progress=None):
    """Dirige la descarga al proveedor sin alterar su validación propia."""
    entry = _ONLINE_PROVIDERS.get(item.get("provider"), {})
    download = entry.get("download")
    if download is None:
        raise ValueError("No existe descargador de originales para este proveedor")
    return download(item, destination_dir, on_progress=on_progress)

def promote_online_preview_original(image_path, cache_dir, online_dir):
    """Incorpora a Sources/Online un original temporal ya descargado.

    Devuelve la ruta definitiva. Las imágenes ajenas a la caché temporal
    permanecen intactas. No realiza descargas ni modifica la configuración.
    """
    if not image_path:
        return image_path

    temp_dir = os.path.realpath(os.path.join(cache_dir, "online", "temp"))
    source = os.path.realpath(image_path)

    # Sólo los originales temporales de WMM necesitan incorporación.
    if os.path.dirname(source) != temp_dir:
        return image_path

    if not online_dir or not os.path.isdir(online_dir):
        raise ValueError("Directorio Online de Sources no disponible")

    target = os.path.join(online_dir, os.path.basename(source))

    # El archivo definitivo tiene prioridad sobre cualquier copia temporal.
    if os.path.exists(target):
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            log_event(f"Original Online ya incorporado: {os.path.basename(target)}",
                origin="ONLINE_SECT", level="INFO", reason="LIBRARY")
            return target
        raise FileExistsError(f"El destino ya existe y no es válido: {target}")

    if not os.path.isfile(source) or os.path.getsize(source) == 0:
        raise FileNotFoundError(f"Original temporal Online no disponible: {source}")

    temporary = None
    try:
        # /temp y Sources pueden estar en volúmenes distintos.
        # Publicar primero como .part evita que Sources indexe una copia parcial.
        with open(source, "rb") as original:
            with tempfile.NamedTemporaryFile(
                    mode="wb", dir=online_dir,
                    prefix=".wmm-online-", suffix=".part",
                    delete=False) as output:
                temporary = output.name
                shutil.copyfileobj(original, output, 1024 * 1024)

        # Si otro proceso publicó el original durante la copia, conservarlo.
        if os.path.exists(target):
            if os.path.isfile(target) and os.path.getsize(target) > 0:
                return target
            raise FileExistsError(f"El destino ya existe y no es válido: {target}")

        os.replace(temporary, target)
        temporary = None

        # El original definitivo ya está publicado. Un fallo al limpiar
        # la caché no debe invalidar una incorporación completada.
        try:
            os.unlink(source)
        except OSError as error:
            log_event(f"No se pudo retirar temporal Online: {error}",
                origin="ONLINE_SECT", level="WARN", reason="LIBRARY")

        size_bytes = os.path.getsize(target)
        log_event(f"Original Online incorporado: {os.path.basename(target)} "
            f"· {size_bytes} bytes ({size_bytes / 1048576:.2f} MiB)",
            origin="ONLINE_SECT", level="INFO", reason="LIBRARY")

        return target

    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

# ==========================================================
# OPERACIONES COMUNES: ORIGINALES PARA PREVISUALIZACIÓN
# ==========================================================

def resolve_online_original_for_preview(item, cache_dir, online_dir=None):
    """Resuelve el original local para una composición temporal.

    Online tiene prioridad sobre /temp. Sólo se solicita al proveedor
    cuando el original no está disponible en ninguna ubicación.
    """
    filename = get_online_original_filename(item)
    if not filename:
        raise ValueError("El proveedor no dispone de un original identificable")

    # 1. Imagen incorporada anteriormente a Sources/Online.
    if online_dir and os.path.isdir(online_dir):
        path = os.path.join(online_dir, filename)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            log_event(f"Original Online reutilizado (Sources): {item['provider']}/{item['id']}",
                origin="ONLINE_SECT", level="INFO", reason="LIBRARY")
            return path

    # 2. Imagen descargada durante una prueba anterior.
    temp_dir = os.path.join(cache_dir, "online", "temp")
    path = os.path.join(temp_dir, filename)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        log_event(f"Original Online reutilizado (/temp): {item['provider']}/{item['id']}",
            origin="ONLINE_SECT", level="INFO", reason="LIBRARY")
        return path

    # 3. Original desconocido localmente: una única descarga.
    os.makedirs(temp_dir, exist_ok=True)

    log_event(f"Iniciando descarga Online: {item['provider']}/{item['id']}",
        origin="ONLINE_SECT", level="INFO", reason="LIBRARY")

    path = download_online_original(item, temp_dir)
    size_bytes = os.path.getsize(path)

    log_event(
        f"Original Online descargado: {item['provider']}/{item['id']} "
        f"· {size_bytes} bytes ({size_bytes / 1048576:.2f} MiB)",
        origin="ONLINE_SECT", level="INFO", reason="LIBRARY")

    return path
