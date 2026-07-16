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
Módulo de encriptación y validación de plantillas EIPD.

Protege las plantillas HTML contra modificaciones no autorizadas mediante:
- Encriptación AES-256 con clave embebida
- Validación de integridad con SHA256
- Desencriptación solo en memoria
"""

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import hashlib
import os

# ============================================================================
# CLAVES DE ENCRIPTACIÓN - VALORES DE EJEMPLO (NO USAR EN PRODUCCIÓN)
# ============================================================================
# IMPORTANTE: Estos son valores de ejemplo para desarrollo.
# Para compilar el ejecutable de producción, se utilizan los módulos
# compilados con Cython que contienen las claves reales.
#
# Si desea desplegar su propia instancia, genere sus propias claves seguras
# utilizando: os.urandom(12) para el salt y una frase secreta única.
# ============================================================================
SALT_MASTER = b'CAMBIAR_CLAVE_EXPORTACION_SEGURA'  # Cambiar por valor único (12+ bytes)

# Frase secreta para derivación de clave
_FRASE_SECRETA = "CAMBIAR_CLAVE_EXPORTACION_SEGURA"


def generar_clave_fernet(password: str, salt: bytes = SALT_MASTER) -> bytes:
    """
    Genera una clave Fernet válida a partir de una contraseña y salt.

    Args:
        password: Contraseña/frase secreta
        salt: Salt para derivación de clave

    Returns:
        Clave Fernet en formato bytes
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


def obtener_clave_sistema() -> bytes:
    """
    Obtiene la clave de encriptación del sistema.

    En producción, esta clave debería:
    - Estar protegida en el ejecutable compilado
    - Generarse a partir de identificadores del sistema
    - Almacenarse en un módulo compilado con Cython

    Returns:
        Clave Fernet para encriptación/desencriptación
    """
    return generar_clave_fernet(_FRASE_SECRETA)


def encriptar_plantilla(contenido_html: str) -> tuple[bytes, str]:
    """
    Encripta el contenido HTML de una plantilla.

    Args:
        contenido_html: Contenido HTML en texto plano

    Returns:
        Tupla (contenido_encriptado, hash_sha256)
    """
    clave = obtener_clave_sistema()
    cipher = Fernet(clave)

    # Encriptar
    contenido_bytes = contenido_html.encode('utf-8')
    contenido_encriptado = cipher.encrypt(contenido_bytes)

    # Calcular hash para validación de integridad
    hash_sha256 = hashlib.sha256(contenido_bytes).hexdigest()

    return contenido_encriptado, hash_sha256


def desencriptar_plantilla(contenido_encriptado: bytes) -> str:
    """
    Desencripta una plantilla EIPD.

    Args:
        contenido_encriptado: Contenido encriptado en bytes

    Returns:
        Contenido HTML desencriptado

    Raises:
        ValueError: Si la desencriptación falla (plantilla corrupta o manipulada)
    """
    try:
        clave = obtener_clave_sistema()
        cipher = Fernet(clave)

        # Desencriptar
        contenido_bytes = cipher.decrypt(contenido_encriptado)
        contenido_html = contenido_bytes.decode('utf-8')

        return contenido_html
    except Exception as e:
        raise ValueError(f"Error al desencriptar plantilla: {e}")


def validar_integridad(contenido_html: str, hash_esperado: str) -> bool:
    """
    Valida la integridad del contenido desencriptado.

    Args:
        contenido_html: Contenido HTML desencriptado
        hash_esperado: Hash SHA256 esperado

    Returns:
        True si el hash coincide, False en caso contrario
    """
    hash_calculado = hashlib.sha256(contenido_html.encode('utf-8')).hexdigest()
    return hash_calculado == hash_esperado


def cargar_plantilla_segura(ruta_plantilla: str) -> str:
    """
    Carga y desencripta una plantilla EIPD de forma segura.

    Args:
        ruta_plantilla: Ruta al archivo .eipd encriptado

    Returns:
        Contenido HTML desencriptado y validado

    Raises:
        FileNotFoundError: Si no se encuentra la plantilla
        ValueError: Si la plantilla está corrupta o ha sido manipulada
    """
    if not os.path.exists(ruta_plantilla):
        raise FileNotFoundError(f"Plantilla no encontrada: {ruta_plantilla}")

    # Leer archivo encriptado
    with open(ruta_plantilla, 'rb') as f:
        contenido_encriptado = f.read()

    # Desencriptar
    try:
        contenido_html = desencriptar_plantilla(contenido_encriptado)
        return contenido_html
    except Exception as e:
        raise ValueError(f"Plantilla corrupta o manipulada: {e}")


# ============================================================================
# SCRIPT DE UTILIDAD PARA ENCRIPTAR PLANTILLAS (uso interno)
# ============================================================================

def encriptar_archivo_plantilla(ruta_html: str, ruta_salida: str = None):
    """
    Utilidad para encriptar un archivo HTML en formato .eipd

    USO (solo para administradores):
    >>> from eipd_crypto import encriptar_archivo_plantilla
    >>> encriptar_archivo_plantilla('plantillas/eipd_sec1.html', 'plantillas/eipd_sec1.eipd')
    
    Returns:
        ruta_salida: Ruta del archivo encriptado generado
    """
    if ruta_salida is None:
        ruta_salida = ruta_html.replace('.html', '.eipd')

    # Leer HTML original
    with open(ruta_html, 'r', encoding='utf-8') as f:
        contenido_html = f.read()

    # Encriptar
    contenido_encriptado, hash_sha256 = encriptar_plantilla(contenido_html)

    # Guardar archivo encriptado
    with open(ruta_salida, 'wb') as f:
        f.write(contenido_encriptado)

    # Guardar hash en archivo .sha256 para verificación futura
    with open(ruta_salida + '.sha256', 'w') as f:
        f.write(hash_sha256)

    return ruta_salida


if __name__ == "__main__":
    # Utilidad de encriptación de plantillas EIPD
    # Uso: python eipd_crypto.py
    # Descomenta la línea siguiente para encriptar una plantilla:
    # encriptar_archivo_plantilla('plantillas/eipd_sec1.html')
    pass
