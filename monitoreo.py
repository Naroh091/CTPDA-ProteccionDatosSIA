
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
Módulo de Monitoreo para la aplicación de supervisión SIA.

Este módulo gestiona la funcionalidad de monitoreo de controles,
permitiendo visualizar, editar y registrar ejecuciones de controles
en fase de monitoreo.
"""

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from models import (
    Session, DatosControlMonitoreo, Control, ValoresDato,
    DatosActividadMonitoreo, Inicio, ConfiguracionFase, TiposDato
)


def proyecto_en_fase_monitoreo(id_sistema):
    """
    Verifica si el proyecto está en fase de monitoreo.

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        bool: True si está en fase de monitoreo, False en caso contrario
    """
    session = Session()
    try:
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto:
            return False
        return True  # TODO: Implementar lógica real de fases cuando esté disponible
    finally:
        session.close()


def obtener_valores_dominio(codigo_tipo):
    """
    Obtiene los valores de un dominio específico desde IA_VALDAT.

    Args:
        codigo_tipo (str): Código del tipo de dato (ESTMON, MAD, FREC)

    Returns:
        list: Lista de diccionarios con id, valor y descripción
    """
    session = Session()
    try:
        tipo = session.query(TiposDato).filter(TiposDato.C_TIPDAT == codigo_tipo).first()
        if not tipo:
            return []

        valores = session.query(ValoresDato)\
            .filter(ValoresDato.TIDA_ID_TIPDAT == tipo.ID_TIPDAT)\
            .order_by(ValoresDato.C_VALOR)\
            .all()

        return [{
            'id': v.ID_VALDAT,
            'valor': v.C_VALOR,
            'texto': v.D_VALOR
        } for v in valores]

    finally:
        session.close()


def calcular_proxima_fecha(fecha_base, frecuencia_codigo):
    """
    Calcula la próxima fecha de ejecución según la frecuencia.

    Args:
        fecha_base (datetime): Fecha desde la que calcular
        frecuencia_codigo (str): Código de frecuencia ('D', 'S', 'M', 'T', 'SM', 'A', 'P')

    Returns:
        str or None: Próxima fecha en formato 'YYYY-MM-DD' o None si es Ad-Hoc
    """
    if not fecha_base or not frecuencia_codigo:
        return None

    if isinstance(fecha_base, str):
        try:
            fecha_base = datetime.strptime(fecha_base, "%Y-%m-%d")
        except ValueError:
            return None

    proxima_fecha = None

    if frecuencia_codigo == 'D':  # Diaria
        proxima_fecha = fecha_base + timedelta(days=1)
    elif frecuencia_codigo == 'S':  # Semanal
        proxima_fecha = fecha_base + timedelta(days=7)
    elif frecuencia_codigo == 'M':  # Mensual
        proxima_fecha = fecha_base + relativedelta(months=1)
    elif frecuencia_codigo == 'T':  # Trimestral
        proxima_fecha = fecha_base + relativedelta(months=3)
    elif frecuencia_codigo == 'SM':  # Semestral
        proxima_fecha = fecha_base + relativedelta(months=6)
    elif frecuencia_codigo == 'A':  # Anual
        proxima_fecha = fecha_base + relativedelta(years=1)
    elif frecuencia_codigo == 'P':  # Ad-Hoc/Personalizable
        return None

    if proxima_fecha:
        hoy = datetime.now().date()
        if proxima_fecha.date() < hoy:
            proxima_fecha = datetime.combine(hoy, datetime.min.time())
        return proxima_fecha.strftime("%Y-%m-%d")

    return None


def formatear_fecha(fecha_str):
    """
    Convierte una fecha de formato YYYY-MM-DD a d/m/Y.

    Args:
        fecha_str (str): Fecha en formato YYYY-MM-DD

    Returns:
        str: Fecha en formato d/m/Y o cadena vacía si no es válida
    """
    if not fecha_str:
        return ""

    try:
        if isinstance(fecha_str, str):
            # Parsear desde YYYY-MM-DD
            fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d")
            # Formatear a d/m/Y
            return fecha_obj.strftime("%d/%m/%Y")
        elif isinstance(fecha_str, datetime):
            return fecha_str.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        pass

    return fecha_str


def obtener_ultima_fecha_ejecucion(id_datcontmon):
    """
    Obtiene la fecha más reciente de ejecución para un control.

    Args:
        id_datcontmon (int): ID del registro de control en monitoreo

    Returns:
        str or None: Fecha en formato 'YYYY-MM-DD' o None
    """
    session = Session()
    try:
        return session.query(func.max(DatosActividadMonitoreo.F_EJECUCION))\
            .filter(DatosActividadMonitoreo.ACT_ID_CONTMON == id_datcontmon)\
            .scalar() or None
    finally:
        session.close()


def obtener_controles_monitoreo(id_sistema):
    """
    Obtiene todos los controles en monitoreo para un sistema.

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        list: Lista de diccionarios con información de controles
    """
    session = Session()
    try:
        controles_monitoreo = session.query(DatosControlMonitoreo)\
            .join(Control, DatosControlMonitoreo.CON_ID_CONTROL == Control.ID_CONTROL)\
            .filter(DatosControlMonitoreo.SIST_ID_SISTEMA == id_sistema)\
            .order_by(Control.D_CONTROL)\
            .all()

        resultado = []
        for cm in controles_monitoreo:
            ultima_fecha = obtener_ultima_fecha_ejecucion(cm.ID_DATCONTMON)

            resultado.append({
                'id_datcontmon': cm.ID_DATCONTMON,  # ✅ CORREGIDO
                'id_control': cm.CON_ID_CONTROL,
                'c_control': cm.control.C_CONTROL or "",
                'descripcion_control': cm.control.D_CONTROL,
                'descripcion_detallada': cm.control.D_DESCMONITOR or "",
                'estado': cm.estado_valor.D_VALOR if cm.estado_valor else "",
                'estado_id': cm.V_ESTADO,
                'responsable': cm.T_RESP or "",
                'madurez_inicial': cm.madurez_inicial_valor.D_VALOR if cm.madurez_inicial_valor else "",
                'madurez_inicial_id': cm.V_MADINI,
                'madurez_actual': cm.madurez_actual_valor.D_VALOR if cm.madurez_actual_valor else "",
                'madurez_actual_id': cm.V_MADACT,
                'madurez_objetivo': cm.madurez_objetivo_valor.D_VALOR if cm.madurez_objetivo_valor else "",
                'madurez_objetivo_id': cm.V_MADOBJ,
                'frecuencia': cm.frecuencia_valor.D_VALOR if cm.frecuencia_valor else "",
                'frecuencia_id': cm.V_FREC,
                'frecuencia_codigo': cm.frecuencia_valor.C_VALOR_TEXT if cm.frecuencia_valor else "",
                'fecha_ultima_ejecucion': formatear_fecha(ultima_fecha) or "",
                'fecha_proxima_ejecucion': formatear_fecha(cm.F_PROXEJEC) or "",
                'descripcion': cm.T_DESC or ""
            })

        return resultado

    finally:
        session.close()


def obtener_detalle_control(id_datcontmon):
    """
    Obtiene el detalle completo de un control en monitoreo.

    Args:
        id_datcontmon (int): ID del registro de control

    Returns:
        dict: Información completa del control o None si no existe
    """
    session = Session()
    try:
        cm = session.query(DatosControlMonitoreo)\
            .filter(DatosControlMonitoreo.ID_DATCONTMON == id_datcontmon)\
            .first()

        if not cm:
            return None

        ultima_fecha = obtener_ultima_fecha_ejecucion(cm.ID_DATCONTMON)
        estados = obtener_valores_dominio('ESTMON')
        madureces = obtener_valores_dominio('MAD')
        frecuencias = obtener_valores_dominio('FREC')
        frecuencia_codigo = cm.frecuencia_valor.C_VALOR_TEXT if cm.frecuencia_valor else ""

        # ✅ Verificar si hay ejecuciones registradas
        tiene_ejecuciones = session.query(DatosActividadMonitoreo)\
            .filter(DatosActividadMonitoreo.ACT_ID_CONTMON == cm.ID_DATCONTMON)\
            .count() > 0

        return {
            'id_datcontmon': cm.ID_DATCONTMON,
            'id_control': cm.CON_ID_CONTROL,
            'descripcion_control': cm.control.D_CONTROL,
            'estado_id': cm.V_ESTADO,
            'responsable': cm.T_RESP or "",
            'madurez_inicial_id': cm.V_MADINI,
            'madurez_actual_id': cm.V_MADACT,
            'madurez_objetivo_id': cm.V_MADOBJ,
            'frecuencia_id': cm.V_FREC,
            'frecuencia_codigo': frecuencia_codigo,
            'fecha_ultima_ejecucion': ultima_fecha or "",
            'fecha_proxima_ejecucion': cm.F_PROXEJEC or "",
            'descripcion': cm.T_DESC or "",
            'estados': estados,
            'madureces': madureces,
            'frecuencias': frecuencias,
            'tiene_ejecuciones': tiene_ejecuciones  # ✅ NUEVO
        }

    finally:
        session.close()


def actualizar_control_monitoreo(id_datcontmon, campo, valor):  # ✅ CORREGIDO
    """
    Actualiza un campo específico de un control en monitoreo (autoguardado).

    Args:
        id_datcontmon (int): ID del registro
        campo (str): Campo a actualizar
        valor: Nuevo valor

    Returns:
        dict: {"success": bool, "error": str (opcional)}
    """
    session = Session()
    try:
        cm = session.query(DatosControlMonitoreo)\
            .filter(DatosControlMonitoreo.ID_DATCONTMON == id_datcontmon)\
            .first()

        if not cm:
            return {"success": False, "error": "Control no encontrado"}

        if campo == "fecha_ultima":
            if not valor:
                return {"success": False, "error": "La fecha de última ejecución es obligatoria"}
            try:
                datetime.strptime(valor, "%Y-%m-%d")
                ejec_existente = session.query(DatosActividadMonitoreo)\
                    .filter_by(ACT_ID_CONTMON=id_datcontmon, F_EJECUCION=valor)\
                    .first()
                if not ejec_existente:
                    max_id = session.query(func.max(DatosActividadMonitoreo.ID_DATACTMONIT)).scalar()
                    next_id = 110 if max_id is None else max_id + 100
                    nueva_ejec = DatosActividadMonitoreo(
                        ID_DATACTMONIT=next_id,
                        SIST_ID_SISTEMA=cm.SIST_ID_SISTEMA,
                        ACT_ID_CONTMON=id_datcontmon,
                        F_EJECUCION=valor,
                        T_DESCEJEC="Ejecución registrada desde fecha última"
                    )
                    session.add(nueva_ejec)
                session.commit()
                return {"success": True}
            except ValueError:
                return {"success": False, "error": "Formato de fecha inválido"}

        elif campo == "estado":
            cm.V_ESTADO = int(valor) if valor else None
        elif campo == "madurez_actual":
            cm.V_MADACT = int(valor) if valor else None
        elif campo == "madurez_objetivo":
            cm.V_MADOBJ = int(valor) if valor else None
        elif campo == "responsable":
            cm.T_RESP = valor.strip() if valor else ""
        elif campo == "descripcion":
            cm.T_DESC = valor.strip() if valor else ""
        elif campo == "frecuencia":
            cm.V_FREC = int(valor) if valor else None  # ✅ CORREGIDO (era V_FREQ)
            if cm.V_FREC:
                frecuencia_valor = session.query(ValoresDato)\
                    .filter(ValoresDato.ID_VALDAT == cm.V_FREC)\
                    .first()
                if frecuencia_valor:
                    codigo_frec = frecuencia_valor.C_VALOR_TEXT or ""
                    ultima_fecha = obtener_ultima_fecha_ejecucion(cm.ID_DATCONTMON)
                    fecha_base = datetime.strptime(ultima_fecha, "%Y-%m-%d") if ultima_fecha else datetime.now()
                    proxima = calcular_proxima_fecha(fecha_base, codigo_frec)
                    cm.F_PROXEJEC = proxima or ""
        elif campo == "fecha_proxima":
            if cm.frecuencia_valor and cm.frecuencia_valor.C_VALOR_TEXT == 'P':
                try:
                    fecha_nueva = datetime.strptime(valor, "%Y-%m-%d")
                    hoy = datetime.now().date()
                    if fecha_nueva.date() < hoy:
                        return {"success": False, "error": "La fecha no puede ser anterior a la fecha actual"}
                    cm.F_PROXEJEC = valor
                except ValueError:
                    return {"success": False, "error": "Formato de fecha inválido"}
            else:
                return {"success": False, "error": "Solo se puede modificar con frecuencia Personalizable"}
        else:
            return {"success": False, "error": "Campo no válido"}

        session.commit()
        return {"success": True}

    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def obtener_ejecuciones_control(id_datcontmon):
    """
    Obtiene todas las ejecuciones de un control ordenadas por fecha descendente.

    Args:
        id_datcontmon (int): ID del control en monitoreo

    Returns:
        list: Lista de ejecuciones
    """
    session = Session()
    try:
        ejecuciones = session.query(DatosActividadMonitoreo)\
            .filter(DatosActividadMonitoreo.ACT_ID_CONTMON == id_datcontmon)\
            .order_by(DatosActividadMonitoreo.F_EJECUCION.desc())\
            .all()

        return [{
            'id': ej.ID_DATACTMONIT,
            'fecha': ej.F_EJECUCION,
            'descripcion': ej.T_DESCEJEC or ""
        } for ej in ejecuciones]

    finally:
        session.close()


def guardar_ejecucion(id_datcontmon, fecha_ejecucion, descripcion, id_ejecucion=None):  # ✅ CORREGIDO
    """
    Guarda o actualiza una ejecución de control.

    Args:
        id_datcontmon (int): ID del control
        fecha_ejecucion (str): Fecha en formato YYYY-MM-DD
        descripcion (str): Descripción de la ejecución
        id_ejecucion (int, optional): ID para actualizar, None para crear

    Returns:
        dict: {"success": bool, "error": str (opcional), "proxima_fecha": str (opcional)}
    """
    session = Session()
    try:
        if not fecha_ejecucion or not descripcion:
            return {"success": False, "error": "Fecha y descripción son obligatorias"}

        try:
            fecha_obj = datetime.strptime(fecha_ejecucion, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": "Formato de fecha inválido"}

        hoy = datetime.now().date()
        if fecha_obj.date() > hoy:
            return {"success": False, "error": "La fecha no puede ser posterior a la fecha actual"}

        control_mon = session.query(DatosControlMonitoreo)\
            .filter(DatosControlMonitoreo.ID_DATCONTMON == id_datcontmon)\
            .first()

        if not control_mon:
            return {"success": False, "error": "Control no encontrado"}

        if id_ejecucion:
            ejecucion = session.query(DatosActividadMonitoreo)\
                .filter(DatosActividadMonitoreo.ID_DATACTMONIT == id_ejecucion)\
                .first()
            if not ejecucion:
                return {"success": False, "error": "Ejecución no encontrada"}
            ejecucion.F_EJECUCION = fecha_ejecucion
            ejecucion.T_DESCEJEC = descripcion.strip()
        else:
            max_id = session.query(func.max(DatosActividadMonitoreo.ID_DATACTMONIT)).scalar()
            next_id = 110 if max_id is None else max_id + 100
            nueva_ejecucion = DatosActividadMonitoreo(
                ID_DATACTMONIT=next_id,
                SIST_ID_SISTEMA=control_mon.SIST_ID_SISTEMA,
                ACT_ID_CONTMON=id_datcontmon,
                F_EJECUCION=fecha_ejecucion,
                T_DESCEJEC=descripcion.strip()
            )
            session.add(nueva_ejecucion)

        # Recalcular próxima fecha
        proxima_fecha = None
        if control_mon.frecuencia_valor:
            codigo_frec = control_mon.frecuencia_valor.C_VALOR_TEXT or ""
            proxima = calcular_proxima_fecha(fecha_obj, codigo_frec)
            if proxima:
                proxima_fecha = proxima
                control_mon.F_PROXEJEC = proxima_fecha

        session.commit()
        return {"success": True, "proxima_fecha": proxima_fecha}

    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def obtener_detalle_ejecucion(id_ejecucion):
    """
    Obtiene los detalles de una ejecución específica.

    Args:
        id_ejecucion (int): ID de la ejecución

    Returns:
        dict or None: Datos de la ejecución o None si no existe
    """
    session = Session()
    try:
        ejecucion = session.query(DatosActividadMonitoreo)\
            .filter(DatosActividadMonitoreo.ID_DATACTMONIT == id_ejecucion)\
            .first()

        if not ejecucion:
            return None

        return {
            'id': ejecucion.ID_DATACTMONIT,
            'id_datcontmon': ejecucion.ACT_ID_CONTMON,  # ✅ CORREGIDO
            'fecha': ejecucion.F_EJECUCION,
            'descripcion': ejecucion.T_DESCEJEC or ""
        }

    finally:
        session.close()


def guardar_control_completo(
    id_datcontmon, estado, responsable, madurez_actual,
    madurez_objetivo, frecuencia, descripcion, fecha_proxima, fecha_ultima=None
):
    """
    Guarda todos los campos de un control en monitoreo de una sola vez y devuelve
    la información actualizada para refrescar la tabla en el frontend.
    """
    session = Session()
    try:
        cm = session.query(DatosControlMonitoreo).options(
            joinedload(DatosControlMonitoreo.estado_valor),
            joinedload(DatosControlMonitoreo.madurez_inicial_valor),
            joinedload(DatosControlMonitoreo.madurez_actual_valor),
            joinedload(DatosControlMonitoreo.madurez_objetivo_valor),
            joinedload(DatosControlMonitoreo.frecuencia_valor),
            joinedload(DatosControlMonitoreo.control)
        ).filter(DatosControlMonitoreo.ID_DATCONTMON == id_datcontmon).first()

        if not cm:
            return {"success": False, "error": "Control no encontrado"}

        # Actualizar campos en IA_DATCONTMON
        cm.V_ESTADO = int(estado) if estado else None
        cm.T_RESP = responsable or ""
        cm.V_MADACT = int(madurez_actual) if madurez_actual else None
        cm.V_MADOBJ = int(madurez_objetivo) if madurez_objetivo else None
        cm.V_FREC = int(frecuencia) if frecuencia else None
        cm.T_DESC = descripcion or ""

        # ✅ Manejar fecha_ultima solo si NO hay ejecuciones previas
        tiene_ejecuciones = session.query(DatosActividadMonitoreo)\
            .filter(DatosActividadMonitoreo.ACT_ID_CONTMON == id_datcontmon)\
            .count() > 0

        if not tiene_ejecuciones and fecha_ultima:
            try:
                fecha_obj = datetime.strptime(fecha_ultima, "%Y-%m-%d")
                hoy = datetime.now().date()
                if fecha_obj.date() > hoy:
                    return {"success": False, "error": "La fecha de última ejecución no puede ser posterior a hoy"}

                max_id = session.query(func.max(DatosActividadMonitoreo.ID_DATACTMONIT)).scalar()
                next_id = 110 if max_id is None else max_id + 100
                nueva_ejec = DatosActividadMonitoreo(
                    ID_DATACTMONIT=next_id,
                    SIST_ID_SISTEMA=cm.SIST_ID_SISTEMA,
                    ACT_ID_CONTMON=id_datcontmon,
                    F_EJECUCION=fecha_ultima,
                    T_DESCEJEC="Ejecución registrada al configurar control"
                )
                session.add(nueva_ejec)
            except ValueError:
                return {"success": False, "error": "Formato de fecha inválido"}

        # ✅ SIEMPRE recalcular fecha próxima
        if frecuencia:
            frecuencia_valor = session.query(ValoresDato)\
                .filter(ValoresDato.ID_VALDAT == int(frecuencia))\
                .first()

            if frecuencia_valor:
                codigo_frec = frecuencia_valor.C_VALOR_TEXT or ""

                if codigo_frec != 'P':  # No personalizable
                    ultima_fecha = obtener_ultima_fecha_ejecucion(cm.ID_DATCONTMON)
                    if ultima_fecha:
                        fecha_base = datetime.strptime(ultima_fecha, "%Y-%m-%d")
                    else:
                        fecha_base = datetime.now()
                    nueva_proxima = calcular_proxima_fecha(fecha_base, codigo_frec)
                    if nueva_proxima:
                        cm.F_PROXEJEC = nueva_proxima
                else:
                    cm.F_PROXEJEC = fecha_proxima or ""

        session.commit()
        session.refresh(cm)

        # ✅ Armar objeto actualizado para el frontend
        control_actualizado = {
            "estado": cm.estado_valor.D_VALOR if cm.estado_valor else None,
            "responsable": cm.T_RESP,
            "madurez_inicial": cm.madurez_inicial_valor.D_VALOR if cm.madurez_inicial_valor else None,
            "madurez_actual": cm.madurez_actual_valor.D_VALOR if cm.madurez_actual_valor else None,
            "madurez_objetivo": cm.madurez_objetivo_valor.D_VALOR if cm.madurez_objetivo_valor else None,
            "frecuencia": cm.frecuencia_valor.D_VALOR if cm.frecuencia_valor else None,
            "fecha_ultima_ejecucion": obtener_ultima_fecha_ejecucion(cm.ID_DATCONTMON),
            "fecha_proxima_ejecucion": cm.F_PROXEJEC
        }

        return {"success": True, "control_actualizado": control_actualizado}

    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}

    finally:
        session.close()

def eliminar_ejecucion(id_ejecucion):
    """
    Elimina una ejecución de control de la base de datos.

    Args:
        id_ejecucion (int): ID de la ejecución a eliminar

    Returns:
        dict: {"success": bool, "error": str (opcional)}
    """
    session = Session()
    try:
        ejecucion = session.query(DatosActividadMonitoreo)\
            .filter(DatosActividadMonitoreo.ID_DATACTMONIT == id_ejecucion)\
            .first()

        if not ejecucion:
            return {"success": False, "error": "Ejecución no encontrada"}

        # Guardar el ID del control antes de eliminar para recalcular fecha próxima
        id_datcontmon = ejecucion.ACT_ID_CONTMON

        # Eliminar la ejecución
        session.delete(ejecucion)
        session.commit()

        # Recalcular fecha próxima después de eliminar
        control_mon = session.query(DatosControlMonitoreo)\
            .filter(DatosControlMonitoreo.ID_DATCONTMON == id_datcontmon)\
            .first()

        if control_mon and control_mon.frecuencia_valor:
            codigo_frec = control_mon.frecuencia_valor.C_VALOR_TEXT or ""
            if codigo_frec != 'P':  # Solo recalcular si no es Personalizable
                ultima_fecha = obtener_ultima_fecha_ejecucion(id_datcontmon)
                if ultima_fecha:
                    fecha_base = datetime.strptime(ultima_fecha, "%Y-%m-%d")
                else:
                    fecha_base = datetime.now()

                nueva_proxima = calcular_proxima_fecha(fecha_base, codigo_frec)
                if nueva_proxima:
                    control_mon.F_PROXEJEC = nueva_proxima
                    session.commit()

        return {"success": True}

    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

def obtener_estadisticas_monitoreo(id_sistema):
    """
    Calcula y devuelve estadísticas agregadas para el cuadro de mando de monitoreo de un sistema.
    Parámetros
    ----------
    id_sistema : int | str
        Identificador del sistema cuyos controles en monitoreo se deben consultar.
        Se utiliza directamente en la consulta sobre DatosControlMonitoreo.SIST_ID_SISTEMA.
    Comportamiento
    --------------
    - Abre una sesión de base de datos (Session) y cierra la sesión al terminar.
    - Recupera todos los registros de DatosControlMonitoreo asociados al sistema.
    - Para cada control:
        - Determina si está suspendido consultando control.estado_valor.C_VALOR.
          Se considera suspendido si C_VALOR == 0. Si no existe estado o C_VALOR es NULL,
          el control se considera activo por defecto.
        - Cuenta controles activos y suspendidos.
        - Calcula la madurez actual sumando valores numéricos extraídos de
          control.madurez_actual_valor.C_VALOR únicamente para controles no suspendidos.
        - Calcula la madurez inicial sumando valores numéricos extraídos de
          control.madurez_inicial_valor.C_VALOR para todos los controles que tengan ese valor.
        - Cuenta controles cuya próxima ejecución (control.F_PROXEJEC) esté dentro de
          los próximos 30 días contados desde la fecha actual (incluye fechas pasadas
          y fechas futuras <= hoy + 30 días). Acepta F_PROXEJEC como objeto date o
          como string en formato ISO "YYYY-MM-DD".
    - Maneja silenciosamente errores de conversión (ValueError, AttributeError, TypeError)
      para madurez y fecha, ignorando valores inválidos.
    - No lanza excepciones por datos inválidos individuales; sin embargo, pueden
      propagarse errores de la capa de acceso a datos (p. ej. problemas de conexión).
    Valores devueltos
    -----------------
    dict con las siguientes claves:
    - 'total_controles' (int): número total de controles recuperados.
    - 'controles_activos' (int): número de controles considerados activos.
    - 'controles_suspendidos' (int): número de controles considerados suspendidos.
    - 'madurez_promedio_actual' (float): promedio de madurez actual entre los controles
      no suspendidos que disponen de valor, redondeado a 1 decimal. Si no hay valores,
      devuelve 0.
    - 'madurez_promedio_inicial' (float): promedio de madurez inicial entre los controles
      que disponen de valor, redondeado a 1 decimal. Si no hay valores, devuelve 0.
    - 'mejora_madurez' (float): diferencia entre madurez_promedio_actual y
      madurez_promedio_inicial, redondeada a 1 decimal.
    - 'controles_proxima_ejecucion' (int): número de controles no suspendidos cuya
      próxima ejecución está dentro del umbral de 30 días.
    Consideraciones y supuestos
    ---------------------------
    - Se asume que las propiedades relacionadas (estado_valor, madurez_actual_valor,
      madurez_inicial_valor) exponen C_VALOR con el valor numérico en formato convertible a int.
    - La lógica considera como "suspendido" únicamente el caso explícito C_VALOR == 0.
    - Fechas inválidas o formatos inesperados se ignoran sin interrumpir el cómputo.
    - La sesión de base de datos se cierra en un bloque finally para evitar fugas
      de recursos.
    """
    session = Session()
    try:
        from datetime import date

        # Obtener todos los controles del sistema en monitoreo
        controles = session.query(DatosControlMonitoreo)\
            .filter(DatosControlMonitoreo.SIST_ID_SISTEMA == id_sistema)\
            .all()

        # Inicializar contadores
        total_controles = len(controles)
        controles_activos = 0
        controles_suspendidos = 0
        suma_madurez_actual = 0
        suma_madurez_inicial = 0
        controles_con_madurez_actual = 0
        controles_con_madurez_inicial = 0
        controles_proxima_ejecucion = 0

        # Fecha límite (30 días desde hoy)
        hoy = date.today()
        limite_30_dias = hoy + timedelta(days=30)

        for control in controles:
            # Determinar si está activo o suspendido - UNA SOLA VEZ
            # Verificar el estado desde IA_VALDAT
            es_suspendido = False
            if control.estado_valor and control.estado_valor.C_VALOR is not None:
                # El valor 0 corresponde a 'SUSPENDIDO' según la tabla IA_VALDAT
                if control.estado_valor.C_VALOR == 0:
                    es_suspendido = True
            # Si no tiene estado o C_VALOR es NULL, se considera activo por defecto (es_suspendido = False)

            # Contar activos/suspendidos
            if es_suspendido:
                controles_suspendidos += 1
            else:
                controles_activos += 1

            # Calcular madurez actual (solo controles no suspendidos)
            if not es_suspendido and control.V_MADACT and control.madurez_actual_valor:
                try:
                    # ✅ CORRECCIÓN: Obtener el valor numérico desde C_VALOR
                    valor_madurez = int(control.madurez_actual_valor.C_VALOR)
                    suma_madurez_actual += valor_madurez
                    controles_con_madurez_actual += 1
                except (ValueError, AttributeError, TypeError):
                    pass

            # Calcular madurez inicial (todos los controles que la tengan)
            if control.V_MADINI and control.madurez_inicial_valor:
                try:
                    valor_madurez_inicial = int(control.madurez_inicial_valor.C_VALOR)
                    suma_madurez_inicial += valor_madurez_inicial
                    controles_con_madurez_inicial += 1
                except (ValueError, AttributeError, TypeError):
                    pass

            # Contar controles con próxima ejecución en 30 días (solo controles NO suspendidos)
            # Y que tengan una fecha de próxima ejecución definida
            if not es_suspendido and control.F_PROXEJEC:
                try:
                    if isinstance(control.F_PROXEJEC, str):
                        fecha_proxima = datetime.strptime(control.F_PROXEJEC, "%Y-%m-%d").date()
                    else:
                        fecha_proxima = control.F_PROXEJEC

                    # Incluir si la fecha de próxima ejecución es <= hoy + 30 días
                    # Esto incluye fechas pasadas y futuras dentro del rango
                    if fecha_proxima <= limite_30_dias:
                        controles_proxima_ejecucion += 1

                except (ValueError, AttributeError, TypeError):
                    # Si la fecha es inválida, ignora este valor
                    # print(f"Fecha inválida para control {control.ID_DATCONTMON}: {control.F_PROXEJEC}") # Descomentar para debug
                    pass

        # Calcular promedios
        madurez_promedio_actual = round(suma_madurez_actual / controles_con_madurez_actual, 1) if controles_con_madurez_actual > 0 else 0
        madurez_promedio_inicial = round(suma_madurez_inicial / controles_con_madurez_inicial, 1) if controles_con_madurez_inicial > 0 else 0

        # Calcular mejora
        mejora_madurez = round(madurez_promedio_actual - madurez_promedio_inicial, 1)

        return {
            'total_controles': total_controles,
            'controles_activos': controles_activos,
            'controles_suspendidos': controles_suspendidos,
            'madurez_promedio_actual': madurez_promedio_actual,
            'madurez_promedio_inicial': madurez_promedio_inicial,
            'mejora_madurez': mejora_madurez,
            'controles_proxima_ejecucion': controles_proxima_ejecucion
        }

    finally:
        session.close()
