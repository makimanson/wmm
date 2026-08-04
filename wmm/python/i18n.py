#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WMM
----------------------------
i18n.py – Módulo centralizado de traducciones.
Inicializa y proporciona el acceso a las traducciones propias de WMM.
"""
import gettext

# Dominio de la aplicación
_APP_DOMAIN = None
# Ruta de traducciones
_LOCALE_DIR = None

def initialize(platform):
    """
    Inicializa el sistema de traducciones a partir de una instancia
    de PlatformManager.
    """
    global _APP_DOMAIN, _LOCALE_DIR

    _APP_DOMAIN = platform.app_domain
    _LOCALE_DIR = platform.locale_dir
    _bind()

def _bind():
    """
    Vincula el dominio de traducción con su directorio.
    """
    if _APP_DOMAIN and _LOCALE_DIR:
        gettext.bindtextdomain(_APP_DOMAIN, _LOCALE_DIR)
        gettext.textdomain(_APP_DOMAIN)

def _(text):
    """
    Devuelve la traducción de 'text' según el dominio de WMM.
    Si no existe traducción, devuelve el texto original.
    """
    if _APP_DOMAIN:
        return gettext.dgettext(_APP_DOMAIN, text)
    return text

def N_(text):
    """
    Marca una cadena como traducible para los extractores de .po.
    No realiza la traducción en tiempo de ejecución; simplemente
    devuelve el texto original.
    """
    return text
