#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
"""
WMM - Consulta geográfica local por coordenadas.

La base contiene puntos de localidades, no límites administrativos.
El resultado indica la localidad más cercana y sus divisiones asociadas,
sin afirmar que las coordenadas pertenezcan a esos territorios.
"""

from bisect import bisect_left
import json
import math

_EARTH_RADIUS_KM = 6371.0088
_RAD = math.pi / 180


def _angular_distance(lat, lon, other_lat, other_lon):
    """Distancia angular Haversine sobre la esfera terrestre."""
    delta_lat = (lat - other_lat) * _RAD
    delta_lon = (lon - other_lon) * _RAD
    h = (math.sin(delta_lat / 2) ** 2
         + math.cos(lat * _RAD) * math.cos(other_lat * _RAD)
         * math.sin(delta_lon / 2) ** 2)
    return 2 * math.asin(min(1.0, math.sqrt(h)))


class GeoLookup:
    """Índice temporal de localidades; no debe mantenerse residente en WMM."""

    def __init__(self, json_path):
        with open(json_path, encoding="utf-8") as file:
            countries = json.load(file)

        locations = []
        for country in countries:
            for state in country.get("states", []):
                for city in state.get("cities", []):
                    locations.append((
                        float(city["latitude"]), float(city["longitude"]),
                        city["name"], state["name"], country["name"],
                        country["iso2"], state.get("iso3166_2")
                    ))

        # Ordenar por latitud permite descartar localidades imposibles
        # sin perder la exactitud de la búsqueda global por distancia.
        locations.sort(key=lambda item: item[0])
        self._locations = locations
        self._latitudes = [item[0] for item in locations]

    def nearest(self, latitude, longitude):
        """Devuelve la localidad más próxima y la distancia a su punto de referencia."""
        lat, lon = float(latitude), float(longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Coordenadas GPS fuera de rango")
        if not self._locations:
            return None

        left = bisect_left(self._latitudes, lat) - 1
        right = left + 1
        best_angle = math.inf
        best = None
        size = len(self._locations)

        while left >= 0 or right < size:
            left_diff = abs(lat - self._latitudes[left]) if left >= 0 else math.inf
            right_diff = abs(lat - self._latitudes[right]) if right < size else math.inf

            # La separación de latitud es una cota inferior de la distancia
            # angular: ninguna localidad restante puede superar al candidato.
            if min(left_diff, right_diff) * _RAD > best_angle:
                break

            index = left if left_diff <= right_diff else right
            if index == left:
                left -= 1
            else:
                right += 1

            place = self._locations[index]
            angle = _angular_distance(lat, lon, place[0], place[1])
            if angle < best_angle:
                best_angle, best = angle, place

        return {
            "city": best[2], "region": best[3], "country": best[4],
            "country_iso2": best[5], "region_iso3166_2": best[6],
            "distance_km": round(best_angle * _EARTH_RADIUS_KM, 3)
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        raise SystemExit("Uso: python geo_lookup.py BASE.json LATITUD LONGITUD")
    lookup = GeoLookup(sys.argv[1])
    print(json.dumps(lookup.nearest(sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=2))
