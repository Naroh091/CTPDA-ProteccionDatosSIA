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

"""
Módulo de verificación de compatibilidad entre versión de aplicación y base de datos.

Este módulo verifica en el arranque de la aplicación si la combinación de
versión de la aplicación (VERSION_APLICACION en config.py) y versión de la
base de datos (almacenada en IA_VALDAT con tipo VERBD, valor ACTUAL) está
expresamente prohibida en la tabla IA_CFGVERSCOMPAT.

PRINCIPIO FUNDAMENTAL: Lo que no está expresamente prohibido, se permite.

Las reglas de bloqueo se definen en IA_CFGVERSCOMPAT con C_TIPO='STARTUP':
- Si existe una regla activa (L_ESTADO=1) con L_COMPATIBLE=0 que coincida
  con la combinación actual de versiones, se bloquea el arranque.
- Si no hay regla que coincida, o todas las que coinciden tienen L_COMPATIBLE=1,
  se permite el arranque.

Uso de campos en las reglas STARTUP (consistente con importación):
- C_VERSION_MIN, C_VERSION_MAX: Rango de versión de la BASE DE DATOS (origen/datos)
- C_VERS_SIST_MIN, C_VERS_SIST_MAX: Rango de versión de la APLICACIÓN (sistema)
- L_COMPATIBLE: 0 = bloquear, 1 = permitir
- C_MENSAJE: Código del mensaje en IA_VALDAT (tipo MSGS)
"""

import config


# ============================================================================
# FUNCIONES DE COMPARACIÓN DE VERSIONES (reutilizadas de importar.py)
# ============================================================================

def comparar_versiones(v1, v2):
    """
    Compara dos versiones en formato semántico simplificado.
    Soporta formatos: 'vX.Y.Z', 'X.Y.Z', 'vX.Y', 'X.Y'
    
    Returns:
        int: -1 si v1 < v2, 0 si v1 == v2, 1 si v1 > v2
    """
    if not v1 or not v2:
        return 0
    
    # Normalizar: eliminar 'v' inicial si existe
    v1_norm = v1.lstrip('vV')
    v2_norm = v2.lstrip('vV')
    
    try:
        parts1 = [int(x) for x in v1_norm.split('.')]
        parts2 = [int(x) for x in v2_norm.split('.')]
    except ValueError:
        if v1_norm < v2_norm:
            return -1
        elif v1_norm > v2_norm:
            return 1
        return 0
    
    # Rellenar con ceros si es necesario
    max_len = max(len(parts1), len(parts2))
    while len(parts1) < max_len:
        parts1.append(0)
    while len(parts2) < max_len:
        parts2.append(0)
    
    for p1, p2 in zip(parts1, parts2):
        if p1 < p2:
            return -1
        elif p1 > p2:
            return 1
    return 0


def version_coincide_patron(version, patron):
    """
    Verifica si una versión coincide con un patrón que puede incluir comodines.
    Soporta comodines: 'X.*' coincide con cualquier versión que empiece por 'X.'
    
    Ejemplos:
        version_coincide_patron('1.5', '1.*') -> True
        version_coincide_patron('2.0', '1.*') -> False
        version_coincide_patron('1.0', '1.0') -> True
    """
    if not patron:
        return True
    if not version:
        return False
    
    # Normalizar
    version_norm = version.lstrip('vV')
    patron_norm = patron.lstrip('vV')
    
    # Si el patrón termina en .* es un comodín
    if patron_norm.endswith('.*'):
        prefijo = patron_norm[:-2]  # Quitar '.*'
        return version_norm.startswith(prefijo + '.') or version_norm == prefijo
    
    # Si el patrón es solo '*', coincide con todo
    if patron_norm == '*':
        return True
    
    # Comparación exacta
    return version_norm == patron_norm


def version_en_rango(version, v_min, v_max):
    """
    Verifica si una versión está dentro del rango [v_min, v_max].
    Soporta comodines en v_min y v_max (ej: '1.*').
    """
    if not version:
        return False
    
    # Si hay comodín, usar coincidencia de patrón
    if v_min and '*' in v_min:
        if not version_coincide_patron(version, v_min):
            return False
    elif v_min and comparar_versiones(version, v_min) < 0:
        return False
    
    if v_max and '*' in v_max:
        if not version_coincide_patron(version, v_max):
            return False
    elif v_max and comparar_versiones(version, v_max) > 0:
        return False
    
    return True


# ============================================================================
# FUNCIONES DE ACCESO A BASE DE DATOS
# ============================================================================

def obtener_mensaje_sistema(session, codigo_mensaje):
    """
    Obtiene el texto de un mensaje del sistema desde IA_VALDAT (tipo MSGS).
    
    Args:
        session: Sesión de SQLAlchemy activa
        codigo_mensaje: Código del mensaje (C_VALOR_TEXT) a buscar
        
    Returns:
        str: El texto del mensaje (D_VALOR) o None si no se encuentra
    """
    from sqlalchemy import and_
    from models import TiposDato, ValoresDato
    
    try:
        tipo_mensajes = session.query(TiposDato).filter_by(C_TIPDAT='MSGS').first()
        if not tipo_mensajes:
            return None
        
        valor = session.query(ValoresDato).filter(
            and_(
                ValoresDato.TIDA_ID_TIPDAT == tipo_mensajes.ID_TIPDAT,
                ValoresDato.C_VALOR_TEXT == codigo_mensaje
            )
        ).first()
        
        return valor.D_VALOR if valor else None
    except Exception:
        return None


def obtener_version_bd(session):
    """
    Obtiene la versión actual de la base de datos desde IA_VALDAT.
    
    Busca en la tabla IA_VALDAT el valor con tipo 'VERBD' y código 'ACTUAL'.
    
    Returns:
        str: Versión de la BD o None si no se encuentra
    """
    from sqlalchemy import and_
    from models import TiposDato, ValoresDato
    
    try:
        tipo_verbd = session.query(TiposDato).filter_by(C_TIPDAT='VERBD').first()
        if not tipo_verbd:
            return None
        
        valor = session.query(ValoresDato).filter(
            and_(
                ValoresDato.TIDA_ID_TIPDAT == tipo_verbd.ID_TIPDAT,
                ValoresDato.C_VALOR_TEXT == 'ACTUAL'
            )
        ).first()
        
        return valor.D_VALOR if valor else None
    except Exception:
        return None


# ============================================================================
# FUNCIÓN PRINCIPAL DE VERIFICACIÓN DE COMPATIBILIDAD
# ============================================================================

def verificar_compatibilidad_arranque():
    """
    Verifica si la combinación de versión de aplicación y versión de BD
    está expresamente prohibida.
    
    PRINCIPIO: Lo que no está expresamente prohibido, se permite.
    
    Busca en IA_CFGVERSCOMPAT reglas con C_TIPO='STARTUP' que coincidan
    con las versiones actuales. Si encuentra una regla con L_COMPATIBLE=0,
    el arranque se bloquea. Si encuentra una regla con L_COMPATIBLE=1 y
    T_SQL_MIGRACION, devuelve el SQL para ejecutar antes de arrancar.
    
    Returns:
        tuple: (compatible, mensaje_error, sql_migracion, mensaje_migracion_error)
            - compatible (bool): True si se permite el arranque, False si se bloquea
            - mensaje_error (str): Mensaje de error si no es compatible, None si es compatible
            - sql_migracion (str): SQL a ejecutar si hay migración, None si no hay
            - mensaje_migracion_error (str): Mensaje a mostrar si falla la migración, None si no hay
    """
    from models import Session, ConfiguracionVersionCompatibilidad
    
    session = None
    try:
        session = Session()
        
        # Obtener versiones actuales
        version_app = config.VERSION_APLICACION
        version_bd = obtener_version_bd(session)
        
        # Si no se puede obtener la versión de BD, permitir arranque
        # (puede ser una BD nueva sin datos de configuración)
        if not version_bd:
            return (True, None, None, None)
        
        # Buscar reglas de tipo STARTUP activas, ordenadas por prioridad
        try:
            reglas = session.query(ConfiguracionVersionCompatibilidad)\
                .filter_by(C_TIPO='STARTUP', L_ESTADO=1)\
                .order_by(ConfiguracionVersionCompatibilidad.N_ORDEN)\
                .all()
        except Exception:
            # Si hay error al consultar la tabla (puede no existir), permitir
            return (True, None, None, None)
        
        # Si no hay reglas definidas, permitir arranque
        if not reglas:
            return (True, None, None, None)
        
        # Evaluar cada regla en orden de prioridad
        for regla in reglas:
            # C_VERSION_MIN/MAX = versión de la BD (origen/datos almacenados)
            # C_VERS_SIST_MIN/MAX = versión de la APP (sistema ejecutándose)
            
            # Verificar si la versión de BD está en el rango definido
            coincide_bd = version_en_rango(
                version_bd,
                regla.C_VERSION_MIN,
                regla.C_VERSION_MAX
            )
            
            # Verificar si la versión de APP está en el rango definido
            coincide_app = version_en_rango(
                version_app,
                regla.C_VERS_SIST_MIN,
                regla.C_VERS_SIST_MAX
            )
            
            # Si ambas condiciones coinciden, aplicar la regla
            if coincide_app and coincide_bd:
                # Obtener mensaje configurado (se usa tanto para bloqueo como para error de migración)
                mensaje_configurado = None
                if regla.C_MENSAJE:
                    mensaje_configurado = obtener_mensaje_sistema(session, regla.C_MENSAJE)
                
                if regla.L_COMPATIBLE == 0:
                    # Combinación bloqueada
                    # Mensaje por defecto si no hay configurado
                    if not mensaje_configurado:
                        mensaje_configurado = (
                            f"La versión de la aplicación ({version_app}) no es compatible "
                            f"con la versión de la base de datos ({version_bd}).\n\n"
                            f"Por favor, utilice una versión compatible de la aplicación "
                            f"o actualice la base de datos."
                        )
                    
                    return (False, mensaje_configurado, None, None)
                else:
                    # Combinación expresamente permitida
                    # Devolver SQL de migración si existe, y el mensaje para usar si falla
                    sql_migracion = regla.T_SQL_MIGRACION if regla.T_SQL_MIGRACION else None
                    return (True, None, sql_migracion, mensaje_configurado)
        
        # No se encontró ninguna regla que coincida: permitir por defecto
        return (True, None, None, None)
        
    except Exception:
        # En caso de cualquier error, permitir arranque silenciosamente
        return (True, None, None, None)
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass


def ejecutar_migracion_arranque(sql_migracion, mensaje_error_configurado=None):
    """
    Ejecuta los scripts de migración de arranque de forma segura.
    
    Los scripts pueden usar variables que serán sustituidas:
    - :version_app -> versión actual de la aplicación
    - :version_bd -> versión actual de la base de datos
    
    Args:
        sql_migracion (str): Scripts SQL separados por ';'
        mensaje_error_configurado (str): Mensaje a mostrar si falla (de C_MENSAJE en la regla)
        
    Returns:
        tuple: (exito, mensaje_error)
            - exito (bool): True si la migración fue exitosa
            - mensaje_error (str): Mensaje de error si falló, None si éxito
    """
    if not sql_migracion:
        return (True, None)
    
    from sqlalchemy import text
    from models import Session
    
    # Separar scripts y filtrar vacíos y comentarios
    scripts = [s.strip() for s in sql_migracion.split(';') 
               if s.strip() and not s.strip().startswith('--')]
    
    if not scripts:
        return (True, None)
    
    session = None
    try:
        session = Session()
        
        # Obtener versiones para sustitución de variables
        version_app = config.VERSION_APLICACION
        version_bd = obtener_version_bd(session) or 'desconocida'
        
        scripts_ejecutados = 0
        for script in scripts:
            # Sustituir variables
            script_final = script\
                .replace(':version_app', f"'{version_app}'")\
                .replace(':version_bd', f"'{version_bd}'")
            
            session.execute(text(script_final))
            scripts_ejecutados += 1
        
        # Confirmar cambios
        session.commit()
        return (True, None)
        
    except Exception:
        # Revertir cambios en caso de error
        if session:
            try:
                session.rollback()
            except Exception:
                pass
        
        # Usar mensaje configurado si existe, sino mensaje por defecto
        if mensaje_error_configurado:
            return (False, mensaje_error_configurado)
        else:
            mensaje = (
                "Error durante la migración automática de la base de datos.\n\n"
                "La base de datos no ha sido modificada.\n"
                "Contacte con soporte técnico si el problema persiste."
            )
            return (False, mensaje)
        
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass


# ============================================================================
# FUNCIÓN PARA MOSTRAR ERROR Y TERMINAR
# ============================================================================

def _obtener_nombre_aplicacion():
    """
    Obtiene el nombre de la aplicación desde el nombre del ejecutable.
    
    Si se ejecuta como .exe, extrae el nombre sin la extensión.
    Si se ejecuta como script Python, devuelve None para no mostrar nombre.
    
    Returns:
        str o None: Nombre de la aplicación o None
    """
    import sys
    import os
    
    try:
        if getattr(sys, 'frozen', False):
            # Ejecutándose como ejecutable empaquetado (PyInstaller)
            exe_path = sys.executable
            nombre_exe = os.path.basename(exe_path)
            # Quitar extensión .exe si existe
            if nombre_exe.lower().endswith('.exe'):
                nombre_exe = nombre_exe[:-4]
            return nombre_exe
    except Exception:
        pass
    return None


def mostrar_error_incompatibilidad(mensaje):
    """
    Muestra un mensaje de error de incompatibilidad y termina la aplicación.
    
    Intenta mostrar una ventana gráfica (tkinter). Si no está disponible,
    termina silenciosamente.
    
    Args:
        mensaje (str): Mensaje de error a mostrar
    """
    import os
    
    # Obtener nombre de la aplicación para el título
    nombre_app = _obtener_nombre_aplicacion()
    if nombre_app:
        titulo = f"{nombre_app} - Error de Compatibilidad"
    else:
        titulo = "Error de Compatibilidad"
    
    # Intentar mostrar ventana gráfica
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        root = tk.Tk()
        root.withdraw()
        
        messagebox.showerror(titulo, mensaje)
        
        root.destroy()
    except Exception:
        # Si tkinter no está disponible, terminar silenciosamente
        pass
    
    # Terminar la aplicación de forma forzada
    # Usamos os._exit() en lugar de sys.exit() para asegurar que el proceso
    # termina completamente, incluyendo hilos en segundo plano
    os._exit(1)


# ============================================================================
# FUNCIÓN DE PUNTO DE ENTRADA PARA APP.PY
# ============================================================================

def verificar_compatibilidad_o_salir():
    """
    Verifica compatibilidad, ejecuta migración si es necesaria, y termina si falla.
    
    Esta función debe llamarse al inicio de app.py, antes de iniciar Flask.
    Si la verificación falla o la migración falla, muestra un mensaje de error y termina.
    
    NOTA: Esta función NO cierra el splash de PyInstaller antes de mostrar errores.
    Para aplicaciones con splash, usar directamente verificar_compatibilidad_arranque()
    y ejecutar_migracion_arranque() con control manual del splash.
    """
    import os
    
    compatible, mensaje_error, sql_migracion, mensaje_migracion_error = verificar_compatibilidad_arranque()
    
    if not compatible:
        mostrar_error_incompatibilidad(mensaje_error)
        os._exit(1)
    
    # Si hay SQL de migración, ejecutarlo
    if sql_migracion:
        exito, mensaje_error = ejecutar_migracion_arranque(sql_migracion, mensaje_migracion_error)
        if not exito:
            mostrar_error_incompatibilidad(mensaje_error)
            os._exit(1)
