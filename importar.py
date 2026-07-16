
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

# importar.py

import pyzipper as zipfile
import json
from io import BytesIO
from flask import Blueprint, request, redirect, url_for, flash
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, and_, text
from datetime import datetime
from collections import Counter, defaultdict
import config

# Importar función para obtener versión actual de BD
from utils import get_valor_actual_verbd

# Importa los modelos y la sesión de la base de datos
from models import (
    Session,
    Inicio,
    RespuestasProyecto,
    DatosElementosAdi,
    DatosRiesgo,
    DatosControl,
    DatosElementoControl,
    DatosControlMonitoreo,
    DatosActividadMonitoreo,
    DatosDocumento,
    DatosElementoDocumento,
    # ============================================
    # NUEVA TABLA AÑADIDA
    # ============================================
    DatosRequisito,
    # ============================================
    # MODELOS PARA CONTROL DE VERSIONES
    # ============================================
    TiposDato,
    ValoresDato,
    ConfiguracionVersionCompatibilidad
)

# Define el blueprint para las rutas de importación
importar_proyecto_db = Blueprint("importar_proyecto", __name__)

# La contraseña de encriptación del archivo zip
ENCRYPTION_PASSWORD = bytes(config.CONTRASENA_EXPORTACION, 'utf-8')

# Mapeo de nombres de archivo a clases de modelo
MODEL_MAPPING = {
    "IA_SISTEMA.json": Inicio,
    "IA_SISTEMAADI.json": RespuestasProyecto,
    "IA_DATELEMADI.json": DatosElementosAdi,
    "IA_DATRIESGOS.json": DatosRiesgo,
    "IA_DATCONTROL.json": DatosControl,
    "IA_DATELEMCONTR.json": DatosElementoControl,
    "IA_DATCONTMON.json": DatosControlMonitoreo,
    "IA_DATACTMONIT.json": DatosActividadMonitoreo,
    "IA_DATDOCS.json": DatosDocumento,
    "IA_DATELEMDOCS.json": DatosElementoDocumento,
    # ============================================
    # NUEVA TABLA AÑADIDA
    # ============================================
    "IA_DATEREQUISITOS.json": DatosRequisito
}

# Define los mapeos de claves primarias y foráneas
PK_MAPPING = {
    'IA_SISTEMA.json': ('ID_SISTEMA', []),
    'IA_SISTEMAADI.json': ('ID_SISTEMAADI', []),
    'IA_DATELEMADI.json': ('ID_DATELEMADI', []),
    'IA_DATRIESGOS.json': ('ID_DATRIES', []),
    'IA_DATCONTROL.json': ('ID_DATCONTROL', []),
    'IA_DATELEMCONTR.json': ('ID_DATELEMCONTR', []),
    'IA_DATCONTMON.json': ('ID_DATCONTMON', []),
    'IA_DATACTMONIT.json': ('ID_DATACTMONIT', []),
    'IA_DATDOCS.json': ('ID_DATDOCS', []),
    'IA_DATELEMDOCS.json': ('ID_DATELEMDOCS', []),
    # ============================================
    # NUEVA TABLA AÑADIDA
    # ============================================
    'IA_DATEREQUISITOS.json': ('ID_DATREQ', []),
}

# Mapeo de claves foráneas
FK_MAPPING = {
    'SIST_ID_SISTEMA': 'IA_SISTEMA.json',
    'ELEMADI_ID_DATELEMADI': 'IA_DATELEMADI.json',
    'ACT_ID_CONTMON': 'IA_DATCONTMON.json',
    'DED_ID_DATDOCS': 'IA_DATDOCS.json',
}


# ============================================================================
# FUNCIONES DE CONTROL DE VERSIONES
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


def obtener_mensaje_sistema(session, codigo_mensaje):
    """Obtiene el texto de un mensaje del sistema desde IA_VALDAT (tipo MSGS)."""
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


def verificar_compatibilidad_version(session, version_app_archivo, version_bd_archivo):
    """
    Verifica si las versiones del archivo exportado son compatibles con el sistema actual.
    
    Las reglas pueden especificar:
    - Versión del archivo (origen): C_VERSION_MIN, C_VERSION_MAX
    - Versión del sistema (destino): C_VERS_SIST_MIN, C_VERS_SIST_MAX
    
    Soporta comodines: '1.*' coincide con cualquier versión 1.x
    
    Returns:
        tuple: (compatible, mensaje, sql_migracion)
    """
    try:
        reglas = session.query(ConfiguracionVersionCompatibilidad)\
            .filter_by(L_ESTADO=1)\
            .order_by(ConfiguracionVersionCompatibilidad.N_ORDEN)\
            .all()
    except Exception as e:
        return (True, None, None)
    
    if not reglas:
        return (True, None, None)
    
    # Versión actual del sistema
    version_sistema_app = config.VERSION_APLICACION
    version_sistema_bd = get_valor_actual_verbd()  # Lee de IA_VALDAT (tipo VERBD, valor ACTUAL)
    
    for regla in reglas:
        # Determinar qué versiones verificar según el tipo de regla
        if regla.C_TIPO == 'APP':
            version_archivo = version_app_archivo
            version_sistema = version_sistema_app
        else:  # 'BD'
            version_archivo = version_bd_archivo
            version_sistema = version_sistema_bd
        
        # Verificar si la versión del archivo está en el rango origen
        coincide_origen = version_en_rango(version_archivo, regla.C_VERSION_MIN, regla.C_VERSION_MAX)
        
        # Verificar si la versión del sistema está en el rango destino (si está definido)
        vers_sist_min = getattr(regla, 'C_VERS_SIST_MIN', None)
        vers_sist_max = getattr(regla, 'C_VERS_SIST_MAX', None)
        
        if vers_sist_min or vers_sist_max:
            coincide_destino = version_en_rango(version_sistema, vers_sist_min, vers_sist_max)
        else:
            coincide_destino = True  # Si no hay restricción de destino, siempre coincide
        
        # Si coinciden ambas condiciones, aplicar la regla
        if coincide_origen and coincide_destino:
            mensaje = obtener_mensaje_sistema(session, regla.C_MENSAJE) if regla.C_MENSAJE else None
            
            if regla.L_COMPATIBLE == 1:
                return (True, mensaje, regla.T_SQL_MIGRACION)
            else:
                return (False, mensaje, None)
    
    # Si no hay regla específica que coincida, permitir importación normal
    return (True, None, None)


def ejecutar_migracion(session, sql_migracion, proyecto_id, version_origen, version_bd_origen):
    """Ejecuta los scripts de migración de forma segura."""
    if not sql_migracion:
        return True, "Sin scripts de migración"
    
    scripts = [s.strip() for s in sql_migracion.split(';') if s.strip() and not s.strip().startswith('--')]
    
    if not scripts:
        return True, "Sin scripts de migración"
    
    try:
        scripts_ejecutados = 0
        for script in scripts:
            script_final = script\
                .replace(':proyecto_id', str(proyecto_id))\
                .replace(':version_origen', f"'{version_origen}'")\
                .replace(':version_bd_origen', f"'{version_bd_origen}'")
            
            session.execute(text(script_final))
            scripts_ejecutados += 1
        
        return True, f"Migración completada ({scripts_ejecutados} scripts ejecutados)"
    except Exception as e:
        return False, f"Error en migración: {str(e)}"


def leer_meta_version(zip_ref):
    """Lee el archivo META_VERSION.json del ZIP si existe."""
    try:
        if 'META_VERSION.json' in zip_ref.namelist():
            json_data = zip_ref.read('META_VERSION.json').decode('utf-8')
            return json.loads(json_data)
    except Exception as e:
        pass
    return None

def verificar_duplicados_post_importacion(session, proyecto_id):
    """
    Verifica si hay duplicados REALES después de importar los datos.
    Solo verifica IA_DATCONTROL porque es la única tabla donde pueden ocurrir duplicados problemáticos.

    NOTA: Para IA_DATRIESGOS es NORMAL tener múltiples registros con el mismo RIE_ID_RIESGO
    porque representan diferentes evaluaciones o estados del mismo riesgo.

    Returns:
        dict: Diccionario con los duplicados encontrados
    """
    duplicados_encontrados = {}

    # SOLO verificar IA_DATCONTROL
    # Un proyecto NO debe tener el mismo control (CON_ID_CONTROL) repetido
    registros_control = session.query(DatosControl).filter_by(
        SIST_ID_SISTEMA=proyecto_id
    ).all()

    valores_control = [r.CON_ID_CONTROL for r in registros_control]
    contador_control = Counter(valores_control)
    duplicados_control = {k: v for k, v in contador_control.items() if v > 1}

    if duplicados_control:
        duplicados_encontrados['IA_DATCONTROL'] = {
            'duplicados': duplicados_control,
            'total_registros': len(registros_control),
            'controles_unicos': len(contador_control)
        }

    return duplicados_encontrados


@importar_proyecto_db.route("/importar-proyecto", methods=["POST"])
def importar_proyecto():

    if 'archivo' not in request.files:
        flash("No se ha seleccionado ningún archivo.", "danger")
        return redirect(url_for('seleccionar_proyecto'))

    archivo_zip = request.files['archivo']
    if archivo_zip.filename == '':
        flash("No se ha seleccionado ningún archivo.", "danger")
        return redirect(url_for('seleccionar_proyecto'))

    session = Session()
    nuevo_proyecto_id = None
    version_archivo_app = None
    version_archivo_bd = None
    sql_migracion = None

    try:
        zip_data = BytesIO(archivo_zip.read())
        imported_data = {}
        pk_reassignments = {}

        # ============================================
        # FASE 0: VERIFICACIÓN DE VERSIÓN
        # ============================================

        with zipfile.AESZipFile(zip_data) as zip_ref:
            zip_ref.setpassword(ENCRYPTION_PASSWORD)
            
            meta_version = leer_meta_version(zip_ref)
            
            if meta_version:
                version_archivo_app = meta_version.get('VERSION_APP', 'desconocida')
                version_archivo_bd = meta_version.get('VERSION_BD', 'desconocida')
                fecha_exportacion = meta_version.get('F_EXPORTACION', 'desconocida')
                
                
                compatible, mensaje, sql_migracion = verificar_compatibilidad_version(
                    session, version_archivo_app, version_archivo_bd
                )
                
                if not compatible:
                    flash(mensaje or "No es posible realizar la importación. Versión incompatible.", "danger")
                    session.close()
                    return redirect(url_for('seleccionar_proyecto'))
                
                if sql_migracion:
                    pass
                else:
                    pass
            else:
                mensaje_sin_version = obtener_mensaje_sistema(session, 'IMPORT_SIN_VERSION')
                if mensaje_sin_version:
                    flash(mensaje_sin_version, "warning")

        # Rebobinar para lectura de datos
        zip_data.seek(0)

        # 1. Leer y procesar los archivos JSON del ZIP

        with zipfile.AESZipFile(zip_data) as zip_ref:
            zip_ref.setpassword(ENCRYPTION_PASSWORD)
            for filename in zip_ref.namelist():
                if filename.endswith('.json') and filename in MODEL_MAPPING:
                    json_data = zip_ref.read(filename).decode('utf-8')
                    imported_data[filename] = json.loads(json_data)

        # 2. Modificar el nombre del proyecto en IA_SISTEMA.json

        if 'IA_SISTEMA.json' in imported_data and imported_data['IA_SISTEMA.json']:
            current_time = datetime.now().strftime("-%Y-%m-%d-%H-%M-%S")
            original_name = imported_data['IA_SISTEMA.json'][0]['D_NOMPROYEC']
            imported_data['IA_SISTEMA.json'][0]['D_NOMPROYEC'] = f"{original_name} IMP{current_time}"

        # 3. Verificar duplicidad y reasignar IDs principales

        for filename in PK_MAPPING.keys():
            if filename in imported_data and imported_data[filename]:
                pk_name, _ = PK_MAPPING[filename]
                model_class = MODEL_MAPPING[filename]

                max_id = session.query(func.max(getattr(model_class, pk_name))).scalar() or 0
                current_max_id = max_id

                pk_reassignments[filename] = {}

                for item in imported_data[filename]:
                    old_id = item.get(pk_name)
                    if old_id is not None:
                        if session.query(model_class).filter_by(**{pk_name: old_id}).first():
                            current_max_id += 100
                            new_id = current_max_id
                            pk_reassignments[filename][old_id] = new_id
                            item[pk_name] = new_id
                        else:
                            pk_reassignments[filename][old_id] = old_id

        # Guardar el ID del nuevo proyecto
        if 'IA_SISTEMA.json' in pk_reassignments and imported_data['IA_SISTEMA.json']:
            nuevo_proyecto_id = imported_data['IA_SISTEMA.json'][0]['ID_SISTEMA']

        # 4. Actualizar claves foráneas

        fk_actualizadas = 0
        for filename, data_list in imported_data.items():
            for item in data_list:
                for fk_name, source_file in FK_MAPPING.items():
                    if fk_name in item and source_file in pk_reassignments:
                        old_fk_value = item[fk_name]
                        if old_fk_value in pk_reassignments[source_file]:
                            new_fk_value = pk_reassignments[source_file][old_fk_value]
                            item[fk_name] = new_fk_value
                            if old_fk_value != new_fk_value:
                                fk_actualizadas += 1


        # 5. Importar los datos a la base de datos

        # Orden de importación (respeta dependencias de FK)
        import_order = [
            "IA_SISTEMA.json",
            "IA_SISTEMAADI.json",
            "IA_DATELEMADI.json",
            "IA_DATRIESGOS.json",
            "IA_DATCONTROL.json",
            "IA_DATELEMCONTR.json",
            "IA_DATCONTMON.json",
            "IA_DATACTMONIT.json",
            "IA_DATDOCS.json",
            "IA_DATELEMDOCS.json",
            # ============================================
            # NUEVA TABLA AÑADIDA (después de IA_SISTEMA)
            # ============================================
            "IA_DATEREQUISITOS.json"
        ]

        for filename in import_order:
            if filename in imported_data:
                model_class = MODEL_MAPPING.get(filename)
                if model_class:
                    count = 0
                    for item_data in imported_data[filename]:
                        try:
                            # Manejo de campos opcionales
                            if filename == "IA_DATRIESGOS.json":
                                if 'L_MANUAL' not in item_data:
                                    item_data['L_MANUAL'] = 0
                                if 'T_DESCRIPCION' not in item_data:
                                    item_data['T_DESCRIPCION'] = None
                                if 'V_RIERESID' not in item_data:
                                    item_data['V_RIERESID'] = None

                            elif filename == "IA_DATCONTROL.json":
                                if 'L_MANUAL' not in item_data:
                                    item_data['L_MANUAL'] = 0

                            # Manejo de campos opcionales para DatosRequisito
                            elif filename == "IA_DATEREQUISITOS.json":
                                # Campos que pueden no existir en exportaciones antiguas
                                if 'T_PLANMEJORA' not in item_data:
                                    item_data['T_PLANMEJORA'] = None

                            new_instance = model_class(**item_data)
                            session.add(new_instance)
                            count += 1
                        except Exception as e:
                            raise

        # 6. VALIDACIÓN CRÍTICA: Solo verificar duplicados en IA_DATCONTROL
        if nuevo_proyecto_id:

            duplicados_post = verificar_duplicados_post_importacion(session, nuevo_proyecto_id)

            if duplicados_post:
                for tabla, info in duplicados_post.items():

                    for control_id, count in list(info['duplicados'].items())[:5]:
                        pass

                # REVERTIR
                session.rollback()
                flash("Error: Se detectaron controles duplicados. Importación cancelada.", "danger")
                return redirect(url_for('seleccionar_proyecto'))
            else:
                pass

        # ============================================
        # FASE 7: EJECUCIÓN DE SCRIPTS DE MIGRACIÓN
        # ============================================
        if sql_migracion and nuevo_proyecto_id:
            
            exito_migracion, mensaje_migracion = ejecutar_migracion(
                session, sql_migracion, nuevo_proyecto_id,
                version_archivo_app or 'desconocida',
                version_archivo_bd or 'desconocida'
            )
            
            if exito_migracion:
                pass
            else:
                session.rollback()
                flash(f"Error durante la migración: {mensaje_migracion}", "danger")
                return redirect(url_for('seleccionar_proyecto'))

        session.commit()
        
        # Mensaje apropiado según si hubo migración
        if sql_migracion:
            mensaje_exito = obtener_mensaje_sistema(session, 'IMPORT_MIGRADO')
            flash(mensaje_exito or "Proyecto importado y migrado a la versión actual.", "success")
        else:
            mensaje_exito = obtener_mensaje_sistema(session, 'IMPORT_OK')
            flash(mensaje_exito or "Proyecto importado con éxito.", "success")

    except zipfile.BadZipFile:
        session.rollback()
        flash("Error: Archivo ZIP inválido o corrupto.", "danger")
    except RuntimeError as e:
        session.rollback()
        if "Bad password for file" in str(e):
            flash("Error: Contraseña incorrecta para el archivo ZIP.", "danger")
        else:
            flash(f"Error al descomprimir: {str(e)}", "danger")
    except IntegrityError as e:
        session.rollback()
        flash(f"Error de integridad en la base de datos: {e}", "danger")
    except Exception as e:
        session.rollback()
        flash(f"Error inesperado: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

    return redirect(url_for('seleccionar_proyecto'))
