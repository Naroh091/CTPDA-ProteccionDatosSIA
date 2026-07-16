
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
Módulo principal de la aplicación Flask para la gestión de proyectos ADI.

Este módulo implementa la lógica principal de una aplicación web que permite:
- Crear, seleccionar, actualizar y eliminar proyectos.
- Configurar información inicial de cada proyecto (nombre, fecha, responsable).
- Completar formularios ADI y guardar respuestas asociadas a cada proyecto.
- Definir y justificar elementos adicionales requeridos por el sistema.
- Visualizar el estado de avance de los distintos componentes del proyecto.
- Navegar entre diferentes secciones: proyectos, inicio, ADI, elementos, riesgos, controles, resultados y ayuda.
- Apagar el servidor de forma segura desde la interfaz web.
- Abrir automáticamente el navegador en la página de selección de proyectos al iniciar la aplicación.

Dependencias principales:
- Flask: Framework web para la creación de rutas y gestión de sesiones.
- SQLAlchemy: ORM para la interacción con la base de datos.
- webbrowser, threading, time: Utilidades para abrir el navegador y gestionar el apagado del servidor.
- models, controllers: Módulos internos para la definición de modelos y lógica de negocio.
"""

import os
import sys
import webbrowser
import threading
import time
import traceback
import logging  # 🔇 Añadido para controlar los logs de Flask
import socket  # Para verificar disponibilidad de puertos
import signal  # Para manejar señales de terminación
import atexit  # Para limpieza al cerrar
import shutil  # Para limpieza de directorios temporales
import tempfile  # Para gestión de temporales
import re  # Para extraer versión del mensaje de actualización
from sqlalchemy import and_, func
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, session as flask_session, jsonify
import documentos
from models import (
    AyudaContexto, ConfiguracionCriticidad, ConfiguracionIncompatibilidad,
    DatosControl, DatosElementoControl, Session, Base, TiposDato, ValoresDato,
    engine, Inicio, Pregunta, Respuesta, RespuestasProyecto, DatosElementosAdi,
    Perfil, DatosRiesgo, Riesgo, CategoriaRiesgo, SubElementosAdi, ElementosAdi,
    ConfiguracionFase, cleanup_database,
    # Modelos adicionales para eliminación completa de proyectos
    DatosActividadMonitoreo, DatosControlMonitoreo, DatosDocumento, DatosElementoDocumento,
    # Modelos para Requisitos de Cumplimiento
    ConfiguracionRequisito, ConfiguracionEstadoRequisito, DatosRequisito, ConfiguracionRequisitoControl,
    ConfiguracionCluster, ConfiguracionRiesgoCluster, ConfiguracionRiesgoGlobal, ConfiguracionManualUso
)
from controllers import avanzar_fase_proyecto, convertir_criticidad_a_nivel, get_preguntas_activas, get_subelementos_activos, get_estado_componentes, get_configuracion_automatica, get_ayuda_preguntas, actualizar_riesgos_activos_por_p1 , get_riesgos_para_formulario, actualizar_controles_activos_por_p1, get_controles_para_formulario, obtener_fase_proyecto, retroceder_fase_proyecto, validar_condiciones_cambio_fase, validar_desactivacion_control, get_requisitos_para_formulario, validar_requisito_individual, calcular_riesgo_global, obtener_info_clusters_sistema, obtener_riesgos_por_cluster, obtener_riesgos_especificos_medio, validar_riesgo_global_para_cambio_fase
from flask import send_file, flash
from exportar import exportar_proyecto_db
from importar import importar_proyecto_db
import actualizacion
import config
import monitoreo
from utils import get_valor_actual_verbd
from controllers import crear_nueva_iteracion
from collections import defaultdict

# Módulo de verificación de compatibilidad APP-BD en arranque
import version_check


# ============================================================================
# FUNCIÓN PARA OBTENER MENSAJES DEL SISTEMA DESDE IA_VALDAT
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

# Importar módulo de splash para funciones auxiliares (lock file, etc.)
import splash

# ============================================================================
# SPLASH NATIVO DE PYINSTALLER
# ============================================================================
# pyi_splash solo existe cuando se ejecuta como .exe empaquetado con --splash
# Se muestra DURANTE la descompresión, antes de que Python arranque
# ============================================================================
_pyi_splash_available = False
try:
    import pyi_splash
    _pyi_splash_available = True
except ImportError:
    # No estamos ejecutando como .exe o no se compiló con --splash
    pass


def cerrar_splash_nativo():
    """Cierra el splash nativo de PyInstaller si está disponible."""
    global _pyi_splash_available
    if _pyi_splash_available:
        try:
            pyi_splash.close()
            _pyi_splash_available = False
        except Exception:
            pass


# Importar módulo de splash para funciones auxiliares (lock file, detección de duplicados)
import splash

# ============================================================================
# NOMBRE DE LA APLICACIÓN (detectado desde el ejecutable)
# ============================================================================
def obtener_nombre_aplicacion():
    """
    Obtiene el nombre de la aplicación desde el nombre del ejecutable.

    Si se ejecuta como .exe, extrae el nombre sin la extensión.
    Si se ejecuta como script Python, usa un nombre por defecto.

    Returns:
        str: Nombre de la aplicación (ej: "ProteccionDatosSIA")
    """
    try:
        if getattr(sys, 'frozen', False):
            # Ejecutándose como ejecutable empaquetado (PyInstaller)
            exe_path = sys.executable
            nombre_exe = os.path.basename(exe_path)
            # Quitar extensión .exe si existe
            if nombre_exe.lower().endswith('.exe'):
                nombre_exe = nombre_exe[:-4]
            return nombre_exe
        else:
            # Ejecutándose como script Python (desarrollo)
            return "SupervisionSIA"
    except Exception:
        return "SupervisionSIA"

# Nombre de la aplicación (se usa en templates, mensajes de cierre)
NOMBRE_APLICACION = obtener_nombre_aplicacion()

# Intentar importar psutil (opcional, solo para método de cierre avanzado)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False



def resource_path(relative_path):
    """Resuelve la ruta absoluta para archivos de recursos tanto en desarrollo como en ejecutable empaquetado.

    Args:
        relative_path (str): Ruta relativa al archivo de recurso.

    Returns:
        str: Ruta absoluta al recurso.

    Note:
        Esta función es especialmente útil cuando se usa PyInstaller para empaquetar la aplicación.
    """
    try:
        base_path = sys._MEIPASS  # Ruta base cuando está empaquetado
    except Exception:
        base_path = os.path.abspath(".")  # Ruta base en desarrollo
    return os.path.join(base_path, relative_path)


def is_port_available(port):
    """
    Verifica si un puerto está disponible para uso.

    Args:
        port (int): Número de puerto a verificar.

    Returns:
        bool: True si el puerto está disponible, False si está en uso.
    """
    try:
        # Crear un socket temporal para verificar el puerto
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)  # Timeout de 1 segundo
            # Intentar enlazar al puerto
            s.bind(('127.0.0.1', port))
            return True
    except (socket.error, OSError) as e:
        # El puerto está en uso o hay un error
        return False


def find_available_port(start_port=5000, max_attempts=20):
    """
    Busca un puerto disponible comenzando desde start_port.

    Args:
        start_port (int): Puerto inicial desde donde comenzar la búsqueda. Por defecto 5000.
        max_attempts (int): Número máximo de puertos a probar. Por defecto 20.

    Returns:
        int: Número de puerto disponible encontrado.

    Raises:
        RuntimeError: Si no se encuentra ningún puerto disponible después de max_attempts intentos.
    """

    for attempt in range(max_attempts):
        port = start_port + attempt

        if is_port_available(port):
            return port
        else:
            pass

    # Si llegamos aquí, no se encontró ningún puerto disponible
    raise RuntimeError(
        f"No se pudo encontrar un puerto disponible después de {max_attempts} intentos. "
        f"Rango probado: {start_port}-{start_port + max_attempts - 1}. "
        f"Por favor, cierre otras aplicaciones y vuelva a intentar."
    )


# Configuración de rutas para plantillas y archivos estáticos
template_folder = resource_path("templates")
static_folder = resource_path("static")

# Inicialización de la aplicación Flask
app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
app.secret_key = "h7G@d93kf!kLzPq9zXw39Lk1"  # Clave secreta para sesiones

# 🔇 Configuración para silenciar logs de peticiones HTTP (incluyendo heartbeat)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Solo mostrar errores, no peticiones normales

#log.setLevel(logging.DEBUG)     # Muestra TODO (DEBUG, INFO, WARNING, ERROR, CRITICAL)
#log.setLevel(logging.INFO)      # Muestra INFO, WARNING, ERROR, CRITICAL
#log.setLevel(logging.WARNING)   # Muestra WARNING, ERROR, CRITICAL
#log.setLevel(logging.ERROR)     # Muestra ERROR, CRITICAL
#log.setLevel(logging.CRITICAL)  # Solo CRITICAL

# Crear tablas en la base de datos si no existen
app.register_blueprint(exportar_proyecto_db)
app.register_blueprint(importar_proyecto_db)


# ============================================================================
# CONTEXT PROCESSOR - Variables globales disponibles en todos los templates
# ============================================================================
@app.context_processor
def inject_app_name():
    """
    Inyecta el nombre de la aplicación en todos los templates.

    Esto permite usar {{ nombre_aplicacion }} en cualquier template
    sin necesidad de pasarlo explícitamente en cada render_template.
    """
    return {
        'nombre_aplicacion': NOMBRE_APLICACION
    }


# ============================================================================
# SISTEMA DE VERIFICACIÓN DE ACTUALIZACIONES
# ============================================================================
# Variable para ejecutar la verificación solo una vez al arrancar
actualizaciones_verificadas = False
mensajes_actualizacion = []  # Almacena los mensajes para mostrarlos una sola vez
actualizacion_exe_disponible = False  # Flag para mostrar el banner de actualización
actualizacion_exe_url = None  # URL de descarga del nuevo ejecutable
actualizacion_exe_version = None  # Versión disponible del nuevo ejecutable

# ============================================================================
# SISTEMA DE AUTO-CIERRE MEJORADO CON HEARTBEAT
# ============================================================================
# Variables de control
ultimo_heartbeat = time.time()
shutdown_requested = False
cierre_en_progreso = False  # 🔒 Nueva bandera para evitar múltiples cierres
lock_cierre = threading.Lock()  # 🔒 Lock para sincronización


def force_shutdown():
    """
    Función mejorada para forzar el cierre completo de la aplicación.
    Usa múltiples métodos para asegurar que el proceso se cierre correctamente.
    Incluye limpieza de archivos temporales del sistema de ofuscación.

    🔒 Thread-safe: Solo permite una ejecución simultánea.
    """
    global cierre_en_progreso

    # Evitar múltiples ejecuciones simultáneas
    with lock_cierre:
        if cierre_en_progreso:
            return
        cierre_en_progreso = True


    try:
        # Método 1: Cerrar todas las conexiones de base de datos
        try:
            # Verificar si Session es scoped_session (tiene remove()) o sessionmaker
            if hasattr(Session, 'remove'):
                Session.remove()
            engine.dispose()
        except Exception as e:
            pass

        # Método 1.5: Esperar a que Windows libere los archivos (crítico en Windows)
        try:
            time.sleep(1.0)  # 🔧 Aumentado de 0.5 a 1.0 segundos para mayor confiabilidad
        except Exception as e:
            pass

        # Método 2: Limpiar archivos temporales del sistema de ofuscación
        try:
            cleanup_database()
        except Exception as e:
            pass
            # No es crítico, continuar con el cierre

        # Método 3: Intentar sys.exit() primero (más limpio)
        try:
            sys.exit(0)
        except SystemExit:
            pass

        # Método 4: Si sys.exit no funciona, usar os._exit
        os._exit(0)

    except Exception as e:

        # Método 5: Último recurso - matar el proceso directamente
        try:
            if PSUTIL_AVAILABLE:
                current_process = psutil.Process(os.getpid())
                current_process.kill()
            else:
                # Si psutil no está disponible, usar signal directamente
                os.kill(os.getpid(), signal.SIGTERM)
        except Exception as e2:
            # Último recurso absoluto
            try:
                os.kill(os.getpid(), signal.SIGKILL)
            except Exception as e3:
                pass  # Si llegamos aquí, no hay nada más que hacer


def limpiar_temporales_huerfanos():
    """
    Limpia directorios temporales huérfanos al iniciar la aplicación.

    Cuando la aplicación se cierra abruptamente (Ctrl+C, kill, etc.), pueden
    quedar directorios temporales sin limpiar. Esta función los detecta y elimina.

    IMPORTANTE: NO elimina el directorio temporal que está siendo usado actualmente.
    """
    # Obtener el directorio temporal actual (el que está en uso)
    from models import db_manager
    current_temp_dir = db_manager.temp_dir if db_manager and db_manager.temp_dir else None

    temp_root = tempfile.gettempdir()
    cleaned = 0
    skipped = 0

    try:
        for item in os.listdir(temp_root):
            if item.startswith('supervisionsia_'):
                temp_path = os.path.join(temp_root, item)

                # NO eliminar el directorio temporal actual
                if current_temp_dir and os.path.normpath(temp_path) == os.path.normpath(current_temp_dir):
                    skipped += 1
                    continue

                if os.path.isdir(temp_path):
                    try:
                        # Intentar eliminar el directorio
                        shutil.rmtree(temp_path)
                        cleaned += 1
                    except (PermissionError, OSError):
                        # Está en uso o protegido, omitir
                        skipped += 1

        if cleaned > 0:
            pass
        if skipped > 0:
            pass
    except Exception as e:
        # No es crítico si falla, solo informar
        pass


def cleanup_handler():
    """
    Handler de limpieza para atexit y señales.
    Se ejecuta automáticamente al cerrar la aplicación de forma limpia.
    """
    try:
        engine.dispose()
        time.sleep(0.5)
        cleanup_database()
    except Exception as e:
        pass


# ============================================================================
# REGISTRAR HANDLERS DE CIERRE
# ============================================================================
# Estos handlers aseguran que los archivos temporales se limpien correctamente
# incluso cuando la aplicación se cierra con Ctrl+C o señales del sistema

# Handler para cierre normal (cuando Python termina normalmente)
atexit.register(cleanup_handler)

# Handlers para señales (Ctrl+C, kill, etc.)
def signal_handler_custom(signum, frame):
    """Handler para señales de cierre (SIGINT, SIGTERM)."""
    force_shutdown()

# Registrar para las señales comunes (solo en sistemas que las soporten)
try:
    signal.signal(signal.SIGINT, signal_handler_custom)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler_custom)  # kill comando
except (AttributeError, ValueError):
    # Algunas señales pueden no estar disponibles en todos los sistemas
    pass


@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    """
    Recibe señales de latido (heartbeat) del cliente y actualiza la marca de tiempo del último latido.

    Esta función está diseñada para ser llamada por los clientes para indicar que siguen activos.
    Actualiza la variable global `ultimo_heartbeat` con el tiempo actual y retorna una respuesta
    vacía con el código HTTP 204 (Sin contenido).

    Retorna:
        tuple: Una cadena vacía y el código HTTP 204.
    """
    global ultimo_heartbeat
    ahora = time.time()
    tiempo_desde_ultimo = ahora - ultimo_heartbeat
    ultimo_heartbeat = ahora


    return '', 204


@app.route('/heartbeat_end', methods=['POST'])
def heartbeat_end():
    """
    Se ejecuta cuando el usuario cierra la pestaña o el navegador.
    Versión mejorada que garantiza el cierre del proceso.

    🔧 MEJORA: Thread NO daemon para asegurar que el cierre se complete.
    """
    global shutdown_requested

    try:

        shutdown_requested = True

        # 🔧 CAMBIO CRÍTICO: Thread NO daemon para asegurar el cierre completo
        def shutdown_with_delay():
            """Thread que ejecuta el cierre con delay para mostrar la respuesta"""
            time.sleep(2.0)  # Tiempo para que la respuesta HTTP se envíe
            force_shutdown()

        # Thread NO daemon: se completará incluso si el proceso principal termina
        shutdown_thread = threading.Thread(target=shutdown_with_delay, daemon=False)
        shutdown_thread.start()

        return '', 204

    except Exception as e:
        traceback.print_exc()
        # Aún así, intentar cerrar
        threading.Thread(target=force_shutdown, daemon=False).start()
        return '', 500




# ============================================================================
# MONITOR DE HEARTBEAT - DETECCIÓN PASIVA DE DESCONEXIÓN
# ============================================================================

def monitor_heartbeat():
    """
    🔧 MONITOR DE HEARTBEAT - MODO SOLO MONITOREO

    Este monitor supervisa los heartbeats pero NO cierra la aplicación por timeout.
    La aplicación solo se cierra cuando:
    - El usuario cierra explícitamente la pestaña/navegador (señal /heartbeat_end)
    - Se solicita cierre explícito (shutdown_requested)

    Los heartbeats sirven para:
    - Monitoreo de conexión en logs
    - Debugging
    - Visibilidad del estado de la aplicación

    🔥 NO HAY CIERRE AUTOMÁTICO POR TIMEOUT - Solo por señal explícita
    """
    global ultimo_heartbeat, shutdown_requested

    # 🔧 Valores importados desde config.py
    INTERVALO_VERIFICACION = config.INTERVALO_VERIFICACION

    while True:
        try:
            time.sleep(INTERVALO_VERIFICACION)

            tiempo_sin_heartbeat = time.time() - ultimo_heartbeat

            # ⚠️ ADVERTENCIA si hace mucho sin heartbeat (pero NO cerrar)
            if tiempo_sin_heartbeat > 300:  # 5 minutos
                pass  # Solo advertencia, no cerrar

            # ✅ Detectar cierre explícito solicitado (ÚNICA forma de cerrar)
            if shutdown_requested:
                force_shutdown()
                break

        except Exception as e:
            traceback.print_exc()

# 🔧 CRÍTICO: Iniciar el monitor como thread NO daemon
# Esto asegura que el monitor siempre funcione y pueda completar el cierre
import uuid
monitor_thread = threading.Thread(target=monitor_heartbeat, daemon=False)
monitor_thread.start()

# ============================================================================
# FIN DEL SISTEMA DE AUTO-CIERRE
# ============================================================================


@app.route("/guardar-inicio", methods=["POST"])
def guardar_inicio():

    """
    Guarda o actualiza la configuración inicial del proyecto.

    Procesa los datos enviados por POST desde el formulario de inicio, valida los campos requeridos,
    crea o actualiza el proyecto en la base de datos, y determina si el proyecto está completo.
    Si algún campo está vacío o la fecha es inválida, muestra un mensaje de error.
    Al guardar correctamente, actualiza la sesión con el ID del proyecto.

    Returns:
        Response: Renderiza la plantilla 'index.html' con mensaje de estado, datos del proyecto y estado de completitud.
    """
    session = Session()
    nombre = request.form.get("nombre_proyecto", "").strip()
    fecha_inicio = request.form.get("fecha_inicio", "").strip()
    dpd = request.form.get("dpd_responsable", "").strip()
    configuracion_automatica = {}

    estado = "Configurado" if nombre and fecha_inicio and dpd else "Pendiente de configuración"

    datos_form = {
        "nombre_proyecto": nombre,
        "fecha_inicio": fecha_inicio,
        "dpd_responsable": dpd,
        "estado": estado
    }

    if estado == "Pendiente de configuración":
        session.close()
        return render_template("index.html", mensaje="⚠️ Todos los campos son obligatorios", datos=datos_form)

    try:
        fecha_obj = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        fecha_guardar = fecha_obj.strftime("%Y-%m-%d")
    except ValueError:
        session.close()
        return render_template("index.html", mensaje="⚠️ Fecha inválida", datos=datos_form)

    id_sistema = flask_session.get("id_sistema")
    proyecto = None

    if id_sistema:
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        configuracion_automatica = get_configuracion_automatica(id_sistema)

    if proyecto:
        # Actualizar proyecto existente
        proyecto.D_NOMPROYEC = nombre
        proyecto.F_INI = fecha_guardar
        proyecto.T_DPD = dpd
        proyecto.T_ESTADO_PROYEC = "Configurado"
        mensaje = "✅ Proyecto actualizado correctamente"
    else:
        # --- OBTENER FASE INICIAL (menor N_ORDEN) ---
        fase_inicial = session.query(ConfiguracionFase)\
        .filter(ConfiguracionFase.N_ORDEN.isnot(None))\
        .order_by(ConfiguracionFase.N_ORDEN.asc())\
        .first()

        # Si no existe fase, usar None; de lo contrario, usar el ID
        id_fase_inicial = fase_inicial.ID_FASE if fase_inicial else None

        if not fase_inicial:
            pass
        else:
            pass


        # Crear nuevo proyecto
        ultimo = session.query(Inicio).order_by(Inicio.ID_SISTEMA.desc()).first()
        nuevo_id = 110 if not ultimo else ultimo.ID_SISTEMA + 100
        proyecto = Inicio(
            ID_SISTEMA=nuevo_id,
            D_NOMPROYEC=nombre,
            F_INI=fecha_guardar,
            T_DPD=dpd,
            T_ESTADO_PROYEC="Configurado",
            N_FASE=id_fase_inicial
        )
        session.add(proyecto)
        mensaje = "✅ Proyecto guardado correctamente"
        flask_session["id_sistema"] = nuevo_id

        # --- insertar riesgos en IA_DATRIESGOS ---
        # Solo copiar riesgos activos (L_ESTADO = 1)
        riesgos = session.query(Riesgo).filter(Riesgo.L_ESTADO == 1).all()
        max_id_riesgos = session.query(func.max(DatosRiesgo.ID_DATRIES)).scalar() or 10

        nuevos_registros_riesgos = []
        for idx, riesgo in enumerate(riesgos, start=1):
            nuevos_registros_riesgos.append(
                DatosRiesgo(
                    ID_DATRIES=max_id_riesgos + (idx * 100),
                    SIST_ID_SISTEMA=nuevo_id,
                    RIE_ID_RIESGO=riesgo.ID_RIESGO,
                    L_ACTIVA=0
                )
            )
        session.add_all(nuevos_registros_riesgos)

        # ✅ AGREGAR ESTO: Crear registros en IA_DATELEMADI
        # Obtener el máximo ID_DATELEMADI
        max_id_elementos = session.query(func.max(DatosElementosAdi.ID_DATELEMADI)).scalar() or 10
        id_counter = max_id_elementos + 100

        # Obtener todos los elementos activos
        elementos_activos = session.query(ElementosAdi).filter(
            ElementosAdi.L_ESTADO == 1
        ).all()

        nuevos_registros_elementos = []
        for elemento in elementos_activos:
            # Obtener subelementos activos del elemento
            subelementos_activos = session.query(SubElementosAdi).filter(
                SubElementosAdi.ELE_ID_ELEM == elemento.ID_ELEM,
                SubElementosAdi.L_ESTADO == 1
            ).all()

            # Crear un registro por cada subelemento con N_ITERACION = 1
            for subelemento in subelementos_activos:
                nuevos_registros_elementos.append(
                    DatosElementosAdi(
                        ID_DATELEMADI=id_counter,
                        SIST_ID_SISTEMA=nuevo_id,
                        ELE_ID_ELEM=elemento.ID_ELEM,
                        SUB_IDSUBELEM=subelemento.ID_SUBELEM,
                        T_DESCRIPCION="",
                        N_ITERACION=1
                    )
                )
                id_counter += 100

        session.add_all(nuevos_registros_elementos)

        # ✅ AGREGAR ESTO: Crear registros en IA_DATELEMCONTR
        # Obtener el máximo ID_DATELEMCONTR
        max_id_elementos_control = session.query(func.max(DatosElementoControl.ID_DATELEMCONTR)).scalar() or 10
        id_counter_control = max_id_elementos_control + 100

        # Obtener todos los elementos activos
        elementos_activos = session.query(ElementosAdi).filter(
            ElementosAdi.L_ESTADO == 1
        ).all()

        nuevos_registros_elementos_control = []
        for elemento in elementos_activos:
            nuevos_registros_elementos_control.append(
                DatosElementoControl(
                    ID_DATELEMCONTR=id_counter_control,
                    SIST_ID_SISTEMA=nuevo_id,
                    ELE_ID_ELEM=elemento.ID_ELEM,
                    L_TRASLAPLI=None,
                    V_INTSCONDES=None,
                    T_ESPCLAUSULA="",         # Vacío por defecto
                    N_ITERACION=0
                )
            )
            id_counter_control += 100

        session.add_all(nuevos_registros_elementos_control)

        # ============================================================================
        # ✅ NUEVO: Inicializar requisitos de cumplimiento para el nuevo proyecto
        # ============================================================================

        # Obtener el máximo ID_DATREQ
        max_id_requisitos = session.query(func.max(DatosRequisito.ID_DATREQ)).scalar() or 10
        id_counter_requisitos = max_id_requisitos + 100

        # Obtener todos los requisitos activos del catálogo
        requisitos_activos = session.query(ConfiguracionRequisito).filter(
            ConfiguracionRequisito.L_ESTADO == 1
        ).all()

        # Obtener estados iniciales dinámicamente usando L_INICIAL
        # Estado inicial de Planificación (tipo 'P')
        estado_inicial_planif = session.query(ConfiguracionEstadoRequisito).filter(
            ConfiguracionEstadoRequisito.L_INICIAL == 1,
            ConfiguracionEstadoRequisito.C_TIPOESTADO == 'P'
        ).first()

        # Estado inicial de Cumplimiento (tipo 'C')
        estado_inicial_cumpl = session.query(ConfiguracionEstadoRequisito).filter(
            ConfiguracionEstadoRequisito.L_INICIAL == 1,
            ConfiguracionEstadoRequisito.C_TIPOESTADO == 'C'
        ).first()

        id_estado_planif = estado_inicial_planif.ID_ESTREQ if estado_inicial_planif else None
        id_estado_cumpl = estado_inicial_cumpl.ID_ESTREQ if estado_inicial_cumpl else None

        # Logs informativos
        if not estado_inicial_planif:
            pass
        else:
            pass

        if not estado_inicial_cumpl:
            pass
        else:
            pass

        # Crear un registro por cada requisito activo
        nuevos_registros_requisitos = []
        for requisito in requisitos_activos:
            # L_APLICA según L_APLICAOBLIG:
            # Si L_APLICAOBLIG = 1 → L_APLICA = 1 (aplica obligatoriamente)
            # Si L_APLICAOBLIG = 0 → L_APLICA = NULL (usuario debe indicarlo)
            l_aplica = 1 if requisito.L_APLICAOBLIG == 1 else None

            nuevos_registros_requisitos.append(
                DatosRequisito(
                    ID_DATREQ=id_counter_requisitos,
                    SIST_ID_SISTEMA=nuevo_id,
                    REQ_ID_REQU=requisito.ID_REQ,
                    L_APLICA=l_aplica,  # Depende de L_APLICAOBLIG
                    T_JUSTAPLICA=None,
                    N_ESTPLANIF=id_estado_planif,  # Estado inicial planificación (ej: "No evaluado")
                    T_JUSTPLANIF=None,
                    N_ESTCUMPL=id_estado_cumpl,  # Estado inicial cumplimiento (ej: "No cumplido")
                    T_JUSTCUMPL=None,
                    L_TRASLAPLI=None,
                    V_INSTRCONTR=None,
                    T_OBSPLIEGO=None,
                    T_PLANMEJORA=None
                )
            )
            id_counter_requisitos += 100

        session.add_all(nuevos_registros_requisitos)
        # ============================================================================
        # FIN DE INICIALIZACIÓN DE REQUISITOS
        # ============================================================================

    proyecto_completo = bool(nombre.strip() and fecha_inicio.strip() and dpd.strip())

    # === CREAR REGISTROS DE DOCUMENTOS ===
    try:
        import documentos as doc_module
        doc_module.inicializar_documentos_proyecto(session, nuevo_id)
    except Exception as e:
        pass
        # No bloquear la creación del proyecto si falla esto

    session.commit()

    # Obtener fase actual DESPUÉS del commit
    fase_actual_info = None
    id_sistema_actual = id_sistema if id_sistema else nuevo_id

    if id_sistema_actual:
        # Refrescar el objeto proyecto después del commit
        session.expire_all()
        proyecto_actualizado = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema_actual).first()

        if proyecto_actualizado and proyecto_actualizado.N_FASE:
            fase_config = session.query(ConfiguracionFase).filter_by(
                ID_FASE=proyecto_actualizado.N_FASE
            ).first()
            if fase_config:
                fase_actual_info = {
                    "nombre": fase_config.D_FASE,
                    "orden": fase_config.N_ORDEN,
                    "es_monitoreo": fase_config.L_MONITOREO == 1
                }

    session.close()

    return render_template(
        "index.html",
        mensaje=mensaje,
        datos=datos_form,
        proyecto_completo=proyecto_completo,
        configuracion_automatica=configuracion_automatica,
        fase_actual=fase_actual_info
        )

@app.route("/anadir-iteracion", methods=["POST"])
def anadir_iteracion_route():
    """
    Gestiona la creación de una nueva iteración (tratamiento) para un sistema y elemento dados.
    Espera un JSON con la siguiente estructura:
        {
            "id_elemento": <int>
        }
    El ID del sistema ('id_sistema') se obtiene de la sesión de Flask.
    Retorna:
        - 200 OK: Si la nueva iteración se crea correctamente. Devuelve los datos de la nueva iteración.
        - 400 Bad Request: Si faltan los IDs requeridos o son inválidos.
        - 404 Not Found: Si ocurre un ValueError durante la creación.
        - 500 Internal Server Error: Para errores inesperados durante la creación.
    Excepciones:
        ValueError: Si los IDs no son enteros válidos o si la función de creación lanza un ValueError.
        Exception: Para cualquier otro error inesperado.
    """

    # Se espera JSON: {"id_sistema", "id_elemento"}
    data = request.get_json()
    id_sistema = flask_session.get('id_sistema') # Usar la sesión para el ID del sistema
    id_elemento = data.get('id_elemento')

    if not id_sistema:
        return jsonify({"success": False, "message": "ID del sistema no encontrado en sesión."}), 400

    if not id_elemento:
        return jsonify({"success": False, "message": "ID del elemento no proporcionado."}), 400

    try:
        id_sistema = int(id_sistema)
        id_elemento = int(id_elemento)
    except ValueError:
        return jsonify({"success": False, "message": "IDs inválidos."}), 400

    try:
        nueva_iteracion = crear_nueva_iteracion(id_sistema, id_elemento)

        return jsonify({
            "success": True,
            "message": f"Nueva tratamiento creado correctamente.",
            "new_iteration": nueva_iteracion
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 404
    except Exception as e:
        return jsonify({"success": False, "message": "Error interno del servidor al crear la iteración."}), 500

@app.context_processor
def inject_date():
    """
    Devuelve un diccionario con la fecha actual en formato ISO para inyectarla en todas las plantillas.

    Esta función se utiliza como procesador de contexto en Flask para que la fecha actual
    esté disponible en todas las plantillas renderizadas.

    Retorno:
        dict: Un diccionario con la clave 'today_date' y el valor de la fecha actual como cadena en formato ISO (YYYY-MM-DD).
    """
    return dict(today_date=date.today().isoformat())


@app.context_processor
def inject_heartbeat_config():
    """
    Inyecta la configuración del sistema de heartbeat en todas las plantillas.
    Permite que base.html acceda a los valores de config.py para pasarlos a JavaScript.
    """
    return dict(config=config)

# Nuevo procesador de contexto para inyectar la versión en todas las plantillas
@app.context_processor
def inject_version_info():
    """
    Inyecta información de versión de la aplicación y la base de datos en el contexto de las plantillas Jinja2.
    Obtiene la versión de la aplicación desde la configuración y la versión actual de la base de datos.
    Si ocurre un error al obtener la versión de la base de datos, se indica el error en la versión mostrada.
    También agrega la fecha actual en formato ISO.
    Returns:
        dict: Un diccionario con las claves 'version_software' (versión completa de la aplicación y base de datos).

    Excepciones:
        Captura cualquier error al obtener la versión de la base de datos y maneja el error mostrando
        un marcador de error en la versión.

    Nota: Este procesador de contexto se ejecuta automáticamente antes de renderizar cualquier plantilla.
    """
    # Obtener la versión de la aplicación desde config.py
    app_version = config.VERSION_APLICACION

    try:
        # Obtener la versión actual de la base de datos
        db_version = get_valor_actual_verbd()

        # Concatenar en el formato deseado: version_aplicacion - version_bd
        version_completa = f"{app_version}-{db_version}"
    except Exception as e:
        # Manejo de errores en caso de que la BD no esté disponible (ej. al inicio o error de conexión)
        # Mostrar solo la versión de la aplicación con un marcador de error para la BD
        version_completa = f"{app_version}-BD_Error"

    # La clave 'version_software' estará disponible en todas las plantillas
    return dict(version_software=version_completa)

@app.template_filter('count_active')
def count_active_filter(items):
    """
    Filtro Jinja2 que cuenta solo los elementos con L_ACTIVA=1.

    Args:
        items: Lista de objetos que tienen el atributo L_ACTIVA

    Returns:
        int: Número de elementos activos
    """
    if not items:
        return 0
    return sum(1 for item in items if getattr(item, 'L_ACTIVA', 0) == 1)

@app.context_processor
def inject_fase_y_perfil():
    """
    Inyecta la fase actual, la configuración automática (incluyendo perfil),
    el nombre del proyecto y las respuestas ADI en todas las plantillas que usan base.html.
    """
    id_sistema = flask_session.get("id_sistema")
    fase_actual_info = None
    configuracion_automatica = {}
    nombre_proyecto_actual = None
    respuestas_adi = {}  # Para sistema de visibilidad dinámica

    if id_sistema:
        session = Session()
        try:
            # --- Proyecto y fase actual ---
            proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
            if proyecto:
                # Obtener nombre del proyecto
                nombre_proyecto_actual = proyecto.D_NOMPROYEC

                # Obtener fase actual
                if proyecto.N_FASE:
                    fase_config = session.query(ConfiguracionFase).filter_by(
                        ID_FASE=proyecto.N_FASE
                    ).first()
                    if fase_config:
                        fase_actual_info = {
                            "nombre": fase_config.D_FASE,
                            "orden": fase_config.N_ORDEN,
                            "es_monitoreo": fase_config.L_MONITOREO == 1
                        }

                # --- Configuración automática (incluye perfil) ---
                # IMPORTANTE: Solo se ejecuta si el proyecto EXISTE en la BD
                configuracion_automatica = get_configuracion_automatica(id_sistema)

                # --- Respuestas ADI para sistema de visibilidad dinámica ---
                try:
                    respuestas_query = session.query(
                        Pregunta.C_PREGUNTA,
                        Respuesta.C_OPCION
                    ).join(
                        RespuestasProyecto,
                        RespuestasProyecto.RES_ID_RESPUESTA == Respuesta.ID_RESPUESTA
                    ).join(
                        Pregunta,
                        Respuesta.PRE_ID_PREGUNTA == Pregunta.ID_PREGUNTA
                    ).filter(
                        RespuestasProyecto.SIST_ID_SISTEMA == id_sistema
                    ).all()
                    respuestas_adi = {r[0]: r[1] for r in respuestas_query}
                except Exception as e:
                    respuestas_adi = {}
            else:
                # El ID en sesión no corresponde a un proyecto existente
                # Limpiar la sesión para evitar problemas futuros
                flask_session.pop("id_sistema", None)

        finally:
            session.close()

    return dict(
        fase_actual=fase_actual_info,
        configuracion_automatica=configuracion_automatica,
        nombre_proyecto_actual=nombre_proyecto_actual,
        respuestas_adi=respuestas_adi
    )


@app.route("/seleccionar-proyecto")
def seleccionar_proyecto():
    """
    Muestra la página de selección de proyectos existentes.

    Incluye verificación de actualizaciones y muestra banner si hay
    actualizaciones disponibles (BD, plantillas o ejecutable).

    Returns:
        Response: Renderiza la plantilla 'seleccion_proyecto.html' con la lista de proyectos.
    """
    global actualizaciones_verificadas, mensajes_actualizacion
    global actualizacion_exe_disponible, actualizacion_exe_url, actualizacion_exe_version

    # Verificar actualizaciones solo una vez al arrancar la aplicación
    if not actualizaciones_verificadas:
        mensajes_actualizacion = actualizacion.verificar_actualizaciones()
        actualizaciones_verificadas = True

        # Procesar la información de actualizaciones pendientes
        if actualizacion.hay_actualizaciones_pendientes():
            info_act = actualizacion.obtener_info_actualizaciones()

            # Si hay actualización de ejecutable, guardar sus datos
            if info_act['exe']:
                actualizacion_exe_disponible = True
                actualizacion_exe_url = info_act['exe']['url']
                actualizacion_exe_version = info_act['exe']['version_nueva']

    # Verificar si hay actualización de exe pendiente ya descargada
    tiene_actualizacion_pendiente = actualizacion.hay_actualizacion_exe_pendiente()

    # Obtener resumen de actualizaciones para el banner
    hay_actualizaciones = actualizacion.hay_actualizaciones_pendientes()
    resumen_actualizaciones = actualizacion.obtener_resumen_actualizaciones() if hay_actualizaciones else ""
    info_actualizaciones = actualizacion.obtener_info_actualizaciones() if hay_actualizaciones else None

    session = Session()
    proyectos = session.query(Inicio).all()
    session.close()

    return render_template(
        "seleccion_proyecto.html",
        proyectos=proyectos,
        active_tab="proyectos",
        # Variables para el banner de actualizaciones
        hay_actualizaciones=hay_actualizaciones,
        resumen_actualizaciones=resumen_actualizaciones,
        info_actualizaciones=info_actualizaciones,
        # Variables específicas del ejecutable (para compatibilidad)
        actualizacion_exe_disponible=actualizacion_exe_disponible,
        actualizacion_exe_url=actualizacion_exe_url,
        actualizacion_exe_version=actualizacion_exe_version,
        actualizacion_exe_descargada=tiene_actualizacion_pendiente,
        version_actual=config.VERSION_APLICACION
    )


@app.route("/cargar-proyecto", methods=["POST"])
def cargar_proyecto():
    """Carga un proyecto seleccionado por el usuario y lo establece en la sesión.

    Returns:
        Response: Redirección al índice principal o a la selección de proyectos si no se seleccionó ninguno.
    """
    id_sistema = request.form.get("proyecto_id")
    if not id_sistema:
        return redirect(url_for("seleccionar_proyecto"))

    flask_session["id_sistema"] = int(id_sistema)
    return redirect(url_for("index"))

@app.route("/eliminar-proyecto/<int:proyecto_id>", methods=["POST"])
def eliminar_proyecto(proyecto_id):
    """Elimina un proyecto y todas sus respuestas asociadas.

    Realiza eliminación explícita de todos los registros dependientes para evitar
    registros huérfanos en caso de que el cascade de SQLAlchemy no funcione
    correctamente (por ejemplo, si PRAGMA foreign_keys está desactivado en SQLite).

    Parámetros:
        proyecto_id (int): Identificador único del proyecto a eliminar.
    Returns:
        Response:
            - Si la eliminación es exitosa, retorna un JSON con success=True y una redirección a la vista de selección de proyecto (código 200).
            - Si el proyecto no se encuentra, retorna un JSON con success=False y un mensaje de error (código 404).
            - En caso de error durante el proceso, retorna un JSON con success=False y el mensaje de error (código 500).
    Excepciones:
        Realiza rollback de la sesión en caso de cualquier excepción durante el proceso de eliminación.
    """
    session = Session()
    try:
        # Obtener el proyecto por ID
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=proyecto_id).first()

        if not proyecto:
            return jsonify({"success": False, "error": "Proyecto no encontrado"}), 404

        # =====================================================================
        # ELIMINACIÓN EXPLÍCITA DE TODAS LAS TABLAS DEPENDIENTES
        # Orden: de las tablas más dependientes a las menos dependientes
        # =====================================================================

        # 1. Tablas de monitoreo (dependen de DatosControlMonitoreo)
        deleted_actmonit = session.query(DatosActividadMonitoreo).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 2. Control de monitoreo
        deleted_contmon = session.query(DatosControlMonitoreo).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 3. Elementos de control
        deleted_elemcontr = session.query(DatosElementoControl).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 4. Controles
        deleted_control = session.query(DatosControl).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 5. Riesgos
        deleted_riesgos = session.query(DatosRiesgo).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 6. Elementos de documentos (dependen de DatosDocumento)
        deleted_elemdocs = session.query(DatosElementoDocumento).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 7. Documentos
        deleted_docs = session.query(DatosDocumento).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 8. Elementos ADI
        deleted_elemadi = session.query(DatosElementosAdi).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 9. Respuestas del proyecto (IA_SISTEMAADI)
        deleted_respuestas = session.query(RespuestasProyecto).filter_by(
            SIST_ID_SISTEMA=proyecto_id
        ).delete(synchronize_session=False)

        # 10. Finalmente eliminar el proyecto
        session.delete(proyecto)
        session.commit()

        # Log de eliminación (útil para depuración)

        return jsonify({"success": True, "redirect": url_for("seleccionar_proyecto")}), 200

    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()

@app.route("/exportar-proyecto", methods=["POST"])
def exportar_proyecto():
    """
    Exporta los datos del proyecto seleccionado como un archivo JSON descargable.
    """
    proyecto_id = request.form.get("proyecto_id")
    if not proyecto_id:
        flash("⚠️ Debes seleccionar un proyecto para exportar.", "warning")
        return redirect(url_for("seleccionar_proyecto"))

    archivo_exportado = exportar_proyecto_db(proyecto_id)
    return send_file(archivo_exportado, as_attachment=True)


@app.route("/importar-proyecto", methods=["POST"])
def importar_proyecto():
    """
    Importa un proyecto desde un archivo JSON exportado previamente.
    """
    if "archivo" not in request.files:
        flash("⚠️ No se ha subido ningún archivo.", "danger")
        return redirect(url_for("seleccionar_proyecto"))

    archivo = request.files["archivo"]
    if archivo.filename == "":
        flash("⚠️ El nombre del archivo es inválido.", "danger")
        return redirect(url_for("seleccionar_proyecto"))

    uploads_folder = os.path.join(os.getcwd(), "uploads")
    os.makedirs(uploads_folder, exist_ok=True)

    ruta_guardado = os.path.join(uploads_folder, archivo.filename)
    archivo.save(ruta_guardado)

    try:
        importar_proyecto_db(ruta_guardado)
        flash("✅ Proyecto importado correctamente.", "success")
    except Exception as e:
        flash(f"❌ Error al importar: {str(e)}", "danger")

    return redirect(url_for("seleccionar_proyecto"))

@app.route("/index-nuevo")
def nuevo_proyecto():
    """Inicializa un nuevo proyecto limpiando la sesión existente.

    Returns:
        Response: Redirección al índice principal.
    """
    flask_session.pop("id_sistema", None)
    return redirect(url_for("index"))


@app.route("/")
def index():
    """
    Página principal que muestra el formulario de configuración del proyecto.

    Obtiene el identificador del sistema desde la sesión y consulta la base de datos para recuperar los datos del proyecto asociado.
    Si existe el proyecto, asigna los valores correspondientes (nombre, fecha de inicio, responsable DPD y estado), usando cadenas vacías si algún valor es None.
    Determina si el proyecto está completo verificando que los campos requeridos no estén vacíos.
    Además, obtiene el estado de los componentes del proyecto para mostrar su progreso.
    Renderiza la plantilla 'index.html' pasando los datos del proyecto, un mensaje (si aplica), el estado de completitud del proyecto y los componentes.

    Returns:
        Response: Renderiza la plantilla 'index.html' con los datos del proyecto, mensaje, estado de completitud y componentes si existe.
    """
    id_sistema = flask_session.get("id_sistema")
    datos = {}
    mensaje = None
    proyecto_completo = False
    configuracion_automatica = {}
    fase_actual_info = None
    msg_dpd = None  # Mensaje dinámico para nota DPD

    # --- Obtener componentes SIEMPRE ---
    # get_estado_componentes ahora maneja id_sistema=None y errores
    componentes = get_estado_componentes(id_sistema)

    # --- Obtener mensaje dinámico MSGDPD (siempre, independiente del proyecto) ---
    session = Session()
    try:
        msg_dpd = obtener_mensaje_sistema(session, 'MSGDPD')
    except Exception:
        msg_dpd = None

    if id_sistema:
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()

        # ✅ Obtener información de la fase actual
        if proyecto and proyecto.N_FASE:
            fase_config = session.query(ConfiguracionFase).filter_by(
                ID_FASE=proyecto.N_FASE
            ).first()
            if fase_config:
                fase_actual_info = {
                    "nombre": fase_config.D_FASE,
                    "orden": fase_config.N_ORDEN,
                    "es_monitoreo": fase_config.L_MONITOREO == 1
                }

        if proyecto:
            # Asignamos valores por defecto vacíos si son None
            nombre = proyecto.D_NOMPROYEC or ""
            fecha_inicio = proyecto.F_INI or ""
            dpd_responsable = proyecto.T_DPD or ""

            datos = {
                "nombre_proyecto": nombre,
                "fecha_inicio": fecha_inicio,
                "dpd_responsable": dpd_responsable,
                "estado": proyecto.T_ESTADO_PROYEC or "Pendiente Configuración"
            }

            # Solo se considera completo si los campos están rellenos en la base de datos
            if nombre.strip() and fecha_inicio.strip() and dpd_responsable.strip():
                proyecto_completo = True

            # --- OBTENER CONFIGURACIÓN AUTOMÁTICA ---
            configuracion_automatica = get_configuracion_automatica(id_sistema)

    session.close()

    return render_template(
        "index.html",
        active_tab="inicio",
        datos=datos,
        mensaje=mensaje,
        proyecto_completo=proyecto_completo,
        componentes=componentes,
        configuracion_automatica=configuracion_automatica,
        fase_actual=fase_actual_info,
        msg_dpd=msg_dpd
        )


@app.route("/formulario/adi")
def formulario_adi():
    """
    Gestiona la ruta '/formulario/adi' para mostrar el formulario ADI del proyecto seleccionado.
    Obtiene el ID del proyecto actual desde la sesión. Si no hay proyecto seleccionado, devuelve un error.
    Recupera todas las preguntas y las respuestas guardadas para el proyecto actual desde la base de datos.
    Agrupa las respuestas guardadas por pregunta y cuenta cuántas preguntas tienen al menos una respuesta.
    Calcula el número total de preguntas.

    Renderiza la plantilla 'formulario_adi.html' con las preguntas, respuestas agrupadas, estado de éxito,
    número de preguntas respondidas, total de preguntas y establece la pestaña activa en 'adi'.

    Returns:
        - Plantilla HTML renderizada para el formulario ADI.
        - Mensaje de error con estado 400 si no hay proyecto seleccionado.
    """
    session = Session()
    try:
        id_sistema = flask_session.get("id_sistema")
        if not id_sistema:
            return render_template('modal_proyecto_no_seleccionado.html'), 400

        # --- CALCULAR monitoreo ---
        monitoreo = False # Inicializamos como False
        # Verificar si hay proyecto seleccionado y si está en fase de monitoreo

        try:
            fase_actual, _ = obtener_fase_proyecto(id_sistema)
            if fase_actual and fase_actual.L_MONITOREO == 1:
                monitoreo = True
        except Exception as e:
            pass


        preguntas = get_preguntas_activas()
        respuestas_guardadas = session.query(RespuestasProyecto).filter_by(SIST_ID_SISTEMA=id_sistema).all()

        # Agrupar respuestas por pregunta
        respuestas_dict = {}
        for r in respuestas_guardadas:
            respuestas_dict.setdefault(r.PRE_ID_PREGUNTA, []).append(r.respuesta.C_OPCION)

        # Leer parámetro de éxito de la URL
        exito = request.args.get("exito") == "1"

        # Contar cuántas preguntas tienen al menos una respuesta guardada
        preguntas_respondidas = len([pid for pid in respuestas_dict if respuestas_dict[pid]])

        # Calcular el total de preguntas
        total_preguntas = len(preguntas)


        # Configuración automática
        configuracion = get_configuracion_automatica(id_sistema)


        return render_template(
            "formulario_adi.html",
            preguntas=preguntas,
            respuestas_guardadas=respuestas_dict,
            exito=exito,
            preguntas_respondidas=preguntas_respondidas,
            total_preguntas=total_preguntas,
            configuracion=configuracion,
            monitoreo=monitoreo,
            active_tab="adi"
        )

    finally:
        session.close()

@app.route("/formulario/adi/ayuda/<int:pregunta_id>")
def ayuda_pregunta(pregunta_id):
    """Busca y retorna la ayuda asociada a una pregunta específica según su ID.
    Parámetros:
        pregunta_id (int): Identificador único de la pregunta, recibido automáticamente desde la URL.
    Retorna:
        Response: Un objeto JSON con la ayuda correspondiente a la pregunta si se encuentra,
                o un mensaje de error si la pregunta no existe o ocurre una excepción.
    Ejemplo de uso:
        /formulario/adi/ayuda/110 → pregunta_id = 110
    Manejo de errores:
        - Si la pregunta no existe, retorna un JSON con mensaje de no encontrada y código 404.
        - Si ocurre una excepción, retorna un JSON con mensaje de error y código 500.


    """
    session = Session()
    try:
        # pregunta_id ya viene automáticamente de la URL

        # Buscar la pregunta en la base de datos
        pregunta_db = session.query(Pregunta).filter_by(ID_PREGUNTA=pregunta_id).first()

        if pregunta_db:
            # Obtener la ayuda usando el ID que ya tenemos
            ayuda = get_ayuda_preguntas(pregunta_id)  # pregunta_id ya está disponible
            return jsonify({'ayuda': ayuda})
        else:
            return jsonify({'ayuda': f'Pregunta con ID {pregunta_id} no encontrada.'}), 404

    except Exception as e:
        return jsonify({'ayuda': 'Error al cargar la ayuda.'}), 500
    finally:
        session.close()



@app.route("/procesar-respuestas", methods=["POST"])
def procesar_respuestas():
    """
    Procesa las respuestas del formulario ADI y las guarda en la base de datos.

    Esta función maneja la ruta "/procesar-respuestas" y realiza las siguientes acciones:
    - Verifica que exista un proyecto seleccionado mediante la variable de sesión "id_sistema".
    - Elimina las respuestas anteriores asociadas al proyecto actual.
    - Calcula el siguiente identificador único para las respuestas (ID_SISTEMAADI).
    - Itera sobre las respuestas enviadas en el formulario, identificando los campos que comienzan con "pregunta_".
    - Para cada respuesta, busca el registro correspondiente en la tabla Respuesta y lo asocia al proyecto.
    - Guarda todas las respuestas en la base de datos.
    - Redirige al formulario ADI con un parámetro de éxito si la operación fue exitosa.
    - Si ocurre una excepción, revierte la transacción y muestra el error.

    Returns:
        Response: Redirección al formulario ADI con parámetro de éxito, o mensaje de error en caso de fallo.
    """
    session = Session()
    try:
        id_sistema = flask_session.get("id_sistema")
        if not id_sistema:
            return render_template('modal_proyecto_no_seleccionado.html'), 400

        # Borrar respuestas anteriores
        session.query(RespuestasProyecto).filter_by(SIST_ID_SISTEMA=id_sistema).delete()

        # Obtener el siguiente ID_SISTEMAADI
        max_id = session.query(func.max(RespuestasProyecto.ID_SISTEMAADI)).first()[0]
        next_id = 110 if max_id is None else max_id + 100

        # Procesar todas las preguntas respondidas
        for key in request.form:
            if key.startswith("pregunta_"):
                pregunta_id = int(key.split("_")[1])
                valores = request.form.getlist(key)

                for valor in valores:
                    if "," in valor:
                        c_opcion, _ = valor.split(",", 1)

                        respuesta = session.query(Respuesta).filter(
                            Respuesta.PRE_ID_PREGUNTA == pregunta_id,
                            Respuesta.C_OPCION == c_opcion
                        ).first()

                        if respuesta:
                            nuevo_registro = RespuestasProyecto(
                                ID_SISTEMAADI=next_id,
                                SIST_ID_SISTEMA=id_sistema,
                                PRE_ID_PREGUNTA=pregunta_id,
                                RES_ID_RESPUESTA=respuesta.ID_RESPUESTA
                            )
                            session.add(nuevo_registro)
                            next_id += 100


        # 💡 ¡HACEMOS COMMIT ANTES DE ACTUALIZAR RIESGOS!
        session.flush() # 👈 ¡IMPORTANTE! Escribe en BD sin commit

        # --- ACTUALIZAR RIESGOS ACTIVOS POR P1 ---
        # IMPORTANTE: forzar_actualizacion=True porque usuario modificó respuestas ADI
        actualizar_riesgos_activos_por_p1(session, id_sistema, forzar_actualizacion=True)

        # --- ACTUALIZAR CONTROLES ACTIVOS POR P1 P7 ---
        # IMPORTANTE: forzar_actualizacion=True porque usuario modificó respuestas ADI
        actualizar_controles_activos_por_p1(session, id_sistema, forzar_actualizacion=True)

        # ⚠️ ¡HACEMOS OTRO COMMIT DESPUÉS DE ACTUALIZAR RIESGOS!
        session.commit()

        # Actualizar configuración automática cuando se guardan respuestas
        get_configuracion_automatica(id_sistema)


        return redirect(url_for("formulario_adi", exito=1))

    except Exception as e:
        session.rollback()
        return f"<h3>Error al guardar: {str(e)}</h3>", 500

    finally:
        session.close()

@app.route("/api/validar-incompatibilidad-adi", methods=["POST"])
def validar_incompatibilidad_adi():
    """
    Valida si una respuesta seleccionada es incompatible con otras ya marcadas.

    Espera JSON:
        {
            "respuesta_seleccionada": int (ID_RESPUESTA),
            "respuestas_actuales": [int, int, ...] (lista de ID_RESPUESTA ya seleccionados)
        }

    Retorna:
        {
            "tiene_incompatibilidad": bool,
            "tipo": "P" | "A" | null,
            "incompatibilidades": [
                {
                    "pregunta_codigo": "P1",
                    "pregunta_texto": "...",
                    "respuesta_codigo": "A",
                    "respuesta_texto": "...",
                    "mensaje": "..."
                }
            ]
        }
    """
    session = Session()
    try:
        data = request.get_json()
        respuesta_seleccionada = data.get('respuesta_seleccionada')
        respuestas_actuales = data.get('respuestas_actuales', [])

        if not respuesta_seleccionada:
            return jsonify({
                "success": False,
                "error": "Falta ID de respuesta seleccionada"
            }), 400

        # Convertir a enteros
        try:
            respuesta_seleccionada = int(respuesta_seleccionada)
            respuestas_actuales = [int(r) for r in respuestas_actuales if r]
        except ValueError:
            return jsonify({
                "success": False,
                "error": "IDs de respuesta inválidos"
            }), 400

        # Si no hay respuestas previas, no puede haber conflicto
        if not respuestas_actuales:
            return jsonify({
                "tiene_incompatibilidad": False,
                "tipo": None,
                "incompatibilidades": []
            })

        # --- 1. BUSCAR INCOMPATIBILIDADES TIPO "P" (PROHIBIDA) ---
        incompatibilidades_prohibidas = session.query(
            ConfiguracionIncompatibilidad,
            Pregunta,
            Respuesta
        ).join(
            Respuesta,
            Respuesta.ID_RESPUESTA == ConfiguracionIncompatibilidad.RES_ID_RESP_DOS
        ).join(
            Pregunta,
            Pregunta.ID_PREGUNTA == Respuesta.PRE_ID_PREGUNTA
        ).filter(
            ConfiguracionIncompatibilidad.RES_ID_RESP_UNO == respuesta_seleccionada,
            ConfiguracionIncompatibilidad.RES_ID_RESP_DOS.in_(respuestas_actuales),
            ConfiguracionIncompatibilidad.C_TIPOINCOMP == 'P'
        ).first()

        # Si hay prohibición, retornar inmediatamente
        if incompatibilidades_prohibidas:
            incompat, pregunta, respuesta = incompatibilidades_prohibidas
            return jsonify({
                "tiene_incompatibilidad": True,
                "tipo": "P",
                "incompatibilidades": [{
                    "pregunta_codigo": pregunta.C_PREGUNTA,
                    "pregunta_texto": pregunta.D_PREGUNTA,
                    "respuesta_codigo": respuesta.C_OPCION,
                    "respuesta_texto": respuesta.D_RESPUESTA,
                    "mensaje": incompat.T_MENSAJE or ""
                }]
            })

        # --- 2. BUSCAR INCOMPATIBILIDADES TIPO "A" (AVISO) ---
        incompatibilidades_aviso = session.query(
            ConfiguracionIncompatibilidad,
            Pregunta,
            Respuesta
        ).join(
            Respuesta,
            Respuesta.ID_RESPUESTA == ConfiguracionIncompatibilidad.RES_ID_RESP_DOS
        ).join(
            Pregunta,
            Pregunta.ID_PREGUNTA == Respuesta.PRE_ID_PREGUNTA
        ).filter(
            ConfiguracionIncompatibilidad.RES_ID_RESP_UNO == respuesta_seleccionada,
            ConfiguracionIncompatibilidad.RES_ID_RESP_DOS.in_(respuestas_actuales),
            ConfiguracionIncompatibilidad.C_TIPOINCOMP == 'A'
        ).all()

        # Si hay avisos, retornar todos
        if incompatibilidades_aviso:
            lista_avisos = []
            for incompat, pregunta, respuesta in incompatibilidades_aviso:
                lista_avisos.append({
                    "pregunta_codigo": pregunta.C_PREGUNTA,
                    "pregunta_texto": pregunta.D_PREGUNTA,
                    "respuesta_codigo": respuesta.C_OPCION,
                    "respuesta_texto": respuesta.D_RESPUESTA,
                    "mensaje": incompat.T_MENSAJE or ""
                })

            return jsonify({
                "tiene_incompatibilidad": True,
                "tipo": "A",
                "incompatibilidades": lista_avisos
            })

        # --- 3. NO HAY INCOMPATIBILIDADES ---
        return jsonify({
            "tiene_incompatibilidad": False,
            "tipo": None,
            "incompatibilidades": []
        })

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Error al validar incompatibilidad: {str(e)}"
        }), 500
    finally:
        session.close()

@app.route("/eliminar-iteracion", methods=["POST"])
def eliminar_iteracion():
    data = request.get_json()
    id_sistema = flask_session.get("id_sistema")
    id_elemento = data.get("id_elemento")
    n_iteracion = data.get("n_iteracion")

    if not id_sistema or not id_elemento or not n_iteracion:
        return jsonify({"success": False, "message": "Datos incompletos"}), 400

    session = Session()
    try:
        # Verificar que haya más de una iteración antes de permitir borrar
        total_elem = session.query(DatosElementosAdi)\
                .filter_by(SIST_ID_SISTEMA=id_sistema, ELE_ID_ELEM=id_elemento)\
                .distinct(DatosElementosAdi.N_ITERACION)\
                .count()

        if total_elem <= 1:
            session.close()
            return jsonify({"success": False, "message": "No se puede eliminar la única iteración"}), 400

        # === 1. Eliminar registros de IA_DATELEMADI ===
        session.query(DatosElementosAdi)\
                .filter_by(SIST_ID_SISTEMA=id_sistema, ELE_ID_ELEM=id_elemento, N_ITERACION=n_iteracion)\
                .delete()

        # === 2. Obtener las iteraciones restantes y ordenarlas ===
        iteraciones_restantes_elem = session.query(DatosElementosAdi.N_ITERACION)\
            .filter_by(SIST_ID_SISTEMA=id_sistema, ELE_ID_ELEM=id_elemento)\
            .distinct()\
            .order_by(DatosElementosAdi.N_ITERACION)\
            .all()

        # Extraer los valores y ordenar
        nums_iter = sorted([row[0] for row in iteraciones_restantes_elem])

        # === 4. Si hay huecos, reindexar secuencialmente ===
        if nums_iter and (len(nums_iter) != nums_iter[-1] or nums_iter[0] != 1):
            # Mapeo: iteración antigua → nueva (1, 2, 3...)
            nuevo_mapeo = {old: new for new, old in enumerate(nums_iter, start=1)}

            # Actualizar cada registro de IA_DATELEMADI con su nuevo número de iteración
            for old_n, new_n in nuevo_mapeo.items():
                if old_n != new_n:  # Solo si cambia
                    session.query(DatosElementosAdi)\
                            .filter_by(SIST_ID_SISTEMA=id_sistema, ELE_ID_ELEM=id_elemento, N_ITERACION=old_n)\
                            .update({"N_ITERACION": new_n})

        session.commit()
        session.close()

        return jsonify({"success": True, "message": f"Iteración {n_iteracion} eliminada y reindexada."})
    except Exception as e:
        session.rollback()
        session.close()
        return jsonify({"success": False, "message": "Error interno"}), 500


@app.route("/formulario/adi_elementos")
def formulario_elementos():

    """
    Vista para el formulario de elementos adicionales.
    Esta función maneja la ruta "/formulario/adi_elementos" y se encarga de mostrar el formulario para la definición de elementos adicionales en el sistema seleccionado. Realiza las siguientes acciones:
    - Verifica que exista un proyecto seleccionado mediante la variable de sesión "id_sistema".
    - Obtiene las preguntas y subelementos activos a través de la función `get_subelementos_activos`.
    - Consulta las definiciones existentes de elementos adicionales en la base de datos para el sistema actual.
    - Calcula el total de subelementos requeridos y cuántos han sido completados.
    - Determina si el formulario está completo.
    - Lee el parámetro "exito" de la URL para mostrar mensajes de éxito si corresponde.
    - Renderiza la plantilla "formulario_adi_elementos.html" pasando las preguntas, definiciones, estado de completitud, éxito y la pestaña activa.
    Returns:
        - El formulario renderizado si todo es correcto.
        - Un mensaje de error y código 400 si no hay proyecto seleccionado.
    """


    session = Session()
    try:
        id_sistema = flask_session.get("id_sistema")
        if not id_sistema:
            return render_template('modal_proyecto_no_seleccionado.html'), 400

        # Obtener fase actual
        fase_actual = None
        try:
            fase_actual, _ = obtener_fase_proyecto(id_sistema)
        except Exception as e:
            pass

        # Calcular monitoreo
        monitoreo = False
        if fase_actual and fase_actual.L_MONITOREO == 1:
            monitoreo = True

        # ✅ AHORA get_subelementos_activos filtrará por fase automáticamente
        preguntas = get_subelementos_activos(id_sistema)
        definiciones = session.query(DatosElementosAdi).filter_by(SIST_ID_SISTEMA=id_sistema).all()

        definiciones_dict = {
            (d.ELE_ID_ELEM, d.N_ITERACION, d.SUB_IDSUBELEM): d.T_DESCRIPCION for d in definiciones
        }

        # Obtener descripción del primer subelemento de cada iteración
        for grupo in preguntas:
            if grupo["subelementos"]:
                primer_subelem = grupo["subelementos"][0]
                clave = (grupo["elemento"].ID_ELEM, grupo["n_iteracion"], primer_subelem.ID_SUBELEM)
                desc = definiciones_dict.get(clave, "")
                grupo["primera_descripcion"] = desc.strip().upper() if desc else ""
            else:
                grupo["primera_descripcion"] = ""

        # Obtener valores de dominio para intensidades
        def _obtener_valores(tipo_codigo):
            tipo = session.query(TiposDato).filter(TiposDato.C_TIPDAT == tipo_codigo).first()
            if not tipo:
                return []
            return session.query(ValoresDato)\
                .filter(ValoresDato.TIDA_ID_TIPDAT == tipo.ID_TIPDAT)\
                .order_by(ValoresDato.C_VALOR)\
                .all()

        intensidades = _obtener_valores('ICD')
        intensidades_list = [{"id": v.ID_VALDAT, "valor": v.C_VALOR, "texto": v.D_VALOR} for v in intensidades]

        # Calcular progreso
        total_requeridos = 0
        total_completos = 0
        for grupo in preguntas:
            for sub in grupo["subelementos"]:
                total_requeridos += 1
                clave = (grupo["elemento"].ID_ELEM, grupo["n_iteracion"], sub.ID_SUBELEM)
                if clave in definiciones_dict and definiciones_dict[clave].strip():
                    total_completos += 1

        completo = (total_requeridos == total_completos)
        exito = request.args.get("exito") == "1"

        # Contar iteraciones por elemento
        total_iteraciones_por_elemento = defaultdict(int)
        for grupo in preguntas:
            total_iteraciones_por_elemento[grupo["elemento"].ID_ELEM] += 1

        # Determinar si hay requisitos visibles en la fase actual
        hay_requisitos_visibles = False
        try:
            requisitos_data, _, _, _, _, _, _, _ = get_requisitos_para_formulario(id_sistema)
            hay_requisitos_visibles = len(requisitos_data) > 0
        except Exception as e:
            pass

        return render_template(
            "formulario_adi_elementos.html",
            preguntas=preguntas,
            definiciones=definiciones_dict,
            intensidades_condiciones=intensidades_list,
            completo=completo,
            exito=exito,
            active_tab="adi_elementos",
            monitoreo=monitoreo,
            hay_requisitos_visibles=hay_requisitos_visibles,
            # fase_actual se inyecta automáticamente por el context processor inject_fase_y_perfil()
            total_iteraciones_por_elemento=total_iteraciones_por_elemento
        )

    finally:
        session.close()


@app.route("/guardar-cambio-elemento-control", methods=["POST"])
def guardar_cambio_elemento_control():
    """
    Guarda un cambio individual en un campo de control de elemento mediante auto-guardado.
    Espera un JSON con:
        - id_datelemcontr: ID del registro de control
        - campo: 'pliego', 'intensidad', o 'clausula'
        - valor: nuevo valor
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"success": False, "error": "No hay proyecto seleccionado"}), 400

    db_session = Session()
    try:
        id_registro = request.json.get('id_datelemcontr')
        campo = request.json.get('campo')
        valor = request.json.get('valor')

        if not id_registro or not campo:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        # Validar ID numérico
        try:
            id_registro = int(id_registro)
        except ValueError:
            return jsonify({"success": False, "error": "ID inválido"}), 400

        # Obtener el registro existente
        registro = db_session.query(DatosElementoControl).filter(
            DatosElementoControl.ID_DATELEMCONTR == id_registro,
            DatosElementoControl.SIST_ID_SISTEMA == id_sistema
        ).first()

        if not registro:
            return jsonify({"success": False, "error": "Registro no encontrado"}), 404

        # Actualizar el campo específico
        if campo == "pliego":
            registro.L_TRASLAPLI = 1 if valor == "1" else 0 if valor == "0" else None
        elif campo == "intensidad":
            try:
                registro.V_INTSCONDES = int(valor) if valor else None
            except ValueError:
                registro.V_INTSCONDES = None
        elif campo == "clausula":
            registro.T_ESPCLAUSULA = valor.strip() if valor else ""
        else:
            return jsonify({"success": False, "error": "Campo no válido"}), 400

        db_session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db_session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db_session.close()

@app.route("/guardar-cambio-elemento", methods=["POST"])
def guardar_cambio_elemento():
    """
    Guarda un cambio individual en la descripción de un subelemento mediante auto-guardado.
    Espera un JSON con:
        - id_elem: ID del elemento
        - n_iteracion: número de iteración
        - id_subelem: ID del subelemento
        - valor: texto de la descripción
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"success": False, "error": "No hay proyecto seleccionado"}), 400

    db_session = Session()
    try:
        data = request.json
        id_elem = data.get('id_elem')
        n_iteracion = data.get('n_iteracion')
        id_subelem = data.get('id_subelem')
        valor = data.get('valor', "").strip()

        if not all([id_elem, n_iteracion, id_subelem]):
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        # Convertir a enteros
        try:
            id_elem = int(id_elem)
            n_iteracion = int(n_iteracion)
            id_subelem = int(id_subelem)
        except ValueError:
            return jsonify({"success": False, "error": "IDs inválidos"}), 400

        # Buscar registro existente
        registro = db_session.query(DatosElementosAdi).filter(
            DatosElementosAdi.SIST_ID_SISTEMA == id_sistema,
            DatosElementosAdi.ELE_ID_ELEM == id_elem,
            DatosElementosAdi.N_ITERACION == n_iteracion,
            DatosElementosAdi.SUB_IDSUBELEM == id_subelem
        ).first()

        if registro:
            registro.T_DESCRIPCION = valor
        else:
            # Crear nuevo registro si no existe (aunque en teoría siempre debería existir)
            max_id = db_session.query(func.max(DatosElementosAdi.ID_DATELEMADI)).scalar()
            next_id = 110 if max_id is None else max_id + 100
            nuevo = DatosElementosAdi(
                ID_DATELEMADI=next_id,
                SIST_ID_SISTEMA=id_sistema,
                ELE_ID_ELEM=id_elem,
                N_ITERACION=n_iteracion,
                SUB_IDSUBELEM=id_subelem,
                T_DESCRIPCION=valor
            )
            db_session.add(nuevo)

        db_session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db_session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db_session.close()


@app.route("/guardar-justificaciones", methods=["POST"])
def guardar_justificaciones():
    """
    Guarda las justificaciones enviadas desde un formulario web.
    Procesa los datos recibidos por POST, identificando los campos que comienzan con "justificacion_".
    Para cada justificación, actualiza o crea el registro correspondiente en IA_DATELEMADI.
    Si no hay un proyecto seleccionado en la sesión, retorna un error 400.
    En caso de éxito, redirige al formulario de elementos con un parámetro de éxito.
    Si ocurre una excepción, revierte la transacción y muestra el error.
    Returns:
        Response: Redirección al formulario de elementos en caso de éxito, o mensaje de error en caso de fallo.
    """
    session = Session()
    try:
        id_sistema = flask_session.get("id_sistema")
        if not id_sistema:
            return render_template('modal_proyecto_no_seleccionado.html'), 400

        # Procesar justificaciones enviadas
        for key in request.form:
            if key.startswith("justificacion_"):
                partes = key.split("_")
                if len(partes) == 4:
                    _, id_elem, n_iteracion, id_subelem = partes
                    try:
                        id_elem = int(id_elem)
                        n_iteracion = int(n_iteracion)
                        id_subelem = int(id_subelem)
                    except ValueError:
                        continue
                    descripcion = request.form[key].strip()

                    # Buscar registro existente
                    registro = session.query(DatosElementosAdi).filter_by(
                        SIST_ID_SISTEMA=id_sistema,
                        ELE_ID_ELEM=id_elem,
                        N_ITERACION=n_iteracion,
                        SUB_IDSUBELEM=id_subelem
                    ).first()

                    if registro:
                        # Actualizar descripción (incluso si está vacía)
                        registro.T_DESCRIPCION = descripcion
                    else:
                        # Crear nuevo registro solo si hay descripción o queremos mantener la estructura
                        # (en tu caso, las iteraciones se crean con "crear_nueva_iteracion", así que esto es raro, pero por si acaso)
                        if descripcion:  # Solo crear si hay contenido
                            # Obtener el siguiente ID
                            max_id = session.query(func.max(DatosElementosAdi.ID_DATELEMADI)).scalar()
                            next_id = 110 if max_id is None else max_id + 100
                            nuevo = DatosElementosAdi(
                                ID_DATELEMADI=next_id,
                                SIST_ID_SISTEMA=id_sistema,
                                ELE_ID_ELEM=id_elem,
                                N_ITERACION=n_iteracion,
                                SUB_IDSUBELEM=id_subelem,
                                T_DESCRIPCION=descripcion
                            )
                            session.add(nuevo)

        session.commit()
        return redirect(url_for("formulario_elementos", exito=1))
    except Exception as e:
        session.rollback()
        return f"<h3>Error al guardar justificaciones: {str(e)}</h3>", 500
    finally:
        session.close()

@app.route("/formulario/requisitos")
def formulario_requisitos():
    """
    Muestra el formulario de Requisitos de Cumplimiento.

    Esta función obtiene el ID del sistema (proyecto) desde la sesión de Flask.
    Si no hay un proyecto seleccionado, retorna un error 400.
    Obtiene los requisitos configurados y sus datos para renderizar la plantilla correspondiente.

    Returns:
        - Si no hay proyecto seleccionado: (str, int) con mensaje de error y código 400.
        - Si ocurre una excepción: (str, int) con mensaje de error y código 500.
        - Si todo es correcto: Renderiza la plantilla 'formulario_requisitos.html' con los datos necesarios.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return render_template('modal_proyecto_no_seleccionado.html'), 400

    # Verificar si está en fase de monitoreo
    monitoreo = False
    requisitos_invalidos = []  # Lista de IDs de requisitos que no cumplen criterios
    motivos_invalidos = {}  # 🆕 Diccionario con motivos específicos por ID
    try:
        fase_actual, _ = obtener_fase_proyecto(id_sistema)
        if fase_actual and fase_actual.L_MONITOREO == 1:
            monitoreo = True

        # Obtener validación de requisitos para identificar cuáles no cumplen criterios
        # NOTA: validar_requisitos_fase ahora incluye TODOS los requisitos "Por decidir"
        # independientemente de la fase, por lo que no necesitamos buscarlos por separado
        if fase_actual:
            from controllers import validar_requisitos_fase
            db_session = Session()  # Session ya importado al inicio del archivo
            try:
                validacion_req = validar_requisitos_fase(db_session, id_sistema, fase_actual)
                requisitos_invalidos = validacion_req.get("requisitos_invalidos", [])
                motivos_invalidos = validacion_req.get("motivos_invalidos", {})  # 🆕 Obtener motivos
            finally:
                db_session.close()
    except Exception as e:
        pass

    try:
        # Leer parámetro de éxito de la URL
        exito = request.args.get("exito") == "1"

        # Obtener datos de requisitos
        (requisitos_data, fase_actual, instrumentos, ocultar_cabecera_cumpl,
         mostrar_resumen_planif, estados_planif_resumen,
         mostrar_resumen_cumpl, estados_cumpl_resumen) = get_requisitos_para_formulario(id_sistema)

        # Calcular estadísticas
        total_requisitos = len(requisitos_data)
        requisitos_aplicables = sum(1 for r in requisitos_data if r['dato'].L_APLICA == 1)
        requisitos_no_aplicables = sum(1 for r in requisitos_data if r['dato'].L_APLICA == 0)
        requisitos_pendientes = sum(1 for r in requisitos_data if r['dato'].L_APLICA is None)

        # 🆕 Estado de análisis GLOBAL: Usar requisitos_invalidos que ya tiene toda la lógica
        # de validación (L_APLICA, estados, justificaciones obligatorias, etc.)
        analisis_pendientes = len(requisitos_invalidos)
        analisis_total = total_requisitos
        todos_completos = (analisis_pendientes == 0 and analisis_total > 0)

        # 🆕 RECALCULAR CONTEOS DE ESTADOS DE CUMPLIMIENTO
        # Para estados con L_AVANCEFASE=1: solo contar si cumple todos los criterios
        # Los que no cumplen criterios se suman a "No cumplido" (primer estado sin L_AVANCEFASE=1)
        requisitos_invalidos_set = set(requisitos_invalidos)

        if estados_cumpl_resumen:
            # Identificar el estado "No cumplido" (primer estado sin L_AVANCEFASE=1)
            estado_no_cumplido = next((e for e in estados_cumpl_resumen if e.L_AVANCEFASE != 1), None)

            # Contar requisitos que tienen estado positivo pero no cumplen criterios
            requisitos_caen_a_no_cumplido = 0

            for estado in estados_cumpl_resumen:
                if estado.L_AVANCEFASE == 1:
                    # Estado "positivo" - solo contar si NO está inválido
                    cumple_criterios = sum(
                        1 for item in requisitos_data
                        if item['dato'].L_APLICA == 1
                        and item['dato'].N_ESTCUMPL == estado.ID_ESTREQ
                        and item['dato'].ID_DATREQ not in requisitos_invalidos_set
                    )
                    no_cumple_criterios = sum(
                        1 for item in requisitos_data
                        if item['dato'].L_APLICA == 1
                        and item['dato'].N_ESTCUMPL == estado.ID_ESTREQ
                        and item['dato'].ID_DATREQ in requisitos_invalidos_set
                    )
                    estado.cantidad = cumple_criterios
                    requisitos_caen_a_no_cumplido += no_cumple_criterios
                else:
                    # Estado "pendiente" - contar normalmente
                    estado.cantidad = sum(
                        1 for item in requisitos_data
                        if item['dato'].L_APLICA == 1
                        and item['dato'].N_ESTCUMPL == estado.ID_ESTREQ
                    )

            # Sumar los que caen a "No cumplido"
            if estado_no_cumplido and requisitos_caen_a_no_cumplido > 0:
                estado_no_cumplido.cantidad += requisitos_caen_a_no_cumplido

        return render_template(
            "formulario_requisitos.html",
            requisitos=requisitos_data,
            instrumentos_contractuales=instrumentos,
            total_requisitos=total_requisitos,
            requisitos_aplicables=requisitos_aplicables,
            requisitos_no_aplicables=requisitos_no_aplicables,
            requisitos_pendientes=requisitos_pendientes,
            exito=exito,
            id_sistema=id_sistema,
            monitoreo=monitoreo,
            active_tab="requisitos",
            ocultar_cabecera_cumpl=ocultar_cabecera_cumpl,
            mostrar_resumen_planif=mostrar_resumen_planif,
            estados_planif_resumen=estados_planif_resumen,
            mostrar_resumen_cumpl=mostrar_resumen_cumpl,
            estados_cumpl_resumen=estados_cumpl_resumen,
            requisitos_invalidos=requisitos_invalidos,
            motivos_invalidos=motivos_invalidos,  # Diccionario con motivos específicos
            # 🆕 Variables para Estado de Análisis global
            analisis_pendientes=analisis_pendientes,
            analisis_total=analisis_total,
            todos_completos=todos_completos
        )
    except Exception as e:
        flash("❌ Error al cargar requisitos. Por favor, inténtalo de nuevo.", "danger")
        import traceback
        traceback.print_exc()
        return f"<h3>Error al cargar requisitos: {str(e)}</h3>", 500

@app.route("/api/obtener_estado_no_aplica", methods=["GET"])
def api_obtener_estado_no_aplica():
    """
    Obtiene el ID del estado de planificación que tiene L_NOAPLICA = 1.

    Returns:
        JSON: {"success": bool, "estado_id": int, "estado_nombre": str}
    """
    try:
        db_session = Session()
        try:
            # Buscar el estado de requisito de planificación con L_NOAPLICA = 1
            estado = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                C_TIPOESTADO='P',  # Planificación
                L_NOAPLICA=1
            ).first()

            if estado:
                return jsonify({
                    "success": True,
                    "estado_id": estado.ID_ESTREQ,
                    "estado_nombre": estado.D_ESTADO
                })
            else:
                return jsonify({
                    "success": False,
                    "mensaje": "No se encontró un estado con L_NOAPLICA = 1"
                }), 404
        finally:
            db_session.close()
    except Exception as e:
        return jsonify({
            "success": False,
            "mensaje": str(e)
        }), 500

@app.route("/api/guardar_campo", methods=["POST"])
def api_guardar_campo():
    """
    API genérica para autoguardado de campos de requisitos, riesgos, controles, etc.

    Espera JSON:
        {
            "tipo": "requisito" | "riesgo" | "control",
            "dato_id": int,
            "campo": str (nombre de la columna),
            "valor": any (puede ser str, int, None)
        }

    Returns:
        JSON: {"success": bool, "mensaje": str}
    """
    try:
        data = request.get_json()

        tipo = data.get('tipo')
        dato_id = data.get('dato_id')
        campo = data.get('campo')
        valor = data.get('valor')

        if not tipo or not dato_id or not campo:
            return jsonify({
                "success": False,
                "mensaje": "Faltan parámetros requeridos (tipo, dato_id, campo)"
            }), 400

        db_session = Session()
        try:
            # Determinar qué tabla y modelo usar según el tipo
            if tipo == 'requisito':
                registro = db_session.query(DatosRequisito).filter_by(
                    ID_DATREQ=dato_id
                ).first()

                if not registro:
                    return jsonify({
                        "success": False,
                        "mensaje": f"Requisito con ID {dato_id} no encontrado"
                    }), 404

            elif tipo == 'riesgo':
                registro = db_session.query(DatosRiesgo).filter_by(
                    ID_DATRIES=dato_id
                ).first()

                if not registro:
                    return jsonify({
                        "success": False,
                        "mensaje": f"Riesgo con ID {dato_id} no encontrado"
                    }), 404

            elif tipo == 'control':
                registro = db_session.query(DatosControl).filter_by(
                    ID_DAT_CONTROL=dato_id
                ).first()

                if not registro:
                    return jsonify({
                        "success": False,
                        "mensaje": f"Control con ID {dato_id} no encontrado"
                    }), 404
            else:
                return jsonify({
                    "success": False,
                    "mensaje": f"Tipo '{tipo}' no soportado"
                }), 400

            # Verificar que el campo existe en el modelo
            if not hasattr(registro, campo):
                return jsonify({
                    "success": False,
                    "mensaje": f"Campo '{campo}' no existe en {tipo}"
                }), 400

            # Convertir valor según sea necesario
            if valor == '' or valor == 'null':
                valor = None
            elif isinstance(valor, str) and valor.isdigit():
                valor = int(valor)

            # Actualizar el campo
            setattr(registro, campo, valor)
            db_session.commit()


            return jsonify({
                "success": True,
                "mensaje": f"Campo {campo} actualizado correctamente"
            }), 200

        except Exception as e:
            db_session.rollback()
            import traceback
            traceback.print_exc()
            return jsonify({
                "success": False,
                "mensaje": f"Error al actualizar: {str(e)}"
            }), 500
        finally:
            db_session.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "mensaje": f"Error interno: {str(e)}"
        }), 500

@app.route("/api/validar_requisito", methods=["POST"])
def api_validar_requisito():
    """
    API para validar un requisito individual en tiempo real.
    Usada para actualizar el marcado visual después de guardar cambios.

    Espera JSON:
        {
            "dato_id": int (ID_DATREQ)
        }

    Returns:
        JSON: {
            "success": bool,
            "valido": bool,
            "motivo": str
        }
    """
    try:
        data = request.get_json()
        dato_id = data.get('dato_id')

        if not dato_id:
            return jsonify({
                "success": False,
                "mensaje": "Falta parámetro dato_id"
            }), 400

        # Obtener ID del sistema de la sesión
        id_sistema = flask_session.get("id_sistema")
        if not id_sistema:
            return jsonify({
                "success": False,
                "mensaje": "No hay proyecto seleccionado"
            }), 400

        # Validar el requisito
        db_session = Session()
        try:
            resultado = validar_requisito_individual(db_session, dato_id, id_sistema)

            return jsonify({
                "success": True,
                "valido": resultado["valido"],
                "motivo": resultado["motivo"]
            }), 200

        finally:
            db_session.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "mensaje": f"Error al validar: {str(e)}"
        }), 500

@app.route("/formulario/riesgos")
def formulario_riesgos():
    """
    Esta función obtiene el ID del sistema (proyecto) desde la sesión de Flask.
    Si no hay un proyecto seleccionado, retorna un error 400.
    Lee el parámetro 'exito' de la URL para indicar si una operación previa fue exitosa.
    Obtiene los datos necesarios para el formulario de riesgos y renderiza la plantilla correspondiente.
    En caso de error, realiza un rollback de la sesión y muestra un mensaje de error.
    Returns:
        - Si no hay proyecto seleccionado: (str, int) con mensaje de error y código 400.
        - Si ocurre una excepción: (str, int) con mensaje de error y código 500.
        - Si todo es correcto: Renderiza la plantilla 'formulario_riesgos.html' con los datos necesarios.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return render_template('modal_proyecto_no_seleccionado.html'), 400

    # --- CALCULAR monitoreo ---
    monitoreo = False # Inicializamos como False
    nivel_riesgo = None  # Inicializar nivel de riesgo
    # Verificar si hay proyecto seleccionado y si está en fase de monitoreo

    try:
        fase_actual, _ = obtener_fase_proyecto(id_sistema)
        if fase_actual and fase_actual.L_MONITOREO == 1:
            monitoreo = True
        # Obtener el nivel de riesgo requerido por la fase
        if fase_actual:
            nivel_riesgo = fase_actual.C_NIVELRIESG
    except Exception as e:
        pass


    try:
        # Leer parámetro de éxito de la URL
        exito = request.args.get("exito") == "1"


        # Leer parámetro ver_todos de la URL
        ver_todos = request.args.get("ver_todos") == "1"

        datos_formulario = get_riesgos_para_formulario(id_sistema, todos_riesgos=ver_todos)

        # ✅ SIMPLIFICADO: Usar directamente los datos de get_riesgos_para_formulario
        # Ya no se llama a calcular_estadisticas_riesgos_por_fase (código duplicado eliminado)

        session = Session()
        hay_riesgo_personal = session.query(Riesgo).filter(Riesgo.L_PERSONAL == 1).count() > 0

        # 🆕 Obtener parámetro SOLO_GLOBAL_100 de la configuración de riesgo global
        solo_global_100 = False
        param_solo_global = session.query(ConfiguracionRiesgoGlobal).filter(
            ConfiguracionRiesgoGlobal.C_PARAMETRO == 'SOLO_GLOBAL_100',
            ConfiguracionRiesgoGlobal.L_ESTADO == 1
        ).first()

        if param_solo_global:
            if param_solo_global.N_VALOR is not None:
                # Convertir a int para comparación robusta (N_VALOR es NUMERIC que puede ser 1.0 o Decimal)
                valor_int = int(float(param_solo_global.N_VALOR))
                solo_global_100 = (valor_int == 1)
        else:
            pass

        # 🆕 Calcular si se debe mostrar el indicador de Riesgo Global
        # Se muestra si: nivel_riesgo == 'R' Y (solo_global_100 == False O todos_completos == True)
        todos_completos = datos_formulario.get('todos_completos', False)

        # Calcular mostrar_riesgo_global paso a paso para debug
        condicion_nivel = (nivel_riesgo == 'R')
        condicion_completitud = (not solo_global_100 or todos_completos)
        mostrar_riesgo_global = condicion_nivel and condicion_completitud


        session.close()

        # Determinar si hay requisitos visibles en la fase actual
        hay_requisitos_visibles = False
        try:
            requisitos_data, _, _, _, _, _, _, _ = get_requisitos_para_formulario(id_sistema)
            hay_requisitos_visibles = len(requisitos_data) > 0
        except Exception as e:
            pass

        return render_template(
            "formulario_riesgos.html",
            **datos_formulario,
            exito=exito,
            id_sistema=id_sistema,
            monitoreo = monitoreo,
            nivel_riesgo = nivel_riesgo,
            hay_riesgo_personal=hay_riesgo_personal,
            hay_requisitos_visibles=hay_requisitos_visibles,
            solo_global_100=solo_global_100,
            mostrar_riesgo_global=mostrar_riesgo_global,
            ver_just_impacto=config.VER_JUST_IMPACTO,
            ver_just_prob=config.VER_JUST_PROB,
            active_tab="riesgos"
        )
    except Exception as e:
        flash("❌ Error en cargar riesgos. Por favor, inténtalo de nuevo.", "danger")
        return f"<h3>Error al cargar riesgos: {str(e)}</h3>", 500




@app.route("/guardar-riesgos", methods=["POST"])
def guardar_riesgos():
    """
    Guarda los cambios realizados en los riesgos asociados a un sistema seleccionado.
    Este endpoint procesa los datos enviados desde un formulario para actualizar los registros de riesgos en la base de datos.
    Las acciones principales incluyen:
    - Actualizar el campo L_APLICA (si el riesgo aplica o no) y sus justificaciones.
    - Actualizar los valores de impacto y probabilidad, junto con sus justificaciones.
    - Mantener el campo L_ACTIVA en 1 (los riesgos activos siempre se muestran).
    - Validar que los IDs recibidos sean numéricos antes de actualizar.
    - Manejar errores y mostrar mensajes apropiados al usuario.
    Retorna:
        Una redirección a la vista correspondiente, mostrando un mensaje de éxito o error según el resultado de la operación.
    Excepciones:
        Realiza rollback de la sesión en caso de cualquier excepción durante el proceso de guardado.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        flash("❌ No hay proyecto seleccionado.", "danger")
        return redirect(url_for('inicio'))

    db_session = Session()
    try:
        for key, value in request.form.items():
            if key.startswith("aplica_"):
                try:
                    id_registro = int(key.split("_", 1)[1])
                except (ValueError, IndexError):
                    continue

                # Obtener valores del formulario
                aplica = 1 if value == "1" else 0
                impacto_id = request.form.get(f"impacto_{id_registro}")
                probabilidad_id = request.form.get(f"probabilidad_{id_registro}")
                jus_aplica = request.form.get(f"jus_aplica_{id_registro}", "").strip()
                jus_impacto = request.form.get(f"jus_impacto_{id_registro}", "").strip()
                jus_prob = request.form.get(f"jus_prob_{id_registro}", "").strip()

                # Validar IDs numéricos
                try:
                    impacto_id = int(impacto_id) if impacto_id else None
                    probabilidad_id = int(probabilidad_id) if probabilidad_id else None
                except ValueError:
                    impacto_id = probabilidad_id = None

                # Actualizar en BD
                registro = db_session.query(DatosRiesgo).filter(
                    DatosRiesgo.ID_DATRIES == id_registro,
                    DatosRiesgo.SIST_ID_SISTEMA == id_sistema
                ).first()

                if registro:
                    registro.L_APLICA = aplica
                    registro.V_IMPACTO = impacto_id
                    registro.V_PROBABILIDAD = probabilidad_id
                    registro.T_JUSAPLICA = jus_aplica
                    registro.T_JUSIMPACTO = jus_impacto
                    registro.T_JUSPROBABILIDAD = jus_prob

        db_session.commit()
        flash("✅ Riesgos guardados correctamente.", "success")
        return redirect(url_for('formulario_riesgos'))

    except Exception as e:
        db_session.rollback()
        flash("❌ Error al guardar los riesgos. Por favor, inténtalo de nuevo.", "danger")
        return redirect(url_for('mostrar_formulario_riesgos'))
    finally:
        db_session.close()


@app.route("/guardar-cambio-riesgo", methods=["POST"])
def guardar_cambio_riesgo():
    """
    Guarda un cambio individual en un campo de riesgo mediante auto-guardado.
    Este endpoint espera recibir un JSON con los siguientes campos:
        - id_registro: ID numérico del registro de riesgo a modificar.
        - campo: Nombre del campo a actualizar. Puede ser uno de:
            'aplica', 'impacto', 'probabilidad', 'jus_aplica', 'jus_impacto', 'jus_prob'.
        - valor: Nuevo valor para el campo especificado.
    El método realiza las siguientes acciones:
        1. Verifica que exista un proyecto seleccionado en la sesión.
        2. Valida que los datos recibidos sean correctos y completos.
        3. Busca el registro de riesgo correspondiente en la base de datos.
        4. Actualiza el campo solicitado con el nuevo valor, realizando validaciones según el tipo de campo.
        5. Guarda los cambios en la base de datos.
    Respuestas:
        - 200: {"success": True} si la operación fue exitosa.
        - 400: {"success": False, "error": "..."} si faltan datos, el ID es inválido, o el campo no es válido.
        - 404: {"success": False, "error": "..."} si el registro no se encuentra.
        - 500: {"success": False, "error": "..."} si ocurre un error inesperado.
    Excepciones:
        - ValueError: Si el ID o los valores numéricos no son válidos.
        - Exception: Para cualquier otro error durante la operación.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"success": False, "error": "No hay proyecto seleccionado"}), 400

    db_session = Session()
    try:
        id_registro = request.json.get('id_registro')
        campo = request.json.get('campo')
        valor = request.json.get('valor')

        if not id_registro or not campo:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        # Validar ID numérico
        try:
            id_registro = int(id_registro)
        except ValueError:
            return jsonify({"success": False, "error": "ID inválido"}), 400

        # Obtener el registro existente
        registro = db_session.query(DatosRiesgo).filter(
            DatosRiesgo.ID_DATRIES == id_registro,
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema
        ).first()

        if not registro:
            return jsonify({"success": False, "error": "Registro no encontrado"}), 404

        # Actualizar el campo específico
        if campo == "aplica":
            registro.L_APLICA = 1 if valor == "1" else 0
        elif campo == "impacto":
            try:
                registro.V_IMPACTO = int(valor) if valor else None
            except ValueError:
                registro.V_IMPACTO = None
        elif campo == "probabilidad":
            try:
                registro.V_PROBABILIDAD = int(valor) if valor else None
            except ValueError:
                registro.V_PROBABILIDAD = None
        elif campo == "jus_aplica":
            registro.T_JUSAPLICA = valor.strip() if valor else ""
        elif campo == "jus_impacto":
            registro.T_JUSIMPACTO = valor.strip() if valor else ""
        elif campo == "jus_prob":
            registro.T_JUSPROBABILIDAD = valor.strip() if valor else ""
        else:
            return jsonify({"success": False, "error": "Campo no válido"}), 400

        db_session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db_session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db_session.close()

@app.route("/riesgos/editar_descripcion/<int:id_dat_riesgo>", methods=["POST"])
def editar_descripcion_personalizada(id_dat_riesgo):
    from models import DatosRiesgo
    session = Session()
    try:
        data = request.get_json()
        nueva_desc = (data.get("descripcion") or "").strip()
        if not nueva_desc:
            return jsonify({"exito": False, "mensaje": "Descripción vacía."}), 400

        riesgo = session.query(DatosRiesgo).filter_by(ID_DATRIES=id_dat_riesgo).first()
        if not riesgo:
            return jsonify({"exito": False, "mensaje": "Riesgo no encontrado."}), 404

        riesgo.T_DESCRIPCION = nueva_desc
        session.commit()
        return jsonify({"exito": True})
    except Exception as e:
        session.rollback()
        return jsonify({"exito": False, "mensaje": str(e)}), 500
    finally:
        session.close()

@app.route("/riesgos/eliminar/<int:id_dat_riesgo>", methods=["POST"])
def eliminar_riesgo_personalizado(id_dat_riesgo):
    """
    Elimina un riesgo personalizado de la base de datos.

    Esta ruta permite eliminar un registro de DatosRiesgo que corresponde a un riesgo personalizado.
    Antes de eliminar, verifica que:
    1. El riesgo existe
    2. El riesgo pertenece al sistema actual
    3. El riesgo es personalizado (L_MANUAL=1 o su riesgo padre tiene L_PERSONAL=1)
    4. No estamos en fase de monitoreo

    Args:
        id_dat_riesgo (int): ID del registro en IA_DATRIESGOS a eliminar

    Returns:
        JSON con exito=True si se eliminó correctamente, o exito=False con mensaje de error
    """
    from models import DatosRiesgo, Riesgo, Inicio

    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"exito": False, "mensaje": "No hay proyecto seleccionado"}), 400

    session = Session()
    try:
        # Verificar que no estamos en fase de monitoreo
        sistema = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not sistema:
            return jsonify({"exito": False, "mensaje": "Sistema no encontrado"}), 404

        if sistema.N_FASE == 4:
            return jsonify({"exito": False, "mensaje": "No se puede eliminar riesgos en fase de monitoreo"}), 403

        # Buscar el riesgo
        dat_riesgo = session.query(DatosRiesgo).filter_by(
            ID_DATRIES=id_dat_riesgo,
            SIST_ID_SISTEMA=id_sistema
        ).first()

        if not dat_riesgo:
            return jsonify({"exito": False, "mensaje": "Riesgo no encontrado"}), 404

        # Verificar que es un riesgo personalizado
        riesgo_base = session.query(Riesgo).filter_by(ID_RIESGO=dat_riesgo.RIE_ID_RIESGO).first()

        if not riesgo_base:
            return jsonify({"exito": False, "mensaje": "Configuración de riesgo no encontrada"}), 404

        es_personal = bool(riesgo_base.L_PERSONAL == 1 or dat_riesgo.L_MANUAL == 1)

        if not es_personal:
            return jsonify({"exito": False, "mensaje": "Solo se pueden eliminar riesgos personalizados"}), 403

        # Eliminar el riesgo
        session.delete(dat_riesgo)
        session.commit()

        return jsonify({"exito": True, "mensaje": "Riesgo personalizado eliminado correctamente"})

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"exito": False, "mensaje": str(e)}), 500
    finally:
        session.close()

@app.route("/riesgos/editar_riesgo_residual/<int:id_dat_riesgo>", methods=["POST"])
def editar_riesgo_residual_personalizado(id_dat_riesgo):
    """
    Actualiza el valor de riesgo residual para un riesgo personalizado.

    Este endpoint permite al usuario establecer manualmente el nivel de riesgo residual
    para riesgos personalizados que no tienen controles asociados.

    Args:
        id_dat_riesgo (int): ID del registro en IA_DATRIESGOS

    Body JSON:
        id_valor_riesgo (int): ID del valor de riesgo en IA_VALDAT

    Returns:
        JSON con exito=True si se guardó correctamente, o exito=False con mensaje de error
    """
    from models import DatosRiesgo, Riesgo, ValoresDato, TiposDato

    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"exito": False, "mensaje": "No hay proyecto seleccionado"}), 400

    session = Session()
    try:
        data = request.get_json()
        id_valor_riesgo = data.get("id_valor_riesgo")

        if not id_valor_riesgo:
            return jsonify({"exito": False, "mensaje": "Debe seleccionar un nivel de riesgo"}), 400

        # Verificar que el valor de riesgo existe y es del tipo correcto
        tipo_nivrie = session.query(TiposDato).filter_by(C_TIPDAT='NIVRIE').first()
        if not tipo_nivrie:
            return jsonify({"exito": False, "mensaje": "Tipo de dato NIVRIE no encontrado"}), 500

        valor_riesgo = session.query(ValoresDato).filter_by(
            ID_VALDAT=id_valor_riesgo,
            TIDA_ID_TIPDAT=tipo_nivrie.ID_TIPDAT
        ).first()

        if not valor_riesgo:
            return jsonify({"exito": False, "mensaje": "Valor de riesgo no válido"}), 400

        # Buscar el riesgo
        dat_riesgo = session.query(DatosRiesgo).filter_by(
            ID_DATRIES=id_dat_riesgo,
            SIST_ID_SISTEMA=id_sistema
        ).first()

        if not dat_riesgo:
            return jsonify({"exito": False, "mensaje": "Riesgo no encontrado"}), 404

        # Verificar que es un riesgo personalizado
        riesgo_base = session.query(Riesgo).filter_by(ID_RIESGO=dat_riesgo.RIE_ID_RIESGO).first()
        if not riesgo_base:
            return jsonify({"exito": False, "mensaje": "Configuración de riesgo no encontrada"}), 404

        es_personal = bool(riesgo_base.L_PERSONAL == 1 or dat_riesgo.L_MANUAL == 1)
        if not es_personal:
            return jsonify({"exito": False, "mensaje": "Solo se puede establecer riesgo residual manual para riesgos personalizados"}), 403

        # Actualizar el valor
        dat_riesgo.V_RIERESID = id_valor_riesgo
        session.commit()

        return jsonify({
            "exito": True,
            "mensaje": f"Riesgo residual actualizado a {valor_riesgo.D_VALOR}"
        })

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"exito": False, "mensaje": str(e)}), 500
    finally:
        session.close()

@app.route("/activar-riesgo", methods=["POST"])
def activar_riesgo():
    """
    Activa un riesgo que estaba inactivo (L_ACTIVA=0) en la base de datos.

    Este endpoint recibe el ID del riesgo original (RIE_ID_RIESGO) y:
    1. Si ya existe un registro en DatosRiesgo para este sistema, actualiza L_ACTIVA=1 y L_APLICA=1
    2. Si no existe, crea un nuevo registro con L_ACTIVA=1 y L_APLICA=1

    Returns:
        JSON con success=True si la operación fue exitosa, o success=False con error si falló
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"success": False, "error": "No hay proyecto seleccionado"}), 400

    db_session = Session()
    try:
        data = request.get_json()
        id_riesgo_original = data.get('id_riesgo')

        if not id_riesgo_original:
            return jsonify({"success": False, "error": "ID de riesgo no proporcionado"}), 400

        try:
            id_riesgo_original = int(id_riesgo_original)
        except ValueError:
            return jsonify({"success": False, "error": "ID de riesgo inválido"}), 400

        # Buscar si ya existe un registro para este riesgo y sistema
        registro = db_session.query(DatosRiesgo).filter(
            DatosRiesgo.RIE_ID_RIESGO == id_riesgo_original,
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema
        ).first()

        if registro:
            # Si existe, actualizar L_ACTIVA y L_APLICA
            registro.L_ACTIVA = 1
            registro.L_APLICA = 1
            registro.L_MANUAL = 1
            db_session.flush()  # Forzar la actualización inmediata
        else:
            # Si no existe, crear un nuevo registro
            nuevo_registro = DatosRiesgo(
                SIST_ID_SISTEMA=id_sistema,
                RIE_ID_RIESGO=id_riesgo_original,
                L_ACTIVA=1,
                L_APLICA=1,
                L_MANUAL=1,
                V_IMPACTO=None,
                V_PROBABILIDAD=None,
                T_JUSAPLICA="",
                T_JUSIMPACTO="",
                T_JUSPROBABILIDAD=""
            )
            db_session.add(nuevo_registro)
            db_session.flush()  # Forzar la escritura inmediata

        db_session.commit()

        # Verificar que se actualizó correctamente
        verificacion = db_session.query(DatosRiesgo).filter(
            DatosRiesgo.RIE_ID_RIESGO == id_riesgo_original,
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema
        ).first()

        if verificacion:
            pass
        else:
            pass
        return jsonify({"success": True, "message": "Riesgo activado correctamente"})

    except Exception as e:
        db_session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Error al activar riesgo: {str(e)}"}), 500
    finally:
        db_session.close()

@app.route("/obtener-mensaje-confirmacion-riesgo", methods=["GET"])
def obtener_mensaje_confirmacion_riesgo():
    """
    Obtiene el mensaje de confirmación para crear riesgo específico desde la tabla IA_VALDAT.
    Busca el registro con C_TIPDAT='MSGRIESGOESPE' y C_VALOR='1' y devuelve el campo D_VALOR.
    """
    session = Session()
    try:
        # Primero obtener el ID del tipo de dato
        tipo_dato = session.query(TiposDato).filter(
            TiposDato.C_TIPDAT == 'MSGS'
        ).first()

        if not tipo_dato:
            return jsonify({
                "success": False,
                "message": "No se encontró el tipo de dato MSGS"
            }), 404

        # Obtener el valor correspondiente
        valor_dato = session.query(ValoresDato).filter(
            and_(
                ValoresDato.TIDA_ID_TIPDAT == tipo_dato.ID_TIPDAT,
                ValoresDato.C_VALOR_TEXT == 'MSGRIESGOESPE'
            )
        ).first()

        if not valor_dato:
            return jsonify({
                "success": False,
                "message": "No se encontró el mensaje de confirmación"
            }), 404

        return jsonify({
            "success": True,
            "mensaje": valor_dato.D_VALOR or ""
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Error al recuperar el mensaje de confirmación"
        }), 500
    finally:
        session.close()

@app.route("/crear-riesgo-personalizado", methods=["POST"])
def crear_riesgo_personalizado():
    """
    Crea un nuevo riesgo personalizado en IA_DATRIESGOS para el sistema actual.
    """
    session = Session()
    id_sistema = flask_session.get("id_sistema")
    data = request.get_json()
    descripcion = (data.get("descripcion") or "").strip()

    if not id_sistema:
        session.close()
        return jsonify({"success": False, "message": "Sistema no definido en sesión."}), 400

    if not descripcion:
        session.close()
        return jsonify({"success": False, "message": "La descripción no puede estar vacía."}), 400

    try:
        # Obtener el control base de tipo personalizado
        riesgo_personal = session.query(Riesgo).filter(Riesgo.L_PERSONAL == 1).first()
        if not riesgo_personal:
            session.close()
            return jsonify({"success": False, "message": "No existe riesgo personalizable."}), 404

        max_id = session.query(func.max(DatosRiesgo.ID_DATRIES)).scalar() or 10
        nuevo_id = max_id + 100

        nuevo_riesgo = DatosRiesgo(
            ID_DATRIES=nuevo_id,
            SIST_ID_SISTEMA=id_sistema,
            RIE_ID_RIESGO=riesgo_personal.ID_RIESGO,
            T_DESCRIPCION=descripcion,
            L_ACTIVA=1,
            L_APLICA=1,
            L_MANUAL=1  # marcamos como manual/personalizado
        )

        session.add(nuevo_riesgo)
        session.commit()
        return jsonify({"success": True, "message": "Riesgo específico del proyecto creado correctamente."}), 200

    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "message": "Error interno del servidor."}), 500
    finally:
        session.close()

@app.route("/activar-control", methods=["POST"])
def activar_control():
    """
    Activa un control que estaba inactivo (L_ACTIVA=0) en la base de datos.

    Este endpoint recibe el ID del control original (CON_ID_CONTROL) y:
    1. Si ya existe un registro en DatosControl para este sistema, actualiza L_ACTIVA=1 y L_APLICA=1
    2. Si no existe, crea un nuevo registro con L_ACTIVA=1 y L_APLICA=1

    Returns:
        JSON con success=True si la operación fue exitosa, o success=False con error si falló
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"success": False, "error": "No hay proyecto seleccionado"}), 400

    db_session = Session()
    try:
        data = request.get_json()
        id_control_original = data.get('id_control')

        if not id_control_original:
            return jsonify({"success": False, "error": "ID de control no proporcionado"}), 400

        try:
            id_control_original = int(id_control_original)
        except ValueError:
            return jsonify({"success": False, "error": "ID de control inválido"}), 400


        # Buscar si ya existe un registro para este control y sistema
        registro = db_session.query(DatosControl).filter(
            DatosControl.CON_ID_CONTROL == id_control_original,
            DatosControl.SIST_ID_SISTEMA == id_sistema
        ).first()

        if registro:

            # Actualización mediante ORM
            registro.L_ACTIVA = 1
            registro.L_APLICA = 1
            registro.L_MANUAL = 1
            db_session.flush()


            # Actualización directa con SQL como backup
            from sqlalchemy import text
            sql_update = text("""
                UPDATE IA_DATCONTROL
                SET L_ACTIVA = 1, L_APLICA = 1, L_MANUAL = 1
                WHERE CON_ID_CONTROL = :id_control
                AND SIST_ID_SISTEMA = :id_sistema
            """)

            resultado_sql = db_session.execute(sql_update, {
                'id_control': id_control_original,
                'id_sistema': id_sistema
            })


        else:

            # Si no existe, crear un nuevo registro
            nuevo_registro = DatosControl(
                SIST_ID_SISTEMA=id_sistema,
                CON_ID_CONTROL=id_control_original,
                L_ACTIVA=1,
                L_APLICA=1,
                L_MANUAL=1,
                V_MADUREZ=None,
                L_TRASLAPE=None,
                V_INTCONDES=None,
                T_JUSCLAUSULA="",
                T_OBSERVACIONES=""
            )
            db_session.add(nuevo_registro)
            db_session.flush()


        # Commit de los cambios
        db_session.commit()

        session_verificacion = Session()
        verificacion_independiente = session_verificacion.query(DatosControl).filter(
            DatosControl.CON_ID_CONTROL == id_control_original,
            DatosControl.SIST_ID_SISTEMA == id_sistema
        ).first()

        if verificacion_independiente:
            pass
        else:
            pass

        session_verificacion.close()

        # Verificar los cambios en la BD
        verificacion = db_session.query(DatosControl).filter(
            DatosControl.CON_ID_CONTROL == id_control_original,
            DatosControl.SIST_ID_SISTEMA == id_sistema
        ).first()

        if verificacion:
            pass
        else:
            pass


        return jsonify({"success": True, "message": "Control activado correctamente"})

    except Exception as e:
        db_session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Error al activar control: {str(e)}"}), 500
    finally:
        db_session.close()

@app.route('/api/calcular-criticidad-riesgo', methods=['POST'])
def api_calcular_criticidad_riesgo():
    """
    Calcula la criticidad inherente de un riesgo en tiempo real según los IDs de impacto y probabilidad proporcionados.
    Este endpoint espera recibir un JSON con los campos 'id_impacto' y 'id_probabilidad'. Utiliza estos valores para buscar
    la configuración correspondiente en la base de datos y determina la criticidad y el nivel de riesgo asociado. El nivel
    de riesgo se devuelve en un formato compatible con el frontend, incluyendo el texto descriptivo y la clase CSS sugerida.
    Returns:
        JSON:
            success (bool): Indica si la operación fue exitosa.
            criticidad (int): Valor numérico de la criticidad calculada (si existe configuración).
            nivel (dict): Información del nivel de riesgo, con las claves:
                texto (str): Descripción textual del nivel de riesgo (e.g., "ALTO", "MEDIO").
                clase (str): Clase CSS sugerida para el nivel de riesgo.
            error (str): Mensaje de error en caso de fallo o configuración no encontrada.
    Status Codes:
        200: Operación exitosa.
        400: Faltan parámetros requeridos.
        404: No se encontró configuración de criticidad para los IDs proporcionados.
        500: Error interno al calcular la criticidad.
    """
    session = Session() # Crear una nueva sesión para esta operación
    try:
        data = request.get_json()
        id_impacto = data.get('id_impacto')
        id_probabilidad = data.get('id_probabilidad')

        if not id_impacto or not id_probabilidad:
            return jsonify({"success": False, "error": "Faltan ID de impacto o probabilidad"}), 400

        # Buscar en la tabla de configuración de criticidad
        config_registro = session.query(ConfiguracionCriticidad).filter(
            and_(
                ConfiguracionCriticidad.V_IMPACTO == id_impacto,
                ConfiguracionCriticidad.V_PROBAB == id_probabilidad
            )
        ).first()

        if config_registro:
            criticidad = config_registro.N_CRITICIDAD
            # Obtener el nivel de riesgo basado en la criticidad calculada
            # Usamos la función importada desde controllers
            nivel_info_backend = convertir_criticidad_a_nivel(criticidad)
            # Ajustamos el formato para que coincida con lo que espera el JS
            nivel_info = {
                "texto": nivel_info_backend, # Suponiendo que convertir_criticidad_a_nivel devuelve solo el texto
                "clase": "" # O puedes definir la clase aquí también en convertir_criticidad_a_nivel
                            # o crear una función específica para el JS en controllers
            }
            # Para mantener la coherencia con el JS existente, ajustamos la función convertir_criticidad_a_nivel
            # o creamos una auxiliar aquí. Vamos con una auxiliar aquí para evitar tocar controllers si no es necesario.
            # Asumiendo que convertir_criticidad_a_nivel devuelve el texto del nivel (e.g., "ALTO")
            texto_nivel = nivel_info_backend
            # Mapeo de texto a clase CSS (debes asegurarte de que coincida con obtenerNivelRiesgo del JS)
            nivel_texto_a_clase = {
                "CRÍTICO": "text-danger fw-bold",
                "ALTO": "text-warning fw-bold",
                "MEDIO": "text-info",
                "BAJO": "text-success",
                "—": "" # o "text-muted" si es el caso
            }
            clase_nivel = nivel_texto_a_clase.get(texto_nivel, "")

            # Devolver la criticidad y el nivel
            return jsonify({
                "success": True,
                "criticidad": criticidad,
                "nivel": {"texto": texto_nivel, "clase": clase_nivel}
            })
        else:
            # Si no se encuentra una configuración específica, devolver un error
            return jsonify({"success": False, "error": f"No se encontró configuración de criticidad para IMPACTO={id_impacto}, PROBAB={id_probabilidad}"}), 404

    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": "Error interno al calcular la criticidad"}), 500
    finally:
        session.close() # Cerrar la sesión al finalizar


@app.route("/formulario/controles")
def formulario_controles():
    """
    Muestra el formulario de controles para el sistema seleccionado.
    Incluye validación para resaltar controles que no cumplen requisitos de fase.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return render_template('modal_proyecto_no_seleccionado.html'), 400

    # --- CALCULAR monitoreo ---
    monitoreo = False
    nivel_riesgo = None  # Inicializar nivel de riesgo
    fase_actual_obj = None  # Objeto SQLAlchemy original
    fase_actual_dict = None  # Diccionario para el template
    try:
        fase_actual_obj, _ = obtener_fase_proyecto(id_sistema)
        if fase_actual_obj and fase_actual_obj.L_MONITOREO == 1:
            monitoreo = True
        # Obtener el nivel de riesgo requerido por la fase
        if fase_actual_obj:
            nivel_riesgo = fase_actual_obj.C_NIVELRIESG
            # ✅ CORRECCIÓN: Convertir a diccionario compatible con base.html Y formulario_controles.html
            fase_actual_dict = {
                "nombre": fase_actual_obj.D_FASE,       # Para base.html
                "orden": fase_actual_obj.N_ORDEN,       # Para compatibilidad
                "es_monitoreo": fase_actual_obj.L_MONITOREO == 1,  # Para compatibilidad
                "C_FASE": fase_actual_obj.C_FASE,       # Para formulario_controles.html
                "L_MONITOREO": fase_actual_obj.L_MONITOREO,  # Por si se necesita
                "C_NIVELRIESG": fase_actual_obj.C_NIVELRIESG  # Por si se necesita
            }
    except Exception as e:
        pass

    try:
        # Leer parámetro de éxito de la URL
        exito = request.args.get("exito") == "1"

        # Leer parámetro ver_todos de la URL
        ver_todos = request.args.get("ver_todos") == "1"

        # 🆕 Leer parámetro id_riesgo_filtro de la URL
        id_riesgo_filtro = request.args.get("id_riesgo_filtro")

        # 🆕 Leer parámetro id_requisito_filtro de la URL
        id_requisito_filtro = request.args.get("id_requisito_filtro")

        # Obtener datos del formulario
        datos_formulario = get_controles_para_formulario(
            id_sistema,
            todos_controles=ver_todos,
            id_riesgo_filtro=id_riesgo_filtro,
            id_requisito_filtro=id_requisito_filtro
        )

        # ✅ NUEVA VALIDACIÓN: Obtener lista de controles inválidos
        controles_invalidos = []
        if not ver_todos:  # Solo validar en modo normal (no en "Ver Todos")
            try:
                from controllers import validar_condiciones_cambio_fase
                validacion = validar_condiciones_cambio_fase(id_sistema)

                # Extraer lista de controles inválidos de la validación
                if 'validaciones' in validacion and 'controles' in validacion['validaciones']:
                    controles_invalidos = validacion['validaciones']['controles'].get('controles_invalidos', [])
            except Exception as e:
                pass

        return render_template(
            "formulario_controles.html",
            **datos_formulario,
            exito=exito,
            id_sistema=id_sistema,
            monitoreo=monitoreo,
            fase_actual=fase_actual_dict,
            nivel_riesgo=nivel_riesgo,  # ✅ PASAR nivel_riesgo AL TEMPLATE
            controles_invalidos=controles_invalidos,  # ✅ PASAR LA LISTA AL TEMPLATE
            id_riesgo_filtro=id_riesgo_filtro,  # 🆕 PASAR id_riesgo_filtro AL TEMPLATE
            id_requisito_filtro=id_requisito_filtro,  # 🆕 PASAR id_requisito_filtro AL TEMPLATE
            active_tab="controles"
        )


    except Exception as e:
        flash("❌ Error en cargar controles. Por favor, inténtalo de nuevo.", "danger")
        return f"<h3>Error al cargar controles: {str(e)}</h3>", 500


@app.route("/guardar-controles", methods=["POST"])
def guardar_controles():
    """
    Guarda los cambios realizados en los controles asociados a un sistema seleccionado.
    Este endpoint procesa los datos enviados desde el formulario de controles.
    Las acciones principales incluyen:
    - Actualizar el campo L_APLICA (si el control aplica o no).
    - Actualizar el valor de intensidad de condiciones (V_INTCONDES).
    - Actualizar la justificación clausula (T_ESPCLAUSULA).
    - Actualizar las observaciones (T_OBSERVACIONES).
    - Mantener el campo L_ACTIVA (se maneja por lógica de perfil/exclusiones).
    - Validar que los IDs recibidos sean numéricos antes de actualizar.
    - Manejar errores y mostrar mensajes apropiados al usuario.
    Retorna:
        Una redirección a la vista correspondiente, mostrando un mensaje de éxito o error según el resultado de la operación.
    Excepciones:
        Realiza rollback de la sesión en caso de cualquier excepción durante el proceso de guardado.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        flash("❌ No hay proyecto seleccionado.", "danger")
        return redirect(url_for('formulario_controles')) # Redirigir a la vista de controles

    db_session = Session()
    try:
        for key, value in request.form.items():
            if key.startswith("aplica_"):
                try:
                    id_registro = int(key.split("_", 1)[1]) # Extrae ID_DATCONTROL
                except (ValueError, IndexError):
                    continue # Si no puede parsear el ID, ignora este campo

                # Obtener valores del formulario para este ID_DATCONTROL
                aplica = request.form.get(f"aplica_{id_registro}")
                pliego = request.form.get(f"pliego_{id_registro}")
                madurez_id = request.form.get(f"madurez_{id_registro}")
                intensidad_id = request.form.get(f"intensidad_{id_registro}")
                jus_clausula = request.form.get(f"jus_clausula_{id_registro}", "").strip()
                observaciones = request.form.get(f"observaciones_{id_registro}", "").strip() # <-- Nuevo campo

                # Convertir valores a tipos correctos o None si están vacíos
                try:
                    aplica = 1 if aplica == "1" else 0 if aplica == "0" else None
                    pliego = 1 if pliego == "1" else 0 if pliego == "0" else None
                    intensidad_id = int(intensidad_id) if intensidad_id else None
                    madurez_id = int(madurez_id) if madurez_id else None
                except ValueError:
                    # Si no es un número válido, se pone a None
                    intensidad_id = None
                    madurez_id = None
                # Buscar el registro específico de control en la base de datos
                # Aseguramos que pertenece al sistema correcto
                registro = db_session.query(DatosControl).filter(
                    DatosControl.ID_DATCONTROL == id_registro,
                    DatosControl.SIST_ID_SISTEMA == id_sistema
                ).first()

                if registro:
                    # Solo actualizamos si el campo no es None (es decir, si fue enviado)
                    if aplica is not None:
                        registro.L_APLICA = aplica
                    if madurez_id is not None:
                        registro.V_MADUREZ = madurez_id
                    if pliego is not None:
                        registro.L_TRASLAPLI = pliego
                    if intensidad_id is not None:
                        registro.V_INTCONDES = intensidad_id
                    # La justificación y observaciones pueden ser vacías, por lo que siempre se actualizan
                    registro.T_ESPCLAUSULA = jus_clausula
                    registro.T_OBSERVACIONES = observaciones # <-- Nuevo campo (asegúrate que el modelo lo tenga)

        db_session.commit()
        flash("✅ Controles guardados correctamente.", "success")
        # Redirigir de vuelta a la misma página de controles
        return redirect(url_for('formulario_controles'))

    except Exception as e:
        db_session.rollback()
        flash("❌ Error al guardar los controles. Por favor, inténtalo de nuevo.", "danger")
        # En caso de error, también redirigimos a la vista de controles
        return redirect(url_for('formulario_controles'))

    finally:
        db_session.close()


@app.route("/guardar-cambio-control", methods=["POST"])
def guardar_cambio_control():
    """
    Guarda un cambio individual en un campo de control mediante auto-guardado.
    Este endpoint espera recibir un JSON con los siguientes campos:
        - id_registro: ID numérico del registro de control (ID_DATCONTROL) a modificar.
        - campo: Nombre del campo a actualizar. Puede ser uno de:
            'aplica', 'intensidad', 'jus_clausula', 'observaciones'.
        - valor: Nuevo valor para el campo especificado.
    El método realiza las siguientes acciones:
        1. Verifica que exista un proyecto seleccionado en la sesión.
        2. Valida que los datos recibidos sean correctos y completos.
        3. Busca el registro de control correspondiente en la base de datos.
        4. Actualiza el campo solicitado con el nuevo valor, realizando validaciones según el tipo de campo.
        5. Guarda los cambios en la base de datos.
    Respuestas:
        - 200: {"success": True} si la operación fue exitosa.
        - 400: {"success": False, "error": "..."} si faltan datos, el ID es inválido, o el campo no es válido.
        - 404: {"success": False, "error": "..."} si el registro no se encuentra.
        - 500: {"success": False, "error": "..."} si ocurre un error inesperado.
    Excepciones:
        - ValueError: Si el ID o los valores numéricos no son válidos.
        - Exception: Para cualquier otro error durante la operación.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"success": False, "error": "No hay proyecto seleccionado"}), 400

    db_session = Session()
    try:
        id_registro = request.json.get('id_registro')
        campo = request.json.get('campo')
        valor = request.json.get('valor')

        if not id_registro or not campo:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        try:
            id_registro = int(id_registro)
        except ValueError:
            return jsonify({"success": False, "error": "ID inválido"}), 400

        registro = db_session.query(DatosControl).filter(
            DatosControl.ID_DATCONTROL == id_registro,
            DatosControl.SIST_ID_SISTEMA == id_sistema
        ).first()

        if not registro:
            return jsonify({"success": False, "error": "Registro de control no encontrado"}), 404

        # 🔒 NUEVA VALIDACIÓN: Solo si se intenta pasar de "Sí" a "No"
        if campo == "aplica" and valor == "0":
            # Verificar si actualmente está en "Sí" (L_APLICA == 1)
            if registro.L_APLICA == 1:
                try:
                    validar_desactivacion_control(id_sistema, registro.CON_ID_CONTROL)
                except ValueError as ve:
                    return jsonify({"success": False, "error": str(ve)}), 400
            else:
                pass
        # Resto de la lógica de actualización
        if campo == "aplica":
            registro.L_APLICA = 1 if valor == "1" else 0
        elif campo == "madurez":
            try:
                registro.V_MADUREZ = int(valor) if valor else None
            except ValueError:
                registro.V_MADUREZ = None
        elif campo == "pliego":
            registro.L_TRASLAPLI = 1 if valor == "1" else 0
        elif campo == "intensidad":
            try:
                registro.V_INTCONDES = int(valor) if valor else None
            except ValueError:
                registro.V_INTCONDES = None
        elif campo == "jus_clausula":
            registro.T_ESPCLAUSULA = valor.strip() if valor else ""
        elif campo == "observaciones":
            registro.T_OBSERVACIONES = valor.strip() if valor else ""
        else:
            return jsonify({"success": False, "error": "Campo no válido para controles"}), 400

        db_session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db_session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db_session.close()

@app.route('/api/calcular-riesgo-residual', methods=['POST'])
def api_calcular_riesgo_residual():
    """
    Calcula el riesgo residual de un riesgo en tiempo real.
    """
    session = Session()
    try:
        data = request.get_json()
        id_registro = data.get('id_registro')  # ID_DATRIES
        criticidad_inherente = data.get('criticidad_inherente')

        if not id_registro or criticidad_inherente is None:
            return jsonify({"success": False, "error": "Faltan parámetros"}), 400

        # Obtener el registro de DatosRiesgo
        datos_riesgo = session.query(DatosRiesgo).filter(
            DatosRiesgo.ID_DATRIES == id_registro
        ).first()

        if not datos_riesgo:
            return jsonify({"success": False, "error": "Registro no encontrado"}), 404

        # Calcular riesgo residual usando la función existente
        from controllers import calcular_riesgo_residual, convertir_criticidad_a_nivel

        riesgo_residual, nivel_residual = calcular_riesgo_residual(
            session,
            datos_riesgo,
            criticidad_inherente
        )

        # Mapeo de texto a clase CSS
        nivel_texto_a_clase = {
            "CRÍTICO": "text-danger fw-bold",
            "ALTO": "text-warning fw-bold",
            "MEDIO": "text-info",
            "BAJO": "text-success",
            "—": ""
        }

        clase_nivel = nivel_texto_a_clase.get(nivel_residual, "")

        return jsonify({
            "success": True,
            "riesgo_residual": riesgo_residual,
            "nivel_residual": {
                "texto": nivel_residual,
                "clase": clase_nivel
            }
        })

    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()

@app.route("/formulario/monitoreo")
def formulario_monitoreo():
    """
    Muestra el formulario de monitoreo de controles.

    Solo accesible si el proyecto está en fase de monitoreo.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return render_template('modal_proyecto_no_seleccionado.html'), 400

    try:
        # Verificar si el proyecto está en fase de monitoreo
        en_monitoreo = monitoreo.proyecto_en_fase_monitoreo(id_sistema)

        # Por ahora permitimos el acceso aunque no esté en fase de monitoreo
        # para permitir el desarrollo y pruebas
        # if not en_monitoreo:
        #     flash("⚠️ El proyecto no está en fase de monitoreo", "warning")
        #     return redirect(url_for('index'))

        # Obtener controles en monitoreo
        controles = monitoreo.obtener_controles_monitoreo(id_sistema)
        estadisticas = monitoreo.obtener_estadisticas_monitoreo(id_sistema)

        # Leer parámetro de éxito
        exito = request.args.get("exito") == "1"

        return render_template(
            "formulario_monitoreo.html",
            controles=controles,
            estadisticas=estadisticas,
            exito=exito,
            id_sistema=id_sistema,
            active_tab="monitoreo"
        )

    except Exception as e:
        flash("❌ Error al cargar monitoreo. Por favor, inténtalo de nuevo.", "danger")
        return f"<h3>Error al cargar monitoreo: {str(e)}</h3>", 500


@app.route("/monitoreo/detalle/<int:id_datcontmon>")
def monitoreo_detalle(id_datcontmon):
    """
    Obtiene el detalle completo de un control en monitoreo.

    Args:
        id_datcontmon (int): ID del registro de control en monitoreo

    Returns:
        JSON con los datos del control o error
    """
    try:
        detalle = monitoreo.obtener_detalle_control(id_datcontmon)

        if detalle:
            return jsonify({"success": True, "control": detalle})
        else:
            return jsonify({"success": False, "error": "Control no encontrado"}), 404

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/monitoreo/actualizar-campo", methods=["POST"])
def monitoreo_actualizar_campo():
    """
    Actualiza un campo específico de un control en monitoreo (autoguardado).

    Espera un JSON con:
        - id_datcontmon: ID del registro
        - campo: nombre del campo a actualizar
        - valor: nuevo valor

    Returns:
        JSON con success y opcionalmente fecha_proxima actualizada
    """
    try:
        data = request.get_json()
        id_datcontmon = data.get('id_datcontmon')
        campo = data.get('campo')
        valor = data.get('valor')

        if not id_datcontmon or not campo:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        # Validar ID numérico
        try:
            id_datcontmon = int(id_datcontmon)
        except ValueError:
            return jsonify({"success": False, "error": "ID inválido"}), 400

        # Actualizar el campo
        resultado = monitoreo.actualizar_control_monitoreo(id_datcontmon, campo, valor)

        # Si se actualizó la frecuencia, obtener la nueva fecha próxima
        if resultado.get("success") and campo == "frecuencia":
            detalle = monitoreo.obtener_detalle_control(id_datcontmon)
            if detalle:
                resultado["fecha_proxima"] = detalle.get("fecha_proxima_ejecucion", "")

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/monitoreo/ejecuciones/<int:id_datcontmon>")
def monitoreo_ejecuciones(id_datcontmon):
    """
    Obtiene todas las ejecuciones de un control.

    Args:
        id_datcontmon (int): ID del control en monitoreo

    Returns:
        JSON con la lista de ejecuciones
    """
    try:
        ejecuciones = monitoreo.obtener_ejecuciones_control(id_datcontmon)
        return jsonify({"success": True, "ejecuciones": ejecuciones})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/monitoreo/ejecucion/<int:id_ejecucion>")
def monitoreo_detalle_ejecucion(id_ejecucion):
    """
    Obtiene los detalles de una ejecución específica para editar.

    Args:
        id_ejecucion (int): ID de la ejecución

    Returns:
        JSON con los datos de la ejecución
    """
    try:
        ejecucion = monitoreo.obtener_detalle_ejecucion(id_ejecucion)

        if ejecucion:
            return jsonify({"success": True, "ejecucion": ejecucion})
        else:
            return jsonify({"success": False, "error": "Ejecución no encontrada"}), 404

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/monitoreo/guardar-ejecucion", methods=["POST"])
def monitoreo_guardar_ejecucion():
    """
    Guarda o actualiza una ejecución de control.

    Espera un JSON con:
        - id_datcontmon: ID del control
        - fecha: fecha de ejecución (YYYY-MM-DD)
        - descripcion: observaciones de la ejecución
        - id_ejecucion (opcional): ID para actualizar registro existente

    Returns:
        JSON con success y opcionalmente proxima_fecha actualizada
    """
    try:
        data = request.get_json()
        id_datcontmon = data.get('id_datcontmon')
        fecha = data.get('fecha')
        descripcion = data.get('descripcion')
        id_ejecucion = data.get('id_ejecucion')

        if not id_datcontmon:
            return jsonify({"success": False, "error": "ID de control requerido"}), 400

        # Validar ID numérico
        try:
            id_datcontmon = int(id_datcontmon)
            if id_ejecucion:
                id_ejecucion = int(id_ejecucion)
        except ValueError:
            return jsonify({"success": False, "error": "ID inválido"}), 400

        # Guardar la ejecución
        resultado = monitoreo.guardar_ejecucion(
            id_datcontmon=id_datcontmon,
            fecha_ejecucion=fecha,
            descripcion=descripcion,
            id_ejecucion=id_ejecucion
        )

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/monitoreo/guardar-control", methods=["POST"])
def monitoreo_guardar_control():
    """
    Guarda todos los campos de un control en monitoreo de una sola vez.
    """
    try:
        data = request.get_json()
        id_datcontmon = data.get('id_datcontmon')

        if not id_datcontmon:
            return jsonify({"success": False, "error": "ID de control requerido"}), 400

        # Validar ID numérico
        try:
            id_datcontmon = int(id_datcontmon)
        except ValueError:
            return jsonify({"success": False, "error": "ID inválido"}), 400

        # Llamar a una nueva función en monitoreo.py
        resultado = monitoreo.guardar_control_completo(
            id_datcontmon=id_datcontmon,
            estado=data.get('estado'),
            responsable=data.get('responsable'),
            madurez_actual=data.get('madurez_actual'),
            madurez_objetivo=data.get('madurez_objetivo'),
            frecuencia=data.get('frecuencia'),
            descripcion=data.get('descripcion'),
            fecha_proxima=data.get('fecha_proxima'),
            fecha_ultima=data.get('fecha_ultima')
        )

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/monitoreo/eliminar-ejecucion/<int:id_ejecucion>", methods=["DELETE"])
def monitoreo_eliminar_ejecucion(id_ejecucion):
    """
    Elimina una ejecución de control.

    Args:
        id_ejecucion (int): ID de la ejecución a eliminar

    Returns:
        JSON con success
    """
    try:
        resultado = monitoreo.eliminar_ejecucion(id_ejecucion)
        return jsonify(resultado)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/estadisticas_monitoreo/<int:id_sistema>')
def api_estadisticas_monitoreo(id_sistema):
    """
    Endpoint para obtener las estadísticas de monitoreo en formato JSON.
    """
    try:
        estadisticas = monitoreo.obtener_estadisticas_monitoreo(id_sistema)
        return jsonify(estadisticas)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/formulario/resultados")
def formulario_resultados():
    """Muestra el formulario de resultados."""
    return render_template("formulario_resultados.html", preguntas=[], active_tab="resultados")



@app.route("/api/ayuda-contexto/<formulario>/<control>")
def obtener_ayuda_contexto(formulario, control):
    """
    Obtiene el texto de ayuda contextual para un control específico.

    Args:
        formulario (str): Nombre del formulario.
        control (str): ID del control HTML.

    Returns:
        JSON: {"success": True, "ayuda": "texto", "id": ID, "pos_x": X, "pos_y": Y, "width": W, "height": H, "screen_width": SW}
              o {"success": False}
    """
    session = Session()
    try:
        ayuda = session.query(AyudaContexto).filter(
            AyudaContexto.C_FORMULARIO == formulario,
            AyudaContexto.C_CONTROL == control,
            AyudaContexto.L_ESTADO == 1
        ).first()

        if ayuda:
            return jsonify({
                "success": True,
                "ayuda": ayuda.T_AYUDA,
                "tipo": ayuda.C_TIPO,
                "id": ayuda.ID_AYUDACONTEXTO,
                "pos_x": ayuda.N_POS_X,
                "pos_y": ayuda.N_POS_Y,
                "width": ayuda.N_WIDTH,
                "height": ayuda.N_HEIGHT,
                "screen_width": ayuda.N_SCREEN_WIDTH
            })
        else:
            return jsonify({"success": False})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


@app.route("/api/ayuda-contexto/formulario/<formulario>")
def obtener_ayudas_formulario(formulario):
    """
    Obtiene TODAS las ayudas contextuales de un formulario específico en una sola petición.

    Esta es la optimización clave: en lugar de hacer N peticiones (una por cada elemento
    del DOM), el frontend hace UNA sola petición que devuelve todas las ayudas del
    formulario, reduciendo drásticamente el tiempo de carga.

    Args:
        formulario (str): Nombre del formulario (ej: 'formulario_controles')

    Returns:
        JSON: {
            "success": true,
            "formulario": "formulario_controles",
            "ayudas": [
                {
                    "id": 123,
                    "control": "th-nombre-control",
                    "tipo": "C",
                    "ayuda": "<p>Texto de ayuda...</p>",
                    "pos_x": null,
                    "pos_y": null,
                    "width": null,
                    "height": null,
                    "screen_width": null
                },
                ...
            ],
            "total": 15
        }
    """
    session = Session()
    try:
        # Consultar todas las ayudas activas del formulario
        ayudas = session.query(AyudaContexto).filter(
            AyudaContexto.C_FORMULARIO == formulario,
            AyudaContexto.L_ESTADO == 1
        ).all()

        # Convertir a lista de diccionarios
        ayudas_list = []
        for ayuda in ayudas:
            ayudas_list.append({
                'id': ayuda.ID_AYUDACONTEXTO,
                'control': ayuda.C_CONTROL,
                'tipo': ayuda.C_TIPO,
                'ayuda': ayuda.T_AYUDA,
                'pos_x': ayuda.N_POS_X,
                'pos_y': ayuda.N_POS_Y,
                'width': ayuda.N_WIDTH,
                'height': ayuda.N_HEIGHT,
                'screen_width': ayuda.N_SCREEN_WIDTH
            })

        return jsonify({
            'success': True,
            'formulario': formulario,
            'ayudas': ayudas_list,
            'total': len(ayudas_list)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'ayudas': []
        }), 500
    finally:
        session.close()


# =============================================================================
# ENDPOINTS DE VISIBILIDAD DINÁMICA
# =============================================================================

@app.route("/api/visibilidad/config/<formulario>")
def obtener_configuracion_visibilidad(formulario):
    """
    Obtiene TODAS las configuraciones de visibilidad de un formulario.

    Similar al endpoint de ayuda-contexto/formulario, devuelve todas las reglas
    de visibilidad en una sola petición para máximo rendimiento.

    Args:
        formulario (str): Nombre del formulario (ej: 'formulario_controles')

    Returns:
        JSON: Lista de configuraciones de visibilidad activas
    """
    from models import ConfiguracionVisibilidad

    session = Session()
    try:
        configs = session.query(ConfiguracionVisibilidad).filter(
            ConfiguracionVisibilidad.C_FORMULARIO == formulario,
            ConfiguracionVisibilidad.L_ACTIVO == 1
        ).order_by(ConfiguracionVisibilidad.N_PRIORIDAD).all()

        configs_list = []
        for config in configs:
            configs_list.append({
                'id': config.ID_CFGVISIBILIDAD,
                'elemento_id': config.C_ELEMENTO_ID,
                'tipo_elem': config.C_TIPO_ELEM,
                'condicion': config.T_CONDICION,
                'accion': config.C_ACCION,
                'prioridad': config.N_PRIORIDAD,
                'descripcion': config.T_DESCRIPCION,
                'l_activo': config.L_ACTIVO
            })

        return jsonify(configs_list)

    except Exception as e:
        return jsonify([]), 500
    finally:
        session.close()



@app.route("/api/ayuda-contexto/guardar-posicion", methods=["POST"])
def guardar_posicion_ayuda():
    """
    Guarda la posición y tamaño del modal de ayuda contextual.

    Espera JSON: {
        "id": ID_AYUDACONTEXTO,
        "pos_x": X,
        "pos_y": Y,
        "width": W,
        "height": H,
        "screen_width": SW
    }

    Returns:
        JSON: {"success": True} o {"success": False, "error": "mensaje"}
    """
    session = Session()
    try:
        data = request.get_json()

        ayuda_id = data.get('id')
        if not ayuda_id:
            return jsonify({"success": False, "error": "ID no proporcionado"}), 400

        ayuda = session.query(AyudaContexto).filter(
            AyudaContexto.ID_AYUDACONTEXTO == ayuda_id
        ).first()

        if not ayuda:
            return jsonify({"success": False, "error": "Ayuda no encontrada"}), 404

        # Actualizar los campos de posición y tamaño
        ayuda.N_POS_X = data.get('pos_x')
        ayuda.N_POS_Y = data.get('pos_y')
        ayuda.N_WIDTH = data.get('width')
        ayuda.N_HEIGHT = data.get('height')
        ayuda.N_SCREEN_WIDTH = data.get('screen_width')

        session.commit()

        # ✨ IMPORTANTE: Forzar sincronización al disco
        # Esto es necesario si MODO_PERSISTENCIA no es "TRANSACCION"
        from models import sync_database
        sync_database()

        return jsonify({"success": True})

    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


@app.route("/formulario/fases")
def formulario_fases():
    """
    Muestra el formulario de seguimiento de fases del proyecto.

    Returns:
        Response: Renderiza la plantilla 'formulario_fases.html' con los datos de las fases.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return render_template('modal_proyecto_no_seleccionado.html'), 400

    try:
        fase_actual, todas_fases = obtener_fase_proyecto(id_sistema)

        validacion_fase = validar_condiciones_cambio_fase(id_sistema)

        return render_template(
            "formulario_fases.html",
            fase_obj=fase_actual,  # Renombrado para no sobrescribir la variable global del context processor
            todas_fases=todas_fases,
            validacion=validacion_fase,
            active_tab="fases"
        )

    except ValueError as ve:
        flash(f"⚠️ {str(ve)}", "danger")
        return redirect(url_for('seleccionar_proyecto'))

    except Exception as e:
        flash("❌ Error al cargar las fases. Por favor, inténtalo de nuevo.", "danger")
        return f"<h3>Error al cargar fases: {str(e)}</h3>", 500


@app.route("/finalizar-fase", methods=["POST"])
def finalizar_fase():
    """
    Finaliza la fase actual del proyecto y avanza a la siguiente fase.

    Returns:
        Response: Redirección al formulario de fases con mensaje.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        flash("❌ No hay proyecto seleccionado.", "danger")
        return redirect(url_for('index'))

    resultado = avanzar_fase_proyecto(id_sistema)

    if resultado["success"]:
        flash(f"✅ {resultado['mensaje']}", "success")
    else:
        flash(f"⚠️ {resultado['mensaje']}", "warning")

    return redirect(url_for('formulario_fases'))

@app.route("/salir-monitoreo", methods=["POST"])
def salir_monitoreo():
    """
    Ruta para manejar la solicitud de salir de la fase de monitoreo.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        flash("❌ No hay proyecto seleccionado.", "danger")
        return redirect(url_for('index'))

    # Llama a la función del controlador
    resultado = retroceder_fase_proyecto(id_sistema)

    if resultado["success"]:
        flash(f"✅ {resultado['mensaje']}", "success")
        # Opcional: Puedes redirigir a la página de fases o a donde sea apropiado
        # Por consistencia con finalizar_fase, redirigimos a la misma página (formulario_fases)
        return redirect(url_for('formulario_fases'))
    else:
        flash(f"❌ {resultado['mensaje']}", "danger")
        return redirect(url_for('formulario_fases')) # O redirigir a inicio u otra página de error


@app.route("/api/validar-fase", methods=["GET"])
def api_validar_fase():
    """
    Endpoint AJAX para validar si se puede avanzar de fase.
    Retorna JSON con el estado de validación.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"error": "No hay proyecto seleccionado"}), 400

    try:
        validacion = validar_condiciones_cambio_fase(id_sistema)
        return jsonify(validacion)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/formulario/documentos")
def formulario_documentos():
    """
    Muestra la página de gestión de documentos (EIPD, IV, etc.).

    Lista todos los documentos disponibles según la fase actual del proyecto
    y permite seleccionar uno para editarlo.
    Incluye sección de exportaciones si el proyecto está en fase de riesgos residuales o monitoreo.
    Incluye exportación de requisitos si la fase actual permite visualizar requisitos.
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return render_template('modal_proyecto_no_seleccionado.html'), 400

    # Obtener nivel de riesgo y si es fase de monitoreo
    nivel_riesgo = None
    fase_monitoreo = False
    mostrar_requisitos = False

    try:
        fase_actual, _ = obtener_fase_proyecto(id_sistema)
        if fase_actual:
            nivel_riesgo = fase_actual.C_NIVELRIESG
            fase_monitoreo = fase_actual.L_MONITOREO == 1

            # Verificar si debe mostrarse la exportación de Requisitos
            # Usa la misma lógica que el context_processor para mostrar la pestaña
            db_session = Session()
            try:
                fase_actual_orden = fase_actual.N_ORDEN

                # Consultar si existen requisitos activos con fase visual <= fase actual
                requisitos = db_session.query(ConfiguracionRequisito).filter(
                    ConfiguracionRequisito.L_ESTADO == 1
                ).all()

                for req in requisitos:
                    if req.N_FASEVISUAL:
                        fase_visual = db_session.query(ConfiguracionFase).filter_by(
                            ID_FASE=req.N_FASEVISUAL
                        ).first()

                        if fase_visual and fase_visual.N_ORDEN <= fase_actual_orden:
                            mostrar_requisitos = True
                            break
                    else:
                        # Si no tiene fase visual definida, siempre es visible
                        mostrar_requisitos = True
                        break
            finally:
                db_session.close()

    except Exception as e:
        pass

    try:
        # Obtener documentos disponibles
        docs_disponibles = documentos.obtener_documentos_disponibles(id_sistema)

        return render_template(
            "formulario_documentos.html",
            documentos=docs_disponibles,
            nivel_riesgo=nivel_riesgo,
            fase_monitoreo=fase_monitoreo,
            mostrar_requisitos=mostrar_requisitos,
            active_tab="documentos"
        )

    except Exception as e:
        flash(f"❌ Error al cargar documentos: {str(e)}", "danger")
        return redirect(url_for('index'))


# ============================================================================
# EXPORTACIÓN DE MITIGACIÓN DE RIESGOS
# ============================================================================

@app.route("/exportar/mitigacion-riesgos", methods=["POST"])
def exportar_mitigacion_riesgos():
    """
    Genera y devuelve un archivo Excel con el informe de mitigación de riesgos.

    El archivo incluye todos los riesgos activos y aplicables (no personales)
    con sus controles de mitigación asociados.

    Returns:
        JSON con:
        - exito: bool indicando si la exportación fue exitosa
        - mensaje: descripción del resultado
        - url_descarga: URL para descargar el archivo (si exito=True)
        - nombre_archivo: nombre del archivo generado (si exito=True)
    """
    from exportaciones import exportar_mitigacion_riesgos as generar_exportacion_mitigacion

    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({
            "exito": False,
            "mensaje": "No hay proyecto seleccionado"
        }), 400

    try:
        # Directorio de salida para exportaciones
        output_dir = tempfile.gettempdir()

        # Generar la exportación
        resultado = generar_exportacion_mitigacion(id_sistema, output_dir)

        if resultado["exito"]:
            # Guardar la ruta del archivo en la sesión para la descarga
            flask_session['ultimo_archivo_exportacion'] = resultado["archivo"]

            return jsonify({
                "exito": True,
                "mensaje": resultado["mensaje"],
                "url_descarga": url_for('descargar_exportacion', filename=resultado["nombre_archivo"]),
                "nombre_archivo": resultado["nombre_archivo"]
            })
        else:
            return jsonify({
                "exito": False,
                "mensaje": resultado["mensaje"]
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "exito": False,
            "mensaje": f"Error inesperado: {str(e)}"
        }), 500


@app.route("/exportar/controles-monitoreo", methods=["POST"])
def exportar_controles_monitoreo():
    """
    Genera y devuelve un archivo CSV con los datos de controles de monitoreo.

    Returns:
        JSON con:
        - exito: bool indicando si la exportación fue exitosa
        - mensaje: descripción del resultado
        - url_descarga: URL para descargar el archivo (si exito=True)
        - nombre_archivo: nombre del archivo generado (si exito=True)
    """
    from exportaciones import exportar_controles_monitoreo_csv

    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({
            "exito": False,
            "mensaje": "No hay proyecto seleccionado"
        }), 400

    try:
        # Directorio de salida para exportaciones
        output_dir = tempfile.gettempdir()

        # Generar la exportación
        resultado = exportar_controles_monitoreo_csv(id_sistema, output_dir)

        if resultado["exito"]:
            return jsonify({
                "exito": True,
                "mensaje": resultado["mensaje"],
                "url_descarga": url_for('descargar_exportacion', filename=resultado["nombre_archivo"]),
                "nombre_archivo": resultado["nombre_archivo"]
            })
        else:
            return jsonify({
                "exito": False,
                "mensaje": resultado["mensaje"]
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "exito": False,
            "mensaje": f"Error inesperado: {str(e)}"
        }), 500


@app.route("/exportar/elementos-descripcion/<formato>", methods=["POST"])
def exportar_elementos_descripcion(formato):
    """
    Genera y devuelve un archivo HTML o PDF con los elementos de descripción.

    Args:
        formato: 'html' o 'pdf'

    Returns:
        JSON con:
        - exito: bool indicando si la exportación fue exitosa
        - mensaje: descripción del resultado
        - url_descarga: URL para descargar el archivo (si exito=True)
        - nombre_archivo: nombre del archivo generado (si exito=True)
    """
    from exportaciones import exportar_elementos_descripcion_html, exportar_elementos_descripcion_pdf

    if formato not in ['html', 'pdf']:
        return jsonify({
            "exito": False,
            "mensaje": "Formato no válido. Use 'html' o 'pdf'."
        }), 400

    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({
            "exito": False,
            "mensaje": "No hay proyecto seleccionado"
        }), 400

    try:
        # Directorio de salida para exportaciones
        output_dir = tempfile.gettempdir()

        # Generar la exportación según el formato
        if formato == 'html':
            resultado = exportar_elementos_descripcion_html(id_sistema, output_dir)
        else:
            resultado = exportar_elementos_descripcion_pdf(id_sistema, output_dir)

        if resultado["exito"]:
            return jsonify({
                "exito": True,
                "mensaje": resultado["mensaje"],
                "url_descarga": url_for('descargar_exportacion', filename=resultado["nombre_archivo"]),
                "nombre_archivo": resultado["nombre_archivo"]
            })
        else:
            return jsonify({
                "exito": False,
                "mensaje": resultado["mensaje"]
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "exito": False,
            "mensaje": f"Error inesperado: {str(e)}"
        }), 500


# ============================================================================
# EXPORTACIÓN DE REQUISITOS DE CUMPLIMIENTO
# ============================================================================

@app.route("/exportar/requisitos-cumplimiento", methods=["POST"])
def exportar_requisitos_cumplimiento():
    """
    Genera y devuelve un archivo Excel con el informe de requisitos de cumplimiento.

    El archivo incluye todos los requisitos aplicables con sus estados de planificación
    y cumplimiento, controles asociados activos y aplicables, y planes de mejora cuando
    corresponda.

    Returns:
        JSON con:
        - exito: bool indicando si la exportación fue exitosa
        - mensaje: descripción del resultado
        - url_descarga: URL para descargar el archivo (si exito=True)
        - nombre_archivo: nombre del archivo generado (si exito=True)
    """
    from exportaciones import exportar_requisitos_cumplimiento as generar_exportacion_requisitos

    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({
            "exito": False,
            "mensaje": "No hay proyecto seleccionado"
        }), 400

    try:
        # Directorio de salida para exportaciones
        output_dir = tempfile.gettempdir()

        # Generar la exportación
        resultado = generar_exportacion_requisitos(id_sistema, output_dir)

        if resultado["exito"]:
            # Guardar la ruta del archivo en la sesión para la descarga
            flask_session['ultimo_archivo_exportacion'] = resultado["archivo"]

            return jsonify({
                "exito": True,
                "mensaje": resultado["mensaje"],
                "url_descarga": url_for('descargar_exportacion', filename=resultado["nombre_archivo"]),
                "nombre_archivo": resultado["nombre_archivo"]
            })
        else:
            return jsonify({
                "exito": False,
                "mensaje": resultado["mensaje"]
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "exito": False,
            "mensaje": f"Error inesperado: {str(e)}"
        }), 500


@app.route("/descargar/exportacion/<filename>")
def descargar_exportacion(filename):
    """
    Descarga un archivo de exportación previamente generado.

    Args:
        filename: Nombre del archivo a descargar

    Returns:
        El archivo para descarga o error 404 si no existe
    """
    # Verificar que hay sesión activa
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return "No autorizado", 403

    # Construir la ruta completa
    filepath = os.path.join(tempfile.gettempdir(), filename)

    # Verificar que el archivo existe y es válido
    if not os.path.exists(filepath):
        return "Archivo no encontrado", 404

    # Verificar que el nombre del archivo corresponde a una exportación válida
    # RM_*.xlsx = Mitigación de Riesgos
    # RC_*.xlsx = Requisitos de Cumplimiento
    # CM_*.csv = Controles Monitoreo
    # ED_*.html = Elementos de Descripción HTML
    # ED_*.pdf = Elementos de Descripción PDF
    es_valido = (
        (filename.startswith("RM_") and filename.endswith(".xlsx")) or
        (filename.startswith("RC_") and filename.endswith(".xlsx")) or
        (filename.startswith("CM_") and filename.endswith(".csv")) or
        (filename.startswith("ED_") and filename.endswith(".html")) or
        (filename.startswith("ED_") and filename.endswith(".pdf"))
    )

    if not es_valido:
        return "Archivo no válido", 400

    # Determinar el mimetype según la extensión
    if filename.endswith(".xlsx"):
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif filename.endswith(".csv"):
        mimetype = 'text/csv; charset=utf-8'
    elif filename.endswith(".html"):
        mimetype = 'text/html; charset=utf-8'
    else:  # .pdf
        mimetype = 'application/pdf'

    try:
        return send_file(
            filepath,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return "Error al descargar el archivo", 500

@app.route('/api/recalcular-riesgo-residual', methods=['POST'])
def api_recalcular_riesgo_residual():
    """
    Recalcula el riesgo residual de un riesgo específico en tiempo real.
    Se usa cuando se cambia la madurez o aplicabilidad de controles.

    Espera JSON:
        {
            "id_riesgo": int  # ID_RIESGO (no ID_DATRIES)
        }

    Returns:
        JSON con el riesgo residual actualizado
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return jsonify({"success": False, "error": "No hay proyecto seleccionado"}), 400

    session = Session()
    try:
        data = request.get_json()
        id_riesgo = data.get('id_riesgo')

        if not id_riesgo:
            return jsonify({"success": False, "error": "ID de riesgo requerido"}), 400

        # Validar ID numérico
        try:
            id_riesgo = int(id_riesgo)
        except ValueError:
            return jsonify({"success": False, "error": "ID de riesgo inválido"}), 400

        # Obtener el registro de DatosRiesgo para este sistema y riesgo
        datos_riesgo = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.RIE_ID_RIESGO == id_riesgo
        ).first()

        if not datos_riesgo:
            return jsonify({"success": False, "error": "Riesgo no encontrado"}), 404

        # Calcular criticidad inherente
        if datos_riesgo.V_IMPACTO and datos_riesgo.V_PROBABILIDAD:
            config_criticidad = session.query(ConfiguracionCriticidad).filter_by(
                V_IMPACTO=datos_riesgo.V_IMPACTO,
                V_PROBAB=datos_riesgo.V_PROBABILIDAD
            ).first()

            if config_criticidad:
                criticidad_inherente = config_criticidad.N_CRITICIDAD
            else:
                return jsonify({
                    "success": False,
                    "error": "No se encontró configuración de criticidad"
                }), 404
        else:
            return jsonify({
                "success": False,
                "error": "El riesgo no tiene impacto o probabilidad definidos"
            }), 400

        # Calcular riesgo residual usando la función existente
        from controllers import calcular_riesgo_residual

        riesgo_residual, nivel_residual = calcular_riesgo_residual(
            session,
            datos_riesgo,
            criticidad_inherente
        )

        # Mapeo de texto a clase CSS
        nivel_texto_a_clase = {
            "CRÍTICO": "text-danger fw-bold",
            "ALTO": "text-warning fw-bold",
            "MEDIO": "text-info",
            "BAJO": "text-success",
            "—": "text-muted"
        }

        clase_nivel = nivel_texto_a_clase.get(nivel_residual, "text-muted")


        return jsonify({
            "success": True,
            "riesgo_residual": riesgo_residual,
            "nivel_residual": {
                "texto": nivel_residual,
                "clase": clase_nivel
            }
        })

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


@app.route("/formulario/documentos/<int:id_datdocs>")
def editar_documento(id_datdocs):
    """
    Muestra el formulario de edición de un documento específico.

    Args:
        id_datdocs (int): ID del documento a editar
    """
    id_sistema = flask_session.get("id_sistema")
    if not id_sistema:
        return render_template('modal_proyecto_no_seleccionado.html'), 400

    # --- CALCULAR monitoreo ---
    monitoreo = False
    try:
        fase_actual, _ = obtener_fase_proyecto(id_sistema)
        if fase_actual and fase_actual.L_MONITOREO == 1:
            monitoreo = True
    except Exception as e:
        pass

    try:
        # Obtener estructura del documento
        estructura = documentos.obtener_estructura_documento(id_datdocs)

        if not estructura:
            flash("❌ Documento no encontrado", "danger")
            return redirect(url_for('formulario_documentos'))

        # Verificar que el documento pertenece al sistema actual
        if estructura['id_sistema'] != id_sistema:
            flash("❌ No tiene permisos para editar este documento", "danger")
            return redirect(url_for('formulario_documentos'))

        # Obtener lista de documentos para el selector
        docs_disponibles = documentos.obtener_documentos_disponibles(id_sistema)

        # 🆕 Obtener el código del tipo de documento

        tipo_doc_codigo = documentos.obtener_codigo_tipo_documento(id_datdocs)

        # 🆕 Obtener estados disponibles específicos del tipo de documento
        estados_disponibles = documentos.obtener_estados_documento(tipo_doc_codigo)
        for estado in estados_disponibles:
            pass

        # 🆕 Obtener el ID del estado actual
        from models import DatosDocumento, ValoresDato
        session = Session()
        doc_actual = session.query(DatosDocumento).filter_by(ID_DATDOCS=id_datdocs).first()
        id_estado_actual = doc_actual.V_SITUACION if doc_actual else None

        # 🆕 Determinar si el documento está finalizado (C_VALOR == 3)
        documento_finalizado = False
        if id_estado_actual:
            estado_obj = session.query(ValoresDato).filter_by(ID_VALDAT=id_estado_actual).first()
            if estado_obj:
                if estado_obj.C_VALOR == 3:  # ✅ CORRECTO - Finalizado
                    documento_finalizado = True
        session.close()


        # 🆕 Verificar si existen relaciones de copia automática
        tiene_copia_automatica = documentos.tiene_relaciones_copia_automatica(id_datdocs)

        # 🆕 Verificar si existen campos configurados
        tiene_campos = documentos.tiene_campos_configurados(id_datdocs)

        # 🆕 Verificar si el documento tiene plantilla configurada
        tiene_plantilla = False
        v_sitnoaplica = None
        from models import ConfiguracionDocumento
        session = Session()
        doc_config = session.query(DatosDocumento).filter_by(ID_DATDOCS=id_datdocs).first()
        if doc_config:
            config_doc = session.query(ConfiguracionDocumento).filter_by(
                ID_CFGDOCS=doc_config.DD_ID_CFGDOCS
            ).first()
            if config_doc and config_doc.T_PLANTILLA:
                tiene_plantilla = True

            # 🆕 Obtener V_SITNOAPLICA para determinar si mostrar el botón de anexos
            if config_doc:
                v_sitnoaplica = config_doc.V_SITNOAPLICA
        session.close()

        return render_template(
            "editar_documento.html",
            estructura=estructura,
            documentos=docs_disponibles,
            estados_disponibles=estados_disponibles,
            id_estado_actual=id_estado_actual,
            documento_finalizado=documento_finalizado,
            monitoreo=monitoreo,
            tiene_copia_automatica=tiene_copia_automatica,
            tiene_campos=tiene_campos,
            tiene_plantilla=tiene_plantilla,
            v_sitnoaplica=v_sitnoaplica,
            id_sistema=id_sistema,
            active_tab="documentos"
        )

    except Exception as e:
        flash(f"❌ Error al cargar documento: {str(e)}", "danger")
        return redirect(url_for('formulario_documentos'))

# ============================================================================
# 🆕 NUEVO ENDPOINT: Obtener mensaje de confirmación para copia automática EIPD
# ============================================================================
@app.route('/api/obtener-mensaje-copia-eipd', methods=['GET'])
def obtener_mensaje_copia_eipd():
    """
    Obtiene el mensaje de confirmación para la copia automática desde IA_VALDAT.

    Busca el registro donde:
    - C_VALOR_TEXT = 'MSGCOPIAEIPD'
    - TIPDAT = 'MSGS'

    Returns:
        JSON con el mensaje HTML formateado o error
    """
    session = Session()
    try:

        # Primero obtener el ID del tipo de dato
        tipo_dato = session.query(TiposDato).filter(
            TiposDato.C_TIPDAT == 'MSGS'
        ).first()

        if not tipo_dato:
            return jsonify({
                "success": False,
                "message": "No se encontró el tipo de dato MSGS"
            }), 404

        # Obtener el valor correspondiente
        mensaje_registro = session.query(ValoresDato).filter(
            and_(
                ValoresDato.TIDA_ID_TIPDAT == tipo_dato.ID_TIPDAT,
                ValoresDato.C_VALOR_TEXT == 'MSGCOPIAEIPD'
            )
        ).first()


        if not mensaje_registro:
            return jsonify({
                'success': False,
                'message': 'No se encontró el mensaje de confirmación en la base de datos'
            }), 404

        # El mensaje está en el campo T_DESC
        mensaje_html = mensaje_registro.D_VALOR if mensaje_registro.D_VALOR else ""


        return jsonify({
            'success': True,
            'mensaje': mensaje_html
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error al obtener el mensaje: {str(e)}'
        }), 500

    finally:
        session.close()



@app.route("/api/guardar-campo-documento", methods=["POST"])
def api_guardar_campo_documento():
    """
    API para autoguardado de campos del documento.

    Espera JSON:
        {
            "id_datelemdocs": int,
            "valor": str
        }
    """
    try:
        data = request.get_json()
        id_datelemdocs = data.get('id_datelemdocs')
        valor = data.get('valor', '')

        if not id_datelemdocs:
            return jsonify({"success": False, "error": "ID de campo requerido"}), 400

        resultado = documentos.guardar_campo_documento(id_datelemdocs, valor)

        if resultado['success']:
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/copiar-datos-automaticos/<int:id_datdocs>", methods=["POST"])
def api_copiar_datos_automaticos(id_datdocs):
    """
    API para copiar datos de elementos ADI al documento.

    Args:
        id_datdocs (int): ID del documento
    """
    try:
        resultado = documentos.copiar_datos_elementos_adi(id_datdocs)

        if resultado['success']:
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/copiar-dato-individual/<int:id_datelemdocs>/<int:id_subelem>', methods=['POST'])
def api_copiar_dato_individual(id_datelemdocs, id_subelem):
    from documentos import copiar_dato_individual
    resultado = copiar_dato_individual(id_datelemdocs, id_subelem)
    return jsonify(resultado)

@app.route("/api/cambiar-estado-documento", methods=["POST"])
def api_cambiar_estado_documento():
    """
    API para cambiar el estado de un documento.

    Espera JSON:
        {
            "id_datdocs": int,
            "id_estado": int
        }
    """
    try:
        data = request.get_json()
        id_datdocs = data.get('id_datdocs')
        id_estado = data.get('id_estado')

        if not id_datdocs or not id_estado:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        # Validar IDs numéricos
        try:
            id_datdocs = int(id_datdocs)
            id_estado = int(id_estado)
        except ValueError:
            return jsonify({"success": False, "error": "IDs inválidos"}), 400

        resultado = documentos.actualizar_situacion_documento(id_datdocs, id_estado)

        if resultado['success']:
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/actualizar-situacion-documento", methods=["POST"])
def api_actualizar_situacion_documento():
    """
    API para actualizar el estado de un documento.

    Espera JSON:
        {
            "id_datdocs": int,
            "situacion": int
        }
    """
    try:
        data = request.get_json()
        id_datdocs = data.get('id_datdocs')
        situacion = data.get('situacion')

        if not id_datdocs or not situacion:
            return jsonify({"success": False, "error": "Datos incompletos"}), 400

        resultado = documentos.actualizar_situacion_documento(id_datdocs, situacion)

        if resultado['success']:
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/generar-documento/<int:id_datdocs>", methods=["POST"])
def api_generar_documento(id_datdocs):
    """
    Genera un documento HTML desde una plantilla encriptada.

    Args:
        id_datdocs (int): ID del documento a generar

    Returns:
        JSON con:
            - success (bool): True si se generó correctamente
            - html (str): Contenido HTML generado
            - nombre_archivo (str): Nombre sugerido para el archivo
            - mensaje (str): Mensaje de error (si success=False)
    """
    try:

        # Llamar a la función de generación de documento
        resultado = documentos.generar_documento_desde_plantilla(id_datdocs)

        if resultado['success']:
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "mensaje": f"Error interno: {str(e)}"
        }), 500


@app.route("/api/generar-documento-pdf/<int:id_datdocs>", methods=["POST"])
def api_generar_documento_pdf(id_datdocs):
    """
    Genera un documento PDF desde una plantilla encriptada.

    Args:
        id_datdocs (int): ID del documento a generar

    Returns:
        Archivo PDF para descargar o JSON con error
    """
    try:

        # Llamar a la función de generación de documento PDF
        resultado = documentos.generar_documento_pdf_desde_plantilla(id_datdocs)

        if resultado['success']:

            # Retornar el PDF como un archivo descargable
            from flask import send_file
            import io

            pdf_buffer = io.BytesIO(resultado['pdf'])
            pdf_buffer.seek(0)

            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=resultado['nombre_archivo']
            )
        else:
            return jsonify(resultado), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "mensaje": f"Error interno: {str(e)}"
        }), 500


@app.route("/api/generar-anexos-csv/<int:id_sistema>", methods=["POST"])
def api_generar_anexos_csv(id_sistema):
    """
    Genera dos archivos CSV con anexos del proyecto:
    1. Matriz de riesgos (Inherente y Residual)
    2. Catálogo de controles y madurez

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        Archivo ZIP con los dos CSV o JSON con error
    """
    try:

        # Llamar a la función de generación de anexos
        resultado = documentos.generar_anexos_csv(id_sistema)

        if resultado['success']:

            # Crear un archivo ZIP con los dos CSV
            from flask import send_file
            import io
            import zipfile

            # Crear buffer para el ZIP
            zip_buffer = io.BytesIO()

            # Crear el archivo ZIP
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for archivo in resultado['archivos']:
                    # Agregar cada CSV al ZIP
                    zip_file.writestr(
                        archivo['nombre_archivo'],
                        archivo['contenido'].encode('utf-8-sig')  # UTF-8 con BOM para Excel
                    )

            zip_buffer.seek(0)

            # Nombre del archivo ZIP con formato Anexos_PPPP_AAAAMMDDHHmmSS.zip
            from datetime import datetime
            from documentos import limpiar_nombre_archivo
            from models import Session, Inicio

            # Obtener el nombre del proyecto
            session = Session()
            try:
                proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
                nombre_proyecto = proyecto.D_NOMPROYEC if proyecto and proyecto.D_NOMPROYEC else 'Proyecto'
            finally:
                session.close()

            # Limpiar nombre del proyecto
            nombre_proyecto_limpio = limpiar_nombre_archivo(nombre_proyecto)

            # Formato de fecha: AAAAMMDDHHmmSS
            fecha_hora = datetime.now().strftime("%Y%m%d%H%M%S")

            # Construir nombre: Anexos_PPPP_AAAAMMDDHHmmSS.zip
            nombre_zip = f"Anexos_{nombre_proyecto_limpio}_{fecha_hora}.zip"

            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=nombre_zip
            )
        else:
            return jsonify(resultado), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "mensaje": f"Error interno: {str(e)}"
        }), 500


@app.context_processor
def inject_tabs():
    """
    Inyecta las pestañas de navegación en todas las plantillas.

    Esta función se ejecuta en cada renderizado de plantilla y agrega la variable 'tabs'
    al contexto, permitiendo mostrar la barra de navegación en todas las vistas.

    Returns:
        dict: Diccionario con la lista de pestañas disponibles para la navegación.
    """
    # Obtener el ID del sistema de la sesión
    id_sistema = flask_session.get("id_sistema")
    mostrar_monitoreo = False
    mostrar_requisitos = False

    # Verificar si hay proyecto seleccionado y si está en fase de monitoreo
    if id_sistema:
        try:
            # Primero verificar que el proyecto existe en la BD
            db_session = Session()
            try:
                proyecto_existe = db_session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
                if not proyecto_existe:
                    # El proyecto no existe, limpiar sesión y continuar sin pestañas especiales
                    flask_session.pop("id_sistema", None)
                    db_session.close()
                else:
                    db_session.close()

                    # Ahora sí, obtener la fase del proyecto (sabemos que existe)
                    fase_actual, _ = obtener_fase_proyecto(id_sistema)
                    if fase_actual and fase_actual.L_MONITOREO == 1:
                        mostrar_monitoreo = True

                    # Verificar si debe mostrarse la pestaña de Requisitos
                    # Solo se muestra si existen requisitos con fase de visualización <= fase actual
                    if fase_actual:
                        db_session = Session()
                        try:
                            fase_actual_orden = fase_actual.N_ORDEN

                            # Consultar si existen requisitos activos con fase visual <= fase actual
                            requisitos = db_session.query(ConfiguracionRequisito).filter(
                                ConfiguracionRequisito.L_ESTADO == 1
                            ).all()

                            for req in requisitos:
                                if req.N_FASEVISUAL:
                                    fase_visual = db_session.query(ConfiguracionFase).filter_by(
                                        ID_FASE=req.N_FASEVISUAL
                                    ).first()

                                    if fase_visual and fase_visual.N_ORDEN <= fase_actual_orden:
                                        mostrar_requisitos = True
                                        break
                                else:
                                    # Si no tiene fase visual definida, siempre es visible
                                    mostrar_requisitos = True
                                    break
                        finally:
                            db_session.close()
            except Exception as inner_e:
                db_session.close()
                raise inner_e

        except Exception as e:
            pass
            # En caso de error, no mostrar monitoreo ni requisitos por seguridad


    tabs = [
        {"name": "Proyectos", "endpoint": "seleccionar_proyecto", "active_tab": "proyectos"},
        {"name": "Inicio", "endpoint": "index", "active_tab": "inicio"},
        {"name": "Seguimiento de Fases", "endpoint": "formulario_fases", "active_tab": "fases"},
        {"name": "ADI", "endpoint": "formulario_adi", "active_tab": "adi"},
        {"name": "Elementos de Descripción", "endpoint": "formulario_elementos", "active_tab": "adi_elementos"},
    ]

    # Insertar pestaña de Requisitos si corresponde (ANTES de Riesgos)
    if mostrar_requisitos:
        tabs.append({"name": "Requisitos", "endpoint": "formulario_requisitos", "active_tab": "requisitos"})

    # Continuar con el resto de pestañas
    tabs.extend([
        {"name": "Riesgos", "endpoint": "formulario_riesgos", "active_tab": "riesgos"},
        {"name": "Controles", "endpoint": "formulario_controles", "active_tab": "controles"},
        {"name": "Informes", "endpoint": "formulario_documentos", "active_tab": "documentos"},
        {"name": "Acerca de", "endpoint": "ayuda", "active_tab": "ayuda"}
    ])

    # Agregar pestaña de Monitoreo solo si corresponde
    if mostrar_monitoreo:
        # Insertar después de "Controles" y antes de "Informes"
        tabs.insert(8 if mostrar_requisitos else 7, {"name": "Monitoreo", "endpoint": "formulario_monitoreo", "active_tab": "monitoreo"})

    return dict(tabs=tabs)

@app.route('/manual-uso')
def manual_uso():
    """
    Muestra el manual de uso de la aplicación con guías configuradas dinámicamente.

    Carga las entradas de manuales/guías desde la tabla IA_MANUALUSO,
    ordenadas por N_ORDVISU, filtrando solo las activas (L_ESTADO=1).

    Returns:
        Response: Renderiza 'formulario_manual_uso.html' con la lista de manuales.
    """
    session = Session()
    try:
        # Obtener manuales activos ordenados
        manuales = session.query(ConfiguracionManualUso)\
            .filter(ConfiguracionManualUso.L_ESTADO == 1)\
            .order_by(ConfiguracionManualUso.N_ORDVISU)\
            .all()

        return render_template('formulario_manual_uso.html', manuales=manuales)

    except Exception as e:
        print(f"❌ Error cargando manuales: {e}")
        # En caso de error, mostrar página sin manuales
        return render_template('formulario_manual_uso.html', manuales=[])

    finally:
        session.close()


@app.route('/ayuda')
def ayuda():
    """
    Muestra la página de ayuda con información sobre los elementos del formulario ADI.

    Esta función maneja la ruta '/ayuda' y renderiza la plantilla 'Ayuda_base.html' que contiene
    una tabla con los elementos del formulario ADI, ejemplos y artículos relacionados del RGPD.

    Returns:
        Response: Renderiza la plantilla 'Ayuda_base.html'.
    """
    return render_template("ayuda_base.html", active_tab="ayuda")


# ============================================================================
# RUTAS PARA APLICAR ACTUALIZACIONES
# ============================================================================

@app.route('/aplicar-actualizaciones', methods=['POST'])
def aplicar_actualizaciones():
    """
    Aplica las actualizaciones pendientes de BD y plantillas.
    Si hay actualización de ejecutable, indica que se requiere descarga.

    Returns:
        JSON con resultado de la operación
    """
    global actualizacion_exe_disponible, actualizacion_exe_url

    resultados = {
        'success': True,
        'requiere_descarga_exe': False,
        'redirect': None
    }

    try:
        # Aplicar actualizaciones de BD y plantillas
        exito = actualizacion.aplicar_actualizaciones_pendientes()

        if not exito:
            resultados['success'] = False

        # Verificar si hay actualización de ejecutable pendiente
        info_act = actualizacion.obtener_info_actualizaciones()
        if info_act['exe'] and actualizacion_exe_url:
            resultados['requiere_descarga_exe'] = True
        else:
            # No hay exe que actualizar, redirigir a selección de proyectos
            resultados['redirect'] = url_for('seleccionar_proyecto')

    except Exception as e:
        resultados['success'] = False

    return jsonify(resultados)


@app.route('/cancelar-actualizaciones', methods=['POST'])
def cancelar_actualizaciones():
    """
    Cancela todas las actualizaciones pendientes.
    """
    global actualizacion_exe_disponible, actualizacion_exe_url, actualizacion_exe_version

    # Limpiar actualizaciones pendientes
    actualizacion.limpiar_actualizaciones_pendientes()
    actualizacion.limpiar_actualizacion_pendiente()  # Limpiar archivos de exe si existen

    # Resetear variables globales
    actualizacion_exe_disponible = False
    actualizacion_exe_url = None
    actualizacion_exe_version = None

    flash("Actualizaciones canceladas", "info")
    return redirect(url_for('seleccionar_proyecto'))


@app.route('/api/sistema/<int:sistema_id>/riesgo-global', methods=['GET'])
def api_obtener_riesgo_global(sistema_id):
    """
    Endpoint para obtener el cálculo de riesgo global de un sistema.

    Se llama desde JavaScript para actualizar el badge y panel de diagnóstico.

    Returns:
        JSON con estructura:
        {
            "success": true,
            "data": {
                "nivel": "ALTO",
                "color": "#ED7D31",
                "causa": "FACTORES_AGRAVANTES",
                "factores": [...],
                "metricas": {...},
                "puede_avanzar": false,
                "mensaje": "..."
            }
        }
    """
    session = Session()
    try:
        resultado = calcular_riesgo_global(session, sistema_id)

        # Preparar respuesta para JSON
        respuesta = {
            'nivel': resultado['nivel'],
            'color': resultado['nivel_config'].C_COLOR if resultado['nivel_config'] else None,
            'causa': resultado['causa'],
            'factores': resultado['factores'],
            'metricas': resultado['metricas'],
            'puede_avanzar': resultado['puede_avanzar'],
            'mensaje': resultado['mensaje']
        }

        return jsonify({'success': True, 'data': respuesta})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/sistema/<int:sistema_id>/riesgo-global/clusters', methods=['GET'])
def api_obtener_clusters_sistema(sistema_id):
    """
    Endpoint para obtener información de clusters del sistema.

    Útil para mostrar el detalle de cada cluster en el panel de diagnóstico.
    """
    session = Session()
    try:
        clusters = obtener_info_clusters_sistema(session, sistema_id)
        return jsonify({'success': True, 'data': clusters})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/sistema/<int:sistema_id>/riesgo-global/cluster/<int:cluster_id>/riesgos', methods=['GET'])
def api_obtener_riesgos_cluster(sistema_id, cluster_id):
    """
    Endpoint para obtener los riesgos de un cluster específico.

    Se usa cuando el usuario hace clic en un cluster para ver sus riesgos.
    """
    session = Session()
    try:
        riesgos = obtener_riesgos_por_cluster(session, sistema_id, cluster_id)

        # Serializar para JSON
        riesgos_json = []
        for r in riesgos:
            riesgos_json.append({
                'id': r.ID_DATRIES,
                'riesgo_id': r.RIE_ID_RIESGO,
                'codigo': r.riesgo.C_RIESGO if r.riesgo else '',
                'denominacion': r.riesgo.D_RIESGO if r.riesgo else '',
                'nivel_residual': r.riesgo_residual_valor.D_VALOR if r.riesgo_residual_valor else 'Sin evaluar'
            })

        return jsonify({'success': True, 'data': riesgos_json})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/sistema/<int:sistema_id>/riesgo-global/especificos', methods=['GET'])
def api_obtener_riesgos_especificos(sistema_id):
    """
    Endpoint para obtener los riesgos específicos del proyecto en nivel MEDIO.
    """
    session = Session()
    try:
        riesgos = obtener_riesgos_especificos_medio(session, sistema_id)

        riesgos_json = []
        for r in riesgos:
            riesgos_json.append({
                'id': r.ID_DATRIES,
                'riesgo_id': r.RIE_ID_RIESGO,
                'codigo': r.riesgo.C_RIESGO if r.riesgo else '',
                'denominacion': r.riesgo.D_RIESGO if r.riesgo else '',
                'nivel_residual': r.riesgo_residual_valor.D_VALOR if r.riesgo_residual_valor else 'Sin evaluar'
            })

        return jsonify({'success': True, 'data': riesgos_json})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/sistema/<int:sistema_id>/validar-cambio-fase', methods=['POST'])
def api_validar_cambio_fase_riesgo_global(sistema_id):
    """
    Endpoint para validar si un sistema puede cambiar de fase según riesgo global.

    Se llama antes de permitir el cambio de fase 3 a fase 4.

    Request body:
        {"fase_destino": 4}
    """
    session = Session()
    try:
        data = request.get_json()
        fase_destino = data.get('fase_destino')

        if not fase_destino:
            return jsonify({'success': False, 'error': 'fase_destino requerido'}), 400

        resultado = validar_riesgo_global_para_cambio_fase(
            session,
            sistema_id,
            fase_destino
        )

        riesgo_global_data = None
        if resultado['riesgo_global']:
            riesgo_global_data = {
                'nivel': resultado['riesgo_global']['nivel'],
                'factores': resultado['riesgo_global']['factores']
            }

        return jsonify({
            'success': True,
            'valido': resultado['valido'],
            'mensaje': resultado['mensaje'],
            'riesgo_global': riesgo_global_data
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

# ============================================================================
# RUTAS PARA ACTUALIZACIÓN DEL EJECUTABLE (.EXE)
# ============================================================================

@app.route('/descargar-actualizacion-exe', methods=['POST'])
def descargar_actualizacion_exe():
    """
    Endpoint AJAX para descargar la actualización del ejecutable.
    Retorna respuesta JSON con el resultado de la descarga.
    """
    global actualizacion_exe_url

    if not actualizacion_exe_url:
        return jsonify({
            'success': False,
            'error': 'No hay URL de actualización disponible'
        }), 400

    try:
        cert_path = actualizacion.resource_path("server_cert.pem")

        # Descargar el archivo
        exito, resultado = actualizacion.descargar_actualizacion_exe(
            actualizacion_exe_url,
            cert_path
        )

        if exito:
            return jsonify({
                'success': True,
                'message': 'Actualización descargada correctamente',
                'ruta': resultado
            })
        else:
            return jsonify({
                'success': False,
                'error': resultado
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error inesperado: {str(e)}'
        }), 500


@app.route('/aplicar-actualizacion-exe', methods=['GET', 'POST'])
def aplicar_actualizacion_exe():
    """
    Aplica la actualización del ejecutable descargada.
    Lanza el script de actualización y cierra la aplicación.
    """
    if not actualizacion.hay_actualizacion_exe_pendiente():
        flash("No hay ninguna actualización pendiente", "warning")
        return redirect(url_for('seleccionar_proyecto'))

    exito, mensaje = actualizacion.ejecutar_actualizacion_exe()

    if exito:
        # Redirigir a una página especial de cierre para actualización
        return redirect(url_for('cerrando_para_actualizar'))
    else:
        flash(f"Error al aplicar actualización: {mensaje}", "danger")
        return redirect(url_for('seleccionar_proyecto'))


@app.route('/cancelar-actualizacion-exe', methods=['POST'])
def cancelar_actualizacion_exe():
    """
    Cancela y limpia una actualización pendiente del ejecutable.
    Redirige a la función general de cancelar actualizaciones.
    """
    return cancelar_actualizaciones()


@app.route('/cerrando-para-actualizar')
def cerrando_para_actualizar():
    """
    Página que se muestra mientras se aplica la actualización.
    Cierra la aplicación después de mostrar el mensaje.
    """
    global shutdown_requested
    shutdown_requested = True

    def shutdown_for_update():
        time.sleep(2)  # Dar tiempo a que se muestre la página
        force_shutdown()

    threading.Thread(target=shutdown_for_update, daemon=False).start()

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>{NOMBRE_APLICACION} - Actualizando</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                margin: 0; padding: 0;
                display: flex; flex-direction: column;
                justify-content: center; align-items: center;
                height: 100vh; color: white;
            }}
            .icon {{ font-size: 80px; }}
            h2 {{ font-weight: 300; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); margin-bottom: 10px; }}
            p {{ opacity: 0.9; margin: 5px 0; font-size: 1.1em; }}
            .info-box {{
                background: rgba(255,255,255,0.2);
                padding: 25px 50px;
                border-radius: 15px;
                margin-top: 30px;
                text-align: center;
            }}
            .info-box p {{ margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="icon">✓</div>
        <h2>Cerrando aplicación...</h2>
        <div class="info-box">
            <p><strong>Se ha abierto una ventana de comandos.</strong></p>
            <p>Siga las instrucciones de esa ventana para</p>
            <p>completar la actualización.</p>
            <p style="margin-top: 20px; opacity: 0.8;">Esta ventana del navegador puede cerrarse.</p>
        </div>
    </body>
    </html>
    """


@app.route('/estado-descarga-exe')
def estado_descarga_exe():
    """
    Endpoint para verificar el estado de la descarga del ejecutable.
    Usado por el frontend para polling del estado.
    """
    tiene_pendiente = actualizacion.hay_actualizacion_exe_pendiente()

    return jsonify({
        'descargada': tiene_pendiente,
        'disponible': actualizacion_exe_disponible,
        'version': actualizacion_exe_version
    })


@app.route('/shutdown')
def shutdown():
    """
    Apaga el servidor Flask de manera segura.
    Versión mejorada que garantiza el cierre completo del proceso.

    Solo permite apagar el servidor si la solicitud proviene de localhost.

    Returns:
        str: Página HTML que muestra el estado del apagado.
        tuple: ('No autorizado', 403) si el intento de apagado no proviene de localhost.
    """
    global shutdown_requested

    if request.remote_addr not in ("127.0.0.1", "::1"):
        return 'No autorizado', 403


    shutdown_requested = True

    def shutdown_server():
        """Thread que ejecuta el cierre con delay para mostrar la página"""
        time.sleep(1.5)  # Tiempo para que se vea la página de cierre
        force_shutdown()

    # 🔧 Thread NO daemon para garantizar el cierre completo
    threading.Thread(target=shutdown_server, daemon=False).start()

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>{NOMBRE_APLICACION} - Aplicación Cerrada</title>
        <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
        <script>
            $(document).ready(function () {{
                setTimeout(function () {{
                    $("#icono").text("✅");
                    $("#msg").text("Aplicación cerrada correctamente");
                    $("#submsg").html("Puede cerrar esta ventana del navegador de forma segura");
                    $(".spinner").hide(); // Ocultar el spinner
                }}, 800);
            }});
        </script>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                color: white;
            }}
            #icono {{
                font-size: 80px;
                margin-bottom: 20px;
                animation: pulse 1.5s infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ transform: scale(1); }}
                50% {{ transform: scale(1.1); }}
            }}
            #msg {{
                font-size: 1.8rem;
                font-weight: 300;
                text-align: center;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                margin-bottom: 15px;
            }}
            #submsg {{
                font-size: 1.1rem;
                font-weight: 200;
                text-align: center;
                opacity: 0.9;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
            }}
            .spinner {{
                width: 50px;
                height: 50px;
                border: 5px solid rgba(255,255,255,0.3);
                border-top-color: white;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-top: 20px;
            }}
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
        </style>
    </head>
    <body>
        <div id="icono">⌛</div>
        <h2 id="msg">Cerrando {NOMBRE_APLICACION}...</h2>
        <p id="submsg"></p>
        <div class="spinner"></div>
    </body>
    </html>
    """



# ============================================================================
# RUTAS PARA SISTEMA DE CARGA Y HEALTH CHECK
# ============================================================================

@app.route('/health')
def health_check():
    """
    Endpoint de health check para verificar que el servidor está listo.

    Usado por la página de carga para saber cuándo redirigir al usuario
    a la aplicación principal.

    Returns:
        JSON: {'status': 'ok', 'ready': True}
    """
    return jsonify({
        'status': 'ok',
        'ready': True
    })


@app.route('/loading')
def loading_page():
    """
    Página de carga que muestra mientras el servidor termina de iniciar.

    Esta página hace polling al endpoint /health hasta que el servidor
    esté completamente listo, momento en el cual redirige automáticamente
    a la página de selección de proyectos.
    """
    return render_template('loading.html')


def open_browser(port=5000):
    """
    Abre el navegador web predeterminado en la página de selección de proyectos.

    Esta función se utiliza para abrir automáticamente el navegador web en la ruta
    de selección de proyectos cuando la aplicación Flask inicia. Se ejecuta en un hilo
    separado para no bloquear el arranque del servidor.

    Args:
        port (int): Puerto en el que está corriendo el servidor Flask. Por defecto 5000.

    No retorna valores.
    """
    webbrowser.open(f"http://127.0.0.1:{port}/seleccionar-proyecto")


if __name__ == "__main__":
    """
    Punto de entrada principal de la aplicación Flask.

    El splash de PyInstaller (--splash) se muestra automáticamente durante
    la descompresión del .exe y se cierra cuando abrimos el navegador.
    """

    # =========================================================================
    # VERIFICAR INSTANCIA DUPLICADA
    # =========================================================================
    if splash.is_another_instance_running():
        cerrar_splash_nativo()
        splash.show_duplicate_instance_warning()
        sys.exit(0)

    # Crear archivo de bloqueo
    splash.create_lock_file()

    # Registrar limpieza del archivo de bloqueo al cerrar
    atexit.register(splash.remove_lock_file)

    # =========================================================================
    # VERIFICAR COMPATIBILIDAD APLICACIÓN-BASE DE DATOS
    # =========================================================================
    # Verifica que la combinación de versión de app y versión de BD no esté
    # expresamente prohibida en IA_CFGVERSCOMPAT (C_TIPO='STARTUP').
    # Si no es compatible, muestra error y termina sin iniciar Flask.
    # Si es compatible pero requiere migración (L_COMPATIBLE=1 con T_SQL_MIGRACION),
    # ejecuta el SQL y si falla muestra el mensaje configurado en C_MENSAJE.
    # Principio: Lo que no está prohibido, se permite.
    # =========================================================================
    try:
        compatible, mensaje_error, sql_migracion, mensaje_migracion_error = version_check.verificar_compatibilidad_arranque()

        if not compatible:
            # Cerrar splash ANTES de mostrar el mensaje de error
            cerrar_splash_nativo()
            version_check.mostrar_error_incompatibilidad(mensaje_error)
            # La función anterior ya hace os._exit(1)

        # Si hay SQL de migración, ejecutarlo
        if sql_migracion:
            exito, mensaje_resultado = version_check.ejecutar_migracion_arranque(sql_migracion, mensaje_migracion_error)
            if not exito:
                # Cerrar splash ANTES de mostrar el mensaje de error
                cerrar_splash_nativo()
                version_check.mostrar_error_incompatibilidad(mensaje_resultado)
                # La función anterior ya hace os._exit(1)

    except Exception:
        # Si hay error en la verificación (BD no accesible, tabla no existe, etc.),
        # permitir el arranque silenciosamente
        pass

    try:
        # =====================================================================
        # LIMPIEZA DE TEMPORALES
        # =====================================================================
        limpiar_temporales_huerfanos()

        # Limpiar residuos de actualizaciones anteriores (.bak, .tmp, updater.bat)
        actualizacion.limpiar_residuos_actualizacion_anterior()

        # =====================================================================
        # BÚSQUEDA DE PUERTO DISPONIBLE
        # =====================================================================
        puerto_disponible = find_available_port(start_port=5000, max_attempts=20)

        # =====================================================================
        # INICIALIZACIÓN DE BASE DE DATOS
        # =====================================================================
        Base.metadata.create_all(engine)

        # =====================================================================
        # ABRIR NAVEGADOR Y CERRAR SPLASH
        # =====================================================================
        def abrir_navegador_y_cerrar_splash():
            """Abre el navegador y cierra el splash de PyInstaller."""
            webbrowser.open(f"http://127.0.0.1:{puerto_disponible}/seleccionar-proyecto")
            time.sleep(0.3)
            cerrar_splash_nativo()

        # Programar apertura del navegador con un pequeño delay
        threading.Timer(0.5, abrir_navegador_y_cerrar_splash).start()

        # =====================================================================
        # INICIAR SERVIDOR FLASK
        # =====================================================================

        # Iniciar aplicación Flask en el puerto disponible
        app.run(debug=False, use_reloader=False, port=puerto_disponible)

    except RuntimeError as e:
        # Error al buscar puerto disponible
        cerrar_splash_nativo()
        splash.remove_lock_file()


        # Mostrar error en ventana
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                f"{NOMBRE_APLICACION} - Error",
                f"No se pudo iniciar la aplicación:\n\n{str(e)}\n\n"
                "Cierre otras aplicaciones y vuelva a intentar."
            )
            root.destroy()
        except:
            pass

        time.sleep(5)
        sys.exit(1)

    except Exception as e:
        # Cualquier otro error inesperado
        cerrar_splash_nativo()
        splash.remove_lock_file()

        traceback.print_exc()

        time.sleep(5)
        sys.exit(1)

    finally:
        # Asegurar limpieza del archivo de bloqueo
        splash.remove_lock_file()

