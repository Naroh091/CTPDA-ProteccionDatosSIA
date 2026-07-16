
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

# actualizacion.py

import os
import sys
import requests
import packaging.version
import config
import utils
import zipfile
import tempfile
from sqlalchemy import text, and_


# ============================================================================
# FUNCIONES DE LOGGING (desactivadas en producción)
# ============================================================================

def log_debug(mensaje):
    """Debug desactivado en producción."""
    pass

def log_info(mensaje):
    """Info desactivado en producción."""
    pass

def log_error(mensaje):
    """Error desactivado en producción."""
    pass

def log_warning(mensaje):
    """Warning desactivado en producción."""
    pass


# ============================================================================


# ============================================================================
# ESTRUCTURA PARA ACTUALIZACIONES PENDIENTES
# ============================================================================
# Almacena información sobre las actualizaciones detectadas pero no aplicadas

actualizaciones_pendientes = {
    'exe': None,       # {'version_actual': '...', 'version_nueva': '...', 'url': '...'}
    'bd': None,        # {'version_actual': '...', 'version_nueva': '...', 'url': '...'}
    'plantillas': [],  # [{'codigo': '...', 'version_actual': '...', 'version_nueva': '...'}]
    'server_data': None,  # Datos del servidor para aplicar actualizaciones
    'cert_path': None     # Ruta del certificado
}


def limpiar_actualizaciones_pendientes():
    """Limpia todas las actualizaciones pendientes."""
    global actualizaciones_pendientes
    actualizaciones_pendientes = {
        'exe': None,
        'bd': None,
        'plantillas': [],
        'server_data': None,
        'cert_path': None
    }


def hay_actualizaciones_pendientes():
    """Retorna True si hay alguna actualización pendiente."""
    return (
        actualizaciones_pendientes['exe'] is not None or
        actualizaciones_pendientes['bd'] is not None or
        len(actualizaciones_pendientes['plantillas']) > 0
    )


def obtener_resumen_actualizaciones():
    """
    Genera un resumen de las actualizaciones pendientes para mostrar en el banner.

    Returns:
        str: Texto descriptivo de las actualizaciones pendientes
    """
    partes = []

    if actualizaciones_pendientes['exe']:
        exe = actualizaciones_pendientes['exe']
        partes.append(f"App: {exe['version_actual']} → {exe['version_nueva']}")

    if actualizaciones_pendientes['bd']:
        bd = actualizaciones_pendientes['bd']
        partes.append(f"BD: {bd['version_actual']} → {bd['version_nueva']}")

    for pl in actualizaciones_pendientes['plantillas']:
        partes.append(f"{pl['codigo'].upper()}: {pl['version_actual']} → {pl['version_nueva']}")

    return " | ".join(partes) if partes else ""


def obtener_info_actualizaciones():
    """
    Retorna información detallada sobre las actualizaciones pendientes.

    Returns:
        dict: Diccionario con la información de actualizaciones
    """
    return actualizaciones_pendientes.copy()


# ============================================================================


def resource_path(relative_path):
    """Resuelve la ruta absoluta para archivos de recursos tanto en desarrollo como en ejecutable empaquetado."""
    try:
        base_path = sys._MEIPASS  # Ruta base cuando está empaquetado
    except Exception:
        base_path = os.path.abspath(".")  # Ruta base en desarrollo
    return os.path.join(base_path, relative_path)


# ============================================================================
# FUNCIONES PARA ACTUALIZACIÓN DE BASE DE DATOS
# ============================================================================

def descargar_fichero_sql(url, cert_path):
    """
    Descarga un fichero SQL desde una URL.

    Args:
        url (str): URL del fichero SQL a descargar.
        cert_path (str): Ruta al certificado SSL para verificación.

    Returns:
        tuple: (bool, str) - (éxito, contenido del fichero o mensaje de error)
    """
    try:
        response = requests.get(url, verify=cert_path, timeout=30.0)
        response.raise_for_status()
        # Decodificar como UTF-8
        contenido = response.content.decode('utf-8')
        return True, contenido
    except requests.exceptions.RequestException as e:
        return False, f"Error al descargar el fichero de actualización: {e}"
    except UnicodeDecodeError as e:
        return False, f"Error de codificación en el fichero descargado: {e}"


def parsear_sentencias_sql(contenido_sql):
    """
    Parsea un contenido SQL y extrae las sentencias individuales.
    Las sentencias están separadas por ';'.

    Args:
        contenido_sql (str): Contenido del fichero SQL.

    Returns:
        list: Lista de sentencias SQL limpias (sin vacías).
    """
    sentencias = []

    # Dividir por ';' y limpiar cada sentencia
    partes = contenido_sql.split(';')

    for parte in partes:
        # Limpiar espacios y saltos de línea
        sentencia = parte.strip()

        # Ignorar sentencias vacías o solo con comentarios
        if sentencia and not sentencia.startswith('--'):
            # Verificar que no sea solo comentarios
            lineas_sin_comentarios = [
                linea for linea in sentencia.split('\n')
                if linea.strip() and not linea.strip().startswith('--')
            ]
            if lineas_sin_comentarios:
                sentencias.append(sentencia)

    return sentencias


def ejecutar_actualizacion_bd(sentencias):
    """
    Ejecuta una lista de sentencias SQL en una única transacción.
    Si alguna falla, se hace rollback de todas.

    Args:
        sentencias (list): Lista de sentencias SQL a ejecutar.

    Returns:
        tuple: (bool, str) - (éxito, mensaje informativo o de error)
    """
    from models import Session

    if not sentencias:
        return False, "No se encontraron sentencias SQL válidas en el fichero de actualización."

    db_session = Session()

    try:
        # Ejecutar cada sentencia dentro de la misma transacción
        for i, sentencia in enumerate(sentencias, 1):
            try:
                db_session.execute(text(sentencia))
            except Exception as e:
                # Si falla una sentencia, hacer rollback y reportar el error
                db_session.rollback()
                return False, f"Error en sentencia {i}/{len(sentencias)}: {str(e)}\n\nSentencia: {sentencia[:200]}..."

        # Si todas las sentencias se ejecutaron correctamente, hacer commit
        db_session.commit()
        return True, f"Se ejecutaron {len(sentencias)} sentencias."

    except Exception as e:
        db_session.rollback()
        return False, f"Error inesperado durante la actualización: {str(e)}"

    finally:
        db_session.close()


def aplicar_actualizacion_bd(db_download_url, cert_path):
    """
    Proceso completo de actualización de base de datos:
    1. Descarga el fichero SQL
    2. Parsea las sentencias
    3. Ejecuta todas en una transacción

    Args:
        db_download_url (str): URL del fichero SQL de actualización.
        cert_path (str): Ruta al certificado SSL.

    Returns:
        tuple: (bool, str) - (éxito, mensaje informativo)
    """
    # Paso 1: Descargar el fichero SQL
    exito, resultado = descargar_fichero_sql(db_download_url, cert_path)
    if not exito:
        return False, resultado

    contenido_sql = resultado

    # Paso 2: Parsear las sentencias
    sentencias = parsear_sentencias_sql(contenido_sql)

    if not sentencias:
        return False, "El fichero de actualización no contiene sentencias SQL válidas."

    # Paso 3: Ejecutar las sentencias en una transacción
    exito, mensaje = ejecutar_actualizacion_bd(sentencias)

    return exito, mensaje


def obtener_url_actualizacion_para_version(server_data, version_local):
    """
    Busca en los datos del servidor la URL de actualización específica para
    la versión local de la base de datos.

    El patrón de búsqueda es: db_download_url_vXXX
    donde XXX es la versión local (ej: "1", "2", "3beta", etc.)

    Args:
        server_data (dict): Datos JSON del servidor con las URLs de actualización.
        version_local (str): Versión actual de la base de datos local.

    Returns:
        str or None: URL de descarga si existe, None si no hay actualización para esta versión.

    Ejemplo:
        Si version_local = "3beta", buscará la clave "db_download_url_v3beta"
        Si version_local = "1", buscará la clave "db_download_url_v1"
    """
    # Construir el nombre de la clave a buscar
    clave_url = f"db_download_url_v{version_local}"

    # Buscar en los datos del servidor
    url = server_data.get(clave_url)

    return url if url else None


# ============================================================================
# FUNCIONES PARA ACTUALIZACIÓN DE PLANTILLAS
# ============================================================================

def get_version_plantilla(codigo_plantilla):
    """
    Recupera la versión actual de una plantilla desde la tabla IA_VALDAT.

    Busca un registro donde:
    - El tipo de dato (IA_TIPDAT) tiene el código 'VERBD' (versión)
    - El valor textual (C_VALOR_TEXT) coincide con el código de la plantilla

    Args:
        codigo_plantilla (str): Código de la plantilla (ej: 'eipd', 'iv')

    Returns:
        str or None: Versión actual de la plantilla o None si no existe registro.
    """
    from models import Session, ValoresDato, TiposDato

    db_session = Session()
    try:
        registro = db_session.query(ValoresDato)\
            .join(TiposDato)\
            .filter(
                and_(
                    TiposDato.C_TIPDAT == 'VERBD',
                    ValoresDato.C_VALOR_TEXT == codigo_plantilla.lower()
                )
            )\
            .first()

        if registro is None:
            return None

        return registro.D_VALOR
    finally:
        db_session.close()


def obtener_codigos_plantillas():
    """
    Obtiene los códigos de todas las plantillas configuradas en IA_CFGDOCS.

    El código se extrae del campo T_PLANTILLA, tomando el nombre del fichero
    sin la extensión .eipd (ej: 'eipd.eipd' -> 'eipd', 'IV.eipd' -> 'iv')

    Returns:
        list: Lista de tuplas (codigo_plantilla, nombre_fichero_completo)
              El código está en minúsculas para normalización.
    """
    from models import Session, ConfiguracionDocumento

    db_session = Session()
    try:
        configuraciones = db_session.query(ConfiguracionDocumento)\
            .filter(ConfiguracionDocumento.T_PLANTILLA.isnot(None))\
            .all()

        plantillas = []
        codigos_vistos = set()

        for cfg in configuraciones:
            if cfg.T_PLANTILLA:
                nombre_fichero = cfg.T_PLANTILLA.strip()
                # Extraer el código (nombre sin extensión .pl)
                if nombre_fichero.lower().endswith('.pl'):
                    codigo = nombre_fichero[:-3].lower()  # Quitar '.pl'
                else:
                    codigo = nombre_fichero.lower()

                # Evitar duplicados
                if codigo not in codigos_vistos:
                    codigos_vistos.add(codigo)
                    plantillas.append((codigo, nombre_fichero))

        return plantillas
    finally:
        db_session.close()


def obtener_url_zip_plantilla(server_data, codigo_plantilla):
    """
    Busca en los datos del servidor la URL del archivo .zip para una plantilla.

    El patrón de búsqueda es: pl_download_url_XXXX
    donde XXXX es el código de la plantilla.

    Args:
        server_data (dict): Datos JSON del servidor.
        codigo_plantilla (str): Código de la plantilla (ej: 'eipd', 'iv')

    Returns:
        str or None: URL del archivo .zip o None si no existe.
    """
    clave = f"pl_download_url_{codigo_plantilla.lower()}"
    url = server_data.get(clave)

    # Verificar que es una URL válida
    if url and isinstance(url, str) and url.startswith('http'):
        return url
    return None


def descargar_archivo_zip(url, cert_path):
    """
    Descarga un archivo .zip desde una URL.

    Args:
        url (str): URL del archivo .zip a descargar.
        cert_path (str): Ruta al certificado SSL.

    Returns:
        tuple: (bool, bytes/str) - (éxito, contenido del archivo o mensaje de error)
    """
    try:
        response = requests.get(url, verify=cert_path, timeout=60.0)
        response.raise_for_status()
        return True, response.content
    except requests.exceptions.RequestException as e:
        return False, f"Error al descargar {url}: {e}"


def descomprimir_y_copiar_plantilla(contenido_zip, directorio_destino):
    """
    Descomprime un archivo .zip en memoria y copia los ficheros al directorio de plantillas.

    Args:
        contenido_zip (bytes): Contenido del archivo .zip.
        directorio_destino (str): Directorio donde copiar los ficheros descomprimidos.

    Returns:
        tuple: (bool, list/str) - (éxito, lista de ficheros copiados o mensaje de error)
    """
    ficheros_copiados = []

    try:
        # Crear un directorio temporal para descomprimir
        with tempfile.TemporaryDirectory() as temp_dir:
            # Guardar temporalmente el .zip
            temp_zip_path = os.path.join(temp_dir, "plantilla.zip")
            with open(temp_zip_path, 'wb') as f:
                f.write(contenido_zip)

            # Descomprimir el .zip
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                # Obtener la lista de ficheros en el .zip
                nombres_ficheros = zip_ref.namelist()

                if not nombres_ficheros:
                    return False, "El archivo .zip está vacío"

                # Extraer todos los ficheros al directorio temporal
                zip_ref.extractall(temp_dir)

                # Asegurar que el directorio destino existe
                if not os.path.exists(directorio_destino):
                    os.makedirs(directorio_destino)

                # Copiar cada fichero al directorio de plantillas
                for nombre_fichero in nombres_ficheros:
                    # Ignorar directorios y ficheros ocultos
                    if nombre_fichero.endswith('/') or nombre_fichero.startswith('.'):
                        continue

                    # Construir rutas
                    ruta_origen = os.path.join(temp_dir, nombre_fichero)
                    ruta_destino = os.path.join(directorio_destino, os.path.basename(nombre_fichero))

                    # Copiar el fichero (sobrescribir si existe)
                    if os.path.isfile(ruta_origen):
                        with open(ruta_origen, 'rb') as f_orig:
                            contenido = f_orig.read()
                        with open(ruta_destino, 'wb') as f_dest:
                            f_dest.write(contenido)

                        ficheros_copiados.append(os.path.basename(nombre_fichero))

        if not ficheros_copiados:
            return False, "No se encontraron ficheros válidos en el .zip"

        return True, ficheros_copiados

    except zipfile.BadZipFile:
        return False, "El archivo descargado no es un .zip válido"
    except Exception as e:
        return False, f"Error al descomprimir o copiar ficheros: {e}"


def obtener_url_sql_plantilla(server_data, codigo_plantilla):
    """
    Busca la URL del fichero SQL de actualización para una plantilla.

    El patrón de búsqueda es: pl_download_url_sql_XXXX
    donde XXXX es el código de la plantilla.

    Args:
        server_data (dict): Datos JSON del servidor.
        codigo_plantilla (str): Código de la plantilla.

    Returns:
        str or None: URL del fichero SQL o None si no existe.
    """
    clave = f"pl_download_url_sql_{codigo_plantilla.lower()}"
    url = server_data.get(clave)
    return url if url and isinstance(url, str) and url.startswith('http') else None


def aplicar_actualizacion_plantilla(server_data, codigo_plantilla, cert_path):
    """
    Proceso completo de actualización de una plantilla:
    1. Descarga el archivo .zip de la plantilla
    2. Descomprime y copia los ficheros al directorio de plantillas
    3. Ejecuta el fichero SQL si existe

    Args:
        server_data (dict): Datos del servidor con las URLs.
        codigo_plantilla (str): Código de la plantilla a actualizar.
        cert_path (str): Ruta al certificado SSL.

    Returns:
        tuple: (bool, str) - (éxito, mensaje informativo)
    """
    # Paso 1: Obtener la URL del .zip
    url_zip = obtener_url_zip_plantilla(server_data, codigo_plantilla)

    if not url_zip:
        return False, f"No se encontró URL de descarga para la plantilla '{codigo_plantilla}'"

    # Paso 2: Descargar el .zip
    exito, resultado = descargar_archivo_zip(url_zip, cert_path)

    if not exito:
        return False, resultado

    contenido_zip = resultado

    # Paso 3: Descomprimir y copiar los ficheros
    directorio_plantillas = resource_path("plantillas")
    exito, resultado = descomprimir_y_copiar_plantilla(contenido_zip, directorio_plantillas)

    if not exito:
        return False, f"Error al descomprimir plantilla: {resultado}"

    ficheros_copiados = resultado

    # Paso 4: Ejecutar el fichero SQL si existe
    url_sql = obtener_url_sql_plantilla(server_data, codigo_plantilla)
    mensaje_sql = ""

    if url_sql:
        exito_sql, contenido_o_error = descargar_fichero_sql(url_sql, cert_path)

        if exito_sql:
            sentencias = parsear_sentencias_sql(contenido_o_error)

            if sentencias:
                exito_ejecucion, mensaje_ejecucion = ejecutar_actualizacion_bd(sentencias)

                if exito_ejecucion:
                    mensaje_sql = f" SQL ejecutado: {mensaje_ejecucion}"
                else:
                    # Si falla el SQL, la actualización se considera fallida
                    return False, f"Ficheros descargados pero error en SQL: {mensaje_ejecucion}"
            else:
                mensaje_sql = " (fichero SQL vacío o sin sentencias válidas)"
        else:
            # Error al descargar el SQL - la actualización falla
            return False, f"Ficheros descargados pero error al obtener SQL: {contenido_o_error}"

    # Éxito total
    ficheros_str = ', '.join(ficheros_copiados)
    return True, f"Ficheros actualizados: {ficheros_str}.{mensaje_sql}"



# ============================================================================
# FUNCIONES PARA ACTUALIZACIÓN DEL EJECUTABLE (.EXE)
# ============================================================================

def obtener_ruta_ejecutable():
    """
    Obtiene la ruta del ejecutable actual.

    Returns:
        str or None: Ruta completa del ejecutable si estamos en modo empaquetado,
                     None si estamos en modo desarrollo.
    """
    log_debug("obtener_ruta_ejecutable() llamada")
    if getattr(sys, 'frozen', False):
        # Estamos ejecutando como .exe empaquetado
        ruta = sys.executable
        log_info(f"Modo ejecutable detectado. Ruta: {ruta}")
        return ruta
    else:
        # Estamos en modo desarrollo
        log_warning("Modo desarrollo detectado. No se puede actualizar.")
        return None


def obtener_directorio_ejecutable():
    """
    Obtiene el directorio donde está el ejecutable.

    Returns:
        str or None: Directorio del ejecutable o None si estamos en desarrollo.
    """
    log_debug("obtener_directorio_ejecutable() llamada")
    ruta_exe = obtener_ruta_ejecutable()
    if ruta_exe:
        directorio = os.path.dirname(ruta_exe)
        log_debug(f"Directorio del ejecutable: {directorio}")
        return directorio
    log_warning("No se pudo obtener directorio del ejecutable (modo desarrollo)")
    return None


def obtener_nombre_base_ejecutable():
    """
    Obtiene el nombre base del ejecutable actual sin la extensión.
    
    Returns:
        str: Nombre base del ejecutable (ej: "ProteccionDatosSIA") o "App" como fallback.
    """
    ruta_exe = obtener_ruta_ejecutable()
    if ruta_exe:
        nombre_completo = os.path.basename(ruta_exe)  # ProteccionDatosSIA.exe
        nombre_base = os.path.splitext(nombre_completo)[0]  # ProteccionDatosSIA
        log_debug(f"Nombre base del ejecutable: {nombre_base}")
        return nombre_base
    log_warning("No se pudo obtener nombre base del ejecutable, usando fallback 'App'")
    return "App"


def hay_actualizacion_exe_pendiente():
    """
    Comprueba si hay una actualización de ejecutable descargada y lista.

    Returns:
        bool: True si existe {NombreApp}_new.exe junto al ejecutable actual
    """
    log_debug("hay_actualizacion_exe_pendiente() llamada")
    directorio = obtener_directorio_ejecutable()
    if not directorio:
        log_debug("No hay directorio ejecutable, retornando False")
        return False

    nombre_base = obtener_nombre_base_ejecutable()
    ruta_nuevo = os.path.join(directorio, f"{nombre_base}_new.exe")
    existe = os.path.exists(ruta_nuevo)
    log_info(f"Verificando {ruta_nuevo}: {'EXISTE' if existe else 'NO EXISTE'}")
    return existe


def obtener_tamanio_archivo_remoto(url, cert_path):
    """
    Obtiene el tamaño del archivo remoto mediante una petición HEAD.

    Args:
        url (str): URL del archivo.
        cert_path (str): Ruta al certificado SSL.

    Returns:
        int or None: Tamaño en bytes o None si no se puede determinar.
    """
    log_debug(f"obtener_tamanio_archivo_remoto() - URL: {url}")
    try:
        response = requests.head(url, verify=cert_path, timeout=10.0, allow_redirects=True)
        response.raise_for_status()
        content_length = response.headers.get('Content-Length')
        if content_length:
            tamanio = int(content_length)
            log_info(f"Tamaño del archivo remoto: {tamanio} bytes ({tamanio/1024/1024:.2f} MB)")
            return tamanio
    except Exception as e:
        log_error(f"Error obteniendo tamaño remoto: {e}")
    return None


def descargar_actualizacion_exe(url, cert_path, callback_progreso=None):
    """
    Descarga el nuevo ejecutable a un archivo temporal junto al actual.

    Args:
        url (str): URL del ejecutable a descargar.
        cert_path (str): Ruta al certificado SSL.
        callback_progreso (callable, optional): Función que recibe (bytes_descargados, bytes_totales)
                                                 para reportar progreso.

    Returns:
        tuple: (bool, str) - (éxito, ruta_destino o mensaje_error)
    """
    log_info("=" * 60)
    log_info("INICIANDO DESCARGA DE ACTUALIZACIÓN")
    log_info("=" * 60)
    log_info(f"URL: {url}")
    log_info(f"Certificado: {cert_path}")

    directorio = obtener_directorio_ejecutable()
    if not directorio:
        log_error("No se puede actualizar en modo desarrollo")
        return False, "No se puede actualizar en modo desarrollo"

    nombre_base = obtener_nombre_base_ejecutable()
    ruta_destino = os.path.join(directorio, f"{nombre_base}_new.exe")
    ruta_temporal = os.path.join(directorio, f"{nombre_base}_downloading.tmp")

    log_info(f"Directorio destino: {directorio}")
    log_info(f"Archivo temporal: {ruta_temporal}")
    log_info(f"Archivo destino: {ruta_destino}")

    try:
        # Verificar que el certificado existe
        if not os.path.exists(cert_path):
            log_error(f"CERTIFICADO NO ENCONTRADO: {cert_path}")
            return False, f"Certificado SSL no encontrado: {cert_path}"

        log_info("Certificado SSL encontrado")

        # Obtener tamaño total para el progreso
        log_info("Obteniendo tamaño del archivo...")
        tamanio_total = obtener_tamanio_archivo_remoto(url, cert_path)

        # Descargar con streaming
        log_info("Iniciando descarga con streaming...")
        response = requests.get(url, verify=cert_path, timeout=300.0, stream=True)
        response.raise_for_status()
        log_info(f"Respuesta HTTP: {response.status_code}")

        # Si no obtuvimos el tamaño con HEAD, intentar del response
        if not tamanio_total:
            tamanio_total = int(response.headers.get('Content-Length', 0))
            log_info(f"Tamaño obtenido de headers: {tamanio_total} bytes")

        bytes_descargados = 0

        log_info("Escribiendo archivo...")
        with open(ruta_temporal, 'wb') as f:
            for chunk in response.iter_content(chunk_size=65536):  # 64KB chunks
                if chunk:
                    f.write(chunk)
                    bytes_descargados += len(chunk)

                    # Reportar progreso si hay callback
                    if callback_progreso and tamanio_total > 0:
                        callback_progreso(bytes_descargados, tamanio_total)

        log_info(f"Descarga completada: {bytes_descargados} bytes")

        # Verificar que se descargó correctamente (tamaño mínimo razonable: 1MB)
        tamanio_descargado = os.path.getsize(ruta_temporal)
        log_info(f"Tamaño del archivo descargado: {tamanio_descargado} bytes")

        if tamanio_descargado < 1024 * 1024:  # Menos de 1MB es sospechoso
            log_error(f"Archivo demasiado pequeño: {tamanio_descargado} bytes")
            os.remove(ruta_temporal)
            return False, f"El archivo descargado es demasiado pequeño ({tamanio_descargado} bytes)"

        # Verificar que es un ejecutable PE válido (comienza con MZ)
        try:
            with open(ruta_temporal, 'rb') as f:
                header = f.read(2)
                if header != b'MZ':
                    log_error(f"El archivo descargado NO es un ejecutable válido. Header: {header}")
                    # Leer los primeros bytes para diagnóstico
                    f.seek(0)
                    primeros_bytes = f.read(200)
                    log_error(f"Primeros 200 bytes del archivo: {primeros_bytes[:200]}")
                    os.remove(ruta_temporal)
                    return False, "El archivo descargado no es un ejecutable válido. Verifique la URL en el servidor."
                log_info("Verificación PE: El archivo es un ejecutable válido (header MZ)")
        except Exception as e:
            log_error(f"Error verificando header del archivo: {e}")

        # Renombrar de temporal a definitivo
        if os.path.exists(ruta_destino):
            log_info(f"Eliminando archivo destino existente: {ruta_destino}")
            os.remove(ruta_destino)

        log_info(f"Renombrando {ruta_temporal} -> {ruta_destino}")
        os.rename(ruta_temporal, ruta_destino)

        log_info("=" * 60)
        log_info("DESCARGA COMPLETADA EXITOSAMENTE")
        log_info("=" * 60)

        return True, ruta_destino

    except requests.exceptions.SSLError as e:
        log_error(f"ERROR SSL: {e}")
        return False, f"Error de certificado SSL: {e}"

    except requests.exceptions.ConnectionError as e:
        log_error(f"ERROR DE CONEXIÓN: {e}")
        return False, f"Error de conexión: {e}"

    except requests.exceptions.Timeout as e:
        log_error(f"TIMEOUT: {e}")
        return False, f"Timeout durante la descarga: {e}"

    except Exception as e:
        log_error(f"ERROR INESPERADO: {type(e).__name__}: {e}")
        import traceback
        log_error(traceback.format_exc())

        # Limpiar archivos parciales
        for ruta in [ruta_temporal, ruta_destino]:
            if os.path.exists(ruta):
                try:
                    os.remove(ruta)
                    log_info(f"Limpiado archivo parcial: {ruta}")
                except:
                    pass
        return False, f"Error descargando actualización: {e}"


def generar_script_actualizacion():
    """
    Genera el script batch que realizará el reemplazo del ejecutable.

    El script:
    1. Espera a que el proceso original termine
    2. Hace backup del .exe viejo
    3. Renombra el nuevo al nombre original
    4. Limpia archivos temporales
    5. Muestra mensaje de éxito (el usuario relanza manualmente)
    6. Se auto-elimina

    Returns:
        tuple: (bool, str) - (éxito, ruta_script o mensaje_error)
    """
    ruta_exe_actual = obtener_ruta_ejecutable()
    if not ruta_exe_actual:
        return False, "No se puede actualizar en modo desarrollo"

    directorio = os.path.dirname(ruta_exe_actual)
    nombre_exe = os.path.basename(ruta_exe_actual)
    nombre_base = obtener_nombre_base_ejecutable()
    ruta_script = os.path.join(directorio, "updater.bat")

    # Nombres de archivos derivados del nombre base del ejecutable
    archivo_nuevo = f"{nombre_base}_new.exe"
    archivo_tmp = f"{nombre_base}_downloading.tmp"
    archivo_log = f"{nombre_base}_update.log"

    # Script batch para actualización
    # Usamos cuadros abiertos por la derecha para que no dependan del largo del nombre
    contenido_script = f'''@echo off
chcp 65001 > nul
title {nombre_base} - Actualizando...
color 1F

echo.
echo  ╔═══════════════════════════════════════════════════════════
echo  ║
echo  ║   {nombre_base} - Actualizador
echo  ║
echo  ╚═══════════════════════════════════════════════════════════
echo.
echo  Esperando a que la aplicacion se cierre...

:wait_loop
tasklist /FI "IMAGENAME eq {nombre_exe}" 2>NUL | find /I /N "{nombre_exe}" >NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak > nul
    goto wait_loop
)

echo.
echo  Aplicacion cerrada. Instalando actualizacion...
echo.

:: Pausa para asegurar liberacion de archivos
timeout /t 3 /nobreak > nul

:: Cambiar al directorio del ejecutable
cd /d "{directorio}"

:: Verificar que existe el archivo nuevo
if not exist "{archivo_nuevo}" (
    color 4F
    echo.
    echo  ╔═══════════════════════════════════════════════════════════
    echo  ║  ERROR: No se encontro el archivo de actualizacion
    echo  ╚═══════════════════════════════════════════════════════════
    echo.
    echo  Pulse cualquier tecla para salir...
    pause > nul
    exit
)

:: Hacer backup del ejecutable actual
if exist "{nombre_exe}" (
    echo  [1/3] Creando copia de seguridad...
    if exist "{nombre_exe}.bak" del /F /Q "{nombre_exe}.bak"
    ren "{nombre_exe}" "{nombre_exe}.bak"
    if errorlevel 1 (
        color 4F
        echo.
        echo  ╔═══════════════════════════════════════════════════════════
        echo  ║  ERROR: No se pudo crear la copia de seguridad
        echo  ║  Cierre todas las instancias e intente de nuevo.
        echo  ╚═══════════════════════════════════════════════════════════
        echo.
        echo  Pulse cualquier tecla para salir...
        pause > nul
        exit
    )
)

:: Renombrar el nuevo ejecutable
echo  [2/3] Instalando nueva version...
ren "{archivo_nuevo}" "{nombre_exe}"
if errorlevel 1 (
    color 4F
    echo.
    echo  ╔═══════════════════════════════════════════════════════════
    echo  ║  ERROR: No se pudo instalar la nueva version
    echo  ╚═══════════════════════════════════════════════════════════
    echo.
    echo  Restaurando version anterior...
    if exist "{nombre_exe}.bak" ren "{nombre_exe}.bak" "{nombre_exe}"
    echo  Pulse cualquier tecla para salir...
    pause > nul
    exit
)

:: Limpiar archivos temporales
echo  [3/3] Limpiando archivos temporales...
if exist "{nombre_exe}.bak" del /F /Q "{nombre_exe}.bak"
if exist "{archivo_tmp}" del /F /Q "{archivo_tmp}"
if exist "{archivo_log}" del /F /Q "{archivo_log}"

:: Mensaje de exito
color 2F
echo.
echo  ╔═══════════════════════════════════════════════════════════
echo  ║
echo  ║   ACTUALIZACION COMPLETADA EXITOSAMENTE
echo  ║
echo  ║   Ya puede cerrar esta ventana y ejecutar {nombre_base}
echo  ║
echo  ╚═══════════════════════════════════════════════════════════
echo.
echo  Pulse cualquier tecla para cerrar...
pause > nul
exit
'''

    try:
        with open(ruta_script, 'w', encoding='utf-8') as f:
            f.write(contenido_script)

        # Establecer atributo oculto en Windows
        try:
            import subprocess as sp
            sp.run(['attrib', '+H', ruta_script], check=False, capture_output=True)
        except:
            pass  # Si falla, no es crítico

        return True, ruta_script
    except Exception as e:
        return False, f"Error creando script de actualización: {e}"


def ejecutar_actualizacion_exe():
    """
    Ejecuta el proceso de actualización del ejecutable:
    1. Verifica que existe el nuevo ejecutable
    2. Genera el script de actualización
    3. Lanza el script en proceso independiente

    Returns:
        tuple: (bool, str) - (éxito, mensaje)
    """
    import subprocess

    log_info("=" * 60)
    log_info("EJECUTANDO ACTUALIZACIÓN DEL EJECUTABLE")
    log_info("=" * 60)

    # Verificar que existe el nuevo ejecutable
    directorio = obtener_directorio_ejecutable()
    if not directorio:
        log_error("No se puede actualizar en modo desarrollo")
        return False, "No se puede actualizar en modo desarrollo"

    nombre_base = obtener_nombre_base_ejecutable()
    ruta_nuevo = os.path.join(directorio, f"{nombre_base}_new.exe")
    log_info(f"Buscando archivo nuevo: {ruta_nuevo}")

    if not os.path.exists(ruta_nuevo):
        log_error(f"ARCHIVO NO ENCONTRADO: {ruta_nuevo}")
        return False, "No se encontró el archivo de actualización descargado"

    log_info(f"Archivo nuevo encontrado. Tamaño: {os.path.getsize(ruta_nuevo)} bytes")

    # Generar script
    log_info("Generando script de actualización...")
    exito, resultado = generar_script_actualizacion()
    if not exito:
        log_error(f"Error generando script: {resultado}")
        return False, resultado

    ruta_script = resultado
    log_info(f"Script generado: {ruta_script}")

    # Lanzar el script en proceso separado e independiente
    try:
        log_info("Lanzando script de actualización...")

        # En Windows, usamos CREATE_NEW_CONSOLE para que el script tenga su propia ventana
        # y pueda seguir ejecutándose después de que la aplicación principal se cierre.
        # No usamos DETACHED_PROCESS porque es incompatible con CREATE_NEW_CONSOLE.
        # No usamos close_fds=True porque no es compatible con creationflags en Windows.

        # Usar start /B para lanzar en segundo plano, o simplemente CREATE_NEW_CONSOLE
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 1  # SW_SHOWNORMAL - mostrar ventana

        subprocess.Popen(
            ['cmd', '/c', 'start', '', ruta_script],
            cwd=directorio,
            shell=False,
            startupinfo=startupinfo
        )

        log_info("Script lanzado exitosamente")
        log_info("La aplicación se cerrará para permitir la actualización")
        return True, "Script de actualización lanzado. La aplicación se cerrará."
    except Exception as e:
        log_error(f"Error lanzando script: {type(e).__name__}: {e}")
        import traceback
        log_error(traceback.format_exc())
        return False, f"Error lanzando script de actualización: {e}"


def limpiar_actualizacion_pendiente():
    """
    Elimina archivos de actualización pendiente si existen.
    Útil si el usuario cancela o si hay un error.
    """
    directorio = obtener_directorio_ejecutable()
    if not directorio:
        return

    nombre_base = obtener_nombre_base_ejecutable()
    nombre_exe = f"{nombre_base}.exe"

    archivos_a_limpiar = [
        os.path.join(directorio, f"{nombre_base}_new.exe"),
        os.path.join(directorio, f"{nombre_base}_downloading.tmp"),
        os.path.join(directorio, "updater.bat"),
        os.path.join(directorio, f"{nombre_exe}.bak")
    ]

    for archivo in archivos_a_limpiar:
        if os.path.exists(archivo):
            try:
                os.remove(archivo)
            except:
                pass


def limpiar_residuos_actualizacion_anterior():
    """
    Limpia archivos residuales de actualizaciones anteriores.
    Se llama al iniciar la aplicación para mantener el directorio limpio.
    """
    directorio = obtener_directorio_ejecutable()
    if not directorio:
        return

    nombre_base = obtener_nombre_base_ejecutable()
    nombre_exe = f"{nombre_base}.exe"

    archivos_residuales = [
        os.path.join(directorio, f"{nombre_exe}.bak"),
        os.path.join(directorio, f"{nombre_base}_downloading.tmp"),
        os.path.join(directorio, f"{nombre_base}_update.log"),
        os.path.join(directorio, "updater.bat")
    ]

    for archivo in archivos_residuales:
        if os.path.exists(archivo):
            try:
                # Quitar atributo oculto antes de borrar (por si acaso)
                try:
                    import subprocess as sp
                    sp.run(['attrib', '-H', archivo], check=False, capture_output=True)
                except:
                    pass
                os.remove(archivo)
            except:
                pass


# ============================================================================
# FUNCIÓN PRINCIPAL DE VERIFICACIÓN DE ACTUALIZACIONES
# ============================================================================

def verificar_actualizaciones():
    """
    Comprueba si hay nuevas versiones de la aplicación, la base de datos y las plantillas
    disponibles en el servidor.

    NO aplica las actualizaciones automáticamente. Solo detecta y almacena
    la información en actualizaciones_pendientes para que el usuario confirme.

    Returns:
        list: Lista de mensajes para mostrar al usuario
    """
    global actualizaciones_pendientes

    log_info("=" * 60)
    log_info("VERIFICANDO ACTUALIZACIONES")
    log_info("=" * 60)

    messages = []

    # Limpiar actualizaciones pendientes anteriores
    limpiar_actualizaciones_pendientes()

    try:
        # Obtiene la ruta del certificado local de forma segura para el ejecutable
        cert_path = resource_path("server_cert.pem")
        log_info(f"Ruta certificado: {cert_path}")
        log_info(f"Certificado existe: {os.path.exists(cert_path)}")

        log_info(f"URL de actualización: {config.URL_ACTUALIZACION}")
        log_info(f"Versión local: {config.VERSION_APLICACION}")

        # Realiza la petición a la URL del servidor
        log_info("Consultando servidor...")
        response = requests.get(config.URL_ACTUALIZACION, verify=cert_path, timeout=5.0)
        response.raise_for_status()
        log_info(f"Respuesta del servidor: {response.status_code}")

        # Parsea el JSON de la respuesta
        server_data = response.json()
        log_info(f"Datos del servidor recibidos: {list(server_data.keys())}")

        # Guardar datos del servidor y certificado para aplicar después
        actualizaciones_pendientes['server_data'] = server_data
        actualizaciones_pendientes['cert_path'] = cert_path

        # --- Detectar actualización de la aplicación (ejecutable) ---
        local_app_version = packaging.version.parse(config.VERSION_APLICACION)
        server_app_version = packaging.version.parse(server_data.get('app_version', '0.0.0'))

        log_info(f"Versión local app: {local_app_version}")
        log_info(f"Versión servidor app: {server_app_version}")

        if server_app_version > local_app_version:
            ruta_exe = obtener_ruta_ejecutable()
            if ruta_exe:
                app_download_url = server_data.get('app_download_url')
                if app_download_url:
                    actualizaciones_pendientes['exe'] = {
                        'version_actual': config.VERSION_APLICACION,
                        'version_nueva': server_data.get('app_version'),
                        'url': app_download_url
                    }

        # --- Detectar actualización de base de datos ---
        version_local_bd = utils.get_valor_actual_verbd()
        local_db_version = packaging.version.parse(version_local_bd)
        server_db_version = packaging.version.parse(server_data.get('db_version', '0.0.0'))

        if server_db_version > local_db_version:
            db_download_url = obtener_url_actualizacion_para_version(server_data, version_local_bd)
            if db_download_url:
                actualizaciones_pendientes['bd'] = {
                    'version_actual': version_local_bd,
                    'version_nueva': server_data.get('db_version', '0.0.0'),
                    'url': db_download_url
                }

        # --- Detectar actualizaciones de plantillas ---
        plantillas = obtener_codigos_plantillas()
        if plantillas:
            for codigo_plantilla, nombre_fichero in plantillas:
                try:
                    clave_version = f"plantilla_{codigo_plantilla}_version"
                    version_servidor_str = server_data.get(clave_version)

                    if not version_servidor_str:
                        continue

                    version_local_str = get_version_plantilla(codigo_plantilla)
                    if not version_local_str:
                        continue

                    try:
                        version_servidor = packaging.version.parse(version_servidor_str)
                        version_local = packaging.version.parse(version_local_str)
                    except Exception:
                        if version_servidor_str == version_local_str:
                            continue
                        version_servidor = version_servidor_str
                        version_local = version_local_str

                    if version_servidor > version_local:
                        actualizaciones_pendientes['plantillas'].append({
                            'codigo': codigo_plantilla,
                            'version_actual': version_local_str,
                            'version_nueva': version_servidor_str
                        })
                except Exception:
                    pass

        # Generar mensaje si hay actualizaciones
        if hay_actualizaciones_pendientes():
            resumen = obtener_resumen_actualizaciones()
            messages.append((
                f"🔄 Actualizaciones disponibles: {resumen}",
                "warning",
                "actualizaciones_disponibles",
                None
            ))

        log_info(f"Verificación completada. Actualizaciones pendientes: {hay_actualizaciones_pendientes()}")

    except requests.exceptions.Timeout:
        log_warning("Timeout al conectar con el servidor de actualizaciones")
        pass
    except requests.exceptions.ConnectionError as e:
        log_warning(f"Error de conexión: {e}")
        pass
    except requests.exceptions.RequestException as e:
        log_warning(f"Error de red: {e}")
        pass
    except Exception as e:
        log_error(f"Error inesperado: {type(e).__name__}: {e}")
        import traceback
        log_error(traceback.format_exc())

    log_info("=" * 60)
    return messages


def aplicar_actualizaciones_pendientes():
    """
    Aplica todas las actualizaciones pendientes (BD y plantillas).
    El ejecutable se maneja aparte por su flujo especial.

    Returns:
        bool: True si todas las actualizaciones se aplicaron correctamente
    """
    global actualizaciones_pendientes

    exito_general = True

    server_data = actualizaciones_pendientes.get('server_data')
    cert_path = actualizaciones_pendientes.get('cert_path')

    if not server_data or not cert_path:
        return False

    # --- Aplicar actualización de base de datos ---
    if actualizaciones_pendientes['bd']:
        bd = actualizaciones_pendientes['bd']
        exito, mensaje = aplicar_actualizacion_bd(bd['url'], cert_path)

        if exito:
            actualizaciones_pendientes['bd'] = None
        else:
            exito_general = False

    # --- Aplicar actualizaciones de plantillas ---
    plantillas_actualizadas = []
    for pl in actualizaciones_pendientes['plantillas'][:]:  # Copia para iterar
        exito, mensaje = aplicar_actualizacion_plantilla(server_data, pl['codigo'], cert_path)

        if exito:
            plantillas_actualizadas.append(pl)
        else:
            exito_general = False

    # Eliminar plantillas actualizadas de la lista
    for pl in plantillas_actualizadas:
        if pl in actualizaciones_pendientes['plantillas']:
            actualizaciones_pendientes['plantillas'].remove(pl)

    return exito_general
