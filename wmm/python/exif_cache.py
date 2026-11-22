#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
"""
WMM - Wallpaper Multi-Monitor Manager

exif_cache.py – Metadatos descriptivos derivados de image_cache.json.

La autoridad sobre qué imágenes existen es image_cache.json. Esta caché
conserva sólo EXIF útiles para WMM, identificados por ruta y mtime_ns.
No interviene en clasificación, renderizado, rotación ni miniaturas.
"""

import json
import os
import hashlib
import tempfile
import math
import re
from contextlib import contextmanager
from xml.etree import ElementTree
from PIL import Image, ExifTags

# Versión de la proyección persistida: EXIF + XMP normalizados.
EXIF_CACHE_SCHEMA = 4

IFD0_TAGS = {
    270, 271, 272, 274, 305, 306, 315, 33432,
    40091, 40092, 40093, 40094, 40095
}
EXIF_TAGS = {36867, 36868, 36880, 36881, 36882, 42036}
XP_TAGS = {40091, 40092, 40093, 40094, 40095}

EXIF_ORIENTATIONS = {
    1: "Normal", 2: "Espejo horizontal", 3: "Girada 180°",
    4: "Espejo vertical", 5: "Espejo horizontal y giro 270°",
    6: "Giro 90° horario", 7: "Espejo horizontal y giro 90°",
    8: "Giro 90° antihorario"
}

def normalize(tag, value):
    """Acepta sólo valores legibles; recupera textos EXIF mal codificados."""
    if isinstance(value, bytes):
        if tag not in XP_TAGS:
            return None
        try:
            value = value.decode("utf-16-le")
        except UnicodeDecodeError:
            return None

    if isinstance(value, str):
        value = value.strip("\x00 \t\r\n")
        # Algunos productores escriben UTF-8 interpretado como Latin-1/CP1252.
        # Reparar sólo conversiones válidas que reduzcan las marcas de mojibake.
        markers = ("Ã", "Â", "Ä")
        original_score = sum(value.count(marker) for marker in markers)
        if original_score:
            for encoding in ("latin-1", "cp1252"):
                try:
                    repaired = value.encode(encoding).decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
                repaired_score = sum(repaired.count(marker) for marker in markers)
                if repaired_score < original_score and not any(
                        ord(char) < 32 and char not in "\t\r\n" for char in repaired):
                    value = repaired
                    break
        return value or None

    if tag == 274 and isinstance(value, int):
        return EXIF_ORIENTATIONS.get(value)

    if isinstance(value, (int, float, bool)):
        return value
    return None

def decimal_gps(value, ref):
    """Convierte DMS a grados decimales sin consultar servicios externos."""
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        return None
    if not isinstance(ref, str) or ref.strip("\x00 ").upper() not in ("N", "S", "E", "W"):
        return None
    ref = ref.strip("\x00 ").upper()
    try:
        degrees, minutes, seconds = (float(part) for part in value)
        result = degrees + minutes / 60 + seconds / 3600
        return round(-result if ref in ("S", "W") else result, 8)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None

# ----------------------------------------------------------
# XMP: equivalencias con los campos existentes de WMM
# ----------------------------------------------------------
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_XML = "{http://www.w3.org/XML/1998/namespace}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_EXIF = "{http://ns.adobe.com/exif/1.0/}"
_TIFF = "{http://ns.adobe.com/tiff/1.0/}"
_EXIFEX = "{http://cipa.jp/exif/1.0/}"
_IPTC_EXT = "{http://iptc.org/std/Iptc4xmpExt/2008-02-29/}"

# Las claves de destino son las del catálogo WMM.
# No se establecen todavía prioridades frente a EXIF/IPTC.
XMP_FIELDS = {
    _DC + "title": "IFD0.XPTitle",
    _DC + "description": "IFD0.ImageDescription",
    _EXIF + "UserComment": "IFD0.XPComment",
    _DC + "subject": "IFD0.XPSubject",

    _DC + "creator": "IFD0.XPAuthor",
    _DC + "rights": "IFD0.Copyright",
    _TIFF + "Artist": "IFD0.Artist",

    _TIFF + "Make": "IFD0.Make",
    _TIFF + "Model": "IFD0.Model",
    _EXIFEX + "LensModel": "Exif.LensModel",
    _TIFF + "Software": "IFD0.Software",

    _EXIF + "DateTimeOriginal": "Exif.DateTimeOriginal",
    _EXIF + "DateTimeDigitized": "Exif.DateTimeDigitized",
    _TIFF + "DateTime": "IFD0.DateTime",
    _EXIF + "GPSDateStamp": "GPSInfo.GPSDateStamp",
}

def _xmp_value(node):
    """Extrae texto de propiedades XMP simples y contenedores RDF."""
    for kind in ("Alt", "Seq", "Bag"):
        container = node.find(_RDF + kind)
        if container is None:
            continue

        items = [item for item in container.findall(_RDF + "li")
                 if "".join(item.itertext()).strip()]
        if not items:
            return None

        if kind == "Alt":
            # Preferir el valor general frente a traducciones particulares.
            item = next((item for item in items
                if item.get(_XML + "lang") == "x-default"), items[0])
            return "".join(item.itertext()).strip()

        if kind == "Seq":
            return "".join(items[0].itertext()).strip()

        # Las palabras clave pueden contener varios valores.
        return ", ".join(dict.fromkeys(
            "".join(item.itertext()).strip() for item in items))

    return (node.text or "").strip() or None

# ----------------------------------------------------------
# XMP: geolocalización de captura
# Normaliza GPS y LocationCreated a las claves existentes
# de WMM. LocationShown no se interpreta como captura.
# ----------------------------------------------------------
def _xmp_gps_coordinate(value, latitude):
    """Convierte grados, minutos, segundos y hemisferio a decimal."""
    if not isinstance(value, str):
        return None

    text = value.strip().upper()
    direction = text[-1:] if text[-1:] in "NSEW" else ""
    if direction:
        text = text[:-1].strip()

    if direction and direction not in ("NS" if latitude else "EW"):
        return None

    parts = [item for item in re.split(r"[,\s]+", text) if item]
    if not 1 <= len(parts) <= 3 or any(
            re.fullmatch(r"[+-]?\d+(?:\.\d+)?", part) is None for part in parts):
        return None

    degrees = float(parts[0])
    minutes = float(parts[1]) if len(parts) > 1 else 0.0
    seconds = float(parts[2]) if len(parts) > 2 else 0.0

    if not (0 <= minutes < 60 and 0 <= seconds < 60):
        return None

    position = abs(degrees) + minutes / 60 + seconds / 3600
    if position > (90 if latitude else 180):
        return None

    if direction and degrees < 0 and direction in "NE":
        return None

    negative = degrees < 0 or direction in "SW"
    return round(-position if negative else position, 8)

def _xmp_gps_altitude(value, reference):
    """Convierte la altitud racional XMP y su referencia vertical."""
    if not isinstance(value, str):
        return None

    try:
        parts = value.strip().split("/")
        if len(parts) > 2:
            return None

        altitude = float(parts[0])
        if len(parts) == 2:
            altitude /= float(parts[1])

        if not math.isfinite(altitude):
            return None
    except (ValueError, ZeroDivisionError, OverflowError):
        return None

    if reference not in (None, "0", "1"):
        return None

    return round(-abs(altitude) if reference == "1" else altitude, 2)

def _xmp_location_created(root):
    """Recupera país, región y localidad del lugar de captura."""
    fields = {
        _IPTC_EXT + "CountryName": "Geolocation.country",
        _IPTC_EXT + "ProvinceState": "Geolocation.region",
        _IPTC_EXT + "City": "Geolocation.city",
    }

    location = next(root.iter(_IPTC_EXT + "LocationCreated"), None)
    if location is None:
        return {}

    selected = {}

    for node in location.iter():
        key = fields.get(node.tag)
        if key:
            value = _xmp_value(node)
            if value:
                selected.setdefault(key, value)

        for name, value in node.attrib.items():
            key = fields.get(name)
            if key and value.strip():
                selected.setdefault(key, value.strip())

    return selected

def _xmp_geolocation(root):
    """Extrae GPS XMP y nombres del lugar de captura."""
    fields = {
        _EXIF + "GPSLatitude": "GPSInfo.Latitude",
        _EXIF + "GPSLongitude": "GPSInfo.Longitude",
        _EXIF + "GPSAltitude": "GPSInfo.AltitudeMeters",
        _EXIF + "GPSAltitudeRef": "_altitude_ref",
    }

    raw = {}

    # Solo propiedades de las descripciones RDF principales.
    # Excluye GPS anidados en estructuras de lugares mostrados.
    for rdf in root.iter(_RDF + "RDF"):
        for description in rdf.findall(_RDF + "Description"):
            for name, value in description.attrib.items():
                key = fields.get(name)
                if key and value.strip():
                    raw.setdefault(key, value.strip())

            for node in description:
                key = fields.get(node.tag)
                if key:
                    value = _xmp_value(node)
                    if value:
                        raw.setdefault(key, value)

    selected = _xmp_location_created(root)

    for key, latitude in (
            ("GPSInfo.Latitude", True),
            ("GPSInfo.Longitude", False)):
        value = _xmp_gps_coordinate(raw.get(key), latitude)
        if value is not None:
            selected[key] = value

    altitude = _xmp_gps_altitude(
        raw.get("GPSInfo.AltitudeMeters"), raw.get("_altitude_ref"))
    if altitude is not None:
        selected["GPSInfo.AltitudeMeters"] = altitude

    return selected

def read_xmp(image):
    """
    Extrae propiedades XMP admitidas por WMM desde una imagen PIL abierta.

    Mantiene los valores separados de EXIF hasta establecer las prioridades.
    No modifica la imagen ni escribe en la caché.
    """
    raw = image.info.get("xmp") or image.info.get("XML:com.adobe.xmp")
    if not isinstance(raw, (bytes, str)) or not raw:
        return {}

    try:
        root = ElementTree.fromstring(raw)
    except (ElementTree.ParseError, ValueError, TypeError):
        return {}

    selected = {}

    for description in root.iter(_RDF + "Description"):
        # XMP admite propiedades como atributos de rdf:Description.
        for key, value in description.attrib.items():
            field = XMP_FIELDS.get(key)
            if field and value.strip():
                selected.setdefault(field, value.strip())

        # Y también como elementos con contenido simple o RDF.
        for property_node in description:
            field = XMP_FIELDS.get(property_node.tag)
            if field and field not in selected:
                value = _xmp_value(property_node)
                if value:
                    selected[field] = value

    # Incorporar la geolocalización XMP del lugar de captura.
    selected.update(_xmp_geolocation(root))
    return selected

# ----------------------------------------------------------
# METADATOS: prioridad por campo y límites de contenido
# XMP prevalece en los textos editoriales; EXIF conserva
# los datos técnicos. Solo se retiene un valor por campo.
# ----------------------------------------------------------
_XMP_EDITORIAL_FIELDS = {
    "IFD0.XPTitle", "IFD0.ImageDescription", "IFD0.XPComment",
    "IFD0.XPSubject", "IFD0.XPAuthor", "IFD0.Copyright", "IFD0.Artist",
}

_METADATA_TEXT_LIMITS = {
    "IFD0.ImageDescription": 160,
    "IFD0.XPComment": 160,
    "IFD0.XPSubject": 120,
    "IFD0.Copyright": 120,
}

def _merge_xmp_metadata(groups, xmp):
    """Resuelve equivalencias y limita el texto antes de persistirlo."""
    for full_key, value in xmp.items():
        if "." not in full_key:
            continue

        family, field = full_key.split(".", 1)
        if family not in ("IFD0", "Exif", "GPSInfo", "Geolocation"):
            continue

        # Admitir textos descriptivos y valores GPS numéricos.
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            continue

        # Las coordenadas se resuelven juntas, nunca por separado.
        if family == "GPSInfo" and field in ("Latitude", "Longitude"):
            continue

        selected = groups.setdefault(family, {})
        if full_key in _XMP_EDITORIAL_FIELDS or field not in selected:
            selected[field] = value

    # GPS: conservar la pareja EXIF completa; si falta alguna
    # coordenada, utilizar la pareja XMP completa disponible.
    gps = groups.get("GPSInfo", {})
    latitude = xmp.get("GPSInfo.Latitude")
    longitude = xmp.get("GPSInfo.Longitude")

    if (isinstance(latitude, (int, float)) and
            isinstance(longitude, (int, float)) and
            not (isinstance(gps.get("Latitude"), (int, float)) and
                 isinstance(gps.get("Longitude"), (int, float)))):
        groups.setdefault("GPSInfo", {}).update({
            "Latitude": latitude,
            "Longitude": longitude
        })

    # Limitar también los textos EXIF, no solamente los XMP.
    # Un campo extenso no debe dominar la composición del wallpaper.
    for family, values in groups.items():
        for field, value in list(values.items()):
            if not isinstance(value, str):
                continue

            text = " ".join(value.split())
            if not text:
                del values[field]
                continue

            limit = _METADATA_TEXT_LIMITS.get(f"{family}.{field}", 96)
            if len(text) > limit:
                text = text[:limit - 1].rstrip() + "…"
            values[field] = text

    return {family: values for family, values in groups.items() if values}

def read_exif(path):
    """Extrae EXIF y XMP admitidos por WMM, con prioridades por campo."""
    with Image.open(path) as image:
        exif = image.getexif()
        if not exif:
            return _merge_xmp_metadata({}, read_xmp(image))

        groups = {}
        ifd0 = {}
        for tag, value in exif.items():
            if tag in IFD0_TAGS:
                normalized = normalize(tag, value)
                if normalized is not None:
                    ifd0[ExifTags.TAGS.get(tag, str(tag))] = normalized
        if ifd0:
            groups["IFD0"] = ifd0

        # Los IFD secundarios no son obligatorios; un directorio defectuoso
        # no invalida la información legible recuperada de IFD0.
        try:
            data = exif.get_ifd(ExifTags.IFD.Exif)
            selected = {}
            for tag, value in data.items():
                if tag in EXIF_TAGS:
                    normalized = normalize(tag, value)
                    if normalized is not None:
                        selected[ExifTags.TAGS.get(tag, str(tag))] = normalized
            if selected:
                groups["Exif"] = selected
        except (KeyError, ValueError, TypeError, OSError):
            pass

        try:
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            if gps:
                selected = {}
                latitude = decimal_gps(gps.get(2), gps.get(1))
                longitude = decimal_gps(gps.get(4), gps.get(3))
                if latitude is not None:
                    selected["Latitude"] = latitude
                if longitude is not None:
                    selected["Longitude"] = longitude
                if gps.get(6) is not None:
                    try:
                        altitude_ref = gps.get(5, 0)
                        if isinstance(altitude_ref, bytes):
                            altitude_ref = altitude_ref[0] if altitude_ref else 0
                        selected["AltitudeMeters"] = round(
                            float(gps[6]) * (-1 if altitude_ref == 1 else 1), 2)
                    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
                        pass
                if isinstance(gps.get(29), str):
                    selected["GPSDateStamp"] = gps[29]
                if selected:
                    groups["GPSInfo"] = selected
        except (KeyError, ValueError, TypeError, OSError):
            pass

        return _merge_xmp_metadata(groups, read_xmp(image))

def enrich_geolocation(entries, geodata_path):
    """Completa sólo ubicaciones GPS pendientes, sin alterar los EXIF."""
    pending = []
    for entry in entries.values():
        gps = entry.get("GPSInfo")
        if "Geolocation" in entry or not isinstance(gps, dict):
            continue
        latitude, longitude = gps.get("Latitude"), gps.get("Longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            pending.append((entry, latitude, longitude))

    # Un catálogo sin coordenadas pendientes no debe cargar la base mundial.
    if not pending or not geodata_path or not os.path.isfile(geodata_path):
        return 0

    try:
        from geo_lookup import GeoLookup
        lookup = GeoLookup(geodata_path)
    except (OSError, ValueError, TypeError, KeyError, ImportError) as error:
        print(f"[WMM EXIF] Base geográfica no disponible: {error}", flush=True)
        return 0

    # Varias fotografías pueden compartir exactamente la misma posición GPS.
    resolved = {}
    completed = 0
    for entry, latitude, longitude in pending:
        coordinates = (latitude, longitude)
        if coordinates not in resolved:
            try:
                place = lookup.nearest(latitude, longitude)
            except (ValueError, TypeError, OverflowError):
                continue
            if place is None:
                continue
            resolved[coordinates] = place
        entry["Geolocation"] = resolved[coordinates]
        completed += 1
    return completed

def reconcile_exif_cache(image_cache, output_path, geodata_path=None):
    """
    Reutiliza EXIF por (ruta, mtime_ns) y poda toda ruta ajena a image_cache.

    Se invocará fuera del hilo de UI. La escritura es atómica: una interrupción
    nunca debe sustituir una caché válida por un JSON incompleto.
    """
    old = {}
    if os.path.isfile(output_path):
        with open(output_path, "r", encoding="utf-8") as file:
            old = json.load(file)

    # Una caché anterior requiere una única reconstrucción completa.
    previous_schema = old.pop("__schema__", None)

    # La proyección final contiene exactamente las rutas materializadas.
    # Una imagen sin EXIF útil conserva mtime_ns para evitar releerla.
    current = {}
    materialized_paths = set()
    stats = {"reused": 0, "extracted": 0, "empty": 0, "failed": 0, "removed": 0}
    for folder in image_cache.get("folders", {}).values():
        for orientation in ("h", "v"):
            for entry in folder.get(orientation, []):
                if not isinstance(entry, list) or len(entry) < 4:
                    continue
                path, mtime_ns = entry[0], entry[3]
                if not isinstance(path, str) or not isinstance(mtime_ns, int) or path in current:
                    continue

                materialized_paths.add(path)
                previous = old.get(path)
                if (previous_schema == EXIF_CACHE_SCHEMA and isinstance(previous, dict)
                        and previous.get("mtime_ns") == mtime_ns):
                    current[path] = previous
                    stats["reused"] += 1
                    continue

                # El original pudo cambiar o desaparecer desde el último Sync.
                # No almacenar EXIF si ya no corresponden a ese mtime_ns.
                try:
                    if os.stat(path).st_mtime_ns != mtime_ns:
                        stats["failed"] += 1
                        continue
                    groups = read_exif(path)
                    if os.stat(path).st_mtime_ns != mtime_ns:
                        stats["failed"] += 1
                        continue
                except (OSError, ValueError, TypeError, SyntaxError):
                    stats["failed"] += 1
                    continue

                current[path] = {"mtime_ns": mtime_ns, **groups}
                stats["extracted"] += 1
                if not groups:
                    stats["empty"] += 1

    # La cascada contabiliza sólo imágenes retiradas por image_cache,
    # no lecturas EXIF fallidas de imágenes todavía materializadas.
    stats["removed"] = len(set(old) - materialized_paths)

    # Los EXIF reutilizados también pueden necesitar geolocalización.
    # Se resuelven después de reconciliar, sin releer las imágenes.
    stats["geolocated"] = enrich_geolocation(current, geodata_path)

    directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=directory,
                prefix=".exif_cache_", suffix=".tmp", delete=False) as file:
            temporary = file.name
            file.write(f'{{\n  "__schema__": {EXIF_CACHE_SCHEMA}')
            for path, entry in current.items():
                file.write(",\n")
                file.write(f"  {json.dumps(path, ensure_ascii=False)}: "
                           f'{{"mtime_ns": {entry["mtime_ns"]}')
                for group in ("IFD0", "Exif", "GPSInfo", "Geolocation"):
                    if entry.get(group):
                        file.write(",\n    " + json.dumps(group) + ": "
                                   + json.dumps(entry[group], ensure_ascii=False))
                file.write("}")
            file.write("\n}\n")
        os.replace(temporary, output_path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

    return stats

@contextmanager
def _exclusive_exif_lock(output_path):
    """Serializa escritores EXIF de distintos procesos sin polling."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        # Mutex de sesión identificado por la ruta de la caché.
        identity = hashlib.sha256(
            os.path.normcase(os.path.abspath(output_path)).encode("utf-8")
        ).hexdigest()

        name = "Local\\WMM-EXIF-" + identity
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        mutex = kernel32.CreateMutexW(None, False, name)
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())

        try:
            status = kernel32.WaitForSingleObject(mutex, 0xFFFFFFFF)
            if status not in (0, 0x80):
                raise OSError(f"No se pudo adquirir mutex EXIF: {status}")

            try:
                yield
            finally:
                kernel32.ReleaseMutex(mutex)
        finally:
            kernel32.CloseHandle(mutex)

    else:
        import fcntl

        with open(output_path + ".lock", "a+b") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)


def reconcile_persisted_cache(data_dir):
    """Lee la caché autoritativa dentro de la exclusión entre procesos."""
    output_path = os.path.join(data_dir, "exif_cache.json")

    with _exclusive_exif_lock(output_path):
        with open(os.path.join(data_dir, "image_cache.json"),
                  encoding="utf-8") as file:
            image_cache = json.load(file)

        # La base geográfica comparte directorio con las cachés,
        # independientemente de la plataforma y de la instalación.
        geodata_path = os.path.join(data_dir, "countries+states+cities.json")
        return reconcile_exif_cache(image_cache, output_path, geodata_path)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python exif_cache.py RUTA_DIRECTORIO_DATA")
    result = reconcile_persisted_cache(sys.argv[1])
    print("EXIF:", result)
