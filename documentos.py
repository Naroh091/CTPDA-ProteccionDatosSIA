
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
Módulo para la gestión de documentos EIPD e Informes de Viabilidad.

Este módulo implementa la lógica para:
- Inicializar documentos al crear proyectos
- Obtener documentos disponibles según fase
- Gestionar la estructura jerárquica de campos
- Autoguardar contenido de campos
- Copiar datos desde elementos ADI automáticamente
- Generar documentos desde plantillas encriptadas

IMPORTANTE: Todos los IDs se generan con incrementos de 100, empezando por 110.
"""

import sys
from sqlalchemy import func, and_, or_
from models import (
    Session, ConfiguracionDocumento, DatosDocumento, ConfiguracionDatoDocumento,
    DatosElementoDocumento, RelacionDocumentoElemento, DatosElementosAdi,
    ValoresDato, TiposDato, ConfiguracionFase, Inicio, DatosRiesgo, Riesgo,
    ConfiguracionCriticidad, DatosControl, Control, Perfil, GrupoControl,
    ConfiguracionRiesgoGlobal, DatosRequisito, ConfiguracionRequisito,
    ConfiguracionEstadoRequisito
)
import unicodedata
import re
import config


def limpiar_nombre_archivo(texto):
    """
    Limpia un texto para usarlo como nombre de archivo en Windows.

    Elimina o reemplaza:
    - Tildes y caracteres diacríticos
    - Espacios (los convierte a guión bajo)
    - Caracteres especiales problemáticos: < > : " / \\ | ? * . , ;
    - Mantiene solo letras, números, guiones y guiones bajos

    Args:
        texto (str): Texto a limpiar

    Returns:
        str: Texto limpio para usar como nombre de archivo
    """
    if not texto:
        return ""

    # 1. Normalizar Unicode para separar caracteres base de diacríticos
    texto_nfd = unicodedata.normalize('NFD', texto)

    # 2. Eliminar diacríticos (marcas de acento)
    texto_sin_tildes = ''.join(
        c for c in texto_nfd
        if unicodedata.category(c) != 'Mn'  # Mn = Nonspacing_Mark (diacríticos)
    )

    # 3. Reemplazar espacios por guiones bajos
    texto_limpio = texto_sin_tildes.replace(' ', '_')

    # 4. Eliminar caracteres problemáticos para Windows
    # Mantener solo: letras, números, guión (-), guión bajo (_)
    texto_limpio = re.sub(r'[^a-zA-Z0-9_-]', '', texto_limpio)

    # 5. Eliminar guiones/guiones bajos múltiples consecutivos
    texto_limpio = re.sub(r'[-_]+', '_', texto_limpio)

    # 6. Eliminar guiones/guiones bajos al inicio y final
    texto_limpio = texto_limpio.strip('_-')

    # 7. Limitar longitud (máximo 50 caracteres para dejar espacio al resto del nombre)
    if len(texto_limpio) > 50:
        texto_limpio = texto_limpio[:50]

    return texto_limpio


def inicializar_documentos_proyecto(session, id_sistema):
    """
    Crea los registros de documentos para un proyecto nuevo.

    Se ejecuta automáticamente al crear un nuevo proyecto y genera:
    - Un registro en IA_DATDOCS por cada tipo de documento configurado
    - Registros en IA_DATELEMDOCS para cada campo del documento
    - Estado inicial: "Pendiente Redacción"

    IMPORTANTE: Los IDs se generan con incrementos de 100, empezando por 110.

    Args:
        session: Sesión de SQLAlchemy activa
        id_sistema (int): ID del sistema/proyecto recién creado

    Returns:
        int: Número de documentos inicializados

    Raises:
        Exception: Si hay error en la creación de registros
    """
    try:

        # Obtener todas las configuraciones de documentos
        configs_docs = session.query(ConfiguracionDocumento).all()

        if not configs_docs:
            return 0

        documentos_creados = 0

        # Obtener el máximo ID actual en IA_DATDOCS
        max_id_datdocs = session.query(func.max(DatosDocumento.ID_DATDOCS)).scalar()
        next_id_datdocs = 110 if max_id_datdocs is None else max_id_datdocs + 100

        # Obtener el máximo ID actual en IA_DATELEMDOCS
        max_id_datelemdocs = session.query(func.max(DatosElementoDocumento.ID_DATELEMDOCS)).scalar()
        next_id_datelemdocs = 110 if max_id_datelemdocs is None else max_id_datelemdocs + 100

        for config in configs_docs:

            # Verificar que el documento tiene configurada la situación inicial
            if not config.V_SITINICIAL:
                continue

            # Crear el documento principal usando V_SITINICIAL de la configuración
            # ⚠️ L_NECESARIO se inicializa en 0 y se activará al completar ADI
            nuevo_doc = DatosDocumento(
                ID_DATDOCS=next_id_datdocs,
                SIST_ID_SISTEMA=id_sistema,
                DD_ID_CFGDOCS=config.ID_CFGDOCS,
                V_SITUACION=config.V_SITINICIAL,  # ✅ Usar situación inicial configurada
                T_OBSERVACIONES="",
                L_NECESARIO=0  # 👈 Inicia desactivado hasta completar ADI
            )
            session.add(nuevo_doc)
            documentos_creados += 1

            # Crear los elementos del documento
            campos = session.query(ConfiguracionDatoDocumento).filter(
                ConfiguracionDatoDocumento.DD_ID_CFGDOCS == config.ID_CFGDOCS
            ).order_by(ConfiguracionDatoDocumento.N_ORDEN).all()

            campos_creados = 0
            for campo in campos:
                nuevo_elemento = DatosElementoDocumento(
                    ID_DATELEMDOCS=next_id_datelemdocs,
                    SIST_ID_SISTEMA=id_sistema,
                    DED_ID_DATDOCS=next_id_datdocs,
                    DED_ID_CFGDATDOCS=campo.ID_CFGDATDOCS,
                    T_DATO=""
                )
                session.add(nuevo_elemento)
                next_id_datelemdocs += 100
                campos_creados += 1


            # Incrementar para el siguiente documento
            next_id_datdocs += 100


        return documentos_creados

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise


def obtener_documentos_disponibles(id_sistema):
    """
    Obtiene los documentos disponibles según la fase actual del proyecto.

    Filtra documentos cuya fase visual (N_FASEVISUAL) sea igual o anterior
    a la fase actual del proyecto.

    Args:
        id_sistema (int): ID del sistema

    Returns:
        list[dict]: Lista de diccionarios con información de cada documento:
            - id_datdocs: ID del registro de datos del documento
            - id_cfgdocs: ID de la configuración del documento
            - descripcion: Descripción del documento
            - instrucciones: Instrucciones generales
            - tipo_documento: Texto del tipo (EIPD, IV, etc.)
            - situacion: Estado actual del documento
            - situacion_clase: Clase CSS según estado
            - observaciones: Observaciones del documento
            - fase_evaluacion: Descripción de la fase de evaluación
    """
    session = Session()
    try:

        # Obtener fase actual
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto or not proyecto.N_FASE:
            return []

        fase_actual = session.query(ConfiguracionFase).filter_by(ID_FASE=proyecto.N_FASE).first()
        if not fase_actual:
            return []


        # Obtener documentos cuya fase visual sea <= fase actual
        documentos = session.query(
            DatosDocumento,
            ConfiguracionDocumento
        ).join(
            ConfiguracionDocumento,
            DatosDocumento.DD_ID_CFGDOCS == ConfiguracionDocumento.ID_CFGDOCS
        ).outerjoin(
            ConfiguracionFase,
            ConfiguracionDocumento.N_FASEVISUAL == ConfiguracionFase.ID_FASE
        ).filter(
            DatosDocumento.SIST_ID_SISTEMA == id_sistema,
            or_(
                ConfiguracionDocumento.N_FASEVISUAL.is_(None),
                ConfiguracionFase.N_ORDEN <= fase_actual.N_ORDEN
            )
        ).order_by(
            ConfiguracionDocumento.N_ORDVISU
        ).all()

        resultado = []
        for dat_doc, cfg_doc in documentos:
            # Obtener situación
            situacion = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == dat_doc.V_SITUACION
            ).first()

            # Obtener tipo de documento
            tipo_doc = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == cfg_doc.V_TIPODOC
            ).first()

            # Obtener fase de evaluación
            fase_eval = session.query(ConfiguracionFase).filter(
                ConfiguracionFase.ID_FASE == cfg_doc.N_FASEVAL
            ).first()

            # Determinar clase CSS según situación
            situacion_clase = 'text-secondary'
            if situacion:
                if situacion.C_VALOR == 1:  # No necesario
                    situacion_clase = 'text-muted'
                elif situacion.C_VALOR == 2:  # Pendiente Redacción
                    situacion_clase = 'text-warning'
                elif situacion.C_VALOR == 3:  # Pendiente Revisión
                    situacion_clase = 'text-info'
                elif situacion.C_VALOR == 4:  # Finalizado
                    situacion_clase = 'text-success'

            resultado.append({
                'id_datdocs': dat_doc.ID_DATDOCS,
                'id_cfgdocs': cfg_doc.ID_CFGDOCS,
                'descripcion': cfg_doc.T_DESC,
                'instrucciones': cfg_doc.T_INSTRUC,
                'tipo_documento': tipo_doc.D_VALOR if tipo_doc else 'Desconocido',
                'situacion': situacion.D_VALOR if situacion else 'Desconocida',
                'situacion_clase': situacion_clase,
                'observaciones': dat_doc.T_OBSERVACIONES or '',
                'fase_evaluacion': fase_eval.D_FASE if fase_eval else 'No definida'
            })

        return resultado

    except Exception as e:
        import traceback
        traceback.print_exc()
        return []
    finally:
        session.close()

def obtener_estructura_documento(id_datdocs):
    """
    Obtiene la estructura completa de un documento con sus campos organizados jerárquicamente.

    Construye un árbol de campos siguiendo la relación de anidamiento (N_ANID y DD_ID_CFGDD_SUP).
    Para cada campo, obtiene:
    - Su configuración (descripción, instrucciones, orden, etc.)
    - El valor guardado por el usuario
    - Referencias automáticas a elementos ADI si están configuradas
    - Botones de copia individual solo si hay datos disponibles

    Args:
        id_datdocs (int): ID del documento

    Returns:
        dict: Estructura del documento con la siguiente información:
            - id_datdocs: ID del documento
            - descripcion: Descripción del documento
            - instrucciones: Instrucciones generales
            - situacion: Estado actual
            - campos: Lista jerárquica de campos (cada campo tiene 'hijos')
        None si el documento no existe o hay error
    """
    session = Session()
    try:

        # Obtener el documento
        documento = session.query(DatosDocumento).filter_by(ID_DATDOCS=id_datdocs).first()
        if not documento:
            return None

        # Obtener configuración del documento
        config_doc = session.query(ConfiguracionDocumento).filter_by(
            ID_CFGDOCS=documento.DD_ID_CFGDOCS
        ).first()

        # Obtener situación
        situacion = session.query(ValoresDato).filter(
            ValoresDato.ID_VALDAT == documento.V_SITUACION
        ).first()

        # Obtener todos los campos de configuración para este documento
        campos_config = session.query(ConfiguracionDatoDocumento).filter(
            ConfiguracionDatoDocumento.DD_ID_CFGDOCS == documento.DD_ID_CFGDOCS
        ).order_by(
            ConfiguracionDatoDocumento.N_ANID,
            ConfiguracionDatoDocumento.N_ORDEN
        ).all()


        # Obtener los datos guardados
        datos_guardados = session.query(DatosElementoDocumento).filter(
            DatosElementoDocumento.DED_ID_DATDOCS == id_datdocs
        ).all()

        datos_dict = {d.DED_ID_CFGDATDOCS: d.T_DATO for d in datos_guardados}
        datos_id_dict = {d.DED_ID_CFGDATDOCS: d.ID_DATELEMDOCS for d in datos_guardados}

        # Construir estructura jerárquica
        campos_por_nivel = {}
        for campo in campos_config:
            nivel = campo.N_ANID or 0
            if nivel not in campos_por_nivel:
                campos_por_nivel[nivel] = []

            # 🆕 Obtener TODAS las relaciones automáticas para este campo
            relaciones = session.query(RelacionDocumentoElemento).filter(
                RelacionDocumentoElemento.RDE_ID_CFGDATDOCS == campo.ID_CFGDATDOCS,
                RelacionDocumentoElemento.L_AUTO == 1,
                RelacionDocumentoElemento.RDE_ID_SUBELEM.isnot(None)
            ).all()

            # 🆕 Construir lista de botones de copia SOLO SI HAY DATOS DISPONIBLES
            botones_copia = []
            for relacion in relaciones:
                # 🔧 CORRECCIÓN: Verificar si existe ALGUNA iteración con datos en el elemento ADI
                dato_adi = session.query(DatosElementosAdi).filter(
                    DatosElementosAdi.SIST_ID_SISTEMA == documento.SIST_ID_SISTEMA,
                    DatosElementosAdi.SUB_IDSUBELEM == relacion.RDE_ID_SUBELEM,
                    DatosElementosAdi.T_DESCRIPCION.isnot(None),
                    DatosElementosAdi.T_DESCRIPCION != ''
                ).first()  # Solo verificar si existe AL MENOS una iteración con datos

                # ✅ SOLO añadir botón si hay datos disponibles y no están vacíos
                if dato_adi and dato_adi.T_DESCRIPCION.strip():
                    # Obtener información del subelemento y elemento
                    from models import SubElementosAdi, ElementosAdi
                    subelem_info = session.query(SubElementosAdi, ElementosAdi).join(
                        ElementosAdi
                    ).filter(
                        SubElementosAdi.ID_SUBELEM == relacion.RDE_ID_SUBELEM
                    ).first()

                    if subelem_info:
                        subelem, elemento = subelem_info
                        botones_copia.append({
                            'codigo': f"ED {elemento.C_ELEMENTO}.{subelem.N_SUBORD}",
                            'id_subelem': subelem.ID_SUBELEM
                        })

            # Mantener compatibilidad con referencia_auto existente (primera relación con datos)
            referencia_auto = None
            codigo_referencia = None
            if botones_copia:  # Solo si hay botones (significa que hay datos)
                # Usar el primer botón disponible
                primer_boton = botones_copia[0]
                # Buscar el dato correspondiente con TODAS las iteraciones
                for relacion in relaciones:
                    # 🔧 CORRECCIÓN: Obtener TODAS las iteraciones
                    datos_adi = session.query(DatosElementosAdi).filter(
                        DatosElementosAdi.SIST_ID_SISTEMA == documento.SIST_ID_SISTEMA,
                        DatosElementosAdi.SUB_IDSUBELEM == relacion.RDE_ID_SUBELEM
                    ).order_by(DatosElementosAdi.N_ITERACION).all()

                    if datos_adi:
                        # Concatenar todas las iteraciones con línea en blanco
                        valores_iteraciones = [d.T_DESCRIPCION for d in datos_adi if d.T_DESCRIPCION and d.T_DESCRIPCION.strip()]
                        if valores_iteraciones:
                            referencia_auto = "\n\n".join(valores_iteraciones)
                            codigo_referencia = primer_boton['codigo']
                            break

            # 🆕 Obtener información del campo superior (padre) si existe
            info_padre = None
            if campo.DD_ID_CFGDD_SUP:
                campo_padre = session.query(ConfiguracionDatoDocumento).filter(
                    ConfiguracionDatoDocumento.ID_CFGDATDOCS == campo.DD_ID_CFGDD_SUP
                ).first()
                if campo_padre:
                    info_padre = {
                        'id_cfgdatdocs': campo_padre.ID_CFGDATDOCS,
                        'descripcion': campo_padre.D_DESC,
                        'n_valores_check': campo_padre.N_VALORES_CHECK
                    }

            campo_info = {
                'id_cfgdatdocs': campo.ID_CFGDATDOCS,
                'id_datelemdocs': datos_id_dict.get(campo.ID_CFGDATDOCS),
                'id_superior': campo.DD_ID_CFGDD_SUP,
                'codigo': campo.C_DATO,
                'descripcion': campo.D_DESC,
                'instrucciones': campo.T_INSTR,
                'texto_antes': campo.T_EXPLANT,
                'texto_despues': campo.T_EXPLPOST,
                'orden': campo.N_ORDEN,
                'obligatorio': campo.L_OBLIG == 1,
                'nivel': nivel,
                'editable': campo.L_EDITABLE == 1,
                'valor': datos_dict.get(campo.ID_CFGDATDOCS, ''),
                'referencia_auto': referencia_auto,
                'codigo_referencia': codigo_referencia,
                'botones_copia': botones_copia,  # 🆕 Lista de botones (vacía si no hay datos)
                'l_check': campo.L_CHECK,  # 🆕 Indicador de checkbox
                'n_valores_check': campo.N_VALORES_CHECK,  # 🆕 Número de valores check
                'info_padre': info_padre,  # 🆕 Información del elemento superior
                'hijos': []
            }

            campos_por_nivel[nivel].append(campo_info)

        # Organizar jerárquicamente
        def construir_arbol(nivel=0, id_padre=None):
            if nivel not in campos_por_nivel:
                return []

            resultado = []
            for campo in campos_por_nivel[nivel]:
                if campo['id_superior'] == id_padre:
                    campo['hijos'] = construir_arbol(nivel + 1, campo['id_cfgdatdocs'])

                    # 🆕 Detectar si todos los hijos son checks con descripciones de 1 carácter
                    if campo['hijos']:
                        todos_checks_cortos = all(
                            hijo.get('l_check') == 1 and
                            hijo.get('descripcion') and
                            len(hijo['descripcion'].strip()) == 1 and
                            hijo['descripcion'].strip().isalnum()
                            for hijo in campo['hijos']
                        )
                        # Marcar el padre si todos sus hijos son checks de 1 carácter
                        campo['checks_inline'] = todos_checks_cortos
                    else:
                        campo['checks_inline'] = False

                    resultado.append(campo)
            return resultado

        estructura = construir_arbol(0, None)


        return {
            'id_datdocs': documento.ID_DATDOCS,
            'id_sistema': documento.SIST_ID_SISTEMA,
            'descripcion': config_doc.T_DESC if config_doc else 'Sin descripción',
            'instrucciones': config_doc.T_INSTRUC if config_doc else '',
            'situacion': situacion.D_VALOR if situacion else 'Desconocida',
            'observaciones': documento.T_OBSERVACIONES or '',
            'campos': estructura
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None
    finally:
        session.close()

def guardar_campo_documento(id_datelemdocs, valor):
    """
    Guarda el valor de un campo específico del documento (autoguardado).

    Args:
        id_datelemdocs (int): ID del registro en IA_DATELEMDOCS
        valor (str): Nuevo valor del campo

    Returns:
        dict: {"success": bool, "mensaje": str}
    """
    session = Session()
    try:
        elemento = session.query(DatosElementoDocumento).filter_by(
            ID_DATELEMDOCS=id_datelemdocs
        ).first()

        if not elemento:
            return {"success": False, "mensaje": "Campo no encontrado"}

        elemento.T_DATO = valor
        session.commit()

        return {"success": True, "mensaje": "Campo guardado correctamente"}

    except Exception as e:
        session.rollback()
        return {"success": False, "mensaje": str(e)}
    finally:
        session.close()


def actualizar_situacion_documento(id_datdocs, nueva_situacion):
    """
    Actualiza el estado de un documento.

    Args:
        id_datdocs (int): ID del documento
        nueva_situacion (int): ID del nuevo valor de situación (IA_VALDAT)

    Returns:
        dict: {"success": bool, "mensaje": str}
    """
    session = Session()
    try:
        documento = session.query(DatosDocumento).filter_by(
            ID_DATDOCS=id_datdocs
        ).first()

        if not documento:
            return {"success": False, "mensaje": "Documento no encontrado"}

        documento.V_SITUACION = nueva_situacion
        session.commit()

        return {"success": True, "mensaje": "Situación actualizada correctamente"}

    except Exception as e:
        session.rollback()
        return {"success": False, "mensaje": str(e)}
    finally:
        session.close()


def copiar_datos_elementos_adi(id_datdocs):
    """
    Copia automáticamente los datos de elementos ADI a campos del documento
    que tengan configurada la relación automática (L_AUTO = 1).

    Si hay múltiples elementos ADI relacionados con el mismo campo de destino,
    se concatenan todos los valores separados por líneas en blanco.

    Args:
        id_datdocs (int): ID del documento

    Returns:
        dict: {"success": bool, "campos_copiados": int, "mensaje": str}
    """
    session = Session()
    try:
        documento = session.query(DatosDocumento).filter_by(
            ID_DATDOCS=id_datdocs
        ).first()

        if not documento:
            return {"success": False, "campos_copiados": 0, "mensaje": "Documento no encontrado"}

        relaciones = session.query(RelacionDocumentoElemento).join(
            ConfiguracionDatoDocumento,
            RelacionDocumentoElemento.RDE_ID_CFGDATDOCS == ConfiguracionDatoDocumento.ID_CFGDATDOCS
        ).filter(
            ConfiguracionDatoDocumento.DD_ID_CFGDOCS == documento.DD_ID_CFGDOCS,
            RelacionDocumentoElemento.L_AUTO == 1,
            RelacionDocumentoElemento.RDE_ID_SUBELEM.isnot(None)
        ).all()

        if not relaciones:
            return {
                "success": True,
                "campos_copiados": 0,
                "mensaje": "No hay campos configurados para copia automática"
            }

        campos_valores = {}

        for relacion in relaciones:
            datos_adi = session.query(DatosElementosAdi).filter(
                DatosElementosAdi.SIST_ID_SISTEMA == documento.SIST_ID_SISTEMA,
                DatosElementosAdi.SUB_IDSUBELEM == relacion.RDE_ID_SUBELEM
            ).order_by(DatosElementosAdi.N_ITERACION).all()

            if datos_adi:
                id_campo = relacion.RDE_ID_CFGDATDOCS
                if id_campo not in campos_valores:
                    campos_valores[id_campo] = []

                for dato_adi in datos_adi:
                    if dato_adi.T_DESCRIPCION:
                        campos_valores[id_campo].append(dato_adi.T_DESCRIPCION)

        campos_copiados = 0
        for id_campo, valores in campos_valores.items():
            elemento_doc = session.query(DatosElementoDocumento).filter(
                DatosElementoDocumento.DED_ID_DATDOCS == id_datdocs,
                DatosElementoDocumento.DED_ID_CFGDATDOCS == id_campo
            ).first()

            if elemento_doc:
                valor_concatenado = "\n\n".join(valores)
                elemento_doc.T_DATO = valor_concatenado
                campos_copiados += 1

        session.commit()

        if campos_copiados > 0:
            mensaje = f"Se copiaron {campos_copiados} campos automáticamente"
        else:
            mensaje = "No hay datos disponibles para copiar desde Elementos de Descripción"

        return {
            "success": True,
            "campos_copiados": campos_copiados,
            "mensaje": mensaje
        }

    except Exception as e:
        session.rollback()
        return {"success": False, "campos_copiados": 0, "mensaje": str(e)}
    finally:
        session.close()


def copiar_dato_individual(id_datelemdocs, id_subelem):
    """
    Copia automáticamente el dato de un elemento ADI específico a un campo del documento.

    Args:
        id_datelemdocs (int): ID del registro en IA_DATELEMDOCS
        id_subelem (int): ID del subelemento ADI específico a copiar

    Returns:
        dict: {"success": bool, "valor_copiado": str, "mensaje": str}
    """
    session = Session()
    try:
        elemento_doc = session.query(DatosElementoDocumento).filter_by(
            ID_DATELEMDOCS=id_datelemdocs
        ).first()

        if not elemento_doc:
            return {"success": False, "valor_copiado": "", "mensaje": "Campo no encontrado"}

        documento = session.query(DatosDocumento).filter_by(
            ID_DATDOCS=elemento_doc.DED_ID_DATDOCS
        ).first()

        if not documento:
            return {"success": False, "valor_copiado": "", "mensaje": "Documento no encontrado"}

        relacion = session.query(RelacionDocumentoElemento).join(
            ConfiguracionDatoDocumento,
            RelacionDocumentoElemento.RDE_ID_CFGDATDOCS == ConfiguracionDatoDocumento.ID_CFGDATDOCS
        ).filter(
            ConfiguracionDatoDocumento.ID_CFGDATDOCS == elemento_doc.DED_ID_CFGDATDOCS,
            RelacionDocumentoElemento.L_AUTO == 1,
            RelacionDocumentoElemento.RDE_ID_SUBELEM == id_subelem
        ).first()

        if not relacion:
            return {
                "success": False,
                "valor_copiado": "",
                "mensaje": "No hay relación automática configurada para este campo y subelemento"
            }

        datos_adi = session.query(DatosElementosAdi).filter(
            DatosElementosAdi.SIST_ID_SISTEMA == documento.SIST_ID_SISTEMA,
            DatosElementosAdi.SUB_IDSUBELEM == id_subelem
        ).order_by(DatosElementosAdi.N_ITERACION).all()

        if not datos_adi:
            return {
                "success": False,
                "valor_copiado": "",
                "mensaje": "No hay datos disponibles en el elemento de descripción seleccionado"
            }

        valores_iteraciones = []
        for dato_adi in datos_adi:
            if dato_adi.T_DESCRIPCION:
                valores_iteraciones.append(dato_adi.T_DESCRIPCION)

        if not valores_iteraciones:
            return {
                "success": False,
                "valor_copiado": "",
                "mensaje": "No hay datos disponibles en el elemento de descripción seleccionado"
            }

        valor_concatenado = "\n\n".join(valores_iteraciones)
        elemento_doc.T_DATO = valor_concatenado
        session.commit()

        return {
            "success": True,
            "valor_copiado": valor_concatenado,
            "mensaje": f"Dato copiado correctamente ({len(valores_iteraciones)} iteración(es))"
        }

    except Exception as e:
        session.rollback()
        return {"success": False, "valor_copiado": "", "mensaje": str(e)}
    finally:
        session.close()


def obtener_estados_documento(tipo_doc_codigo=None):
    """
    Obtiene todos los estados posibles para documentos según el tipo.

    Args:
        tipo_doc_codigo (str, optional): Código del tipo de documento (ej: 'EIPD', 'IV').
                                         Si se proporciona, devuelve solo los estados de ese tipo (SITDOC_XXX).
                                         Si es None, devuelve todos los estados SITDOC genéricos.

    Returns:
        list[dict]: Lista de estados con id, codigo y descripcion
    """
    session = Session()
    try:
        # Construir el código del tipo de dato según el tipo de documento
        if tipo_doc_codigo:
            codigo_tipdat = f'SITDOC_{tipo_doc_codigo}'
        else:
            codigo_tipdat = 'SITDOC'

        tipo_situacion = session.query(TiposDato).filter(
            TiposDato.C_TIPDAT == codigo_tipdat
        ).first()

        if not tipo_situacion:
            return []

        estados = session.query(ValoresDato).filter(
            ValoresDato.TIDA_ID_TIPDAT == tipo_situacion.ID_TIPDAT
        ).order_by(ValoresDato.N_ORDEN).all()


        return [
            {
                'id': estado.ID_VALDAT,
                'codigo': estado.C_VALOR,
                'descripcion': estado.D_VALOR
            }
            for estado in estados
        ]

    except Exception as e:
        return []
    finally:
        session.close()


def obtener_codigo_tipo_documento(id_datdocs):
    """
    Obtiene el código del tipo de documento (ej: 'EIPD', 'IV') a partir del ID_DATDOCS.

    Args:
        id_datdocs (int): ID del documento

    Returns:
        str: Código del tipo de documento (ej: 'EIPD', 'IV') o None si no se encuentra
    """
    session = Session()
    try:

        # Obtener el documento
        documento = session.query(DatosDocumento).filter(
            DatosDocumento.ID_DATDOCS == id_datdocs
        ).first()

        if not documento:
            return None


        # Obtener la configuración del documento
        config_doc = session.query(ConfiguracionDocumento).filter(
            ConfiguracionDocumento.ID_CFGDOCS == documento.DD_ID_CFGDOCS
        ).first()

        if not config_doc:
            return None


        # Obtener el tipo de documento desde ValoresDato
        tipo_doc = session.query(ValoresDato).filter(
            ValoresDato.ID_VALDAT == config_doc.V_TIPODOC
        ).first()

        if not tipo_doc:
            return None


        if tipo_doc.C_VALOR_TEXT:
            return tipo_doc.C_VALOR_TEXT
        else:
            return None

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None
    finally:
        session.close()


def tiene_relaciones_copia_automatica(id_datdocs):
    """
    Verifica si existen relaciones de copia automática configuradas para un documento.

    Un documento tiene relaciones de copia automática si existe al menos un registro
    en IA_CFGRELDOCEL que esté relacionado con algún campo del tipo de documento.

    Args:
        id_datdocs (int): ID del documento

    Returns:
        bool: True si existen relaciones de copia automática, False en caso contrario
    """
    session = Session()
    try:

        # Obtener el documento
        documento = session.query(DatosDocumento).filter(
            DatosDocumento.ID_DATDOCS == id_datdocs
        ).first()

        if not documento:
            return False


        # Contar las relaciones automáticas para los campos de este tipo de documento
        count = session.query(func.count(RelacionDocumentoElemento.ID_CFGRELDOCEL)).join(
            ConfiguracionDatoDocumento,
            RelacionDocumentoElemento.RDE_ID_CFGDATDOCS == ConfiguracionDatoDocumento.ID_CFGDATDOCS
        ).filter(
            ConfiguracionDatoDocumento.DD_ID_CFGDOCS == documento.DD_ID_CFGDOCS,
            RelacionDocumentoElemento.L_AUTO == 1  # Solo relaciones automáticas
        ).scalar()


        tiene_relaciones = count > 0

        return tiene_relaciones

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def tiene_campos_configurados(id_datdocs):
    """
    Verifica si existen campos configurados en IA_CFGDATDOCS para el tipo de documento.

    Esto determina si el documento tiene estructura de campos editables que requieren
    funcionalidades como desplegar/plegar y guardado automático.

    Args:
        id_datdocs (int): ID del documento

    Returns:
        bool: True si existen campos configurados, False en caso contrario
    """
    session = Session()
    try:

        # Obtener el documento
        documento = session.query(DatosDocumento).filter(
            DatosDocumento.ID_DATDOCS == id_datdocs
        ).first()

        if not documento:
            return False


        # Contar los campos configurados para este tipo de documento
        count = session.query(func.count(ConfiguracionDatoDocumento.ID_CFGDATDOCS)).filter(
            ConfiguracionDatoDocumento.DD_ID_CFGDOCS == documento.DD_ID_CFGDOCS
        ).scalar()


        tiene_campos = count > 0

        return tiene_campos

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def actualizar_documentos_necesarios(session, id_sistema, necesidad_eipd):
    """
    Actualiza el campo L_NECESARIO de los documentos según la evaluación del ADI.

    Esta función se ejecuta después de completar el cuestionario ADI y:
    - Activa (L_NECESARIO=1) todos los documentos NO EIPD
    - Activa (L_NECESARIO=1) los documentos EIPD solo si necesidad_eipd es "NECESARIA"
    - Mantiene desactivados (L_NECESARIO=0) los documentos EIPD si necesidad_eipd no es "NECESARIA"

    Args:
        session: Sesión activa de SQLAlchemy
        id_sistema (int): ID del sistema/proyecto
        necesidad_eipd (str): Resultado de evaluar_necesidad_eipd_lambda
                             ("NECESARIA", "NO NECESARIA", "RECOMENDADA", "PENDIENTE")

    Returns:
        dict: Resumen de la actualización con contadores
            - documentos_eipd_activados: número de docs EIPD activados
            - documentos_eipd_desactivados: número de docs EIPD mantenidos desactivados
            - documentos_no_eipd_activados: número de docs NO EIPD activados
            - total_procesados: total de documentos procesados

    Raises:
        Exception: Si hay error en la actualización
    """
    try:
        #print(f"\n{'='*70}")
        #print(f"📄 ACTUALIZANDO DOCUMENTOS NECESARIOS - Sistema {id_sistema}")
        #print(f"📊 Necesidad EIPD: {necesidad_eipd}")
        #print(f"{'='*70}\n")

        # Contadores para el resumen
        docs_eipd_activados = 0
        docs_eipd_desactivados = 0
        docs_no_eipd_activados = 0

        # Obtener todos los documentos del proyecto con su configuración
        documentos = session.query(
            DatosDocumento,
            ConfiguracionDocumento
        ).join(
            ConfiguracionDocumento,
            DatosDocumento.DD_ID_CFGDOCS == ConfiguracionDocumento.ID_CFGDOCS
        ).filter(
            DatosDocumento.SIST_ID_SISTEMA == id_sistema
        ).all()

        if not documentos:
            return {
                'documentos_eipd_activados': 0,
                'documentos_eipd_desactivados': 0,
                'documentos_no_eipd_activados': 0,
                'total_procesados': 0
            }

        #print(f"📋 Procesando {len(documentos)} documentos...\n")

        for dat_doc, cfg_doc in documentos:
            # Obtener el tipo de documento desde ValoresDato
            tipo_doc = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == cfg_doc.V_TIPODOC
            ).first()

            if not tipo_doc:
        #        print(f"⚠️ Documento {cfg_doc.T_DESC}: No se encontró tipo de documento")
                continue

            tipo_codigo = tipo_doc.C_VALOR_TEXT if tipo_doc.C_VALOR_TEXT else ""

            # Determinar si es EIPD
            es_eipd = tipo_codigo == "EIPD"

            # Lógica de activación
            if es_eipd:
                # Para documentos EIPD: activar solo si es NECESARIA
                if necesidad_eipd == "NECESARIA":
                    dat_doc.L_NECESARIO = 1
                    docs_eipd_activados += 1
        #           print(f"   ✅ EIPD '{cfg_doc.T_DESC}': ACTIVADO (EIPD NECESARIA)")
                else:
                    dat_doc.L_NECESARIO = 0
                    docs_eipd_desactivados += 1
        #            print(f"   ⭕ EIPD '{cfg_doc.T_DESC}': DESACTIVADO (EIPD {necesidad_eipd})")
            else:
                # Para documentos NO EIPD: activar siempre
                dat_doc.L_NECESARIO = 1
                docs_no_eipd_activados += 1
        #        print(f"   ✅ '{cfg_doc.T_DESC}' (tipo: {tipo_codigo}): ACTIVADO")

        # Resumen de la operación
        total_procesados = docs_eipd_activados + docs_eipd_desactivados + docs_no_eipd_activados

        #print(f"\n{'='*70}")
        #print(f"📊 RESUMEN DE ACTUALIZACIÓN:")
        #print(f"   ✅ Documentos EIPD activados: {docs_eipd_activados}")
        #print(f"   ⭕ Documentos EIPD desactivados: {docs_eipd_desactivados}")
        #print(f"   ✅ Documentos NO EIPD activados: {docs_no_eipd_activados}")
        #print(f"   📝 Total procesados: {total_procesados}")
        #print(f"{'='*70}\n")

        return {
            'documentos_eipd_activados': docs_eipd_activados,
            'documentos_eipd_desactivados': docs_eipd_desactivados,
            'documentos_no_eipd_activados': docs_no_eipd_activados,
            'total_procesados': total_procesados
        }

    except Exception as e:
        #print(f"❌ Error al actualizar documentos necesarios: {e}")
        import traceback
        traceback.print_exc()
        raise


def calcular_variables_adicionales_eipd(id_sistema):
    """
    Calcula variables adicionales específicas para documentos EIPD.

    Variables generadas:
    - {{PERFIL}}: Descripción del perfil de supervisión
    - {{NUM_CONTROLES}}: Número de controles activos que aplican
    - {{MADUREZ_MEDIA}}: Media aritmética de la madurez de los controles
    - {{NUM_GRUPOS_CONTROL}}: Número de grupos de controles activados y que aplican
    - {{NUM_RIESGOS_AUT}}: Número de riesgos activos que aplican y que NO son manuales
    - {{NUM_RIESGOS}}: Número de riesgos activos que aplican (incluyendo manuales)
    - {{TIPO_ADQUISICION}}: Descripción de la respuesta a la pregunta P1 del ADI

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        dict: Diccionario con las variables adicionales
    """
    from controllers import obtener_perfil_por_puntuacion, calcular_puntuacion_adi
    import re
    import unicodedata

    session = Session()
    try:

        # ========== 1. PERFIL DE SUPERVISIÓN ==========
        # Calcular puntuación ADI
        puntos_adi = calcular_puntuacion_adi(id_sistema)

        perfil = None
        perfil_obj = None

        if puntos_adi is not None:
            # Obtener perfil correspondiente
            perfil_obj = obtener_perfil_por_puntuacion(session, puntos_adi)
            if perfil_obj and perfil_obj.D_PERFIL:
                perfil = perfil_obj.D_PERFIL
            else:
                perfil = "No disponible"
        else:
            perfil = "No calculado"

        # ========== 1.1. VARIABLES DE CHECKBOX PARA CADA PERFIL ==========
        # Obtener todos los perfiles de la tabla IA_PERFIL
        todos_perfiles = session.query(Perfil).order_by(Perfil.N_PTOSMIN).all()


        # Para cada perfil, crear una variable ES_XXX
        variables_perfiles = {}
        for p in todos_perfiles:
            # Normalizar el nombre del perfil para la variable
            # 1. Convertir a mayúsculas
            nombre_normalizado = p.D_PERFIL.upper()

            # 2. Eliminar acentos usando unicodedata (método robusto)
            nombre_normalizado = ''.join(
                c for c in unicodedata.normalize('NFD', nombre_normalizado)
                if unicodedata.category(c) != 'Mn'
            )

            # 3. Eliminar espacios y caracteres especiales, reemplazar por guión bajo
            nombre_normalizado = re.sub(r'[^A-Z0-9]', '_', nombre_normalizado)

            # 4. Eliminar guiones bajos múltiples
            nombre_normalizado = re.sub(r'_+', '_', nombre_normalizado)

            # 5. Eliminar guiones bajos al inicio y final
            nombre_normalizado = nombre_normalizado.strip('_')

            # Crear variable ES_XXX
            variable_nombre = f"ES_{nombre_normalizado}"

            # Asignar "X" si es el perfil actual, "" si no (igual que los demás checkboxes)
            if perfil_obj and perfil_obj.ID_PERFIL == p.ID_PERFIL:
                variables_perfiles[variable_nombre] = "X"
            else:
                variables_perfiles[variable_nombre] = ""

        # ========== 2. NÚMERO DE CONTROLES ACTIVOS Y APLICABLES ==========
        controles_activos = session.query(DatosControl).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema,
            DatosControl.L_ACTIVA == 1,
            DatosControl.L_APLICA == 1
        ).all()

        num_controles = len(controles_activos)

        # ========== 2.1. NÚMERO DE GRUPOS DE CONTROLES ACTIVADOS Y QUE APLICAN ==========
        num_grupos_control = session.query(GrupoControl.ID_GRUCONTROL).distinct()\
            .join(Control, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL)\
            .join(DatosControl, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL)\
            .filter(
                DatosControl.SIST_ID_SISTEMA == id_sistema,
                DatosControl.L_ACTIVA == 1,
                DatosControl.L_APLICA == 1
            )\
            .count()

        # ========== 3. MADUREZ MEDIA DE CONTROLES ==========
        madurez_media = 0.0

        if num_controles > 0:
            suma_madurez = 0.0
            controles_con_madurez = 0

            for control in controles_activos:
                if control.V_MADUREZ:
                    # Obtener el valor numérico de la madurez desde IA_VALDAT
                    valor_madurez = session.query(ValoresDato).filter(
                        ValoresDato.ID_VALDAT == control.V_MADUREZ
                    ).first()

                    if valor_madurez and valor_madurez.C_VALOR is not None:
                        # C_VALOR contiene el valor numérico de la madurez (1-4)
                        madurez_numerica = float(valor_madurez.C_VALOR)
                        suma_madurez += madurez_numerica
                        controles_con_madurez += 1

            # Calcular la media
            if controles_con_madurez > 0:
                madurez_media = suma_madurez / controles_con_madurez
                madurez_media = round(madurez_media, 2)
            else:
                pass
        else:
            pass

        # ========== 4. NÚMERO DE RIESGOS ACTIVOS Y QUE APLICAN ==========
        # NUM_RIESGOS: Total de riesgos activos y que aplican (incluyendo manuales)
        num_riesgos = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1,
            DatosRiesgo.L_APLICA == 1
        ).count()

        # NUM_RIESGOS_AUT: Riesgos activos que aplican y que NO son manuales
        num_riesgos_aut = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1,
            DatosRiesgo.L_APLICA == 1,
            or_(DatosRiesgo.L_MANUAL == 0, DatosRiesgo.L_MANUAL.is_(None))
        ).count()

        # ========== 5. TIPO DE ADQUISICIÓN (P1) - SELECCIÓN MÚLTIPLE ==========
        # Obtener TODAS las descripciones de las respuestas a la pregunta P1
        from models import Pregunta, Respuesta, RespuestasProyecto

        query_p1 = session.query(Respuesta.D_RESPUESTA)\
            .join(RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == Respuesta.ID_RESPUESTA)\
            .join(Pregunta, Pregunta.ID_PREGUNTA == Respuesta.PRE_ID_PREGUNTA)\
            .filter(
                RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                Pregunta.C_PREGUNTA == 'P1'
            )\
            .order_by(Respuesta.C_OPCION)\
            .all()

        if query_p1:
            # Concatenar todas las descripciones con ";"
            descripciones = [row[0] for row in query_p1]
            tipo_adquisicion = ";".join(descripciones)
        else:
            tipo_adquisicion = "No respondida"

        # Generar diccionario de variables
        variables = {
            'PERFIL': perfil,
            'NUM_CONTROLES': str(num_controles),
            'MADUREZ_MEDIA': str(madurez_media),
            'NUM_GRUPOS_CONTROL': str(num_grupos_control),
            'NUM_RIESGOS_AUT': str(num_riesgos_aut),
            'NUM_RIESGOS': str(num_riesgos),
            'TIPO_ADQUISICION': tipo_adquisicion
        }

        # Añadir las variables de perfiles
        variables.update(variables_perfiles)


        return variables

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'PERFIL': 'Error al calcular',
            'NUM_CONTROLES': '0',
            'MADUREZ_MEDIA': '0.0',
            'NUM_GRUPOS_CONTROL': '0',
            'NUM_RIESGOS_AUT': '0',
            'NUM_RIESGOS': '0',
            'TIPO_ADQUISICION': 'Error al calcular'
        }
    finally:
        session.close()


def calcular_estadisticas_riesgos_para_documento(id_sistema):
    """
    Calcula las estadísticas de riesgos (inherente y residual) para exportar a documento.
    🆕 AHORA INCLUYE: PERFIL, NUM_CONTROLES, MADUREZ_MEDIA, NUM_GRUPOS_CONTROL,
    NUM_RIESGOS_AUT, NUM_RIESGOS, TIPO_ADQUISICION

    Genera variables con formato:
    - {{R_CRITICO_I}}, {{R_ALTO_I}}, {{R_MEDIO_I}}, {{R_BAJO_I}}, {{R_TOTAL_I}} (inherente)
    - {{R_CRITICO_R}}, {{R_ALTO_R}}, {{R_MEDIO_R}}, {{R_BAJO_R}}, {{R_TOTAL_R}} (residual)
    - {{PERFIL}} (perfil de supervisión)
    - {{NUM_CONTROLES}} (número de controles activos y aplicables)
    - {{MADUREZ_MEDIA}} (media aritmética de madurez de controles)
    - {{NUM_GRUPOS_CONTROL}} (número de grupos de controles activados y que aplican)
    - {{NUM_RIESGOS_AUT}} (número de riesgos activos que aplican y que NO son manuales)
    - {{NUM_RIESGOS}} (número de riesgos activos que aplican, incluyendo manuales)
    - {{TIPO_ADQUISICION}} (descripción de la respuesta a la pregunta P1 del ADI)

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        dict: Diccionario con variables de riesgos y variables adicionales
    """
    from collections import defaultdict
    # Importar la función de controllers.py que ya existe
    from controllers import calcular_riesgo_residual, convertir_criticidad_a_nivel

    session = Session()
    try:

        # Obtener riesgos activos y aplicables
        riesgos = session.query(DatosRiesgo, Riesgo).join(
            Riesgo, DatosRiesgo.RIE_ID_RIESGO == Riesgo.ID_RIESGO
        ).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1,
            DatosRiesgo.L_APLICA == 1
        ).all()


        # Contadores para inherente y residual
        inherente_counts = defaultdict(int)
        residual_counts = defaultdict(int)

        # Procesar cada riesgo
        for dat_riesgo, riesgo in riesgos:
            # ========== CALCULAR RIESGO INHERENTE ==========
            if dat_riesgo.V_IMPACTO and dat_riesgo.V_PROBABILIDAD:
                nivel_inh = _calcular_nivel_riesgo_inherente(session, dat_riesgo)
                inherente_counts[nivel_inh] += 1

                # ========== CALCULAR RIESGO RESIDUAL ==========
                # Obtener la criticidad numérica del riesgo inherente
                config_criticidad = session.query(ConfiguracionCriticidad).filter_by(
                    V_IMPACTO=dat_riesgo.V_IMPACTO,
                    V_PROBAB=dat_riesgo.V_PROBABILIDAD
                ).first()

                if config_criticidad and config_criticidad.N_CRITICIDAD is not None:
                    criticidad_inherente = config_criticidad.N_CRITICIDAD

                    # Usar la función existente de controllers.py para calcular el residual
                    riesgo_residual_numerico, nivel_residual_texto = calcular_riesgo_residual(
                        session,
                        dat_riesgo,
                        criticidad_inherente
                    )

                    # Contar el nivel residual calculado
                    if nivel_residual_texto and nivel_residual_texto != "—":
                        residual_counts[nivel_residual_texto] += 1
                    else:
                        pass

        # Calcular totales
        total_inherente = sum(inherente_counts.values())
        total_residual = sum(residual_counts.values())

        # Generar diccionario de variables de riesgos
        variables = {
            # Inherente
            'R_CRITICO_I': str(inherente_counts.get('CRÍTICO', 0)),
            'R_ALTO_I': str(inherente_counts.get('ALTO', 0)),
            'R_MEDIO_I': str(inherente_counts.get('MEDIO', 0)),
            'R_BAJO_I': str(inherente_counts.get('BAJO', 0)),
            'R_TOTAL_I': str(total_inherente),

            # Residual
            'R_CRITICO_R': str(residual_counts.get('CRÍTICO', 0)),
            'R_ALTO_R': str(residual_counts.get('ALTO', 0)),
            'R_MEDIO_R': str(residual_counts.get('MEDIO', 0)),
            'R_BAJO_R': str(residual_counts.get('BAJO', 0)),
            'R_TOTAL_R': str(total_residual)
        }


        # 🆕 AÑADIR VARIABLES ADICIONALES
        variables_adicionales = calcular_variables_adicionales_eipd(id_sistema)
        variables.update(variables_adicionales)

        # 🆕 AÑADIR HTML DE RIESGO GLOBAL
        variables['riesgoglobal'] = generar_html_riesgo_global(id_sistema)

        return variables

    except Exception as e:
        import traceback
        traceback.print_exc()
        return generar_variables_riesgo_vacias()
    finally:
        session.close()


def _calcular_nivel_riesgo_inherente(session, dat_riesgo):
    """
    Calcula el nivel de riesgo inherente usando la tabla IA_CFGCRITICIDAD.
    Esta es la forma correcta que usa el sistema.

    Args:
        session: Sesión activa de SQLAlchemy
        dat_riesgo: Registro de DatosRiesgo

    Returns:
        str: Nivel de riesgo ('CRÍTICO', 'ALTO', 'MEDIO', 'BAJO', 'SIN VALORAR')
    """
    from models import ConfiguracionCriticidad

    # Verificar que tenga impacto y probabilidad
    if not dat_riesgo.V_IMPACTO or not dat_riesgo.V_PROBABILIDAD:
        return 'SIN VALORAR'

    # Buscar en IA_CFGCRITICIDAD la criticidad correspondiente
    config_criticidad = session.query(ConfiguracionCriticidad).filter_by(
        V_IMPACTO=dat_riesgo.V_IMPACTO,
        V_PROBAB=dat_riesgo.V_PROBABILIDAD
    ).first()

    if not config_criticidad or config_criticidad.N_CRITICIDAD is None:
        return 'SIN VALORAR'

    # Convertir criticidad a nivel usando los mismos rangos que controllers.py
    criticidad = config_criticidad.N_CRITICIDAD

    if criticidad >= 15:
        return 'CRÍTICO'
    elif criticidad >= 9:
        return 'ALTO'
    elif criticidad >= 5:
        return 'MEDIO'
    elif criticidad > 0:
        return 'BAJO'
    else:
        return 'SIN VALORAR'


def generar_variables_riesgo_vacias():
    """
    Genera un diccionario de variables de riesgo con valores en 0.
    🆕 AHORA INCLUYE: PERFIL, NUM_CONTROLES, MADUREZ_MEDIA, NUM_GRUPOS_CONTROL,
    NUM_RIESGOS_AUT, NUM_RIESGOS, TIPO_ADQUISICION y ES_XXX para cada perfil

    Returns:
        dict: Variables de riesgo con valores '0' y variables adicionales con valores por defecto
    """
    session = Session()
    try:
        # Variables base de riesgo
        variables = {
            'R_CRITICO_I': '0',
            'R_ALTO_I': '0',
            'R_MEDIO_I': '0',
            'R_BAJO_I': '0',
            'R_TOTAL_I': '0',
            'R_CRITICO_R': '0',
            'R_ALTO_R': '0',
            'R_MEDIO_R': '0',
            'R_BAJO_R': '0',
            'R_TOTAL_R': '0',
            'PERFIL': 'No calculado',
            'NUM_CONTROLES': '0',
            'MADUREZ_MEDIA': '0.0',
            'NUM_GRUPOS_CONTROL': '0',
            'NUM_RIESGOS_AUT': '0',
            'NUM_RIESGOS': '0',
            'TIPO_ADQUISICION': 'No calculado',
            'riesgoglobal': '<p><em>No disponible</em></p>'
        }

        # Añadir variables ES_XXX para cada perfil con valor vacío (desmarcados)
        import re
        import unicodedata

        todos_perfiles = session.query(Perfil).order_by(Perfil.N_PTOSMIN).all()

        for p in todos_perfiles:
            # Normalizar el nombre del perfil usando el mismo método que calcular_variables_adicionales_eipd
            # 1. Convertir a mayúsculas
            nombre_normalizado = p.D_PERFIL.upper()

            # 2. Eliminar acentos usando unicodedata (método robusto)
            nombre_normalizado = ''.join(
                c for c in unicodedata.normalize('NFD', nombre_normalizado)
                if unicodedata.category(c) != 'Mn'
            )

            # 3. Eliminar espacios y caracteres especiales, reemplazar por guión bajo
            nombre_normalizado = re.sub(r'[^A-Z0-9]', '_', nombre_normalizado)

            # 4. Eliminar guiones bajos múltiples
            nombre_normalizado = re.sub(r'_+', '_', nombre_normalizado)

            # 5. Eliminar guiones bajos al inicio y final
            nombre_normalizado = nombre_normalizado.strip('_')

            variable_nombre = f"ES_{nombre_normalizado}"
            variables[variable_nombre] = ""  # Cadena vacía para checkboxes desmarcados

        return variables

    except Exception as e:
        # En caso de error, retornar solo las variables básicas
        return {
            'R_CRITICO_I': '0',
            'R_ALTO_I': '0',
            'R_MEDIO_I': '0',
            'R_BAJO_I': '0',
            'R_TOTAL_I': '0',
            'R_CRITICO_R': '0',
            'R_ALTO_R': '0',
            'R_MEDIO_R': '0',
            'R_BAJO_R': '0',
            'R_TOTAL_R': '0',
            'PERFIL': 'No calculado',
            'NUM_CONTROLES': '0',
            'MADUREZ_MEDIA': '0.0',
            'NUM_GRUPOS_CONTROL': '0',
            'NUM_RIESGOS_AUT': '0',
            'NUM_RIESGOS': '0',
            'TIPO_ADQUISICION': 'No calculado',
            'riesgoglobal': '<p><em>No disponible</em></p>'
        }
    finally:
        session.close()


def generar_html_riesgo_global(id_sistema):
    """
    Genera el HTML para la sección de Riesgo Global del documento EIPD.

    Esta función:
    1. Verifica si la fase actual requiere evaluación de riesgo residual (nivel R)
    2. Si no aplica, devuelve un mensaje configurable desde IA_CFGRIESGLOBAL
    3. Si aplica, genera el HTML completo con:
       - Badge del nivel de riesgo global
       - Criterio determinante
       - Factores agravantes (si existen)
       - Tabla de distribución por clusters

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        str: HTML formateado para insertar en la plantilla EIPD
    """
    from controllers import calcular_riesgo_global, obtener_info_clusters_sistema, obtener_fase_proyecto

    session = Session()
    try:

        # 1. Verificar fase actual
        fase_actual, _ = obtener_fase_proyecto(id_sistema)

        if not fase_actual or fase_actual.C_NIVELRIESG != 'R':
            # Obtener mensaje de NO APLICABLE desde configuración
            param_no_aplica = session.query(ConfiguracionRiesgoGlobal).filter(
                ConfiguracionRiesgoGlobal.C_PARAMETRO == 'MSG_NO_APLICABLE',
                ConfiguracionRiesgoGlobal.L_ESTADO == 1
            ).first()

            if param_no_aplica and param_no_aplica.T_MENSAJE:
                mensaje = param_no_aplica.T_MENSAJE
            else:
                mensaje = "NO APLICABLE - Esta sección se completa en fases con evaluación de riesgo residual."

            nivel_actual = fase_actual.C_NIVELRIESG if fase_actual else 'No definido'
            return f'<p><em>{mensaje}</em></p>'

        # 2. Calcular riesgo global
        resultado_rg = calcular_riesgo_global(session, id_sistema)

        if not resultado_rg or not resultado_rg.get('nivel'):
            return '<p><em>No se ha podido calcular el riesgo global. Verifique que todos los riesgos tengan evaluación completa.</em></p>'

        nivel = resultado_rg['nivel']
        causa = resultado_rg.get('causa')
        factores = resultado_rg.get('factores', [])
        metricas = resultado_rg.get('metricas', {})

        # 3. Obtener info de clusters
        clusters_info = obtener_info_clusters_sistema(session, id_sistema)

        # 4. Generar HTML compacto
        html_parts = []

        # 4.1. Badge del nivel
        colores_nivel = {
            'BAJO': ('#d4edda', '#155724', '#155724'),
            'MEDIO': ('#fff3cd', '#856404', '#856404'),
            'ALTO': ('#f8d7da', '#721c24', '#721c24'),
            'CRITICO': ('#721c24', '#ffffff', '#721c24')
        }
        bg_color, text_color, border_color = colores_nivel.get(nivel, ('#e9ecef', '#333333', '#333333'))

        html_parts.append(f'<table style="width: auto; margin-bottom: 10px;"><tbody><tr>')
        html_parts.append(f'<td style="font-weight: bold; padding-right: 20px; border: none;">Nivel de Riesgo Global del Tratamiento:</td>')
        html_parts.append(f'<td style="border: none;"><span style="display: inline-block; padding: 6px 20px; font-weight: bold; font-size: 12pt; border-radius: 4px; background-color: {bg_color}; color: {text_color}; border: 2px solid {border_color};">{nivel}</span></td>')
        html_parts.append(f'</tr></tbody></table>')

        # 4.2. Criterio determinante
        if causa == 'RIESGO_INDIVIDUAL':
            if nivel == 'CRITICO':
                criterio = f"Existen {metricas.get('criticos', 0)} riesgo(s) con nivel residual CRÍTICO. No es posible autorizar el paso a producción hasta mitigar estos riesgos a un nivel inferior."
            else:
                criterio = f"Existen {metricas.get('altos', 0)} riesgo(s) con nivel residual ALTO. No es posible autorizar el paso a producción hasta mitigar estos riesgos a un nivel inferior."
        elif causa == 'FACTORES_AGRAVANTES':
            criterio = "Aunque ningún riesgo residual individual alcanza nivel ALTO o CRÍTICO, se han identificado factores agravantes que elevan el nivel global."
        elif nivel == 'MEDIO':
            criterio = "Todos los riesgos residuales individuales se sitúan en nivel MEDIO o BAJO. No se han identificado factores agravantes activos que eleven el nivel global."
        else:
            criterio = "Todos los riesgos residuales individuales se sitúan en nivel BAJO. El tratamiento presenta un nivel de riesgo aceptable."

        html_parts.append(f'<p style="margin: 8px 0;"><strong>Criterio determinante:</strong> {criterio}</p>')

        # 4.3. Factores agravantes (si existen)
        if factores:
            html_parts.append('<div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px 14px; margin: 10px 0;">')
            html_parts.append('<p style="margin: 0 0 8px 0;"><strong>Factores agravantes activos:</strong></p><ul style="margin: 0 0 0 20px; padding: 0;">')
            for factor in factores:
                if factor['tipo'] == 'CONCENTRACION':
                    html_parts.append(f'<li><strong>Concentración:</strong> {factor["cantidad"]} de {factor["total"]} riesgos ({factor["porcentaje"]}%) en nivel MEDIO (umbral: {factor["umbral"]}%).</li>')
                elif factor['tipo'] == 'CLUSTER':
                    html_parts.append(f'<li><strong>Cluster {factor["cluster_codigo"]} ({factor["cluster_nombre"]}):</strong> {factor["cantidad"]} riesgos en nivel MEDIO (umbral: &ge;{factor["umbral"]}).</li>')
                elif factor['tipo'] == 'ESPECIFICOS':
                    html_parts.append(f'<li><strong>Riesgos específicos del proyecto:</strong> {factor["cantidad"]} riesgos específicos en nivel MEDIO (umbral: &ge;{factor["umbral"]}).</li>')
                elif factor['tipo'] == 'RIESGO_CRITICO':
                    html_parts.append(f'<li><strong>Riesgos críticos:</strong> {factor["cantidad"]} riesgo(s) con nivel residual CRÍTICO.</li>')
                elif factor['tipo'] == 'RIESGO_ALTO':
                    html_parts.append(f'<li><strong>Riesgos altos:</strong> {factor["cantidad"]} riesgo(s) con nivel residual ALTO.</li>')
            html_parts.append('</ul></div>')
            if nivel in ('ALTO', 'CRITICO'):
                html_parts.append('<p style="margin: 8px 0;"><strong>Implicación:</strong> No es posible autorizar el paso a producción hasta mitigar los factores agravantes identificados.</p>')
        else:
            total_aplicables = metricas.get('total_aplicables', 0)
            medios = metricas.get('medios', 0)
            pct_medio = metricas.get('pct_medio', 0)
            html_parts.append(f'<p style="margin: 8px 0;">El análisis de factores agravantes no ha detectado situaciones que requieran elevar el nivel:</p>')
            html_parts.append('<ul style="margin: 5px 0 10px 20px; padding: 0;">')
            html_parts.append(f'<li><strong>Concentración:</strong> {medios} de {total_aplicables} riesgos aplicables ({pct_medio}%) en nivel MEDIO, por debajo del umbral del 70%.</li>')
            html_parts.append('<li><strong>Clusters:</strong> Ningún cluster de riesgos interrelacionados supera su umbral de activación.</li>')
            html_parts.append('<li><strong>Riesgos específicos:</strong> No se han identificado riesgos específicos del proyecto en nivel MEDIO que superen el umbral.</li>')
            html_parts.append('</ul>')

        # 4.4. Tabla de clusters (sin thead para evitar repetición en saltos de página PDF)
        if clusters_info:
            html_parts.append('<p style="margin: 10px 0 5px 0;"><strong>Distribución de riesgos residuales MEDIO por cluster:</strong></p>')
            html_parts.append('<table style="width: 100%; border-collapse: collapse; font-size: 10pt;"><tbody>')
            # Cabecera como primera fila del tbody (no se repetirá en saltos de página)
            html_parts.append('<tr>')
            html_parts.append('<td style="background-color: #2e7d32; color: white; padding: 6px 8px; text-align: left; width: 50px; font-weight: bold;">ID</td>')
            html_parts.append('<td style="background-color: #2e7d32; color: white; padding: 6px 8px; text-align: left; font-weight: bold;">Cluster</td>')
            html_parts.append('<td style="background-color: #2e7d32; color: white; padding: 6px 8px; text-align: center; width: 90px; font-weight: bold;">Riesgos MEDIO</td>')
            html_parts.append('<td style="background-color: #2e7d32; color: white; padding: 6px 8px; text-align: center; width: 70px; font-weight: bold;">Umbral</td>')
            html_parts.append('<td style="background-color: #2e7d32; color: white; padding: 6px 8px; text-align: center; width: 55px; font-weight: bold;">Estado</td>')
            html_parts.append('</tr>')

            for cluster in clusters_info:
                supera = cluster['supera_umbral']
                fila_style = 'background-color: #fff3cd;' if supera else ''
                texto_style = 'font-weight: bold;' if supera else ''
                # Usar X roja para superación, V verde para OK (caracteres ASCII seguros)
                estado = '<span style="color: #dc3545; font-weight: bold;">X</span>' if supera else '<span style="color: #28a745; font-weight: bold;">V</span>'
                html_parts.append(f'<tr style="{fila_style}">')
                html_parts.append(f'<td style="padding: 5px 8px; border-bottom: 1px solid #e0e0e0; {texto_style}">{cluster["codigo"]}</td>')
                html_parts.append(f'<td style="padding: 5px 8px; border-bottom: 1px solid #e0e0e0; {texto_style}">{cluster["nombre"]}</td>')
                html_parts.append(f'<td style="padding: 5px 8px; border-bottom: 1px solid #e0e0e0; text-align: center; {texto_style}">{cluster["riesgos_medio"]}</td>')
                html_parts.append(f'<td style="padding: 5px 8px; border-bottom: 1px solid #e0e0e0; text-align: center;">&ge;{cluster["umbral"]}</td>')
                html_parts.append(f'<td style="padding: 5px 8px; border-bottom: 1px solid #e0e0e0; text-align: center;">{estado}</td>')
                html_parts.append('</tr>')

            html_parts.append('</tbody></table>')
            html_parts.append('<p style="font-style: italic; color: #666; font-size: 9pt; margin: 3px 0 0 0;"><strong>Nota:</strong> Los clusters agrupan riesgos con causa raíz común o efectos sinérgicos. V indica cluster bajo control; X indica superación del umbral.</p>')

        html_final = ''.join(html_parts)
        return html_final

    except Exception as e:
        import traceback
        traceback.print_exc()
        return '<p><em>Error al generar la sección de Riesgo Global.</em></p>'
    finally:
        session.close()


def generar_documento_desde_plantilla(id_datdocs):
    """
    Genera un documento HTML a partir de una plantilla encriptada, inyectando los datos
    del proyecto desde la tabla IA_DATELEMDOCS.

    El proceso es:
    1. Obtener la configuración del documento para encontrar T_PLANTILLA
    2. Cargar y desencriptar la plantilla desde el archivo .eipd
    3. Obtener todos los datos de IA_DATELEMDOCS para este documento
    4. Reemplazar las variables {{C_DATO}} en la plantilla con los valores de T_DATO
    5. Retornar el HTML generado

    Args:
        id_datdocs (int): ID del documento a generar

    Returns:
        dict: Diccionario con:
            - success (bool): True si se generó correctamente
            - html (str): Contenido HTML generado (si success=True)
            - nombre_archivo (str): Nombre sugerido para el archivo
            - mensaje (str): Mensaje de error (si success=False)
    """
    from eipd_crypto import cargar_plantilla_segura
    import os
    import re

    session = Session()
    try:

        # 1. Obtener el documento y su configuración
        documento = session.query(DatosDocumento).filter(
            DatosDocumento.ID_DATDOCS == id_datdocs
        ).first()

        if not documento:
            return {
                'success': False,
                'mensaje': f'No se encontró el documento con ID {id_datdocs}'
            }

        configuracion = session.query(ConfiguracionDocumento).filter(
            ConfiguracionDocumento.ID_CFGDOCS == documento.DD_ID_CFGDOCS
        ).first()

        if not configuracion:
            return {
                'success': False,
                'mensaje': 'No se encontró la configuración del documento'
            }

        # 2. Verificar que exista plantilla configurada
        if not configuracion.T_PLANTILLA:
            return {
                'success': False,
                'mensaje': 'Este documento no tiene plantilla configurada'
            }


        # 3. Construir ruta a la plantilla encriptada
        # La plantilla debe estar en la carpeta 'plantillas' junto al ejecutable
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        ruta_plantilla = os.path.join(base_dir, 'plantillas', configuracion.T_PLANTILLA)

        if not os.path.exists(ruta_plantilla):
            return {
                'success': False,
                'mensaje': f'No se encontró el archivo de plantilla: {configuracion.T_PLANTILLA}'
            }


        # 4. Cargar y desencriptar la plantilla
        try:
            contenido_plantilla = cargar_plantilla_segura(ruta_plantilla)
        except Exception as e:
            return {
                'success': False,
                'mensaje': f'Error al desencriptar plantilla: {str(e)}'
            }

        # 5. Obtener todos los datos del documento desde IA_DATELEMDOCS
        datos_elementos = session.query(
            DatosElementoDocumento,
            ConfiguracionDatoDocumento
        ).join(
            ConfiguracionDatoDocumento,
            DatosElementoDocumento.DED_ID_CFGDATDOCS == ConfiguracionDatoDocumento.ID_CFGDATDOCS
        ).filter(
            DatosElementoDocumento.DED_ID_DATDOCS == id_datdocs
        ).all()


        # 6. Crear diccionario de variables para reemplazo
        # Clave: C_DATO, Valor: T_DATO
        # También almacenar información sobre qué campos son checkboxes
        variables = {}
        checkboxes = {}  # 🆕 Diccionario para almacenar campos que son checkboxes

        for dat_elem, cfg_elem in datos_elementos:
            c_dato = cfg_elem.C_DATO
            t_dato = dat_elem.T_DATO if dat_elem.T_DATO else ""

            if c_dato:
                variables[c_dato] = t_dato

                # 🆕 Si el campo es un checkbox (L_CHECK = 1), marcarlo
                if cfg_elem.L_CHECK == 1:
                    checkboxes[c_dato] = t_dato
                else:
                    pass

        # 6.1. Agregar variables calculadas de estadísticas de riesgos
        variables_riesgos = calcular_estadisticas_riesgos_para_documento(documento.SIST_ID_SISTEMA)

        # 6.2. Separar las variables de perfil (ES_XXX) que son checkboxes
        for variable_nombre, valor in variables_riesgos.items():
            if variable_nombre.startswith("ES_"):
                # Añadir al diccionario de checkboxes para que se procesen igual que los demás
                checkboxes[variable_nombre] = valor
                estado = "MARCADO (X)" if valor == "X" else "DESMARCADO"

        # 6.3. Añadir todas las variables al diccionario general
        variables.update(variables_riesgos)

        # 7. Reemplazar variables en la plantilla
        # Las variables en la plantilla deben estar en formato {{C_DATO}}
        html_generado = contenido_plantilla

        # 🆕 7.1. Primero reemplazar checkboxes y rating-boxes con marca visual cuando sea necesario
        for c_dato, valor in checkboxes.items():
            # Para checkboxes normales: <span class="checkbox">{{C_DATO}}</span>
            # Para rating-boxes: <div class="rating-box{{C_DATO}}">1</div>
            # Si el valor es "X", reemplazamos apropiadamente según el contexto
            # Si el valor está vacío, dejamos el elemento vacío o sin la clase 'checked'

            # 🔍 Detectar el contexto: ¿Es un checkbox normal o un rating-box?
            # Para rating-box, buscamos el patrón: class="rating-box{{C_DATO}}"
            # Para checkbox normal, buscamos: <span class="checkbox">{{C_DATO}}</span>

            patron_rating_box = r'class="rating-box\{\{\s*' + re.escape(c_dato) + r'\s*\}\}"'
            patron_checkbox_normal = r'<span\s+class="checkbox">\{\{\s*' + re.escape(c_dato) + r'\s*\}\}</span>'

            # Verificar si es un rating-box o checkbox normal
            es_rating_box = re.search(patron_rating_box, html_generado) is not None
            es_checkbox_normal = re.search(patron_checkbox_normal, html_generado) is not None

            if es_rating_box:
                # 📦 Es un RATING-BOX
                if valor == "X":
                    # Reemplazar class="rating-box{{C_DATO}}" con class="rating-box checked"
                    html_generado = re.sub(
                        r'class="rating-box\{\{\s*' + re.escape(c_dato) + r'\s*\}\}"',
                        'class="rating-box checked"',
                        html_generado
                    )
                else:
                    # Reemplazar class="rating-box{{C_DATO}}" con class="rating-box"
                    html_generado = re.sub(
                        r'class="rating-box\{\{\s*' + re.escape(c_dato) + r'\s*\}\}"',
                        'class="rating-box"',
                        html_generado
                    )

            elif es_checkbox_normal:
                # ☑️ Es un CHECKBOX NORMAL
                patron = r'\{\{\s*' + re.escape(c_dato) + r'\s*\}\}'

                if valor == "X":
                    # Marcar el checkbox con ✓
                    marca_checkbox = "✓"
                    html_generado = re.sub(patron, marca_checkbox, html_generado)
                else:
                    # Dejar vacío
                    html_generado = re.sub(patron, "", html_generado)

            else:
                # ⚠️ No se detectó el contexto, aplicar reemplazo genérico
                patron = r'\{\{\s*' + re.escape(c_dato) + r'\s*\}\}'

                if valor == "X":
                    html_generado = re.sub(patron, "✓", html_generado)
                else:
                    html_generado = re.sub(patron, "", html_generado)

        # 7.2. Luego reemplazar las variables normales (texto)
        for c_dato, valor in variables.items():
            # Saltar los checkboxes, ya fueron procesados
            if c_dato in checkboxes:
                continue

            # Reemplazar {{C_DATO}} con el valor
            patron = r'\{\{\s*' + re.escape(c_dato) + r'\s*\}\}'
            html_generado = re.sub(patron, valor, html_generado)

        # 8. Verificar si quedaron variables sin reemplazar
        variables_sin_reemplazar = re.findall(r'\{\{([^}]+)\}\}', html_generado)
        if variables_sin_reemplazar:
            pass

        # 9. Generar nombre de archivo con formato TTTT_PPPP_AAAAMMDDHHmmSS.html
        from datetime import datetime

        proyecto = session.query(Inicio).filter(
            Inicio.ID_SISTEMA == documento.SIST_ID_SISTEMA
        ).first()

        # Obtener el tipo de documento (OBS de IA_VALDAT)
        tipo_documento = ""
        if configuracion.V_TIPODOC:
            valor_tipo = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == configuracion.V_TIPODOC
            ).first()
            if valor_tipo and valor_tipo.OBS:
                tipo_documento = limpiar_nombre_archivo(valor_tipo.OBS)

        # Si no hay OBS, usar T_DESC de la configuración como fallback
        if not tipo_documento:
            tipo_documento = limpiar_nombre_archivo(configuracion.T_DESC)

        # Obtener nombre del proyecto y limpiarlo
        nombre_proyecto = proyecto.D_NOMPROYEC if proyecto else "proyecto"
        nombre_proyecto_limpio = limpiar_nombre_archivo(nombre_proyecto)

        # Obtener fecha y hora actual en formato AAAAMMDDHHmmSS
        ahora = datetime.now()
        fecha_hora = ahora.strftime("%Y%m%d%H%M%S")

        # Construir nombre: TTTT_PPPP_AAAAMMDDHHmmSS.html
        nombre_archivo = f"{tipo_documento}_{nombre_proyecto_limpio}_{fecha_hora}.html"


        return {
            'success': True,
            'html': html_generado,
            'nombre_archivo': nombre_archivo
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'mensaje': f'Error al generar documento: {str(e)}'
        }
    finally:
        session.close()


def generar_documento_pdf_desde_plantilla(id_datdocs):
    """
    Genera un documento PDF a partir de una plantilla encriptada, inyectando los datos
    del proyecto desde la tabla IA_DATELEMDOCS.

    El proceso es:
    1. Generar el HTML usando generar_documento_desde_plantilla()
    2. Convertir el HTML a PDF usando wkhtmltopdf (ejecutable externo)
    3. Retornar el PDF como bytes

    IMPORTANTE: wkhtmltopdf debe estar en la carpeta 'bin' junto al ejecutable

    Args:
        id_datdocs (int): ID del documento a generar

    Returns:
        dict: Diccionario con:
            - success (bool): True si se generó correctamente
            - pdf (bytes): Contenido del PDF en bytes (si success=True)
            - nombre_archivo (str): Nombre sugerido para el archivo
            - mensaje (str): Mensaje de error (si success=False)
    """
    import subprocess
    import tempfile

    try:

        # 1. Primero generar el HTML
        resultado_html = generar_documento_desde_plantilla(id_datdocs)

        if not resultado_html['success']:
            return resultado_html


        # 2. Buscar el ejecutable wkhtmltopdf
        wkhtmltopdf_path = _buscar_wkhtmltopdf()

        if not wkhtmltopdf_path:
            return {
                'success': False,
                'mensaje': 'No se encontró wkhtmltopdf.exe. Por favor, colóquelo en la carpeta "bin" de la aplicación.'
            }


        # 3. Crear archivos temporales para HTML y PDF
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as html_temp:
            html_temp.write(resultado_html['html'])
            html_temp_path = html_temp.name

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_temp:
            pdf_temp_path = pdf_temp.name

        try:
            # 4. Ejecutar wkhtmltopdf para convertir HTML a PDF

            comando = [
                wkhtmltopdf_path,
                '--quiet',                    # Suprimir salida verbose
                '--enable-local-file-access', # Permitir acceso a archivos locales
                '--page-size', 'A4',          # Tamaño de página
                '--margin-top', '20mm',       # Márgenes
                '--margin-bottom', '20mm',
                '--margin-left', '20mm',
                '--margin-right', '20mm',
                '--encoding', 'UTF-8',        # Codificación
                html_temp_path,               # Archivo HTML de entrada
                pdf_temp_path                 # Archivo PDF de salida
            ]

            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=30  # Timeout de 30 segundos
            )

            if resultado.returncode != 0:
                error_msg = resultado.stderr if resultado.stderr else "Error desconocido"
                return {
                    'success': False,
                    'mensaje': f'Error al generar PDF: {error_msg}'
                }

            # 5. Leer el PDF generado
            with open(pdf_temp_path, 'rb') as pdf_file:
                pdf_bytes = pdf_file.read()


            # 6. Cambiar la extensión del nombre de archivo de .html a .pdf
            nombre_archivo_pdf = resultado_html['nombre_archivo'].replace('.html', '.pdf')


            return {
                'success': True,
                'pdf': pdf_bytes,
                'nombre_archivo': nombre_archivo_pdf
            }

        finally:
            # Limpiar archivos temporales
            import os
            try:
                os.unlink(html_temp_path)
                os.unlink(pdf_temp_path)
            except Exception as e:
                pass

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'mensaje': 'Timeout al generar PDF. El documento puede ser demasiado grande.'
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'mensaje': f'Error al generar documento PDF: {str(e)}'
        }


def _buscar_wkhtmltopdf():
    """
    Busca el ejecutable wkhtmltopdf en diferentes ubicaciones.

    Orden de búsqueda:
    1. Carpeta 'bin' junto al ejecutable (para distribución .exe)
    2. Carpeta 'bin' en el directorio actual (para desarrollo)
    3. PATH del sistema

    Returns:
        str: Ruta al ejecutable wkhtmltopdf o None si no se encuentra
    """
    import os
    import shutil


    # 🎯 PRIMERO: Buscar en el directorio temporal de PyInstaller
    if getattr(sys, 'frozen', False):
        # Estamos dentro de un ejecutable de PyInstaller
        base_path = sys._MEIPASS

        # Rutas relativas dentro del bundle - TODAS las posibles
        rutas_bundle = [
            os.path.join(base_path, 'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe'),
            os.path.join(base_path, 'wkhtmltopdf', 'wkhtmltopdf.exe'),
            os.path.join(base_path, 'wkhtmltopdf.exe'),
            os.path.join(base_path, 'bin', 'wkhtmltopdf.exe'),
        ]

        for ruta in rutas_bundle:
            if os.path.isfile(ruta):
                return ruta


    # Si no estamos en PyInstaller o no se encontró en el bundle
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # Rutas de respaldo (en caso de no estar en bundle PyInstaller)
    posibles_rutas = [
        os.path.join(base_dir, 'bin', 'wkhtmltopdf.exe'),
        os.path.join(base_dir, 'wkhtmltopdf.exe'),
        os.path.join(os.getcwd(), 'bin', 'wkhtmltopdf.exe'),
    ]

    # Buscar en las rutas definidas
    for ruta in posibles_rutas:
        if os.path.isfile(ruta):
            return ruta

    # Buscar en el PATH del sistema
    wkhtmltopdf_system = shutil.which('wkhtmltopdf')
    if wkhtmltopdf_system:
        return wkhtmltopdf_system

    # No encontrado
    for ruta in posibles_rutas:
        pass

    return None


def generar_anexos_csv(id_sistema):
    """
    Genera tres archivos CSV con anexos para el proyecto:
    1. Matriz completa de riesgos (Inherente y Residual)
    2. Catálogo completo de controles aplicados y su nivel de madurez
    3. Requisitos de cumplimiento con estados de planificación y cumplimiento

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        dict: Diccionario con:
            - success (bool): True si se generó correctamente
            - archivos (list): Lista de diccionarios con 'contenido' y 'nombre_archivo' para cada CSV
            - mensaje (str): Mensaje de error (si success=False)
    """
    from datetime import datetime
    import io

    session = Session()
    try:

        # Obtener información del proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto:
            return {
                'success': False,
                'mensaje': 'No se encontró el proyecto especificado'
            }

        # Limpiar nombre del proyecto usando la función auxiliar
        nombre_proyecto = proyecto.D_NOMPROYEC if proyecto.D_NOMPROYEC else 'Proyecto'
        nombre_proyecto_limpio = limpiar_nombre_archivo(nombre_proyecto)

        # Obtener fecha y hora actual en formato AAAAMMDDHHmmSS
        ahora = datetime.now()
        fecha_hora = ahora.strftime("%Y%m%d%H%M%S")

        archivos_generados = []

        # ==================== ARCHIVO 1: MATRIZ DE RIESGOS ====================

        # Obtener riesgos activos y que aplican
        riesgos = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema
        ).all()

        # Crear el CSV de riesgos en memoria
        # 🆕 Añadidas columnas Probabilidad e Impacto
        # 🆕 Columnas de justificación condicionales según config
        csv_riesgos = io.StringIO()

        # Construir encabezado dinámicamente según config
        columnas = ["Descripción del riesgo", "Activo", "Aplica", "Probabilidad", "Impacto",
                   "Riesgo inherente", "Riesgo residual", "Justif. Aplica"]

        # Añadir columnas de justificación según configuración
        if config.VER_JUST_IMPACTO == 1:
            columnas.append("Justif. Impacto")
        if config.VER_JUST_PROB == 1:
            columnas.append("Justif. Probabilidad")

        # Escribir encabezado
        csv_riesgos.write(";".join(columnas) + "\n")

        riesgos_procesados = 0
        for riesgo in riesgos:
            # Obtener descripción del riesgo
            if riesgo.L_MANUAL == 1:
                # Riesgo personalizado - obtener de IA_DATRIESGOS
                descripcion = riesgo.T_DESCRIPCION if riesgo.T_DESCRIPCION else "Sin descripción"
            else:
                # Riesgo del catálogo - obtener de IA_RIESGOS
                riesgo_catalogo = session.query(Riesgo).filter(
                    Riesgo.ID_RIESGO == riesgo.RIE_ID_RIESGO
                ).first()
                descripcion = riesgo_catalogo.D_RIESGO if riesgo_catalogo else "Sin descripción"

            # Limpiar descripción para CSV (eliminar saltos de línea y punto y coma)
            descripcion = descripcion.replace('\n', ' ').replace('\r', ' ').replace(';', ',')

            # 🆕 Obtener descripción de Probabilidad desde IA_VALDAT
            probabilidad_texto = "Sin valorar"
            if riesgo.V_PROBABILIDAD:
                valor_probabilidad = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == riesgo.V_PROBABILIDAD
                ).first()
                if valor_probabilidad:
                    probabilidad_texto = valor_probabilidad.D_VALOR if valor_probabilidad.D_VALOR else "Sin valorar"

            # 🆕 Obtener descripción de Impacto desde IA_VALDAT
            impacto_texto = "Sin valorar"
            if riesgo.V_IMPACTO:
                valor_impacto = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == riesgo.V_IMPACTO
                ).first()
                if valor_impacto:
                    impacto_texto = valor_impacto.D_VALOR if valor_impacto.D_VALOR else "Sin valorar"

            # Calcular riesgo inherente
            criticidad_inherente = None
            nivel_inherente = "—"

            if riesgo.V_IMPACTO and riesgo.V_PROBABILIDAD:
                config_criticidad = session.query(ConfiguracionCriticidad).filter_by(
                    V_IMPACTO=riesgo.V_IMPACTO,
                    V_PROBAB=riesgo.V_PROBABILIDAD
                ).first()

                if config_criticidad:
                    criticidad_inherente = config_criticidad.N_CRITICIDAD
                    # Convertir criticidad a nivel textual
                    if criticidad_inherente >= 15:
                        nivel_inherente = "CRÍTICO"
                    elif criticidad_inherente >= 9:
                        nivel_inherente = "ALTO"
                    elif criticidad_inherente >= 5:
                        nivel_inherente = "MEDIO"
                    elif criticidad_inherente > 0:
                        nivel_inherente = "BAJO"

            # Calcular riesgo residual usando la función existente
            from controllers import calcular_riesgo_residual
            riesgo_residual_num, nivel_residual = calcular_riesgo_residual(
                session, riesgo, criticidad_inherente
            )

            # Formatear para CSV
            riesgo_inherente_str = nivel_inherente if nivel_inherente != "—" else "Sin valorar"
            riesgo_residual_str = nivel_residual if nivel_residual != "—" else "Sin valorar"

            # Campos adicionales
            activo = "Sí" if riesgo.L_ACTIVA == 1 else "No"
            aplica = "Sí" if riesgo.L_APLICA == 1 else "No"

            # Limpiar campos de justificación para CSV
            justif_aplica = (riesgo.T_JUSAPLICA or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')
            justif_probabilidad = (riesgo.T_JUSPROBABILIDAD or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')
            justif_impacto = (riesgo.T_JUSIMPACTO or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')

            # 🆕 Construir fila dinámicamente según config
            valores = [
                f'"{descripcion}"',
                activo,
                aplica,
                f'"{probabilidad_texto}"',
                f'"{impacto_texto}"',
                f'"{riesgo_inherente_str}"',
                f'"{riesgo_residual_str}"',
                f'"{justif_aplica}"'
            ]

            # Añadir justificaciones según configuración
            if config.VER_JUST_IMPACTO == 1:
                valores.append(f'"{justif_impacto}"')
            if config.VER_JUST_PROB == 1:
                valores.append(f'"{justif_probabilidad}"')

            # Escribir línea
            csv_riesgos.write(";".join(valores) + "\n")
            riesgos_procesados += 1


        # Guardar el contenido del CSV de riesgos con formato TTTT_PPPP_AAAAMMDDHHmmSS.csv
        nombre_archivo_riesgos = f"Riesgos_{nombre_proyecto_limpio}_{fecha_hora}.csv"
        archivos_generados.append({
            'contenido': csv_riesgos.getvalue(),
            'nombre_archivo': nombre_archivo_riesgos
        })
        csv_riesgos.close()

        # ==================== ARCHIVO 2: CATÁLOGO DE CONTROLES ====================

        # Obtener controles activos y que aplican
        controles = session.query(DatosControl).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema
        ).all()

        # Crear el CSV de controles en memoria
        # 🆕 Añadidas columnas "Grupo de control" e "Instrumento contractual"
        csv_controles = io.StringIO()
        csv_controles.write("Descripción del control;Activo;Aplica;Grupo de control;Nivel de madurez;Traslado a pliegos (Si/No); Instrumento contractual; Traslado a pliegos; Implementación\n")

        controles_procesados = 0
        for control in controles:
            # Obtener descripción del control desde IA_CONTROLES
            control_catalogo = session.query(Control).filter(
                Control.ID_CONTROL == control.CON_ID_CONTROL
            ).first()

            descripcion = control_catalogo.D_CONTROL if control_catalogo else "Sin descripción"

            # Limpiar descripción para CSV (eliminar saltos de línea y punto y coma)
            descripcion = descripcion.replace('\n', ' ').replace('\r', ' ').replace(';', ',')

            # 🆕 Obtener descripción del Grupo de control desde IA_GRUCONTROL (GRU_ID_CONTROL)
            grupo_control_texto = "Sin grupo"
            if control_catalogo and control_catalogo.grupo_control:
                grupo_control_texto = control_catalogo.grupo_control.D_CONTROL if control_catalogo.grupo_control.D_CONTROL else "Sin grupo"
                # Limpiar para CSV
                grupo_control_texto = grupo_control_texto.replace('\n', ' ').replace('\r', ' ').replace(';', ',')

            # Obtener nivel de madurez
            nivel_madurez = "Sin valorar"
            if control.V_MADUREZ:
                valor_madurez = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == control.V_MADUREZ
                ).first()

                if valor_madurez:
                    nivel_madurez = valor_madurez.D_VALOR

            # 🆕 Obtener descripción del Instrumento contractual desde IA_VALDAT (V_INTCONDES)
            instrumento_contractual = "Sin definir"
            if control.V_INTCONDES:
                valor_instrumento = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == control.V_INTCONDES
                ).first()

                if valor_instrumento:
                    instrumento_contractual = valor_instrumento.D_VALOR if valor_instrumento.D_VALOR else "Sin definir"

            # Campos adicionales
            activo = "Sí" if control.L_ACTIVA == 1 else "No"
            aplica = "Sí" if control.L_APLICA == 1 else "No"
            traslado_pliegos = "Sí" if control.L_TRASLAPLI == 1 else "No"

            # Limpiar observaciones para CSV
            observaciones = (control.T_OBSERVACIONES or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')
            traslado_pliegos_txt = (control.T_ESPCLAUSULA or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')

            # 🆕 Escribir línea en CSV con Grupo de control e Instrumento contractual
            csv_controles.write(f'"{descripcion}";{activo};{aplica};"{grupo_control_texto}";"{nivel_madurez}";{traslado_pliegos};"{instrumento_contractual}";"{traslado_pliegos_txt}";"{observaciones}"\n')
            controles_procesados += 1


        # Guardar el contenido del CSV de controles con formato TTTT_PPPP_AAAAMMDDHHmmSS.csv
        nombre_archivo_controles = f"Controles_{nombre_proyecto_limpio}_{fecha_hora}.csv"
        archivos_generados.append({
            'contenido': csv_controles.getvalue(),
            'nombre_archivo': nombre_archivo_controles
        })
        csv_controles.close()

        # ==================== ARCHIVO 3: REQUISITOS DE CUMPLIMIENTO ====================

        # Obtener requisitos del proyecto
        requisitos = session.query(DatosRequisito).filter(
            DatosRequisito.SIST_ID_SISTEMA == id_sistema
        ).all()

        # Crear el CSV de requisitos en memoria
        csv_requisitos = io.StringIO()
        csv_requisitos.write("Código;Requisito;Base normativa;Aplica;Justif. No aplica;Estado planificación;Justif. planificación;Estado cumplimiento;Justif. cumplimiento;Traslado a pliegos;Instrumento contractual;Obs. pliego;Plan de mejora\n")

        requisitos_procesados = 0
        for dato_req in requisitos:
            # Obtener información del requisito del catálogo
            req_catalogo = session.query(ConfiguracionRequisito).filter(
                ConfiguracionRequisito.ID_REQ == dato_req.REQ_ID_REQU
            ).first()

            codigo = req_catalogo.C_REQUISITO if req_catalogo else ""
            denominacion = req_catalogo.D_REQUISITO if req_catalogo else "Sin descripción"
            base_normativa = req_catalogo.T_BASENORMATIVA if req_catalogo else ""

            # Limpiar para CSV
            denominacion = denominacion.replace('\n', ' ').replace('\r', ' ').replace(';', ',')
            base_normativa = (base_normativa or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',')

            # Estado aplica
            aplica = "Sí" if dato_req.L_APLICA == 1 else ("No" if dato_req.L_APLICA == 0 else "Por decidir")

            # Justificación no aplica
            justif_no_aplica = (dato_req.T_JUSTAPLICA or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')

            # Estado de planificación (obtener descripción)
            estado_planif_texto = "Sin evaluar"
            if dato_req.N_ESTPLANIF:
                estado_planif = session.query(ConfiguracionEstadoRequisito).filter(
                    ConfiguracionEstadoRequisito.ID_ESTREQ == dato_req.N_ESTPLANIF
                ).first()
                if estado_planif:
                    estado_planif_texto = estado_planif.D_ESTADO or "Sin evaluar"

            # Justificación planificación
            justif_planif = (dato_req.T_JUSTPLANIF or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')

            # Estado de cumplimiento (obtener descripción)
            estado_cumpl_texto = "Sin evaluar"
            if dato_req.N_ESTCUMPL:
                estado_cumpl = session.query(ConfiguracionEstadoRequisito).filter(
                    ConfiguracionEstadoRequisito.ID_ESTREQ == dato_req.N_ESTCUMPL
                ).first()
                if estado_cumpl:
                    estado_cumpl_texto = estado_cumpl.D_ESTADO or "Sin evaluar"

            # Justificación cumplimiento
            justif_cumpl = (dato_req.T_JUSTCUMPL or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')

            # Traslado a pliegos
            traslado_pliegos = "Sí" if dato_req.L_TRASLAPLI == 1 else "No"

            # Instrumento contractual (obtener descripción)
            instrumento_texto = "Sin definir"
            if dato_req.V_INSTRCONTR:
                valor_instrumento = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == dato_req.V_INSTRCONTR
                ).first()
                if valor_instrumento:
                    instrumento_texto = valor_instrumento.D_VALOR or "Sin definir"

            # Observaciones pliego
            obs_pliego = (dato_req.T_OBSPLIEGO or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')

            # Plan de mejora
            plan_mejora = (dato_req.T_PLANMEJORA or "").replace('\n', ' ').replace('\r', ' ').replace(';', ',').replace('"', '""')

            # Escribir línea en CSV
            csv_requisitos.write(f'"{codigo}";"{denominacion}";"{base_normativa}";{aplica};"{justif_no_aplica}";"{estado_planif_texto}";"{justif_planif}";"{estado_cumpl_texto}";"{justif_cumpl}";{traslado_pliegos};"{instrumento_texto}";"{obs_pliego}";"{plan_mejora}"\n')
            requisitos_procesados += 1


        # Guardar el contenido del CSV de requisitos
        nombre_archivo_requisitos = f"Requisitos_{nombre_proyecto_limpio}_{fecha_hora}.csv"
        archivos_generados.append({
            'contenido': csv_requisitos.getvalue(),
            'nombre_archivo': nombre_archivo_requisitos
        })
        csv_requisitos.close()


        return {
            'success': True,
            'archivos': archivos_generados
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'mensaje': f'Error al generar anexos CSV: {str(e)}'
        }
    finally:
        session.close()
