
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
Modelos de datos SQLAlchemy para la aplicación de supervisión SIA.

Este módulo define las clases ORM que representan la estructura de la base de datos utilizada por la aplicación,
incluyendo preguntas y respuestas del formulario ADI, sistemas/proyectos, elementos y subelementos adicionales,
y las relaciones entre ellos. También configura la conexión a la base de datos SQLite, gestionando la ruta
según el modo de ejecución (script o ejecutable).

SISTEMA DE OFUSCACIÓN AUTOMÁTICA:
- El sistema detecta automáticamente si la BD está ofuscada o no
- Mantiene el mismo formato (ofuscado/no ofuscado) al guardar cambios
- Funciona transparentemente sin necesidad de configuración manual
- Se crea un archivo temporal desofuscado para trabajar (si está ofuscado)
- Los cambios se sincronizan periódicamente al archivo original
- Al cerrar, se limpia el archivo temporal

Clases principales:
- Pregunta: Preguntas del formulario ADI.
- Respuesta: Opciones de respuesta para cada pregunta.
- Inicio: Sistemas o proyectos gestionados.
- RespuestasProyecto: Respuestas seleccionadas por proyecto y pregunta.
- ElementosAdi: Elementos adicionales asociados a proyectos.
- SubElementosAdi: Subelementos de cada elemento adicional.
- DatosElementosAdi: Datos específicos asociados a elementos y subelementos por proyecto.

Incluye la configuración de la base de datos y las relaciones entre las tablas.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session as SQLASession
from sqlalchemy.types import Text
import os
import sys
import hashlib
import atexit
import shutil
import tempfile
import threading
import time

# Importar configuración
import config

# Base para los modelos declarativos de SQLAlchemy
Base = declarative_base()

# ============================================================================
# SISTEMA DE OFUSCACIÓN AUTOMÁTICA DE BASE DE DATOS
# ============================================================================

# Tamaño del checksum SHA256 (32 bytes)
CHECKSUM_SIZE = 32

def _get_obfuscation_key():
    """
    Genera una clave de ofuscación basada en la contraseña configurada.

    Returns:
        bytes: Clave de 16 bytes para XOR con el header de SQLite
    """
    key_string = config.DB_OBFUSCATION_KEY
    key_hash = hashlib.sha256(key_string.encode('utf-8')).digest()
    return key_hash[:16]


def _calculate_checksum(data):
    """
    Calcula el checksum SHA256 de los datos.

    Args:
        data (bytes): Datos para calcular checksum

    Returns:
        bytes: Hash SHA256 (32 bytes)
    """
    return hashlib.sha256(data).digest()


def _is_database_obfuscated(db_path):
    """
    Verifica si una base de datos tiene el header ofuscado.

    Args:
        db_path (str): Ruta al archivo de base de datos

    Returns:
        bool: True si está ofuscado, False si es un SQLite estándar
    """
    if not os.path.exists(db_path):
        return False

    try:
        with open(db_path, 'rb') as f:
            header = f.read(16)

        sqlite_magic = b'SQLite format 3\x00'
        return header != sqlite_magic
    except Exception:
        return False


def _verify_database_integrity(db_path):
    """
    Verifica la integridad de una base de datos ofuscada.
    Comprueba que el checksum embebido coincida con el calculado.

    Args:
        db_path (str): Ruta al archivo de base de datos

    Returns:
        tuple: (bool, str) - (True si es válido, mensaje de error si aplica)
    """
    try:
        with open(db_path, 'rb') as f:
            data = bytearray(f.read())

        if len(data) < (16 + CHECKSUM_SIZE):
            return False, "Archivo demasiado pequeño"

        # Obtener clave
        key = _get_obfuscation_key()

        # Desofuscar checksum (últimos 32 bytes)
        checksum_obfuscated = bytearray(data[-CHECKSUM_SIZE:])
        for i in range(CHECKSUM_SIZE):
            checksum_obfuscated[i] ^= key[i % 16]

        # Desofuscar header temporalmente para verificar
        for i in range(16):
            data[i] ^= key[i]

        # Calcular hash del contenido (sin los últimos 32 bytes)
        content = bytes(data[:-CHECKSUM_SIZE])
        calculated_hash = _calculate_checksum(content)

        # Comparar
        if bytes(checksum_obfuscated) != calculated_hash:
            return False, "Checksum no coincide - archivo modificado"

        return True, "OK"

    except Exception as e:
        return False, f"Error al verificar: {e}"


def _deobfuscate_to_bytes(db_path):
    """
    Desofusca una base de datos y devuelve los bytes desofuscados SIN tocar el archivo original.

    Args:
        db_path (str): Ruta al archivo de base de datos ofuscada

    Returns:
        bytes: Contenido desofuscado de la base de datos

    Raises:
        ValueError: Si el archivo está corrupto o fue manipulado
    """
    if not _is_database_obfuscated(db_path):
        # Si no está ofuscado, leer directamente
        with open(db_path, 'rb') as f:
            return f.read()

    try:
        # Verificar integridad primero
        is_valid, error_msg = _verify_database_integrity(db_path)

        if not is_valid:
            raise ValueError(
                f"❌ BASE DE DATOS CORRUPTA O MANIPULADA\n\n"
                f"La base de datos '{os.path.basename(db_path)}' no pasó la verificación de integridad.\n"
                f"Razón: {error_msg}\n\n"
                f"Posibles causas:\n"
                f"- El archivo fue modificado con un editor de texto\n"
                f"- El archivo está corrupto\n"
                f"- El archivo no es una base de datos válida de SupervisionSIA\n\n"
                f"Por favor, use una copia de seguridad válida."
            )

        # Leer archivo
        with open(db_path, 'rb') as f:
            data = bytearray(f.read())

        # Obtener clave
        key = _get_obfuscation_key()

        # Desofuscar checksum (últimos 32 bytes)
        for i in range(CHECKSUM_SIZE):
            data[-(CHECKSUM_SIZE - i)] ^= key[i % 16]

        # Desofuscar header (primeros 16 bytes)
        for i in range(16):
            data[i] ^= key[i]

        # Remover checksum (últimos 32 bytes) y devolver
        content = bytes(data[:-CHECKSUM_SIZE])

        return content

    except ValueError:
        # Re-lanzar errores de validación
        raise
    except Exception as e:
        raise ValueError(f"Error al desofuscar base de datos: {e}")


def _obfuscate_from_bytes(data):
    """
    Ofusca datos de una base de datos SQLite añadiendo checksum y ofuscando header.
    NO modifica ningún archivo, solo procesa los bytes.

    Args:
        data (bytes): Contenido de la base de datos a ofuscar

    Returns:
        bytes: Datos ofuscados con checksum
    """
    try:
        data_array = bytearray(data)

        # Calcular checksum del contenido
        content_hash = _calculate_checksum(data)

        # Añadir checksum al final
        data_with_hash = data_array + content_hash

        # Obtener clave
        key = _get_obfuscation_key()

        # Ofuscar header (primeros 16 bytes)
        for i in range(16):
            data_with_hash[i] ^= key[i]

        # Ofuscar checksum (últimos 32 bytes)
        for i in range(CHECKSUM_SIZE):
            data_with_hash[-(CHECKSUM_SIZE - i)] ^= key[i % 16]

        return bytes(data_with_hash)

    except Exception as e:
        raise ValueError(f"Error al ofuscar base de datos: {e}")


def _obfuscate_database_file(db_path):
    """
    Ofusca un archivo de base de datos SQLite.

    Args:
        db_path (str): Ruta al archivo de base de datos

    Returns:
        bool: True si se ofuscó correctamente
    """
    if _is_database_obfuscated(db_path):
        # Ya está ofuscado
        return True

    try:
        # Leer archivo
        with open(db_path, 'rb') as f:
            data = f.read()

        # Ofuscar
        obfuscated_data = _obfuscate_from_bytes(data)

        # Guardar
        with open(db_path, 'wb') as f:
            f.write(obfuscated_data)

        return True

    except Exception:
        return False


# ============================================================================
# GESTOR DE BASE DE DATOS TEMPORAL
# ============================================================================

class DatabaseManager:
    """
    Gestor que detecta automáticamente si la BD está ofuscada y mantiene el formato.

    La estrategia es:
    1. Detectar automáticamente si el archivo original está ofuscado
    2. Crear un archivo temporal desofuscado para trabajo (si es necesario)
    3. Sincronizar cambios periódicamente manteniendo el formato original
    4. Limpiar el temporal al cerrar
    """

    def __init__(self, original_db_path):
        """
        Inicializa el gestor de base de datos.

        Args:
            original_db_path (str): Ruta al archivo de base de datos original
        """
        self.original_db_path = original_db_path
        self.temp_db_path = None
        self.temp_dir = None
        self.sync_thread = None
        self.stop_sync = threading.Event()
        self._lock = threading.Lock()
        self._closed = False

        # ✨ NUEVO: Detectar automáticamente si está ofuscado
        self.is_obfuscated = _is_database_obfuscated(original_db_path)

        # NO registrar atexit aquí - se registrará después al final del módulo

    def initialize(self):
        """
        Inicializa el sistema: detecta ofuscación, crea archivo temporal y configura sincronización.

        Returns:
            str: Ruta al archivo temporal que se debe usar para trabajar
        """
        # Crear directorio temporal
        self.temp_dir = tempfile.mkdtemp(prefix='supervisionsia_')

        # Nombre del archivo temporal
        self.temp_db_path = os.path.join(self.temp_dir, 'working.db')

        # Desofuscar el original a bytes (o leer directamente si no está ofuscado)
        try:
            deobfuscated_data = _deobfuscate_to_bytes(self.original_db_path)

            # Escribir al archivo temporal
            with open(self.temp_db_path, 'wb') as f:
                f.write(deobfuscated_data)

        except ValueError as e:
            # Error de integridad
            self.cleanup()
            raise
        except Exception as e:
            self.cleanup()
            raise ValueError(f"Error al inicializar base de datos temporal: {e}")

        # Iniciar sincronización automática si está configurada
        if config.MODO_PERSISTENCIA == "AUTO":
            self._start_auto_sync()

        return self.temp_db_path

    def sync_to_disk(self):
        """
        Sincroniza los cambios del archivo temporal al archivo original.
        MODIFICADO: Mantiene el formato original (ofuscado o no ofuscado)
        Esta operación es thread-safe.
        """
        if self._closed or not self.temp_db_path:
            return

        with self._lock:
            try:
                # Leer el archivo temporal
                with open(self.temp_db_path, 'rb') as f:
                    temp_data = f.read()

                # NUEVO: Decidir si ofuscar o no según el formato original
                if self.is_obfuscated:
                    # Ofuscar los datos
                    final_data = _obfuscate_from_bytes(temp_data)
                else:
                    # Mantener sin ofuscar
                    final_data = temp_data

                # Usar un archivo temporal primero para evitar corrupción si hay error
                backup_path = self.original_db_path + '.bak'

                # Backup del original por si acaso (solo si existe)
                if os.path.exists(self.original_db_path):
                    shutil.copy2(self.original_db_path, backup_path)

                # Escribir el nuevo contenido (ofuscado o no)
                with open(self.original_db_path, 'wb') as f:
                    f.write(final_data)

                # Si todo salió bien, eliminar el backup
                if os.path.exists(backup_path):
                    os.remove(backup_path)

            except Exception as e:
                # Restaurar backup si existe
                backup_path = self.original_db_path + '.bak'
                if os.path.exists(backup_path):
                    try:
                        shutil.copy2(backup_path, self.original_db_path)
                        os.remove(backup_path)
                    except Exception:
                        pass

    def _start_auto_sync(self):
        """Inicia el hilo de sincronización automática."""
        if self.sync_thread and self.sync_thread.is_alive():
            return

        self.stop_sync.clear()
        self.sync_thread = threading.Thread(target=self._auto_sync_worker, daemon=True)
        self.sync_thread.start()

    def _auto_sync_worker(self):
        """Worker que sincroniza periódicamente."""
        while not self.stop_sync.is_set():
            # Esperar el intervalo configurado
            if self.stop_sync.wait(timeout=config.INTERVALO_PERSISTENCIA):
                break  # Se solicitó detener

            # Sincronizar
            self.sync_to_disk()

    def cleanup(self):
        """
        Limpia recursos: sincroniza una última vez y elimina archivos temporales.
        """
        if self._closed:
            return

        self._closed = True

        # Detener sincronización automática
        if self.sync_thread and self.sync_thread.is_alive():
            self.stop_sync.set()
            self.sync_thread.join(timeout=5)

        # Sincronización final
        if self.temp_db_path and os.path.exists(self.temp_db_path):
            self.sync_to_disk()

        # IMPORTANTE: Cerrar el engine de SQLAlchemy antes de limpiar
        # Esto libera todas las conexiones al archivo temporal
        global engine
        if engine:
            try:
                engine.dispose()
            except Exception:
                pass

        # Dar un pequeño tiempo para que Windows libere el archivo
        time.sleep(0.5)

        # Eliminar archivos temporales con reintentos (necesario en Windows)
        if self.temp_dir and os.path.exists(self.temp_dir):
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    shutil.rmtree(self.temp_dir)
                    break
                except PermissionError:
                    if attempt < max_retries - 1:
                        # En Windows, el archivo puede estar bloqueado temporalmente
                        time.sleep(0.5)
                        continue
                except Exception:
                    pass


# ============================================================================
# INICIALIZACIÓN DE LA BASE DE DATOS
# ============================================================================

def get_db_path():
    """Determina la ruta correcta al archivo de base de datos según el modo de ejecución.

    Returns:
        str: Ruta absoluta al archivo de base de datos 'supervisionSIA.db' dentro de la carpeta /data.

    Nota:
        - En modo ejecutable (.exe), usa el directorio del ejecutable
        - En modo script (.py), usa el directorio del archivo actual
    """
    if getattr(sys, 'frozen', False):
        # Ejecutado como .exe (PyInstaller)
        base_dir = os.path.dirname(sys.executable)
    else:
        # Ejecutado como script .py
        base_dir = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_dir, 'data', 'supervisionSIA.db')


# Inicializar el gestor de base de datos
original_db_path = get_db_path()

# Verificar que el archivo existe
if not os.path.exists(original_db_path):
    sys.exit(1)

db_manager = DatabaseManager(original_db_path)

try:
    # Crear archivo temporal y obtener su ruta
    working_db_path = db_manager.initialize()
except ValueError as e:
    sys.exit(1)

# Crear engine usando el archivo temporal
# IMPORTANTE: En Windows, convertir backslashes a forward slashes para SQLAlchemy
working_db_path_normalized = working_db_path.replace('\\', '/')
engine = create_engine(f"sqlite:///{working_db_path_normalized}", echo=False)

# Fabrica de sesiones para interactuar con la BD
Session = sessionmaker(bind=engine)


# ============================================================================
# HOOKS PARA SINCRONIZACIÓN EN MODO TRANSACCION
# ============================================================================

if config.MODO_PERSISTENCIA == "TRANSACCION":
    @event.listens_for(Session, "after_commit")
    def after_commit(session):
        """Hook que se ejecuta después de cada commit exitoso."""
        db_manager.sync_to_disk()


# ============================================================================
# FUNCIÓN PÚBLICA PARA SINCRONIZACIÓN MANUAL
# ============================================================================

def sync_database():
    """
    Función pública para sincronizar manualmente la base de datos.
    Útil en modo MANUAL o para forzar sincronización en cualquier momento.
    """
    db_manager.sync_to_disk()


def cleanup_database():
    """
    Función pública para forzar limpieza de archivos temporales.
    Útil cuando necesitas cerrar explícitamente antes de salir de Flask.

    IMPORTANTE: Después de llamar esto, no se pueden hacer más operaciones
    de base de datos hasta reiniciar la aplicación.
    """
    db_manager.cleanup()


# ============================================================================
# REGISTRO DE LIMPIEZA AUTOMÁTICA
# ============================================================================
# IMPORTANTE: Registrar esto AL FINAL, después de crear todo
# Se ejecutará automáticamente cuando Python termine
atexit.register(db_manager.cleanup)


class Pregunta(Base):
    """Modelo que representa una pregunta del formulario ADI.

    Attributes:
        ID_PREGUNTA (int): Clave primaria, identificador único de la pregunta.
        C_PREGUNTA (str): Código identificativo de la pregunta.
        D_PREGUNTA (str): Texto descriptivo de la pregunta.
        L_ESTADO (int): Estado de la pregunta (1=activa, 0=inactiva).
        N_TIPCAMPO (int): Tipo de campo (0=Texto, 1=select, 2=checkbox).

    Relaciones:
        respuestas (relationship): Relación uno-a-muchos con Respuesta (opciones posibles).
        sistemas_adi (relationship): Relación uno-a-muchos con RespuestasProyecto (respuestas seleccionadas en proyectos).

    Nota:
        - Cada instancia representa una pregunta del formulario ADI.
        - Permite asociar opciones de respuesta y respuestas seleccionadas por proyecto.
    """
    __tablename__ = 'IA_ADIPREG'

    ID_PREGUNTA = Column(Integer, primary_key=True)
    C_PREGUNTA = Column(String(10))
    D_PREGUNTA = Column(String(255))
    L_ESTADO = Column(Integer)
    N_TIPCAMPO = Column(Integer)
    T_AYUDA = Column(String(255))

    # Relaciones
    respuestas = relationship("Respuesta", back_populates="pregunta")
    sistemas_adi = relationship("RespuestasProyecto", back_populates="pregunta")


class Respuesta(Base):
    """Modelo que representa una respuesta posible para una pregunta ADI.

    Attributes:
        ID_RESPUESTA (int): Clave primaria, identificador único de la respuesta.
        PRE_ID_PREGUNTA (int): Clave foránea a la pregunta relacionada (Pregunta).
        C_OPCION (str): Código identificativo de la opción (por ejemplo, 'A', 'B', 'C').
        D_RESPUESTA (str): Texto descriptivo de la respuesta.
        N_PTOSBASE (float): Puntos base asignados a esta respuesta.
        N_MULTIPLICADOR (float): Factor multiplicador para cálculos.
        N_ADICIONAL (float): Puntos adicionales para cálculos.
        L_ESTADO (int): Estado de la respuesta (1=activa, 0=inactiva).

    Relaciones:
        pregunta (relationship): Relación muchos-a-uno con la pregunta (Pregunta).
        sistemas_adi (relationship): Relación uno-a-muchos con RespuestasProyecto (respuestas seleccionadas en proyectos).
        riesgos_adi (relationship): Relación uno-a-muchos con RiesgoAdiRespuesta (riesgos asociados a esta respuesta en proyectos).
        controles_respuesta (relationship): Relación uno-a-muchos con ControlRespuesta (controles asociados a esta respuesta).

    Nota:
        - Cada instancia representa una opción de respuesta posible para una pregunta ADI.
        - Permite asociar la respuesta a proyectos específicos mediante RespuestasProyecto.
    """
    __tablename__ = 'IA_ADIRESP'

    ID_RESPUESTA = Column(Integer, primary_key=True)
    PRE_ID_PREGUNTA = Column(Integer, ForeignKey('IA_ADIPREG.ID_PREGUNTA'))
    C_OPCION = Column(String(1))
    D_RESPUESTA = Column(String(255))
    N_PTOSBASE = Column(Float)
    N_MULTIPLICADOR = Column(Float)
    N_ADICIONAL = Column(Float)
    L_ESTADO = Column(Integer)
    N_AMPLIVULNER = Column(Float)


    # Relaciones
    pregunta = relationship("Pregunta", back_populates="respuestas")
    sistemas_adi = relationship("RespuestasProyecto", back_populates="respuesta")
    riesgos_adi = relationship("RiesgoAdiRespuesta", back_populates="respuesta_proyecto", cascade="all, delete-orphan")
    controles_respuesta = relationship("ControlRespuesta", back_populates="respuesta", cascade='all, delete-orphan')


class Inicio(Base):
    """Modelo que representa un sistema o proyecto en la aplicación SIA.

    Attributes:
        ID_SISTEMA (int): Clave primaria, identificador único del sistema/proyecto.
        D_NOMPROYEC (str): Nombre descriptivo del sistema/proyecto.
        F_INI (str): Fecha de inicio del sistema/proyecto (formato YYYY-MM-DD).
        T_DPD (str): Responsable o DPD del sistema/proyecto.
        T_ESTADO_PROYEC (str): Estado actual del sistema/proyecto.

    Relaciones:
        sistemas_adi (relationship): Relación uno-a-muchos con RespuestasProyecto (respuestas ADI asociadas).
        datos_elementos_adi (relationship): Relación uno-a-muchos con DatosElementosAdi (datos de elementos ADI asociados).
        datos_riesgos (relationship): Relación uno-a-muchos con DatosRiesgo (datos de riesgos asociados).
        datos_controles = relationship("DatosControl", back_populates="sistema", cascade='all, delete-orphan')
        datos_elementos_control = relationship("DatosElementoControl", back_populates="sistema", cascade='all, delete-orphan')
        datos_actividad_monitoreo = relationship("DatosActividadMonitoreo", back_populates="sistema", cascade='all, delete-orphan')
        datos_control_monitoreo = relationship("DatosControlMonitoreo", back_populates="sistema", cascade='all, delete-orphan')

    Nota:
        - Cada instancia representa un sistema o proyecto gestionado en la aplicación.
        - Permite asociar respuestas ADI y datos de elementos adicionales a cada sistema/proyecto.
    """
    __tablename__ = 'IA_SISTEMA'

    ID_SISTEMA = Column(Integer, primary_key=True)
    D_NOMPROYEC = Column(String(255))
    F_INI = Column(String(10))
    T_DPD = Column(String(255))
    T_ESTADO_PROYEC = Column(String(255))
    N_FASE = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))

    # Relaciones
    sistemas_adi = relationship("RespuestasProyecto", cascade='all, delete-orphan')
    datos_elementos_adi = relationship("DatosElementosAdi", back_populates="sistema", cascade='all, delete-orphan')
    datos_riesgos = relationship("DatosRiesgo", back_populates="sistema", cascade='all, delete-orphan')
    datos_controles = relationship("DatosControl", back_populates="sistema", cascade='all, delete-orphan')
    datos_elementos_control = relationship("DatosElementoControl", back_populates="sistema", cascade='all, delete-orphan')
    datos_actividad_monitoreo = relationship("DatosActividadMonitoreo", back_populates="sistema", cascade='all, delete-orphan')
    datos_control_monitoreo = relationship("DatosControlMonitoreo", back_populates="sistema", cascade='all, delete-orphan')
    fase = relationship("ConfiguracionFase")
    documentos = relationship("DatosDocumento", back_populates="sistema", cascade='all, delete-orphan')
    elementos_documentos = relationship("DatosElementoDocumento", back_populates="sistema", cascade='all, delete-orphan')
    datos_requisitos = relationship("DatosRequisito", back_populates="sistema", cascade='all, delete-orphan')

class RespuestasProyecto(Base):
    """Modelo que representa la respuesta seleccionada para una pregunta ADI en un proyecto.

    Atributes:
        ID_SISTEMAADI (int): Clave primaria, identificador único del registro.
        SIST_ID_SISTEMA (int): Clave foránea al sistema/proyecto relacionado (Inicio).
        PRE_ID_PREGUNTA (int): Clave foránea a la pregunta relacionada (Pregunta).
        RES_ID_RESPUESTA (int): Clave foránea a la respuesta seleccionada (Respuesta).

    Relaciones:
        sistema (relationship): Relación muchos-a-uno con el sistema/proyecto (Inicio).
        pregunta (relationship): Relación muchos-a-uno con la pregunta (Pregunta).
        respuesta (relationship): Relación muchos-a-uno con la respuesta (Respuesta).

    Nota:
        - Cada registro representa la respuesta seleccionada para una pregunta específica en un proyecto.
        - Permite consultar fácilmente las respuestas dadas por proyecto y pregunta, así como los riesgos asociados.
    """
    __tablename__ = 'IA_SISTEMAADI'

    ID_SISTEMAADI = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'))
    PRE_ID_PREGUNTA = Column(Integer, ForeignKey('IA_ADIPREG.ID_PREGUNTA'))
    RES_ID_RESPUESTA = Column(Integer, ForeignKey('IA_ADIRESP.ID_RESPUESTA'))

    # Relaciones
    sistema = relationship("Inicio", back_populates="sistemas_adi")
    pregunta = relationship("Pregunta", back_populates="sistemas_adi")
    respuesta = relationship("Respuesta", back_populates="sistemas_adi")

class ElementosAdi(Base):
    """Modelo que representa un elemento adicional (bloque padre de subelementos).

    Attributes:
        ID_ELEM (int): Clave primaria, identificador único del elemento.
        N_ORDEN (int): Número de orden de presentación.
        D_ELEMENTO (str): Descripción textual del elemento.
        T_TIEMPO (str): Tiempo asociado al elemento.
        T_CRITICIDAD (str): Nivel de criticidad del elemento.
        T_IMPORTA (str): Indicador de importancia.

        sub_elementos (relationship): Relación uno-a-muchos con SubElementosAdi.
        datos_elementos_adi (relationship): Relación uno-a-muchos con DatosElementosAdi.
        datos_elementos_control (relationship): Relación uno-a-muchos con DatosElementoControl.

    Nota:
        - Cada elemento puede tener varios subelementos asociados.
        - Permite almacenar información adicional y relaciones con proyectos a través de DatosElementosAdi.
    """
    __tablename__ = 'IA_ELEMENADI'

    ID_ELEM = Column(Integer, primary_key=True)
    C_ELEMENTO = Column(Integer)
    N_ORDEN = Column(Integer)
    D_ELEMENTO = Column(String(255))
    T_TIEMPO = Column(String(255))
    T_CRITICIDAD = Column(String(255))
    T_IMPORTA = Column(String(255))
    L_ESTADO = Column(Integer)
    L_MULTIPLE = Column(Integer)
    N_FASEVISUAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_FASEVAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))

    # Relaciones
    # cascade='all, delete-orphan' Elimina subelementos si se elimina el padre
    sub_elementos = relationship('SubElementosAdi', back_populates='elemento', cascade='all, delete-orphan')
    datos_elementos_adi = relationship('DatosElementosAdi', back_populates='elemento', cascade='all, delete-orphan')
    datos_elementos_control = relationship('DatosElementoControl', back_populates='elemento', cascade='all, delete-orphan')
    fase_visual = relationship("ConfiguracionFase", foreign_keys=[N_FASEVISUAL])
    fase_evaluacion = relationship("ConfiguracionFase", foreign_keys=[N_FASEVAL])

class SubElementosAdi(Base):
    """Modelo que representa un subelemento dentro de un elemento adicional.

    Attributes:
        ID_SUBELEM (int): Clave primaria del subelemento.
        ELE_ID_ELEM (int): Clave foránea al elemento padre (ElementosAdi).
        N_SUBORD (int): Número de orden del subelemento.
        D_SUBELEM (str): Descripción textual del subelemento.
        L_ESTADO (int): Estado del subelemento (1=activo, 0=inactivo).

        elemento (relationship): Relación muchos-a-uno con ElementosAdi.
        datos_elementos_adi (relationship): Relación uno-a-muchos con DatosElementosAdi.
    """
    __tablename__ = 'IA_SUBELEMENADI'

    ID_SUBELEM = Column(Integer, primary_key=True)
    ELE_ID_ELEM = Column(Integer, ForeignKey('IA_ELEMENADI.ID_ELEM'))
    N_SUBORD = Column(Integer)
    D_SUBELEM = Column(String(255))
    L_ESTADO = Column(Integer)


    # Relaciones
    # cascade='all, delete-orphan' Elimina subelementos si se elimina el padre
    elemento = relationship('ElementosAdi', back_populates='sub_elementos')
    datos_elementos_adi = relationship('DatosElementosAdi', back_populates='sub_elemento', cascade='all, delete-orphan')


class DatosElementosAdi(Base):
    """Modelo que almacena los datos específicos asociados a elementos y subelementos ADI para cada proyecto.

    Attributes:
        ID_DATELEMADI (int): Clave primaria, identificador único del registro.
        SIST_ID_SISTEMA (int): Clave foránea al sistema/proyecto relacionado.
        ELE_ID_ELEM (int): Clave foránea al elemento ADI relacionado.
        SUB_IDSUBELEM (int): Clave foránea al subelemento ADI relacionado.
        T_DESCRIPCION (str): Descripción detallada en formato texto largo.
        N_ITERACION (int): Número de iteración del dato.

        sistema (relationship): Relación muchos-a-uno con el sistema/proyecto.
        elemento (relationship): Relación muchos-a-uno con el elemento ADI.
        sub_elemento (relationship): Relación muchos-a-uno con el subelemento ADI.

    Nota:
        - Si SUB_IDSUBELEM es None, el registro corresponde solo al elemento (sin subelemento).
        - Permite almacenar información adicional específica para cada combinación de sistema, elemento y subelemento.
    """
    __tablename__ = 'IA_DATELEMADI'

    ID_DATELEMADI = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'))
    ELE_ID_ELEM = Column(Integer, ForeignKey('IA_ELEMENADI.ID_ELEM'))
    SUB_IDSUBELEM = Column(Integer, ForeignKey('IA_SUBELEMENADI.ID_SUBELEM'))
    T_DESCRIPCION = Column(Text)  # Campo de texto largo
    N_ITERACION = Column(Integer, default=1)  # Número de iteración del dato

    # Relaciones
    sistema = relationship("Inicio", back_populates="datos_elementos_adi")
    elemento = relationship("ElementosAdi", back_populates="datos_elementos_adi")
    sub_elemento = relationship("SubElementosAdi", back_populates="datos_elementos_adi")

class Perfil(Base):
    """Modelo que representa los perfiles de supervisión.

    Atributes:
        ID_PERFIL (int): Clave primaria, identificador único del perfil.
        D_PERFIL (str): Nombre o descripción corta del perfil.
        N_PTOSMIN (float): Puntuación mínima asociada al perfil.
        N_PTOSMAX (float): Puntuación máxima asociada al perfil.
        L_MININCLUSIVO (int): 1 si el límite mínimo es inclusivo (>=), 0 si es exclusivo (>).
        L_MAXINCLUSIVO (int): 1 si el límite máximo es inclusivo (<=), 0 si es exclusivo (<).
        TIEMPO_ESTIMADO (str): Tiempo estimado recomendado para el perfil.
        T_DESCRIPCION (str): Descripción detallada del perfil.

    Relaciones:
        riesgos (relationship): Relación uno-a-muchos con Riesgo (riesgos asociados a este perfil).
        controles (relationship): Relación uno-a-muchos con Control (controles asociados a este perfil).

    Nota:
        - Cada instancia representa un perfil de supervisión con su rango de puntuación y riesgos asociados.
        - Los campos L_MININCLUSIVO y L_MAXINCLUSIVO permiten definir si los límites son inclusivos o exclusivos:
          * Esencial: >= 0 y < 3 (L_MININCLUSIVO=1, L_MAXINCLUSIVO=0)
          * Estándar: >= 3 y <= 6 (L_MININCLUSIVO=1, L_MAXINCLUSIVO=1)
          * Exhaustivo: > 6 y <= 9999 (L_MININCLUSIVO=0, L_MAXINCLUSIVO=1)
    """
    __tablename__ = 'IA_PERFIL'

    ID_PERFIL = Column(Integer, primary_key=True)
    D_PERFIL = Column(String(50))
    N_PTOSMIN = Column(Float)
    N_PTOSMAX = Column(Float)
    L_MININCLUSIVO = Column(Integer, default=1)  # 1 = >=, 0 = >
    L_MAXINCLUSIVO = Column(Integer, default=1)  # 1 = <=, 0 = <
    TIEMPO_ESTIMADO = Column(String(50))
    T_DESCRIPCION = Column(Text)

    # Relaciones
    riesgos = relationship("Riesgo", back_populates="perfil", cascade="all, delete-orphan")
    controles = relationship("Control", back_populates="perfil", cascade='all, delete-orphan')

    def contiene_puntuacion(self, puntuacion):
        """
        Verifica si una puntuación está dentro del rango del perfil,
        considerando si los límites son inclusivos o exclusivos.

        Args:
            puntuacion (float): Puntuación a verificar.

        Returns:
            bool: True si la puntuación está dentro del rango, False en caso contrario.
        """
        # Verificar límite inferior
        if self.L_MININCLUSIVO == 1:
            cumple_min = puntuacion >= self.N_PTOSMIN
        else:
            cumple_min = puntuacion > self.N_PTOSMIN

        # Verificar límite superior
        if self.L_MAXINCLUSIVO == 1:
            cumple_max = puntuacion <= self.N_PTOSMAX
        else:
            cumple_max = puntuacion < self.N_PTOSMAX

        return cumple_min and cumple_max



class Riesgo(Base):
    """Modelo que representa un riesgo asociado a un perfil de supervisión.

    Attributes:
        ID_RIESGO (int): Clave primaria, identificador único del riesgo.
        C_RIESGO (str): Código identificativo del riesgo (hasta 4 caracteres).
        CATEGORIA (str): Categoría del riesgo.
        D_RIESGO (str): Descripción breve del riesgo.
        T_DESCRIPCION (str): Descripción detallada del riesgo.
        PER_ID_PERFIL (int): Clave foránea al perfil asociado (Perfil).
        ACTIVACION_AUTOMATICA (str): Información sobre la activación automática del riesgo.
        T_BASENORMATIVA (str): Base normativa asociada al riesgo.
        L_ESTADO (int): Estado del riesgo (1=activo, 0=inactivo).
        N_ORDVISU (int): Orden de visualización del riesgo.
        N_FASEVISUAL (int): Clave foránea a la fase de visualización (IA_CFGFASES).
        N_FASEVAL (int): Clave foránea a la fase de evaluación (IA_CFGFASES).
        N_RIERESMIN (int): Número mínimo de riesgos (uso interno).
        N_CONTRMIN (int): Número mínimo de controles (uso interno).
        L_PERSONAL (int): Indica si el riesgo es personalizado por el usuario (1) o estándar (0).

    Relaciones:
        perfil (relationship): Relación muchos-a-uno con Perfil (perfil al que pertenece el riesgo).
        respuestas_adi (relationship): Relación uno-a-muchos con RiesgoAdiRespuesta (respuestas ADI asociadas al riesgo).
        datos_por_sistema (relationship): Relación uno-a-muchos con DatosRiesgo (datos específicos por sistema/proyecto).
        categoria (relationship): Relación muchos-a-uno con CategoriaRiesgo (categoría del riesgo).
        controles_riesgo (relationship): Relación uno-a-muchos con RiesgoControl (controles asociados al riesgo).
        fase_visual (relationship): Relación muchos-a-uno con ConfiguracionFase (fase de visualización).
        fase_evaluacion (relationship): Relación muchos-a-uno con ConfiguracionFase (fase de evaluación).

    Nota:
        - Cada instancia representa un riesgo vinculado a un perfil de supervisión.
        - Permite asociar riesgos a respuestas ADI específicas mediante RiesgoAdiRespuesta.
    """

    __tablename__ = 'IA_RIESGOS'

    ID_RIESGO = Column(Integer, primary_key=True)
    C_RIESGO = Column(String(4))
    CAT_ID_CATRIES = Column(Integer, ForeignKey('IA_CATRIESGOS.ID_CATRIES'))
    D_RIESGO = Column(String(255))
    T_DESCRIPCION = Column(String(255))
    PER_ID_PERFIL = Column(Integer, ForeignKey('IA_PERFIL.ID_PERFIL'))
    ACTIVACION_AUTOMATICA = Column(String(100))
    T_BASENORMATIVA = Column(String(255))
    L_ESTADO = Column(Integer)
    N_ORDVISU = Column(Integer)
    N_FASEVISUAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_FASEVAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_RIERESMIN = Column(Integer)
    N_CONTRMIN = Column(Integer)
    L_PERSONAL = Column(Integer)  # 0=riesgo estándar, 1=riesgo personalizado por el usuario

    # Relaciones
    perfil = relationship("Perfil", back_populates="riesgos")
    respuestas_adi = relationship("RiesgoAdiRespuesta", back_populates="riesgo", cascade='all, delete-orphan')
    datos_por_sistema = relationship("DatosRiesgo", back_populates="riesgo", cascade='all, delete-orphan')
    categoria = relationship("CategoriaRiesgo", back_populates="riesgos" )
    controles_riesgo = relationship("RiesgoControl", back_populates="riesgo", cascade='all, delete-orphan')
    fase_visual = relationship("ConfiguracionFase", foreign_keys=[N_FASEVISUAL], back_populates="riesgos_fase_visual")
    fase_evaluacion = relationship("ConfiguracionFase", foreign_keys=[N_FASEVAL], back_populates="riesgos_fase_evaluacion")
    clusters = relationship("ConfiguracionCluster",secondary="IA_CFGRIESCLUSTER",back_populates="riesgos")


class RiesgoAdiRespuesta(Base):
    """Modelo que representa la relación entre un riesgo y una respuesta seleccionada en un proyecto ADI.

    Attributes:
        ID_RIESGTIPADQS (int): Clave primaria, identificador único del registro.
        RIE_ID_RIESGO (int): Clave foránea al riesgo relacionado (Riesgo).
        RESP_ID_RESP (int): Clave foránea a la respuesta seleccionada en el formulario ADI (RespuestasProyecto).

    Relaciones:
        riesgo (relationship): Relación muchos-a-uno con Riesgo (riesgo asociado).
        respuesta_proyecto (relationship): Relación muchos-a-uno con Respuesta (respuesta seleccionada en el proyecto).

    Nota:
        - Cada instancia vincula un riesgo específico a una respuesta seleccionada en un proyecto ADI.
        - Permite mapear la activación automática de riesgos en función de las respuestas dadas en el formulario ADI.
    """
    __tablename__ = 'IA_RIESGTIPADSQ'

    ID_RIESGTIPADQS = Column(Integer, primary_key=True)
    RIE_ID_RIESGO = Column(Integer, ForeignKey('IA_RIESGOS.ID_RIESGO'))
    RESP_ID_RESP = Column(Integer, ForeignKey('IA_ADIRESP.ID_RESPUESTA'))
    PRE_ID_PREGUNTA = Column(Integer, ForeignKey('IA_ADIPREG.ID_PREGUNTA'))

    # Relaciones
    riesgo = relationship("Riesgo", back_populates="respuestas_adi")
    respuesta_proyecto = relationship("Respuesta", back_populates="riesgos_adi")

class DatosRiesgo(Base):
    """Modelo que representa los datos específicos de un riesgo asociado a un sistema/proyecto.

    Attributes:
        ID_DATRIES (int): Clave primaria, identificador único del registro.
        SIST_ID_SISTEMA (int): Clave foránea al sistema/proyecto relacionado (Inicio).
        RIE_ID_RIESGO (int): Clave foránea al riesgo relacionado (Riesgo).
        L_APLICA (int): Indica si el riesgo aplica en este sistema (1=aplica, 0=no aplica).
        T_JUSAPLICA (str): Justificación sobre por qué aplica o no el riesgo.
        V_PROBABILIDAD (int): Valor numérico de probabilidad asignado (por ejemplo, 1-5).
        T_JUSPROBABILIDAD (str): Justificación del valor de probabilidad.
        V_IMPACTO (int): Valor numérico de impacto asignado (por ejemplo, 1-5).
        T_JUSIMPACTO (str): Justificación del valor de impacto.
        L_ACTIVA (int): Estado de activación del riesgo en este sistema (1=activa, 0=inactiva).
        T_DESCRIPCION (str): Descripción detallada del riesgo en este contexto.
        V_RIERESID (int): Valor de riesgo residual (clave foránea a IA_VALDAT.ID_VALDAT).

    Relaciones:
        sistema (relationship): Relación muchos-a-uno con Inicio (sistema/proyecto).
        riesgo (relationship): Relación muchos-a-uno con Riesgo (riesgo asociado).
        probabilidad_valor (relationship): Relación muchos-a-uno con ValoresDato (valor de probabilidad).
        impacto_valor (relationship): Relación muchos-a-uno con ValoresDato (valor de impacto).
        riesgo_residual_valor (relationship): Relación muchos-a-uno con ValoresDato (valor de riesgo residual).

    Nota:
        - Cada instancia registra cómo se evalúa un riesgo específico en un sistema/proyecto.
        - Permite personalizar la aplicación, probabilidad, impacto y justificaciones por proyecto.
        - Es clave para la evaluación de riesgos personalizada por sistema.
        - Los valores de probabilidad e impacto están controlados por la tabla IA_VALDAT.
    """
    __tablename__ = 'IA_DATRIESGOS'

    ID_DATRIES = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'))
    RIE_ID_RIESGO = Column(Integer, ForeignKey('IA_RIESGOS.ID_RIESGO'))
    L_APLICA = Column(Integer)
    T_JUSAPLICA = Column(String(255))
    V_PROBABILIDAD = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_JUSPROBABILIDAD = Column(String(255))
    V_IMPACTO = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_JUSIMPACTO = Column(String(255))
    L_ACTIVA = Column(Integer)
    L_MANUAL = Column(Integer, default=0)  # 0=automático, 1=activado manualmente por usuario
    T_DESCRIPCION = Column(String(255))
    V_RIERESID = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))

    # Relaciones
    sistema = relationship("Inicio", back_populates="datos_riesgos")
    riesgo = relationship("Riesgo", back_populates="datos_por_sistema")
    probabilidad_valor = relationship("ValoresDato", foreign_keys=[V_PROBABILIDAD], back_populates="valores_probabilidad")
    impacto_valor = relationship("ValoresDato", foreign_keys=[V_IMPACTO], back_populates="valores_impacto")
    riesgo_residual_valor = relationship("ValoresDato", foreign_keys=[V_RIERESID], back_populates="valores_riesgo_residual")

class CategoriaRiesgo(Base):
    """Modelo que representa las categorías y subcategorías de riesgos.

    Attributes:
        ID_CATRIES (int): Clave primaria, identificador único de la categoría.
        D_CATEGORIA (str): Nombre descriptivo de la categoría o subcategoría.
        N_SUBCAT (int): Indica si es una subcategoría (1=sí, 0=no).

    Relaciones:
        riesgos (relationship): Relación uno-a-muchos con Riesgo (riesgos asociados a esta categoría).

    Nota:
        - Permite organizar los riesgos por categorías jerárquicas.
        - Si N_SUBCAT = 1, se considera una subcategoría; si = 0, es una categoría principal.
        - Es útil para filtrar, reportes y visualización de riesgos por área.
    """
    __tablename__ = 'IA_CATRIESGOS'

    ID_CATRIES = Column(Integer, primary_key=True)
    D_CATEGORIA = Column(String(255))
    N_SUBCAT = Column(Integer)

    # Relaciones
    riesgos = relationship("Riesgo", back_populates="categoria")

class TiposDato(Base):
    """Modelo que representa los tipos de datos utilizados en el sistema de supervisión.

    Attributes:
        ID_TIPDAT (int): Clave primaria, identificador único del tipo de dato.
        C_TIPDAT (str): Código corto del tipo de dato (máximo 10 caracteres).
        D_TIPDAT (str): Descripción detallada del tipo de dato (máximo 255 caracteres).

    Relaciones:
        valores (relationship): Relación uno-a-muchos con ValoresDato (valores posibles para este tipo de dato).

    Nota:
        - Cada instancia representa un tipo de dato disponible en el sistema.
        - Se utiliza para clasificar y categorizar diferentes tipos de información.
    """
    __tablename__ = 'IA_TIPDAT'

    ID_TIPDAT = Column(Integer, primary_key=True)
    C_TIPDAT = Column(String(10))
    D_TIPDAT = Column(String(255))

    # Relaciones
    valores = relationship("ValoresDato", back_populates="tipo_dato", cascade='all, delete-orphan')

class ConfiguracionCriticidad(Base):
    """Modelo que representa la configuración de criticidad basada en probabilidad e impacto.

    Esta tabla define una matriz de riesgo: cada combinación de valor de probabilidad y valor de impacto
    produce un valor de criticidad. Se utiliza para calcular automáticamente la criticidad de un riesgo
    en función de sus valores evaluados.

    Attributes:
        ID_CRITIC (int): Clave primaria, identificador único de la configuración.
        V_IMPACTO (int): Clave foránea al valor de impacto (referencia a IA_VALDAT.ID_VALDAT).
        V_PROBAB (int): Clave foránea al valor de probabilidad (referencia a IA_VALDAT.ID_VALDAT).
        N_CRITICIDAD (int/float): Valor numérico de criticidad resultante de la combinación.

    Relaciones:
        impacto_valor (relationship): Relación muchos-a-uno con ValoresDato (valor de impacto).
        probabilidad_valor (relationship): Relación muchos-a-uno con ValoresDato (valor de probabilidad).

    Nota:
        - Esta tabla es estática y se configura una vez (por ejemplo, 5x5 matriz de riesgo).
        - Se usa para calcular la criticidad automática en DatosRiesgo cuando se asignan probabilidad e impacto.
    """
    __tablename__ = 'IA_CFGCRITICIDAD'

    ID_CRITIC = Column(Integer, primary_key=True)
    V_IMPACTO = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    V_PROBAB = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    N_CRITICIDAD = Column(Integer)

    # Relaciones
    impacto_valor = relationship("ValoresDato", foreign_keys=[V_IMPACTO], back_populates="configuraciones_impacto")
    probabilidad_valor = relationship("ValoresDato", foreign_keys=[V_PROBAB], back_populates="configuraciones_probabilidad")

class ConfiguracionFase(Base):
    """Modelo que representa la configuración de las fases del proceso de supervisión.

    Attributes:
        ID_FASE (int): Clave primaria, identificador único de la fase.
        C_FASE (int): Código numérico de la fase.
        D_FASE (str): Descripción textual de la fase.
        T_INSTRUCCIONES (str): Instrucciones generales para esta fase.
        N_ORDEN (int): Orden de presentación de la fase.
        L_MONITOREO (int): Indica si la fase implica monitoreo (1=sí, 0=no).
        T_INSTRCAMFASE (str): Instrucciones específicas para el cambio de fase.

    Nota:
        - Esta tabla define las etapas del proceso de supervisión.
        - Se utiliza para guiar al usuario y gestionar el flujo del trabajo.
    """
    __tablename__ = 'IA_CFGFASES'

    ID_FASE = Column(Integer, primary_key=True)
    C_FASE = Column(Integer)
    D_FASE = Column(String(255))
    T_INSTRUCIONES = Column(String(255))
    N_ORDEN = Column(Integer)
    L_MONITOREO = Column(Integer)
    T_INSTRCAMFASE = Column(String(255))
    C_NIVELRIESG = Column(String(1))


    # Relaciones con Riesgo para fases de visualización y evaluación
    riesgos_fase_visual = relationship(
        "Riesgo",
        foreign_keys=[Riesgo.N_FASEVISUAL],
        back_populates="fase_visual"
    )
    riesgos_fase_evaluacion = relationship(
        "Riesgo",
        foreign_keys=[Riesgo.N_FASEVAL],
        back_populates="fase_evaluacion"
    )

class DatosActividadMonitoreo(Base):
    """Modelo que registra la ejecución de actividades de monitoreo asociadas a una fase.

    Attributes:
        ID_DATACTMONIT (int): Clave primaria, identificador único del registro.
        SIST_ID_SISTEMA (int): Clave foránea al sistema/proyecto relacionado (Inicio).
        ACT_ID_CONTMON (int): Clave foránea a la actividad de monitoreo relacionada (DatosControlMonitoreo).
        F_EJECUCION (date): Fecha de ejecución de la actividad.
        T_DESCEJEC (str): Descripción o resultado de la ejecución.

    Relaciones:
        sistema (relationship): Relación muchos-a-uno con Inicio (sistema/proyecto).
        actividad_monitoreo (relationship): Relación muchos-a-uno con DatosControlMonitoreo (actividad específica).

    Nota:
        - Cada registro documenta cuándo y cómo se ejecutó una actividad de monitoreo específica.
        - Permite auditar y rastrear las acciones realizadas en cada proyecto.
    """
    __tablename__ = 'IA_DATACTMONIT'

    ID_DATACTMONIT = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'))
    ACT_ID_CONTMON = Column(Integer, ForeignKey('IA_DATCONTMON.ID_DATCONTMON'))
    F_EJECUCION = Column(String) # DATE en la captura. Se usa String para evitar problemas de conversión, o puedes usar Date si prefieres.
    T_DESCEJEC = Column(String(255))

    # Relaciones
    sistema = relationship("Inicio", back_populates="datos_actividad_monitoreo")
    actividad_monitoreo = relationship("DatosControlMonitoreo", back_populates="ejecuciones")

class DatosControlMonitoreo(Base):
    """Modelo que almacena los datos de control específicos para monitoreo, vinculados a un sistema y un control.

    Attributes:
        ID_DATCONTMON (int): Clave primaria, identificador único del registro.
        SIST_ID_SISTEMA (int): Clave foránea al sistema/proyecto relacionado (Inicio).
        CON_ID_CONTROL (int): Clave foránea al control relacionado (Control).
        V_ESTADO (int): Clave foránea al valor de estado (referencia a IA_VALDAT.ID_VALDAT).
        T_RESP (str): Respuesta o observación sobre el control.
        V_MADINI (int): Clave foránea al valor de madurez inicial (referencia a IA_VALDAT.ID_VALDAT).
        V_MADACT (int): Clave foránea al valor de madurez actual (referencia a IA_VALDAT.ID_VALDAT).
        V_MADOBJ (int): Clave foránea al valor de madurez objetivo (referencia a IA_VALDAT.ID_VALDAT).
        T_DESC (str): Descripción detallada del estado del control.
        V_FREC (int): Clave foránea al valor de frecuencia (referencia a IA_VALDAT.ID_VALDAT).
        F_PROXEJEC (date): Fecha de la próxima ejecución planeada.

    Relaciones:
        sistema (relationship): Relación muchos-a-uno con Inicio (sistema/proyecto).
        control (relationship): Relación muchos-a-uno con Control.
        estado_valor (relationship): Relación muchos-a-uno con ValoresDato (V_ESTADO).
        madurez_inicial_valor (relationship): Relación muchos-a-uno con ValoresDato (V_MADINI).
        madurez_actual_valor (relationship): Relación muchos-a-uno con ValoresDato (V_MADACT).
        madurez_objetivo_valor (relationship): Relación muchos-a-uno con ValoresDato (V_MADOBJ).
        frecuencia_valor (relationship): Relación muchos-a-uno con ValoresDato (V_FREC).
        ejecuciones (relationship): Relación uno-a-muchos con DatosActividadMonitoreo (registros de ejecución).

    Nota:
        - Esta tabla centraliza la información de seguimiento y monitoreo de controles por proyecto.
        - Utiliza valores predefinidos (desde IA_VALDAT) para estados, niveles de madurez y frecuencias.
        - Es clave para la gestión activa de controles y su evolución en el tiempo.
    """
    __tablename__ = 'IA_DATCONTMON'

    ID_DATCONTMON = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'))
    CON_ID_CONTROL = Column(Integer, ForeignKey('IA_CONTROLES.ID_CONTROL'))
    V_ESTADO = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_RESP = Column(String(255))
    V_MADINI = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    V_MADACT = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    V_MADOBJ = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_DESC = Column(Text)
    V_FREC = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    F_PROXEJEC = Column(String)  # DATE en la captura. Se usa String para evitar problemas de conversión

    # Relaciones
    sistema = relationship("Inicio", back_populates="datos_control_monitoreo")
    control = relationship("Control", back_populates="datos_control_monitoreo")
    estado_valor = relationship("ValoresDato", foreign_keys=[V_ESTADO], back_populates="valores_estado_control")
    madurez_inicial_valor = relationship("ValoresDato", foreign_keys=[V_MADINI], back_populates="valores_madurez_inicial")
    madurez_actual_valor = relationship("ValoresDato", foreign_keys=[V_MADACT], back_populates="valores_madurez_actual")
    madurez_objetivo_valor = relationship("ValoresDato", foreign_keys=[V_MADOBJ], back_populates="valores_madurez_objetivo")
    frecuencia_valor = relationship("ValoresDato", foreign_keys=[V_FREC], back_populates="valores_frecuencia")
    ejecuciones = relationship("DatosActividadMonitoreo", back_populates="actividad_monitoreo")

class Control(Base):
    """Modelo que representa un control dentro del sistema de supervisión.

    Attributes:
        ID_CONTROL (int): Clave primaria, identificador único del control.
        C_CONTROL (str): Código corto del control.
        D_CONTROL (str): Descripción del control.
        GRU_ID_CONTROL (int): Clave foránea al grupo de control (GrupoControl).
        PER_ID_PERFIL (int): Clave foránea al perfil asociado (Perfil).
        L_ORIENTA (int): Indica orientación del control (1=sí, 0=no).
        L_ESTADO (int): Estado del control (1=activo, 0=inactivo).
        N_ORDVISUAL (int): Orden visual de presentación.
        N_MADUMIN (int): Clave foránea al valor de madurez mínima (referencia a IA_VALDAT).
        D_DESCRIPCION (str): Descripción detallada del control.
        T_INSTRUCCIONES (str): Instrucciones para la implementación del control.
        D_DESCMONITOR (str): Descripción para monitoreo del control.

    Relaciones:
        grupo_control (relationship): Relación muchos-a-uno con GrupoControl.
        perfil (relationship): Relación muchos-a-uno con Perfil.
        respuestas_control (relationship): Relación uno-a-muchos con ControlRespuesta.
        datos_control (relationship): Relación uno-a-muchos con DatosControl.
        riesgos_control (relationship): Relación uno-a-muchos con RiesgoControl.
        datos_control_monitoreo (relationship): Relación uno-a-muchos con DatosControlMonitoreo.
        madurez_minima_valor (relationship): Relación muchos-a-uno con ValoresDato (N_MADUMIN).
    """
    __tablename__ = 'IA_CONTROLES'

    ID_CONTROL = Column(Integer, primary_key=True)
    C_CONTROL = Column(String(10))
    D_CONTROL = Column(String(255))
    GRU_ID_CONTROL = Column(Integer, ForeignKey('IA_GRUCONTROL.ID_GRUCONTROL'))
    PER_ID_PERFIL = Column(Integer, ForeignKey('IA_PERFIL.ID_PERFIL'))
    L_ORIENTA = Column(Integer)
    L_ESTADO = Column(Integer)
    N_ORDVISUAL = Column(Integer)
    D_DESCRIPCION = Column(String(255))
    T_INSTRUCCIONES = Column(String(255))
    N_MADUMIN = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    D_DESCMONITOR = Column(String(255))


    # Relaciones
    grupo_control = relationship("GrupoControl", back_populates="controles")
    perfil = relationship("Perfil", back_populates="controles")
    respuestas_control = relationship("ControlRespuesta", back_populates="control", cascade='all, delete-orphan')
    datos_control = relationship("DatosControl", back_populates="control", cascade='all, delete-orphan')
    riesgos_control = relationship("RiesgoControl", back_populates="control", cascade='all, delete-orphan')
    datos_control_monitoreo = relationship("DatosControlMonitoreo", back_populates="control", cascade='all, delete-orphan')
    madurez_minima_valor = relationship("ValoresDato", foreign_keys=[N_MADUMIN], back_populates="valores_madurez_minima")
    requisitos_asociados = relationship("ConfiguracionRequisito", secondary="IA_CFGREQCONTR", back_populates="controles_asociados")

class GrupoControl(Base):
    """Modelo que representa un grupo de controles (categoría de controles).

    Attributes:
        ID_GRUCONTROL (int): Clave primaria, identificador único del grupo.
        C_CONTROL (str): Código del grupo.
        D_CONTROL (str): Descripción del grupo.
        N_ORDVISUAL (int): Orden visual de presentación.
        L_OBLIG (int): Indica si el grupo es obligatorio (1=sí, 0=no).
        N_FASEVISUAL (int): Clave foránea a la fase visual (referencia a IA_CFGFASES.ID_FASE).
        N_FASEVAL (int): Clave foránea a la fase de evaluación (referencia a IA_CFGFASES.ID_FASE).
        L_MONITOREO (int): Indica si el grupo implica monitoreo (1=sí, 0=no).

    Relaciones:
        controles (relationship): Relación uno-a-muchos con Control.
    """
    __tablename__ = 'IA_GRUCONTROL'

    ID_GRUCONTROL = Column(Integer, primary_key=True)
    C_CONTROL = Column(String(10))
    D_CONTROL = Column(String(255))
    N_ORDVISUAL = Column(Integer)
    L_OBLIG = Column(Integer)
    N_FASEVISUAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_FASEVAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    L_MONITOREO = Column(Integer)

    # Relaciones
    controles = relationship("Control", back_populates="grupo_control")


class ControlActivacionNo(Base):
    """Modelo que configura qué grupos de control NO se activan según respuestas ADI.

    Define exclusiones de grupos de control basadas en las respuestas del cuestionario ADI.
    Por ejemplo, si la respuesta a P6 es D, no se activa el grupo 2 de control.

    Attributes:
        ID_CONACTNO (int): Clave primaria, identificador único del registro.
        CON_ID_GRUCONTROL (int): FK al grupo de control que se excluye (IA_GRUCONTROL).
        PRE_ID_PREGUNTA (int): FK a la pregunta ADI que determina la exclusión (IA_ADIPREG).
        RES_ID_RESPUESTA (int): FK a la respuesta ADI que activa la exclusión (IA_ADIRESP).

    Relaciones:
        grupo_control: Grupo de control excluido.
        pregunta: Pregunta ADI relacionada.
        respuesta: Respuesta ADI que activa la exclusión.

    Nota:
        - Es una tabla de configuración (datos estáticos).
        - Se usa para determinar qué grupos de control desactivar según el ADI.
    """
    __tablename__ = 'IA_CONACTNO'

    ID_CONACTNO = Column(Integer, primary_key=True)
    CON_ID_GRUCONTROL = Column(Integer, ForeignKey('IA_GRUCONTROL.ID_GRUCONTROL'))
    PRE_ID_PREGUNTA = Column(Integer, ForeignKey('IA_ADIPREG.ID_PREGUNTA'))
    RES_ID_RESPUESTA = Column(Integer, ForeignKey('IA_ADIRESP.ID_RESPUESTA'))

    # Relaciones
    grupo_control = relationship("GrupoControl")
    pregunta = relationship("Pregunta")
    respuesta = relationship("Respuesta")


class ControlRespuesta(Base):
    """Modelo que vincula un control con una respuesta ADI seleccionada.

    Attributes:
        ID_CONTIPADQS (int): Clave primaria, identificador único del registro.
        CON_ID_CONTROL (int): Clave foránea al control (Control).
        RESP_ID_RESP (int): Clave foránea a la respuesta (Respuesta).

    Relaciones:
        control (relationship): Relación muchos-a-uno con Control.
        respuesta (relationship): Relación muchos-a-uno con Respuesta.
    """
    __tablename__ = 'IA_CONTIPADSQ'

    ID_CONTIPADQS = Column(Integer, primary_key=True)
    CON_ID_CONTROL = Column(Integer, ForeignKey('IA_CONTROLES.ID_CONTROL'))
    RESP_ID_RESP = Column(Integer, ForeignKey('IA_ADIRESP.ID_RESPUESTA'))

    # Relaciones
    control = relationship("Control", back_populates="respuestas_control")
    respuesta = relationship("Respuesta", back_populates="controles_respuesta")

class DatosControl(Base):
    """Modelo que almacena los datos específicos de un control por sistema/proyecto.

    Attributes:
        ID_DATCONTROL (int): Clave primaria, identificador único del registro.
        SIST_ID_SISTEMA (int): Clave foránea al sistema/proyecto (Inicio).
        CON_ID_CONTROL (int): Clave foránea al control (Control).
        L_ACTIVA (int): Indica si el control está activo (1=si, 0=no).
        L_APLICA (int): Indica si aplica en este sistema (1=si, 0=no).
        L_TRASLAPLI (int): Indica si hay traslape aplicable (1=si, 0=no).
        V_INTCONDES (int): Valor de intensidad de condiciones (referencia a IA_VALDAT).
        T_ESPCLAUSULA (str): Texto especial de cláusula o justificación.
        T_OBSERVACIONES (str): Observaciones adicionales.
        V_MADUREZ (int): Valor de madurez del control (referencia a IA_VALDAT).

    Relaciones:
        sistema (relationship): Relación muchos-a-uno con Inicio.
        control (relationship): Relación muchos-a-uno con Control.
        valor_condicion (relationship): Relación muchos-a-uno con ValoresDato.
        madurez_valor (relationship): Relación muchos-a-uno con ValoresDato (para V_MADUREZ).
    """
    __tablename__ = 'IA_DATCONTROL'

    ID_DATCONTROL = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'))
    CON_ID_CONTROL = Column(Integer, ForeignKey('IA_CONTROLES.ID_CONTROL'))
    L_ACTIVA = Column(Integer)
    L_APLICA = Column(Integer)
    L_TRASLAPLI = Column(Integer)
    V_INTCONDES = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_ESPCLAUSULA = Column(String(255))
    T_OBSERVACIONES = Column(String(255))
    V_MADUREZ = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    L_MANUAL = Column(Integer, default=0)  # 0=automático, 1=activado manualmente por usuario

    # Relaciones
    sistema = relationship("Inicio", back_populates="datos_controles")
    control = relationship("Control", back_populates="datos_control")
    valor_condicion = relationship("ValoresDato", foreign_keys=[V_INTCONDES], back_populates="valores_condicion")
    madurez_valor = relationship("ValoresDato", foreign_keys=[V_MADUREZ], back_populates="valores_madurez")

class RiesgoControl(Base):
    """Modelo que representa la relación entre un riesgo y un control.

    Attributes:
        ID_RIESCONTR (int): Clave primaria, identificador único del registro.
        RIE_ID_RIESGO (int): Clave foránea al riesgo (Riesgo).
        CON_ID_CONTROL (int): Clave foránea al control (Control).
        PESO (int): Peso asignado a la relación (1-9).
        T_JUSTIFICACION (str): Justificación del peso asignado.

    Relaciones:
        riesgo (relationship): Relación muchos-a-uno con Riesgo.
        control (relationship): Relación muchos-a-uno con Control.
    """
    __tablename__ = 'IA_RIESCONTR'

    ID_RIESCONTR = Column(Integer, primary_key=True)
    RIE_ID_RIESGO = Column(Integer, ForeignKey('IA_RIESGOS.ID_RIESGO'))
    CON_ID_CONTROL = Column(Integer, ForeignKey('IA_CONTROLES.ID_CONTROL'))
    PESO = Column(Integer)
    T_JUSTIFICACION = Column(String(255))

    # Relaciones
    riesgo = relationship("Riesgo", back_populates="controles_riesgo")
    control = relationship("Control", back_populates="riesgos_control")

class DatosElementoControl(Base):
    """Modelo que almacena los datos de control asociados a un elemento ADI específico dentro de un sistema/proyecto.

    Attributes:
        ID_DATELEMCONTR (int): Clave primaria, identificador único del registro.
        SIST_ID_SISTEMA (int): Clave foránea al sistema/proyecto (Inicio).
        ELE_ID_ELEM (int): Clave foránea al elemento ADI (ElementosAdi).
        L_TRASLAPLI (int): Indica si hay traslape aplicable (1=sí, 0=no).
        V_INTSCONDES (int): Valor de intensidad de condiciones (referencia a IA_VALDAT).
        T_ESPCLAUSULA (str): Texto especial de cláusula o justificación.
        N_ITERACION (int): Número de iteración del dato.

    Relaciones:
        sistema (relationship): Relación muchos-a-uno con Inicio.
        elemento (relationship): Relación muchos-a-uno con ElementosAdi.
        intensidad_valor (relationship): Relación muchos-a-uno con ValoresDato (V_INTSCONDES).
    """
    __tablename__ = 'IA_DATELEMCONTR'

    ID_DATELEMCONTR = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'))
    ELE_ID_ELEM = Column(Integer, ForeignKey('IA_ELEMENADI.ID_ELEM'))
    L_TRASLAPLI = Column(Integer)
    V_INTSCONDES = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_ESPCLAUSULA = Column(String(255))
    N_ITERACION = Column(Integer)

    # Relaciones
    sistema = relationship("Inicio", back_populates="datos_elementos_control")
    elemento = relationship("ElementosAdi", back_populates="datos_elementos_control")
    intensidad_valor = relationship("ValoresDato", foreign_keys=[V_INTSCONDES], back_populates="valores_intensidad_elemento")

class ValoresDato(Base):
    """Modelo que representa los valores posibles asociados a un tipo de dato.

    Attributes:
        ID_VALDAT (int): Clave primaria, identificador único del valor.
        TIDA_ID_TIPDAT (str): Clave foránea al tipo de dato (IA_TIPDAT).
        C_VALOR (int): Código numérico del valor (puede ser utilizado como clave interna).
        D_VALOR (str): Descripción del valor.
        OBS (str): Observaciones o comentarios adicionales sobre el valor.

    Relaciones:
        tipo_dato (relationship): Relación muchos-a-uno con TiposDato (el tipo al que pertenece este valor).
        valores_probabilidad (relationship): Relación uno-a-muchos con DatosRiesgo (como valor de probabilidad).
        valores_impacto (relationship): Relación uno-a-muchos con DatosRiesgo (como valor de impacto).
        valores_usados (relationship): Relación uno-a-muchos con DatosRiesgo (usado como probabilidad o impacto).
        valores_condicion (relationship): Relación uno-a-muchos con DatosControl (como valor de condición).
        valores_madurez (relationship): Relación uno-a-muchos con DatosControl (como valor de madurez).
        valores_intensidad_elemento (relationship): Relación uno-a-muchos con DatosElementoControl (como valor de intensidad).
        configuraciones_impacto (relationship): Relación uno-a-muchos con ConfiguracionCriticidad (como valor de impacto).
        configuraciones_probabilidad (relationship): Relación uno-a-muchos con ConfiguracionCriticidad (como valor de probabilidad).
        valores_estado_control (relationship): Relación uno-a-muchos con DatosControlMonitoreo (como valor de estado).
        valores_madurez_inicial (relationship): Relación uno-a-muchos con DatosControl
        valores_madurez_actual (relationship): Relación uno-a-muchos con DatosControlMonitoreo (como valor de madurez actual).
        valores_madurez_objetivo (relationship): Relación uno-a-muchos con DatosControlMonitoreo (como valor de madurez objetivo).
        valores_frecuencia (relationship): Relación uno-a-muchos con DatosControlMonitoreo (como valor de frecuencia).
        valores_madurez_minima (relationship): Relación uno-a-muchos con Control (como valor de madurez mínima).


    Nota:
        - Cada instancia representa un valor específico disponible para un tipo de dato definido.
        - Se utiliza para gestionar listas de valores controladas (ej. estados, categorías, niveles, etc.).
        - La clave foránea TIDA_ID_TIPDAT vincula cada valor a un tipo de dato existente.
    """
    __tablename__ = 'IA_VALDAT'

    ID_VALDAT = Column(Integer, primary_key=True)
    TIDA_ID_TIPDAT = Column(Integer, ForeignKey('IA_TIPDAT.ID_TIPDAT'))
    C_VALOR = Column(Integer)
    C_VALOR_TEXT = Column(String(255))
    D_VALOR = Column(String(255))
    OBS = Column(String(255))
    N_ORDEN = Column(Integer)

    # Relaciones
    tipo_dato = relationship("TiposDato", back_populates="valores")
    # Relación para acceder a todos los DatosRiesgo donde este valor se usa como probabilidad
    valores_probabilidad = relationship(
        "DatosRiesgo",
        primaryjoin="ValoresDato.ID_VALDAT == DatosRiesgo.V_PROBABILIDAD",
        back_populates="probabilidad_valor"
    )
    # Relación para acceder a todos los DatosRiesgo donde este valor se usa como impacto
    valores_impacto = relationship(
        "DatosRiesgo",
        primaryjoin="ValoresDato.ID_VALDAT == DatosRiesgo.V_IMPACTO",
        back_populates="impacto_valor"
    )
    # Relación para acceder a todos los DatosRiesgo donde este valor se usa como probabilidad o impacto
    valores_usados = relationship(
        "DatosRiesgo",
        primaryjoin="or_(ValoresDato.ID_VALDAT == DatosRiesgo.V_PROBABILIDAD, ValoresDato.ID_VALDAT == DatosRiesgo.V_IMPACTO)",
        viewonly=True
    )
    # Relación para acceder a todos los DatosControl donde este valor se usa como valor de condición
    valores_condicion = relationship(
        "DatosControl",
        primaryjoin="ValoresDato.ID_VALDAT == DatosControl.V_INTCONDES",
        back_populates="valor_condicion"
    )
    # Relación para acceder a todos los DatosControl donde este valor se usa como valor de madurez
    valores_madurez = relationship(
        "DatosControl",
        primaryjoin="ValoresDato.ID_VALDAT == DatosControl.V_MADUREZ",
        back_populates="madurez_valor"
    )
    # Relación para acceder a todos los DatosElementoControl donde este valor se usa como valor de intensidad
    valores_intensidad_elemento = relationship(
    "DatosElementoControl",
    primaryjoin="ValoresDato.ID_VALDAT == DatosElementoControl.V_INTSCONDES",
    back_populates="intensidad_valor"
    )
    # Relación para acceder a todas las configuraciones donde este valor se usa como impacto
    configuraciones_impacto = relationship(
        "ConfiguracionCriticidad",
        foreign_keys=[ConfiguracionCriticidad.V_IMPACTO],
        back_populates="impacto_valor"
    )

    # Relación para acceder a todas las configuraciones donde este valor se usa como probabilidad
    configuraciones_probabilidad = relationship(
        "ConfiguracionCriticidad",
        foreign_keys=[ConfiguracionCriticidad.V_PROBAB],
        back_populates="probabilidad_valor"
    )

    # Relaciones con DatosControlMonitoreo
    valores_estado_control = relationship(
        "DatosControlMonitoreo",
        foreign_keys=[DatosControlMonitoreo.V_ESTADO],
        back_populates="estado_valor"
    )

    valores_madurez_inicial = relationship(
        "DatosControlMonitoreo",
        foreign_keys=[DatosControlMonitoreo.V_MADINI],
        back_populates="madurez_inicial_valor"
    )

    valores_madurez_actual = relationship(
        "DatosControlMonitoreo",
        foreign_keys=[DatosControlMonitoreo.V_MADACT],
        back_populates="madurez_actual_valor"
    )
    valores_madurez_objetivo = relationship(
        "DatosControlMonitoreo",
        foreign_keys=[DatosControlMonitoreo.V_MADOBJ],
        back_populates="madurez_objetivo_valor"
    )
    #
    valores_frecuencia = relationship(
        "DatosControlMonitoreo",
        foreign_keys=[DatosControlMonitoreo.V_FREC],
        back_populates="frecuencia_valor"
    )

    # Añade esta relación dentro de la clase ValoresDato (junto a las otras relaciones)
    valores_madurez_minima = relationship(
        "Control",
        foreign_keys=[Control.N_MADUMIN],
        back_populates="madurez_minima_valor"
    )

    # Relación para acceder a todos los DatosRiesgo donde este valor se usa como riesgo residual
    valores_riesgo_residual = relationship(
        "DatosRiesgo",
        foreign_keys=[DatosRiesgo.V_RIERESID],
        back_populates="riesgo_residual_valor"
    )

class AyudaContexto(Base):
    """
    Modelo para almacenar ayudas contextuales (tooltips) de la aplicación.

    Attributes:
        ID_AYUDACONTEXTO (int): Identificador único de la ayuda.
        C_FORMULARIO (str): Nombre del formulario donde aparece el control.
        C_CONTROL (str): Identificador del control HTML.
        T_AYUDA (str): Texto de ayuda a mostrar.
        C_TIPO (str): Tipo de ayuda.
        L_ESTADO (int): Estado activo/inactivo de la ayuda.
        N_POS_X (int): Posición X (left) del modal en píxeles.
        N_POS_Y (int): Posición Y (top) del modal en píxeles.
        N_WIDTH (int): Ancho del modal en píxeles.
        N_HEIGHT (int): Alto del modal en píxeles.
        N_SCREEN_WIDTH (int): Ancho de la pantalla cuando se guardó la posición.
    """
    __tablename__ = 'IA_AYUDACONTEXTO'

    ID_AYUDACONTEXTO = Column(Integer, primary_key=True)
    C_FORMULARIO = Column(String(50))
    C_CONTROL = Column(String(100))
    T_AYUDA = Column(Text)
    C_TIPO = Column(Text)
    L_ESTADO = Column(Integer, default=1)

    # Campos para guardar posición y tamaño del modal
    N_POS_X = Column(Integer, nullable=True)
    N_POS_Y = Column(Integer, nullable=True)
    N_WIDTH = Column(Integer, nullable=True)
    N_HEIGHT = Column(Integer, nullable=True)
    N_SCREEN_WIDTH = Column(Integer, nullable=True)


class ConfiguracionDocumento(Base):
    """Modelo que representa la configuración de un tipo de documento (EIPD, IV, etc.)."""
    __tablename__ = 'IA_CFGDOCS'

    ID_CFGDOCS = Column(Integer, primary_key=True)
    T_DESC = Column(Text)
    T_INSTRUC = Column(Text)
    V_TIPODOC = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_PLANTILLA = Column(String(255))
    N_FASEVISUAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_FASEVAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_ORDVISU = Column(Integer)
    V_SITINICIAL = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    V_SITFINAL = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    V_SITATRAS = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    V_SITNOAPLICA = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))

    # Relaciones
    tipo_documento_valor = relationship("ValoresDato", foreign_keys=[V_TIPODOC])
    fase_visual = relationship("ConfiguracionFase", foreign_keys=[N_FASEVISUAL])
    fase_evaluacion = relationship("ConfiguracionFase", foreign_keys=[N_FASEVAL])
    situacion_inicial_valor = relationship("ValoresDato", foreign_keys=[V_SITINICIAL])
    situacion_final_valor = relationship("ValoresDato", foreign_keys=[V_SITFINAL])
    situacion_atras_valor = relationship("ValoresDato", foreign_keys=[V_SITATRAS])
    situacion_noaplica_valor = relationship("ValoresDato", foreign_keys=[V_SITNOAPLICA])
    campos = relationship("ConfiguracionDatoDocumento", back_populates="documento", cascade='all, delete-orphan')
    datos_documentos = relationship("DatosDocumento", back_populates="configuracion", cascade='all, delete-orphan')


class ConfiguracionDatoDocumento(Base):
    """Modelo que representa un campo o sección dentro de un documento."""
    __tablename__ = 'IA_CFGDATDOCS'

    ID_CFGDATDOCS = Column(Integer, primary_key=True)
    DD_ID_CFGDOCS = Column(Integer, ForeignKey('IA_CFGDOCS.ID_CFGDOCS'), nullable=False)
    DD_ID_CFGDD_SUP = Column(Integer, ForeignKey('IA_CFGDATDOCS.ID_CFGDATDOCS'))
    C_DATO = Column(Text)
    D_DESC = Column(Text)
    T_INSTR = Column(Text)
    T_EXPLANT = Column(Text)
    T_EXPLPOST = Column(Text)
    N_ORDEN = Column(Integer)
    L_OBLIG = Column(Integer, default=0)
    N_ANID = Column(Integer)
    L_EDITABLE = Column(Integer, default=1)
    N_VALORES_CHECK = Column(Integer)
    L_CHECK = Column(Integer)

    # Relaciones
    documento = relationship("ConfiguracionDocumento", back_populates="campos")
    elemento_superior = relationship("ConfiguracionDatoDocumento", remote_side=[ID_CFGDATDOCS], backref='sub_elementos')
    relaciones_elementos = relationship(
        "RelacionDocumentoElemento",
        foreign_keys="[RelacionDocumentoElemento.RDE_ID_CFGDATDOCS]",
        back_populates="campo_documento",
        cascade='all, delete-orphan'
    )
    datos_elementos = relationship("DatosElementoDocumento", back_populates="campo", cascade='all, delete-orphan')


class RelacionDocumentoElemento(Base):
    """Modelo que relaciona campos de documentos con elementos de descripción ADI."""
    __tablename__ = 'IA_CFGRELDOCEL'

    ID_CFGRELDOCEL = Column(Integer, primary_key=True)
    RDE_ID_CFGDATDOCS = Column(Integer, ForeignKey('IA_CFGDATDOCS.ID_CFGDATDOCS'), nullable=False)
    RDE_ID_SUBELEM = Column(Integer, ForeignKey('IA_SUBELEMENADI.ID_SUBELEM'))
    RDE_ID_CFGCATDOCSREL = Column(Integer, ForeignKey('IA_CFGDATDOCS.ID_CFGDATDOCS'))
    L_AUTO = Column(Integer, default=0)

    # Relaciones
    campo_documento = relationship(
        "ConfiguracionDatoDocumento",
        foreign_keys=[RDE_ID_CFGDATDOCS],
        back_populates="relaciones_elementos"
    )

    subelemento = relationship("SubElementosAdi")

    # Relación con el campo relacionado (si existe)
    campo_relacionado = relationship(
        "ConfiguracionDatoDocumento",
        foreign_keys=[RDE_ID_CFGCATDOCSREL]
    )


class DatosDocumento(Base):
    """Modelo que representa un documento específico de un proyecto."""
    __tablename__ = 'IA_DATDOCS'

    ID_DATDOCS = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'), nullable=False)
    DD_ID_CFGDOCS = Column(Integer, ForeignKey('IA_CFGDOCS.ID_CFGDOCS'), nullable=False)
    V_SITUACION = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_OBSERVACIONES = Column(Text)
    L_NECESARIO = Column(Integer, default=1)


    # Relaciones
    sistema = relationship("Inicio", back_populates="documentos")
    configuracion = relationship("ConfiguracionDocumento", back_populates="datos_documentos")
    situacion_valor = relationship("ValoresDato", foreign_keys=[V_SITUACION])
    elementos = relationship("DatosElementoDocumento", back_populates="documento", cascade='all, delete-orphan')


class DatosElementoDocumento(Base):
    """Modelo que almacena el contenido de cada campo del documento por proyecto."""
    __tablename__ = 'IA_DATELEMDOCS'

    ID_DATELEMDOCS = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'), nullable=False)
    DED_ID_DATDOCS = Column(Integer, ForeignKey('IA_DATDOCS.ID_DATDOCS'), nullable=False)
    DED_ID_CFGDATDOCS = Column(Integer, ForeignKey('IA_CFGDATDOCS.ID_CFGDATDOCS'), nullable=False)
    T_DATO = Column(Text)

    # Relaciones
    sistema = relationship("Inicio", back_populates="elementos_documentos")
    documento = relationship("DatosDocumento", back_populates="elementos")
    campo = relationship("ConfiguracionDatoDocumento", back_populates="datos_elementos")

class ConfiguracionIncompatibilidad(Base):
    """Modelo que representa la configuración de incompatibilidades entre respuestas ADI.
    Attributes:
        ID_CFGINCOMPADI (int): Clave primaria, identificador único de la configuración.
        T_DESC (str): Descripción de la incompatibilidad.
        RES_ID_RESP_UNO (int): Clave foránea a la primera respuesta incompatible (Respuesta).
        RES_ID_RESP_DOS (int): Clave foránea a la segunda respuesta incompatible (Respuesta).
        C_TIPOINCOMP (str): Tipo de incompatibilidad (por ejemplo, 'E' para exclusiva).
        T_MENSAJE (str): Mensaje de advertencia o error a mostrar al usuario.
    Relaciones:
        respuesta_uno (relationship): Relación muchos-a-uno con Respuesta (primera respuesta).
        respuesta_dos (relationship): Relación muchos-a-uno con Respuesta (segunda respuesta).
    Nota:
        - Se utiliza para validar que no se seleccionen respuestas mutuamente excluyentes en el formulario ADI.
        - La clave foránea apunta a la tabla IA_ADIRESP (Respuesta).
    """
    __tablename__ = 'IA_CFGINCOMPADI'
    ID_CFGINCOMPADI = Column(Integer, primary_key=True)
    T_DESC = Column(String(255))
    RES_ID_RESP_UNO = Column(Integer, ForeignKey('IA_ADIRESP.ID_RESPUESTA'))
    RES_ID_RESP_DOS = Column(Integer, ForeignKey('IA_ADIRESP.ID_RESPUESTA'))
    C_TIPOINCOMP = Column(String(1))  # Ej: 'E' para exclusiva
    T_MENSAJE = Column(String(255))

    # Relaciones
    respuesta_uno = relationship("Respuesta", foreign_keys=[RES_ID_RESP_UNO])
    respuesta_dos = relationship("Respuesta", foreign_keys=[RES_ID_RESP_DOS])



class ReglaEIPD(Base):
    """Modelo que representa una regla de evaluación de necesidad de EIPD.

    Attributes:
        ID_REGLA (int): Clave primaria.
        C_CODIGO (str): Código único de la regla (ej: 'R001').
        D_REGLA (str): Descripción legible.
        T_EXPRESION (str): Expresión lambda Python.
        V_RESULTADO (int): FK a IA_VALDAT (nivel EIPD).
        N_ORDEN (int): Orden de evaluación.
        L_ACTIVA (int): 1=activa, 0=inactiva.
        L_EXCLUYENTE (int): 1=detiene evaluación, 0=continúa.
        T_NOTAS (str): Notas jurídicas.
    """
    __tablename__ = 'IA_CFGREGLASEIPD'

    ID_REGLA = Column(Integer, primary_key=True)
    C_CODIGO = Column(String(20))
    D_REGLA = Column(Text)
    T_EXPRESION = Column(Text)
    V_RESULTADO = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    N_ORDEN = Column(Integer, default=0)
    L_ACTIVA = Column(Integer, default=1)
    L_EXCLUYENTE = Column(Integer, default=0)
    T_NOTAS = Column(Text)

    # Relaciones
    resultado_valor = relationship("ValoresDato", foreign_keys=[V_RESULTADO])


class ConfiguracionVisibilidad(Base):
    """
    Modelo para configurar la visibilidad dinámica de elementos según respuestas ADI.

    Permite ocultar/mostrar o habilitar/deshabilitar elementos de formularios
    basándose en las respuestas del cuestionario ADI del proyecto.

    Attributes:
        ID_CFGVISIBILIDAD (int): Identificador único de la configuración.
        C_FORMULARIO (str): Nombre del formulario (ej: 'formulario_controles').
        C_ELEMENTO_ID (str): ID del elemento HTML. Si termina en '-', es un prefijo.
        C_TIPO_ELEM (str): Tipo de elemento (th, td, select, button, div, etc.).
        T_CONDICION (str): Expresión JavaScript a evaluar (ej: "respuestas['P1'] === 'A'").
        C_ACCION (str): Acción a realizar: 'ocultar', 'mostrar', 'deshabilitar', 'habilitar'.
        N_PRIORIDAD (int): Orden de aplicación (menor = mayor prioridad).
        T_DESCRIPCION (str): Descripción legible de la regla.
        L_ACTIVO (int): 1=activo, 0=inactivo.
    """
    __tablename__ = 'IA_CFGVISIBILIDAD'

    ID_CFGVISIBILIDAD = Column(Integer, primary_key=True)
    C_FORMULARIO = Column(String(100))
    C_ELEMENTO_ID = Column(String(100))
    C_TIPO_ELEM = Column(String(50))
    T_CONDICION = Column(Text)
    C_ACCION = Column(String(20))
    N_PRIORIDAD = Column(Integer, default=100)
    T_DESCRIPCION = Column(Text)
    L_ACTIVO = Column(Integer, default=1)


# ============================================================================
# MODELOS PARA REQUISITOS DE CUMPLIMIENTO
# ============================================================================
# Las siguientes clases implementan el sistema de Requisitos de Cumplimiento
# del RGPD, que complementan al catálogo de riesgos con condiciones imperativas
# cuyo cumplimiento es preceptivo para la licitud del tratamiento.
# ============================================================================


class ConfiguracionRequisito(Base):
    """Modelo que representa el catálogo maestro de requisitos de cumplimiento RGPD.

    Los Requisitos de Cumplimiento son condiciones imperativas derivadas del RGPD
    que deben verificarse obligatoriamente, a diferencia de los riesgos que se
    evalúan por probabilidad/impacto.

    Attributes:
        ID_REQ (int): Identificador único del requisito (no autoincremental).
        C_REQUISITO (str): Código del requisito (ej: 'RC001', 'RC002').
        D_REQUISITO (str): Denominación o nombre descriptivo del requisito.
        T_DESCRIPCION (str): Explicación detallada del requisito.
        L_APLICAOBLIG (int): Booleano (1/0). Si es 1, el requisito aplica siempre;
                            si es 0, el usuario puede marcarlo como "No aplica".
        T_BASENORMATIVA (str): Artículo(s) del RGPD que fundamentan el requisito.
        L_ESTADO (int): Booleano (1/0) para activar/desactivar el requisito.
        N_ORDVISU (int): Orden de visualización en la interfaz.
        N_FASEVISUAL (int): FK a fase en la que se visualiza el requisito.
        N_FASEVALPLANIF (int): FK a fase de evaluación de planificación (Fase 2).
        N_FASEVALCUMPL (int): FK a fase de evaluación de cumplimiento (Fase 3).

    Relaciones:
        fase_visual: Fase en la que se muestra el requisito.
        fase_val_planif: Fase para evaluación de planificación.
        fase_val_cumpl: Fase para evaluación de cumplimiento efectivo.
        controles_asociados: Lista de controles vinculados (muchos a muchos).
        datos_requisitos: Datos de evaluación por proyecto.
    """
    __tablename__ = 'IA_CFGREQUISITOS'

    ID_REQ = Column(Integer, primary_key=True)
    C_REQUISITO = Column(String(4))
    D_REQUISITO = Column(String(255))
    T_DESCRIPCION = Column(String(255))
    L_APLICAOBLIG = Column(Integer, default=1)
    T_BASENORMATIVA = Column(String(255))
    L_ESTADO = Column(Integer)
    N_ORDVISU = Column(Integer)
    N_FASEVISUAL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_FASEVALPLANIF = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))
    N_FASEVALCUMPL = Column(Integer, ForeignKey('IA_CFGFASES.ID_FASE'))

    # Relaciones
    fase_visual = relationship("ConfiguracionFase", foreign_keys=[N_FASEVISUAL])
    fase_val_planif = relationship("ConfiguracionFase", foreign_keys=[N_FASEVALPLANIF])
    fase_val_cumpl = relationship("ConfiguracionFase", foreign_keys=[N_FASEVALCUMPL])

    # Relación muchos a muchos con controles a través de IA_CFGREQCONTR
    controles_asociados = relationship(
        "Control",
        secondary="IA_CFGREQCONTR",
        back_populates="requisitos_asociados"
    )

    # Relación uno a muchos con datos de requisitos por proyecto
    datos_requisitos = relationship(
        "DatosRequisito",
        back_populates="requisito",
        cascade='all, delete-orphan'
    )


class ConfiguracionEstadoRequisito(Base):
    """Modelo que representa los posibles estados de un requisito de cumplimiento.

    Existen dos tipos de estados:
    - Estados de Planificación (Fase 2): No evaluado, No aplica, Planificación
      insuficiente, Planificación adecuada.
    - Estados de Cumplimiento (Fase 3): No cumplido, Parcialmente cumplido,
      Sustancialmente cumplido, Plenamente cumplido.

    Attributes:
        ID_ESTREQ (int): Identificador único del estado (no autoincremental).
        C_ESTADO (str): Código del estado (ej: '0', '1', '2', '3').
        D_ESTADO (str): Denominación del estado.
        T_DESCRIPCION (str): Descripción detallada del estado.
        C_TIPOESTADO (str): Tipo de estado: 'P' para Planificación, 'C' para Cumplimiento.
        N_ORDVISU (int): Orden de visualización.
        L_AVANCEFASE (int): Booleano (1/0). Si es 1, permite avanzar de fase.
        L_JUSTOBLIG (int): Booleano (1/0). Si es 1, requiere justificación obligatoria.
        L_INICIAL (int): Booleano (1/0). Si es 1, este es el estado inicial para su tipo.
        L_NOAPLICA (int): Booleano (1/0). Si es 1, este es el estado "No aplica" especial.
        L_PLANMEJORA (int): Booleano (1/0). Si es 1, muestra el campo Plan de Mejora.

    Relaciones:
        datos_planif: Datos de requisitos que tienen este estado en planificación.
        datos_cumpl: Datos de requisitos que tienen este estado en cumplimiento.
    """
    __tablename__ = 'IA_CFGESTREQ'

    ID_ESTREQ = Column(Integer, primary_key=True)
    C_ESTADO = Column(String(4))
    D_ESTADO = Column(String(255))
    T_DESCRIPCION = Column(String(255))
    C_TIPOESTADO = Column(String(1))  # 'P' = Planificación, 'C' = Cumplimiento
    N_ORDVISU = Column(Integer)
    L_AVANCEFASE = Column(Integer)
    L_JUSTOBLIG = Column(Integer)
    L_INICIAL = Column(Integer, default=0)  # 1 = Estado inicial para su tipo
    L_NOAPLICA = Column(Integer, default=0)  # 1 = Estado "No aplica" especial
    L_PLANMEJORA = Column(Integer, default=0)  # 1 = Mostrar campo Plan de Mejora

    # Relaciones inversas con DatosRequisito
    datos_planif = relationship(
        "DatosRequisito",
        foreign_keys="[DatosRequisito.N_ESTPLANIF]",
        back_populates="estado_planif"
    )

    datos_cumpl = relationship(
        "DatosRequisito",
        foreign_keys="[DatosRequisito.N_ESTCUMPL]",
        back_populates="estado_cumpl"
    )


class DatosRequisito(Base):
    """Modelo que almacena la evaluación de requisitos por proyecto/sistema.

    Cada registro representa la evaluación de un requisito específico para un
    proyecto concreto, con información tanto de planificación (Fase 2) como
    de cumplimiento efectivo (Fase 3).

    Attributes:
        ID_DATREQ (int): Identificador único (no autoincremental).
        SIST_ID_SISTEMA (int): FK al proyecto/sistema (IA_SISTEMA).
        REQ_ID_REQU (int): FK al requisito del catálogo (IA_CFGREQUISITOS).
        L_APLICA (int): Booleano (1/0). 1 si el requisito aplica al proyecto.
        T_JUSTAPLICA (str): Justificación si se marca como "No aplica".
        N_ESTPLANIF (int): FK al estado de planificación (IA_CFGESTREQ).
        T_JUSTPLANIF (str): Justificación de cómo se prevé cumplir (Fase 2).
        N_ESTCUMPL (int): FK al estado de cumplimiento efectivo (IA_CFGESTREQ).
        T_JUSTCUMPL (str): Justificación de cómo se ha cumplido con evidencias (Fase 3).
        L_TRASLAPLI (int): Booleano (1/0). 1 si se ha trasladado a pliegos contractuales.
        V_INSTRCONTR (int): FK a tipo de instrumento contractual (IA_VALDAT).
        T_OBSPLIEGO (str): Observaciones sobre el traslado a pliegos.
        T_PLANMEJORA (str): Plan de mejora (obligatorio si estado = Sustancialmente cumplido).

    Relaciones:
        sistema: Proyecto al que pertenece esta evaluación.
        requisito: Requisito del catálogo que se está evaluando.
        estado_planif: Estado de planificación actual.
        estado_cumpl: Estado de cumplimiento actual.
        instrumento_contractual: Valor de dominio del instrumento contractual.
    """
    __tablename__ = 'IA_DATEREQUISITOS'

    ID_DATREQ = Column(Integer, primary_key=True)
    SIST_ID_SISTEMA = Column(Integer, ForeignKey('IA_SISTEMA.ID_SISTEMA'), nullable=False)
    REQ_ID_REQU = Column(Integer, ForeignKey('IA_CFGREQUISITOS.ID_REQ'), nullable=False)
    L_APLICA = Column(Integer)
    T_JUSTAPLICA = Column(Text)
    N_ESTPLANIF = Column(Integer, ForeignKey('IA_CFGESTREQ.ID_ESTREQ'))
    T_JUSTPLANIF = Column(Text)
    N_ESTCUMPL = Column(Integer, ForeignKey('IA_CFGESTREQ.ID_ESTREQ'))
    T_JUSTCUMPL = Column(Text)
    L_TRASLAPLI = Column(Integer)
    V_INSTRCONTR = Column(Integer, ForeignKey('IA_VALDAT.ID_VALDAT'))
    T_OBSPLIEGO = Column(Text)
    T_PLANMEJORA = Column(Text)

    # Relaciones
    sistema = relationship("Inicio", back_populates="datos_requisitos")
    requisito = relationship("ConfiguracionRequisito", back_populates="datos_requisitos")
    estado_planif = relationship(
        "ConfiguracionEstadoRequisito",
        foreign_keys=[N_ESTPLANIF],
        back_populates="datos_planif"
    )
    estado_cumpl = relationship(
        "ConfiguracionEstadoRequisito",
        foreign_keys=[N_ESTCUMPL],
        back_populates="datos_cumpl"
    )
    instrumento_contractual = relationship("ValoresDato", foreign_keys=[V_INSTRCONTR])


class ConfiguracionRequisitoControl(Base):
    """Modelo que relaciona requisitos con controles (tabla de asociación muchos a muchos).

    Los controles vinculados a un requisito sirven como orientación para evidenciar
    el cumplimiento y facilitar la trazabilidad en auditorías. A diferencia de la
    relación control-riesgo, aquí no se aplican pesos.

    Attributes:
        ID_REQCONTR (int): Identificador único (no autoincremental).
        REQ_ID_REQU (int): FK al requisito (IA_CFGREQUISITOS).
        REQ_ID_CONTROL (int): FK al control (IA_CONTROLES).

    Relaciones:
        Se utilizan principalmente las relaciones many-to-many definidas en
        ConfiguracionRequisito.controles_asociados y
        Control.requisitos_asociados.
    """
    __tablename__ = 'IA_CFGREQCONTR'

    ID_REQCONTR = Column(Integer, primary_key=True)
    REQ_ID_REQU = Column(Integer, ForeignKey('IA_CFGREQUISITOS.ID_REQ'), nullable=False)
    REQ_ID_CONTROL = Column(Integer, ForeignKey('IA_CONTROLES.ID_CONTROL'), nullable=False)

# ============================================================================
# MODELOS PARA RIESGO GLOBAL
# ============================================================================

class ConfiguracionCluster(Base):
    """Modelo que representa los clusters de riesgos interconectados.

    Los clusters agrupan riesgos relacionados que, si se materializan conjuntamente,
    tendrían efectos compuestos. Se utilizan para calcular el factor agravante de
    interdependencia en el riesgo global.

    Attributes:
        ID_CLUSTER (int): Identificador único del cluster (no autoincremental).
        C_CLUSTER (str): Código del cluster (ej: 'C1', 'C2', ... 'C11').
        D_CLUSTER (str): Denominación del cluster.
        T_DESCRIPCION (str): Descripción detallada del cluster.
        N_UMBRAL (int): Número de riesgos en MEDIO que activa el factor agravante.
        N_ORDVISU (int): Orden de visualización.
        L_ESTADO (int): Estado activo/inactivo (1/0).

    Relaciones:
        riesgos: Lista de riesgos asociados a este cluster (muchos a muchos).
    """
    __tablename__ = 'IA_CFGCLUSTERS'

    ID_CLUSTER = Column(Integer, primary_key=True)
    C_CLUSTER = Column(String(10))
    D_CLUSTER = Column(String(255))
    T_DESCRIPCION = Column(Text)
    N_UMBRAL = Column(Integer)
    N_ORDVISU = Column(Integer)
    L_ESTADO = Column(Integer, default=1)

    # Relación N:N con riesgos
    riesgos = relationship(
        "Riesgo",
        secondary="IA_CFGRIESCLUSTER",
        back_populates="clusters"
    )


class ConfiguracionRiesgoCluster(Base):
    """Tabla intermedia para la relación N:N entre Riesgos y Clusters.

    Permite que un riesgo pueda pertenecer a múltiples clusters y viceversa.

    Attributes:
        ID_RIESCLUSTER (int): Identificador único (no autoincremental).
        RIE_ID_RIESGO (int): FK al riesgo (IA_RIESGOS).
        CLU_ID_CLUSTER (int): FK al cluster (IA_CFGCLUSTERS).
    """
    __tablename__ = 'IA_CFGRIESCLUSTER'

    ID_RIESCLUSTER = Column(Integer, primary_key=True)
    RIE_ID_RIESGO = Column(Integer, ForeignKey('IA_RIESGOS.ID_RIESGO'), nullable=False)
    CLU_ID_CLUSTER = Column(Integer, ForeignKey('IA_CFGCLUSTERS.ID_CLUSTER'), nullable=False)


class ConfiguracionRiesgoGlobal(Base):
    """Modelo que almacena todos los parámetros del sistema de riesgo global.

    Esta tabla unifica la configuración de:
    - Niveles de riesgo global (BAJO, MEDIO, ALTO, CRÍTICO)
    - Factores agravantes (concentración, clusters, específicos)
    - Parámetros generales (fases de validación)

    Attributes:
        ID_CFGRIESGLOBAL (int): Identificador único (no autoincremental).
        C_PARAMETRO (str): Código único del parámetro (ej: 'NIVEL_BAJO', 'FACTOR_CONCENTRACION').
        C_GRUPO (str): Grupo del parámetro ('NIVEL', 'FACTOR', 'GENERAL').
        D_PARAMETRO (str): Descripción del parámetro.
        N_VALOR (float): Valor numérico (umbral, orden, etc.).
        T_VALOR (str): Valor texto (nombre del nivel, tipo de umbral).
        C_COLOR (str): Color hexadecimal para visualización.
        L_BLOQUEAFASE (int): 1 si este nivel bloquea el avance de fase.
        T_MENSAJE (str): Mensaje a mostrar en la UI.
        N_ORDVISU (int): Orden de visualización.
        L_ESTADO (int): Estado activo/inactivo (1/0).
    """
    __tablename__ = 'IA_CFGRIESGLOBAL'

    ID_CFGRIESGLOBAL = Column(Integer, primary_key=True)
    C_PARAMETRO = Column(String(30), nullable=False)
    C_GRUPO = Column(String(20))
    D_PARAMETRO = Column(String(255))
    N_VALOR = Column(Float)
    T_VALOR = Column(String(50))
    C_COLOR = Column(String(7))
    L_BLOQUEAFASE = Column(Integer)
    T_MENSAJE = Column(Text)
    N_ORDVISU = Column(Integer)
    L_ESTADO = Column(Integer, default=1)


# ============================================================================
# MODELO PARA CONTROL DE VERSIONES EN IMPORTACIÓN/EXPORTACIÓN
# ============================================================================

class ConfiguracionVersionCompatibilidad(Base):
    """Modelo que gestiona las reglas de compatibilidad de versiones para importación.

    Permite definir qué versiones de archivos exportados son compatibles con la
    versión actual del sistema, y opcionalmente ejecutar scripts de migración
    para adaptar datos de versiones antiguas.

    Attributes:
        ID_VERSCOMPAT (int): Identificador único de la regla.
        C_TIPO (str): Tipo de versión a verificar ('APP' = aplicación, 'BD' = base de datos).
        C_VERSION_MIN (str): Versión mínima del archivo origen (inclusive). Soporta comodines: '1.*'
        C_VERSION_MAX (str): Versión máxima del archivo origen (inclusive). NULL = sin límite.
        C_VERS_SIST_MIN (str): Versión mínima del sistema destino. Soporta comodines: '2.*'
        C_VERS_SIST_MAX (str): Versión máxima del sistema destino. NULL = sin límite.
        L_COMPATIBLE (int): 1 = Versiones compatibles (permitir importación),
                           0 = Versiones bloqueadas (rechazar importación).
        T_SQL_MIGRACION (str): Scripts SQL a ejecutar post-importación, separados por ';'.
                              Puede usar variables :proyecto_id, :version_origen, :version_bd_origen.
        C_MENSAJE (str): Código del mensaje en IA_VALDAT (tipo MENSAJES) a mostrar.
        T_DESCRIPCION (str): Descripción de la regla para administración.
        N_ORDEN (int): Orden de evaluación. Menor número = mayor prioridad.
        L_ESTADO (int): 1 = Regla activa, 0 = Regla inactiva.

    Funcionamiento:
        - Las reglas se evalúan en orden de N_ORDEN (ascendente)
        - Una regla coincide si: versión archivo en rango origen Y versión sistema en rango destino
        - La primera regla que coincida se aplica
        - Si ninguna regla coincide, se permite importación normal sin mensaje
        - Soporta comodines: '1.*' coincide con cualquier versión 1.x

    Ejemplos de reglas:
        - Bloquear v1.* importando a v2.*: C_VERSION_MIN='1.*', C_VERS_SIST_MIN='2.*', L_COMPATIBLE=0
        - Permitir v1.0+ sin restricción: C_VERSION_MIN='1.0', C_VERSION_MAX=NULL, L_COMPATIBLE=1
    """
    __tablename__ = 'IA_CFGVERSCOMPAT'

    ID_VERSCOMPAT = Column(Integer, primary_key=True)
    C_TIPO = Column(String(3), nullable=False)  # 'APP' o 'BD'
    C_VERSION_MIN = Column(String(20))          # Versión mínima archivo origen
    C_VERSION_MAX = Column(String(20))          # Versión máxima archivo origen
    C_VERS_SIST_MIN = Column(String(20))        # Versión mínima sistema destino
    C_VERS_SIST_MAX = Column(String(20))        # Versión máxima sistema destino
    L_COMPATIBLE = Column(Integer, nullable=False)  # 1 = compatible, 0 = bloqueado
    T_SQL_MIGRACION = Column(Text)              # Scripts SQL separados por ';'
    C_MENSAJE = Column(String(30))              # Código del mensaje en IA_VALDAT
    T_DESCRIPCION = Column(Text)
    N_ORDEN = Column(Integer, default=100)      # Menor = mayor prioridad
    L_ESTADO = Column(Integer, default=1)       # 1 = activa



class ConfiguracionManualUso(Base):
    """Modelo que configura las guías/manuales disponibles en la pantalla de ayuda.

    Permite gestionar dinámicamente las entradas de guías rápidas que se muestran
    en la página de manual de uso, vinculándolas con los contenidos de ayuda
    contextual almacenados en IA_AYUDACONTEXTUAL.

    Attributes:
        ID_MANUAL (int): Identificador único de la entrada de manual.
        C_AYUDA (str): Código de la ayuda contextual asociada (ej: 'h_manual', 'h_integracion').
                       Debe existir en IA_AYUDACONTEXTUAL.C_AYUDA.
        D_TITULO (str): Título que se muestra en la interfaz (ej: 'Guía rápida de uso').
        T_DESCRIPCION (str): Descripción adicional opcional del contenido.
        L_COLAPSADO (int): 1 = panel colapsado por defecto, 0 = expandido.
        C_ICONO (str): Clase CSS del icono a mostrar (opcional, ej: 'bi-book').
        N_ORDVISU (int): Orden de visualización (menor número = primero).
        L_ESTADO (int): 1 = activo, 0 = inactivo.

    Ejemplo de uso:
        - Código ayuda: 'h_manual', Título: 'Guía rápida de uso', Orden: 1
        - Código ayuda: 'h_integracion', Título: 'Guía rápida de integración', Orden: 2
    """
    __tablename__ = 'IA_MANUALUSO'

    ID_MANUAL = Column(Integer, primary_key=True)
    C_AYUDA = Column(String(50), nullable=False)  # Código en IA_AYUDACONTEXTUAL
    D_TITULO = Column(String(255), nullable=False)  # Título visible
    T_DESCRIPCION = Column(Text)  # Descripción adicional
    L_COLAPSADO = Column(Integer, default=1)  # 1=colapsado, 0=expandido
    C_ICONO = Column(String(50))  # Clase CSS del icono (opcional)
    N_ORDVISU = Column(Integer, default=100)  # Orden de visualización
    L_ESTADO = Column(Integer, default=1)  # 1=activo, 0=inactivo

    def __repr__(self):
        return f"<ConfiguracionManualUso {self.C_AYUDA}: {self.D_TITULO}>"

