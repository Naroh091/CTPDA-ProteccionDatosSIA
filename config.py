# -*- coding: utf-8 -*-

# Aplicación para la protección de datos en Sistemas IA
# Copyright (C) 2025-2026 Consejo de Transparencia y Protección de Datos de Andalucía
#
#
#
# Este programa se distribuye bajo la Licencia Pública de la Unión Europea,
# versión 1.2 (EUPL v1.2), disponible en:
# https://eupl.eu/1.2/es/
#
# Este programa se distribuye con la esperanza de que sea útil,
# pero SIN NINGUNA GARANTÍA; sin siquiera la garantía implícita de
# COMERCIABILIDAD o APTITUD PARA UN PROPÓSITO PARTICULAR.
# Consulte el texto completo de la licencia en el archivo LICENCIA.txt.

# Variables y constantes de configuración
URL_ACTUALIZACION = "CAMBIAR_CLAVE_EXPORTACION_SEGURA"
VERSION_APLICACION = "v1.0"
VERSION_BD_INICIAL = "1.0"

# ============================================================================
# CREDENCIALES - VALORES DE EJEMPLO (NO USAR EN PRODUCCIÓN)
# ============================================================================
# IMPORTANTE: Estos son valores de ejemplo para desarrollo.
# Para compilar el ejecutable de producción, se utilizan los módulos
# compilados con Cython que contienen las credenciales reales.
#
# Si desea desplegar su propia instancia, genere sus propias claves seguras.
# ============================================================================
CONTRASENA_EXPORTACION = "CAMBIAR_CLAVE_EXPORTACION_SEGURA"

# ============================================================================
# PROTECCIÓN DE BASE DE DATOS - CLAVE DE OFUSCACIÓN
# ============================================================================
# Esta clave se usa para:
# 1. Ofuscar el header de SQLite (prevenir apertura con SQLiteStudio)
# 2. Ofuscar el checksum embebido (para verificación de integridad)
#
# IMPORTANTE: NO cambiar esta clave una vez en producción.
# Si cambias la clave, las bases de datos protegidas anteriormente
# no se podrán abrir.
# ============================================================================
DB_OBFUSCATION_KEY = "CAMBIAR_CLAVE_EXPORTACION_SEGURA"

# ============================================================================
# CONFIGURACIÓN DE PERSISTENCIA DE BASE DE DATOS
# ============================================================================
# Controla cuándo se persisten los cambios de la BD temporal a la ofuscada
# MODO_PERSISTENCIA puede ser:
# - "MANUAL": Solo al llamar explícitamente a sync_to_disk()
# - "AUTO": Automáticamente cada INTERVALO_PERSISTENCIA segundos
# - "TRANSACCION": Después de cada commit de SQLAlchemy
# ============================================================================
MODO_PERSISTENCIA = "TRANSACCION"  # "MANUAL", "AUTO" o "TRANSACCION"
INTERVALO_PERSISTENCIA = 30  # Segundos entre sincronizaciones automáticas (solo para modo AUTO)

# ============================================================================
# CONFIGURACIÓN DEL SISTEMA DE HEARTBEAT
# ============================================================================
# Controla los tiempos del sistema de detección de cierre del navegador
# para evitar procesos huérfanos.
#
# PARÁMETROS DEL CLIENTE (steps.js - navegador):
# - HEARTBEAT_INTERVAL: Frecuencia de envío de heartbeat al servidor (ms)
# - NAVIGATION_TIMEOUT: Tiempo para distinguir navegación interna de cierre (ms)
#
# PARÁMETROS DEL SERVIDOR (app.py):
# - TIMEOUT_HEARTBEAT: DESACTIVADO - No se cierra por timeout
# - INTERVALO_VERIFICACION: Frecuencia de comprobación del servidor (seg)
#
# MODO ACTUAL: SOLO MONITOREO
# Los heartbeats se envían para monitoreo/debugging pero NO cierran la aplicación.
# La aplicación solo se cierra cuando el usuario cierra la pestaña/navegador
# (mediante señal explícita con sendBeacon a /heartbeat_end)
# ============================================================================
HEARTBEAT_INTERVAL = 3000      # milisegundos
NAVIGATION_TIMEOUT = 2000      # milisegundos
# TIMEOUT_HEARTBEAT = 30       # DESACTIVADO - No se usa (sin cierre por timeout)
INTERVALO_VERIFICACION = 3     # segundos

# ============================================================================
# CONFIGURACIÓN DE VISIBILIDAD DE JUSTIFICACIONES EN RIESGOS
# ============================================================================
# Controla la visibilidad de las columnas de justificación en el formulario
# de riesgos y en la exportación CSV.
# 0 = Ocultar la columna (pero los datos se siguen guardando)
# 1 = Mostrar la columna
# ============================================================================
VER_JUST_IMPACTO = 0       # Visibilidad de "Justif. Impacto"
VER_JUST_PROB = 0          # Visibilidad de "Justif. Probabilidad"
