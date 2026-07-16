
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
Módulo de controladores para la gestión de componentes del sistema ADI.

Incluye funciones para:
- Obtener preguntas activas y sus respuestas activas asociadas.
- Obtener subelementos activos agrupados por elemento.
- Consultar el estado de avance de los diferentes componentes del sistema (ADI, Elementos de Descripción, Riesgos, Controles, EIPD).

Estas funciones interactúan con los modelos de datos y la base de datos para facilitar la lógica de negocio de los formularios y el seguimiento del progreso.
"""
import math
import json
import ast
from models import ConfiguracionFase, Inicio, Session, Pregunta, Respuesta, RespuestasProyecto, SubElementosAdi, DatosElementosAdi, Perfil, Riesgo, RiesgoAdiRespuesta, DatosRiesgo, CategoriaRiesgo, ValoresDato, TiposDato, ElementosAdi, DatosControl, Control, GrupoControl, RiesgoControl, ConfiguracionCriticidad, ReglaEIPD, ConfiguracionRequisito, DatosRequisito, ConfiguracionEstadoRequisito, ConfiguracionRequisitoControl, ConfiguracionCluster, ConfiguracionRiesgoCluster, ConfiguracionRiesgoGlobal

from sqlalchemy import and_, or_, exists, select, update, func, tuple_, case



def get_preguntas_activas():
    """
    Obtiene todas las preguntas activas con sus respuestas activas asociadas.

    Realiza una consulta a la base de datos para obtener:
    - Todas las preguntas marcadas como activas (L_ESTADO = 1)
    - Para cada pregunta, filtra sus respuestas manteniendo solo las activas

    Returns:
        list[Pregunta]: Lista de objetos Pregunta con sus respuestas activas.
        Cada pregunta tendrá solo las respuestas con L_ESTADO = 1.

    Note:
        - Utiliza no_autoflush para evitar escrituras no deseadas en la BD
        - Filtra las respuestas en memoria después de la consulta
        - Siempre cierra la sesión de base de datos mediante finally

    Example:
        >>> preguntas_activas = get_preguntas_activas()
        >>> for pregunta in preguntas_activas:
        ...     print(f"Pregunta: {pregunta.D_PREGUNTA}")
        ...     for respuesta in pregunta.respuestas:
        ...         print(f" - Respuesta: {respuesta.D_RESPUESTA}")
    """
    # Crea una nueva sesión de base de datos
    db_session = Session()
    try:
        # Desactiva autoflush para evitar escrituras automáticas no deseadas
        with db_session.no_autoflush:
            # Consulta todas las preguntas activas
            preguntas = db_session.query(Pregunta).filter(Pregunta.L_ESTADO == 1).all()

            # Para cada pregunta, filtra sus respuestas manteniendo solo las activas
            for pregunta in preguntas:
                # Filtrar respuestas activas
                respuestas_activas = [r for r in pregunta.respuestas if r.L_ESTADO == 1]
                # Ordenar por C_OPCION
                pregunta.respuestas = sorted(respuestas_activas, key=lambda r: r.C_OPCION)

            return preguntas
    finally:
        # Asegura que la sesión se cierre siempre, incluso si hay errores
        db_session.close()


def get_subelementos_activos(id_sistema=None):
    """
    Obtiene todos los subelementos activos de la tabla IA_SUBELEMENADI.
    Filtra según la fase actual del proyecto (N_FASEVISUAL <= fase actual).

    Args:
        id_sistema (int, optional): ID del sistema para filtrar los datos.
    Returns:
        list[dict]: Lista de diccionarios con elementos, sus subelementos y datos de control.
    """
    from models import DatosElementoControl

    db_session = Session()
    try:
        # Obtener la fase actual del proyecto
        fase_actual_orden = None
        if id_sistema:
            proyecto = db_session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
            if proyecto and proyecto.N_FASE:
                fase_config = db_session.query(ConfiguracionFase).filter_by(
                    ID_FASE=proyecto.N_FASE
                ).first()
                if fase_config:
                    fase_actual_orden = fase_config.N_ORDEN

        # Construir la consulta base de elementos
        query_elementos = db_session.query(ElementosAdi).filter(ElementosAdi.L_ESTADO == 1)

        # 🔒 FILTRAR POR FASE: Solo elementos con N_FASEVISUAL <= fase actual
        if fase_actual_orden is not None:
            # Subconsulta para obtener N_ORDEN de la fase visual del elemento
            subq_fase_visual = (
                db_session.query(ConfiguracionFase.N_ORDEN)
                .filter(ConfiguracionFase.ID_FASE == ElementosAdi.N_FASEVISUAL)
                .correlate(ElementosAdi)
                .scalar_subquery()
            )

            query_elementos = query_elementos.filter(
                or_(
                    ElementosAdi.N_FASEVISUAL.is_(None),  # Sin fase definida = siempre visible
                    subq_fase_visual <= fase_actual_orden
                )
            )

        elementos_data = query_elementos.order_by(ElementosAdi.N_ORDEN.asc()).all()

        resultado = []
        for elemento in elementos_data:
            # Obtenemos las iteraciones existentes en DatosElementosAdi para ese elemento
            query_iteraciones = (
                db_session.query(DatosElementosAdi.N_ITERACION)
                .filter(DatosElementosAdi.ELE_ID_ELEM == elemento.ID_ELEM)
            )

            # Añadir filtro por sistema
            if id_sistema:
                query_iteraciones = query_iteraciones.filter(
                    DatosElementosAdi.SIST_ID_SISTEMA == id_sistema
                )

            iteraciones = [row.N_ITERACION for row in query_iteraciones.distinct()]

            for n_iteracion in iteraciones:
                subelementos_activos = [s for s in elemento.sub_elementos if s.L_ESTADO == 1]
                subelementos_ordenados = sorted(
                    subelementos_activos,
                    key=lambda s: s.N_SUBORD
                )

                # Obtener datos de control con filtro por sistema
                dato_control = None
                if id_sistema:
                    dato_control = db_session.query(DatosElementoControl).filter(
                        DatosElementoControl.ELE_ID_ELEM == elemento.ID_ELEM,
                        DatosElementoControl.SIST_ID_SISTEMA == id_sistema,
                        DatosElementoControl.N_ITERACION == 0
                    ).first()

                resultado.append(
                    {
                        "elemento": elemento,
                        "n_iteracion": n_iteracion,
                        "subelementos": subelementos_ordenados,
                        "l_traslapli": dato_control.L_TRASLAPLI if dato_control else None,
                        "v_intscondes": dato_control.V_INTSCONDES if dato_control else None,
                        "t_espclausula": dato_control.T_ESPCLAUSULA if dato_control else "",
                        "id_datelemcontr": dato_control.ID_DATELEMCONTR if dato_control else None
                    }
                )

        return resultado
    finally:
        db_session.close()

"""
Método refactorizado para calcular la puntuación ADI de forma totalmente parametrizable.

Este método elimina todos los valores hardcoded y obtiene los parámetros directamente
de las tablas IA_ADIRESP, IA_VALDAT y IA_TIPDAT.

Fórmula: J25 = (J12 × J16 + J18 + J20) × L12

Donde:
- J12 = MAX(J10, MIN_J12) [Base de decisiones con mínimo MIN_J12]
- J10 = Suma de N_PTOSBASE para respuestas de P2 (Naturaleza de decisiones)
      * A (Soporte tareas internas sin decisión sobre personas): 0 puntos
      * B (Apoyo a la decisión humana): 1.5 puntos
      * C (Decisiones automatizadas de impacto limitado): 2.5 puntos
      * D (Decisiones automatizadas con impacto significativo): 4 puntos
- MIN_J12 = Valor mínimo obtenido de IA_VALDAT donde C_VALOR='MINJ12' y tipo='PARAMCALC' (default: 0.5)
- J16 = Máximo de N_MULTIPLICADOR de P3 (multiplicador por tipos de datos: 1.0, 1.3, 1.8, 2.0)
- J18 = Suma de N_ADICIONAL de respuestas de P4 (Colectivos afectados)
- J20 = Suma de N_ADICIONAL de respuestas de P5 (Dificultades RGPD: +0.5 por cada una, excepto L)
- L12 = Máximo de N_AMPLIVULNER de P4 (factor de amplificación por vulnerabilidad: 1.0 o 1.2)

Nota V022: Se eliminó J11 (puntos por evaluación RIA de la antigua P5).
           La antigua P6 (Dificultades RGPD) ahora es P5.
           La antigua P7 (Uso datos personales) ahora es P6.
"""


def to_float(value, default=0.0):
    """
    Convierte cualquier valor a float de manera robusta.

    Maneja:
    - None → default
    - Strings con coma decimal: '0,5' → 0.5
    - Strings con punto decimal: '0.5' → 0.5
    - Números int/float: 1 → 1.0
    - Strings vacíos: '' → default
    - Valores inválidos → default

    Args:
        value: Valor a convertir (puede ser None, str, int, float)
        default: Valor por defecto si la conversión falla (default: 0.0)

    Returns:
        float: Valor convertido o default
    """
    # Si es None, retornar default
    if value is None:
        return default

    # Si ya es un número (int o float), convertir a float
    if isinstance(value, (int, float)):
        return float(value)

    # Si es string, procesar
    if isinstance(value, str):
        # Limpiar espacios
        value = value.strip()

        # Si está vacío, retornar default
        if not value:
            return default

        # Reemplazar coma por punto
        value = value.replace(',', '.')

        # Intentar convertir
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    # Para cualquier otro tipo, retornar default
    return default


def calcular_puntuacion_adi(id_sistema):
    """
    Calcula la puntuación ADI de forma totalmente parametrizable.

    Args:
        id_sistema (int): ID del sistema para el cual calcular la puntuación

    Returns:
        float: Puntuación calculada, None si está incompleto, 0.0 si hay error
    """
    session = Session()
    try:
        # --- 1. Validar completitud ---
        total_preguntas_activas = session.query(Pregunta).filter(
            Pregunta.L_ESTADO == 1
        ).count()

        if total_preguntas_activas == 0:
            return 0.0

        respuestas_dadas = session.query(RespuestasProyecto)\
            .join(Respuesta, Respuesta.ID_RESPUESTA == RespuestasProyecto.RES_ID_RESPUESTA)\
            .join(Pregunta, Pregunta.ID_PREGUNTA == Respuesta.PRE_ID_PREGUNTA)\
            .filter(
                RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                Pregunta.L_ESTADO == 1
            ).count()

        if respuestas_dadas < total_preguntas_activas:
            return None  # ← INCOMPLETO

        # --- 2. Obtener el valor MIN_J12 desde la base de datos ---
        min_j12_query = session.query(ValoresDato.D_VALOR)\
            .join(TiposDato, TiposDato.ID_TIPDAT == ValoresDato.TIDA_ID_TIPDAT)\
            .filter(
                ValoresDato.C_VALOR_TEXT == 'MINJ12',
                TiposDato.C_TIPDAT == 'PARAMCALC'
            ).first()

        # Usar to_float para convertir de manera robusta
        min_j12 = to_float(min_j12_query[0], default=0.5) if min_j12_query else 0.5

        # --- 3. Obtener todas las respuestas seleccionadas para este sistema ---
        respuestas_seleccionadas = session.query(
            Pregunta.C_PREGUNTA,
            Respuesta.N_PTOSBASE,
            Respuesta.N_MULTIPLICADOR,
            Respuesta.N_ADICIONAL,
            Respuesta.N_AMPLIVULNER
        ).select_from(RespuestasProyecto)\
            .join(Respuesta, Respuesta.ID_RESPUESTA == RespuestasProyecto.RES_ID_RESPUESTA)\
            .join(Pregunta, Pregunta.ID_PREGUNTA == Respuesta.PRE_ID_PREGUNTA)\
            .filter(
                RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                Pregunta.L_ESTADO == 1,
                Respuesta.L_ESTADO == 1
            ).all()

        # --- 4. Calcular J10 (suma de N_PTOSBASE de P2 - Naturaleza de decisiones) ---
        # Nota V022: Se eliminó J11 (puntos RIA). Ahora J10 viene SOLO de P2.
        # Técnicamente sumamos todos los N_PTOSBASE, pero solo P2 tiene valores > 0
        j10 = sum(
            to_float(r.N_PTOSBASE, default=0.0)
            for r in respuestas_seleccionadas
        )

        # J12 = MAX(J10, MIN_J12) - Base de decisiones con mínimo garantizado
        j12 = max(j10, min_j12)

        # --- 5. Calcular J16 (máximo multiplicador de P3 - Tipos de datos) ---
        multiplicadores = [
            to_float(r.N_MULTIPLICADOR, default=1.0)
            for r in respuestas_seleccionadas
        ]
        j16 = max(multiplicadores) if multiplicadores else 1.0

        # --- 6. Calcular J18 + J20 (suma de N_ADICIONAL de P4 + P5) ---
        # J18 = Puntos por colectivos afectados (P4)
        # J20 = Puntos por dificultades RGPD (P5, antes P6)
        j18j20 = sum(
            to_float(r.N_ADICIONAL, default=0.0)
            for r in respuestas_seleccionadas
        )

        # --- 7. Calcular L12 (factor amplificación por vulnerabilidad de P4) ---
        # 1.2 si hay colectivos vulnerables (C) o menores (D), 1.0 en otro caso
        amplivulner = [
            to_float(r.N_AMPLIVULNER, default=1.0)
            for r in respuestas_seleccionadas
        ]
        l12 = max(amplivulner) if amplivulner else 1.0

        # --- 8. Calcular puntuación final ---
        # Fórmula: (J12 × J16 + J18 + J20) × L12
        puntuacion = (j12 * j16 + j18j20) * l12

        # Redondear hacia arriba (ceil)
        import math
        resultado = math.ceil(puntuacion)


        return float(resultado)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return 0.0
    finally:
        session.close()



def obtener_perfil_por_puntuacion(session, puntos_adi):
    """
    Obtiene el perfil más adecuado basado en la puntuación ADI.

    Utiliza los campos L_MININCLUSIVO y L_MAXINCLUSIVO de cada perfil para
    determinar si los límites son inclusivos (>= / <=) o exclusivos (> / <).

    Criterios V022:
        - ESENCIAL:   puntuación < 3      (L_MININCLUSIVO=1, L_MAXINCLUSIVO=0)
        - ESTÁNDAR:   puntuación >= 3 Y <= 6 (L_MININCLUSIVO=1, L_MAXINCLUSIVO=1)
        - EXHAUSTIVO: puntuación > 6      (L_MININCLUSIVO=0, L_MAXINCLUSIVO=1)

    Args:
        session (Session): Sesión activa de SQLAlchemy para realizar consultas.
        puntos_adi (float): Puntuación ADI calculada para la búsqueda.

    Returns:
        Perfil | None: Instancia del modelo Perfil que mejor se ajusta a la puntuación,
                       o None si no se encuentra ningún perfil.
    """
    # --- Validar entrada ---
    if puntos_adi is None:
        return None

    # --- Obtener todos los perfiles ordenados por N_PTOSMIN ---
    perfiles = session.query(Perfil).order_by(Perfil.N_PTOSMIN.asc()).all()

    if not perfiles:
        return None

    # --- Buscar el perfil que contenga la puntuación ---
    for perfil in perfiles:
        # Obtener valores de inclusividad (por defecto 1 si no están definidos)
        min_inclusivo = perfil.L_MININCLUSIVO if perfil.L_MININCLUSIVO is not None else 1
        max_inclusivo = perfil.L_MAXINCLUSIVO if perfil.L_MAXINCLUSIVO is not None else 1

        # Verificar límite inferior
        if min_inclusivo == 1:
            cumple_min = puntos_adi >= perfil.N_PTOSMIN
        else:
            cumple_min = puntos_adi > perfil.N_PTOSMIN

        # Verificar límite superior
        if max_inclusivo == 1:
            cumple_max = puntos_adi <= perfil.N_PTOSMAX
        else:
            cumple_max = puntos_adi < perfil.N_PTOSMAX

        # Si cumple ambas condiciones, es el perfil correcto
        if cumple_min and cumple_max:
            return perfil

    # --- Fallback: Si no se encuentra ningún perfil, retornar el último (más alto) ---
    return perfiles[-1]


def actualizar_riesgos_activos_por_p1(session, id_sistema, forzar_actualizacion=False):
    """
    Actualiza los riesgos activos de un sistema en función de las respuestas ADI y la pregunta P1.
    Este método realiza la activación y desactivación de riesgos para un sistema específico, siguiendo la lógica:
        - Si todas las respuestas ADI están completas, se calcula el perfil correspondiente según la puntuación ADI.
        - Si solo está respondida la pregunta P1, se utiliza esa información para determinar el perfil.
        - Desactiva todos los riesgos del sistema (solo modifica el campo L_ACTIVA).
        - Activa riesgos nuevos (nunca evaluados, L_APLICA IS NULL) y les asigna L_APLICA=1.
        - Activa riesgos ya evaluados por el usuario (L_APLICA no es NULL), pero no sobrescribe el valor de L_APLICA.
        - Nunca sobrescribe L_APLICA si ya fue definido por el usuario.
    Parámetros:
        session (Session): Sesión de SQLAlchemy para ejecutar las consultas y actualizaciones.
        id_sistema (int): Identificador del sistema cuyos riesgos se deben actualizar.
        forzar_actualizacion (bool): Si True, desactiva TODOS los riesgos (incluso manuales) y recalcula según nuevas reglas.
        Si False (default), preserva activaciones manuales (L_APLICA=1).
    Excepciones:
        Lanza una excepción si ocurre algún error durante la actualización y revierte la transacción.
    Salida:
        No retorna ningún valor. Imprime información sobre el proceso y los riesgos activados.
    """
    try:

        #--- 1. Obtener perfil según respuestas ADI ---
        puntos_adi = calcular_puntuacion_adi(id_sistema)
        if puntos_adi is None:
            return

        #--- 2. Buscar perfil correspondiente usando la función centralizada ---
        perfil_obj = obtener_perfil_por_puntuacion(session, puntos_adi)
        if not perfil_obj:
            return
        id_perfil = perfil_obj.ID_PERFIL

        # --- 3. Desactivar riesgos según modo forzar_actualizacion ---
        if forzar_actualizacion:
            # MODO FORZADO: Desactivar TODO (incluso manuales) y resetear L_MANUAL
            session.execute(
                update(DatosRiesgo)
                .where(DatosRiesgo.SIST_ID_SISTEMA == id_sistema)
                .values(L_ACTIVA=0, L_MANUAL=0)
            )
        else:
            # MODO PRESERVACIÓN: NO TOCAR los que tienen L_MANUAL=1
            session.execute(
                update(DatosRiesgo)
                .where(
                    and_(
                        DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
                        or_(
                            DatosRiesgo.L_MANUAL == 0,
                            DatosRiesgo.L_MANUAL.is_(None)
                        )
                    )
                )
                .values(L_ACTIVA=0)
            )

            # Contar cuántos manuales hay
            manuales_count = session.query(func.count(DatosRiesgo.ID_DATRIES)).filter(
                DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
                DatosRiesgo.L_MANUAL == 1
            ).scalar()


        # --- 4. Activar riesgos NUEVOS (nunca evaluados) ---
        # 4.1. Subconsulta para riesgos con PRE_ID_PREGUNTA y RESP_ID_RESP informados (se activan SIEMPRE)
        subq_pregunta_respuesta = (
            select(Riesgo.ID_RIESGO, RespuestasProyecto.SIST_ID_SISTEMA)
            .select_from(Riesgo)
            .join(RiesgoAdiRespuesta, Riesgo.ID_RIESGO == RiesgoAdiRespuesta.RIE_ID_RIESGO)
            .join(RespuestasProyecto,
                and_(
                    RespuestasProyecto.RES_ID_RESPUESTA == RiesgoAdiRespuesta.RESP_ID_RESP,
                    RespuestasProyecto.PRE_ID_PREGUNTA == RiesgoAdiRespuesta.PRE_ID_PREGUNTA
                ))
            .where(
                and_(
                    RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                    RiesgoAdiRespuesta.PRE_ID_PREGUNTA.isnot(None),
                    RiesgoAdiRespuesta.RESP_ID_RESP.isnot(None)
                )
            )
            .distinct()
        )

        # 4.2. Subconsulta para riesgos por perfil (lógica anterior)
        subq_perfil = (
            select(Riesgo.ID_RIESGO, RespuestasProyecto.SIST_ID_SISTEMA)
            .select_from(Riesgo)
            .join(RiesgoAdiRespuesta, Riesgo.ID_RIESGO == RiesgoAdiRespuesta.RIE_ID_RIESGO)
            .join(RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == RiesgoAdiRespuesta.RESP_ID_RESP)
            .where(
                and_(
                    RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                    Riesgo.PER_ID_PERFIL <= id_perfil
                )
            )
            .distinct()
        )

        # 4.3. Combinar ambas subconsultas con UNION
        combined_subquery = subq_pregunta_respuesta.union(subq_perfil)

        stmt_nuevos = (
            update(DatosRiesgo)
            .where(
                and_(
                    DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
                    DatosRiesgo.L_APLICA.is_(None),  # Nunca evaluado
                    tuple_(DatosRiesgo.RIE_ID_RIESGO, DatosRiesgo.SIST_ID_SISTEMA).in_(
                        combined_subquery
                    )
                )
            )
            .values(L_ACTIVA=1, L_APLICA=1)
        )

        result_nuevos = session.execute(stmt_nuevos)

        # --- 5. Activar riesgos YA EVALUADOS → solo L_ACTIVA = 1 ---
        # 5.1. Subconsulta para riesgos con PRE_ID_PREGUNTA y RESP_ID_RESP informados (se activan SIEMPRE)
        subq_pregunta_respuesta_eval = (
            select(Riesgo.ID_RIESGO, RespuestasProyecto.SIST_ID_SISTEMA)
            .select_from(Riesgo)
            .join(RiesgoAdiRespuesta, Riesgo.ID_RIESGO == RiesgoAdiRespuesta.RIE_ID_RIESGO)
            .join(RespuestasProyecto,
                and_(
                    RespuestasProyecto.RES_ID_RESPUESTA == RiesgoAdiRespuesta.RESP_ID_RESP,
                    RespuestasProyecto.PRE_ID_PREGUNTA == RiesgoAdiRespuesta.PRE_ID_PREGUNTA
                ))
            .where(
                and_(
                    RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                    RiesgoAdiRespuesta.PRE_ID_PREGUNTA.isnot(None),
                    RiesgoAdiRespuesta.RESP_ID_RESP.isnot(None)
                )
            )
            .distinct()
        )

        # 5.2. Subconsulta para riesgos por perfil (lógica anterior)
        subq_perfil_eval = (
            select(Riesgo.ID_RIESGO, RespuestasProyecto.SIST_ID_SISTEMA)
            .select_from(Riesgo)
            .join(RiesgoAdiRespuesta, Riesgo.ID_RIESGO == RiesgoAdiRespuesta.RIE_ID_RIESGO)
            .join(RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == RiesgoAdiRespuesta.RESP_ID_RESP)
            .where(
                and_(
                    RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                    Riesgo.PER_ID_PERFIL <= id_perfil
                )
            )
            .distinct()
        )

        # 5.3. Combinar ambas subconsultas con UNION
        combined_subquery_eval = subq_pregunta_respuesta_eval.union(subq_perfil_eval)

        stmt_evaluados = (
            update(DatosRiesgo)
            .where(
                and_(
                    DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
                    DatosRiesgo.L_APLICA.isnot(None),  # Ya evaluado por usuario
                    tuple_(DatosRiesgo.RIE_ID_RIESGO, DatosRiesgo.SIST_ID_SISTEMA).in_(
                        combined_subquery_eval
                    )
                )
            )
            .values(L_ACTIVA=1)
        )
        result_evaluados = session.execute(stmt_evaluados)

    except Exception as e:
        session.rollback()
        raise


def actualizar_controles_activos_por_p1(session, id_sistema, forzar_actualizacion=False):
    """
    Inicializa los registros base en IA_DATCONTROL para todos los controles activos y actualiza los controles activos de un sistema según:
        - Los controles específicos vinculados a las respuestas ADI seleccionadas en IA_CONTIPADSQ.
        - El perfil de supervisión calculado a partir de las respuestas ADI.
        - Las exclusiones de grupos de control configuradas en IA_CONACTNO.

    Solo modifica el campo L_ACTIVA en DatosControl:
        - Si un control debe estar activo (vinculado en IA_CONTIPADSQ, perfil adecuado y no excluido) y L_ACTIVA es 0 o NULL, se pone a 1.
        - Si un control no debe estar activo (no vinculado, perfil inadecuado o excluido), se pone L_ACTIVA = 0.
        - Para controles nuevos nunca evaluados, también se asigna L_APLICA=1.
        - No sobrescribe L_APLICA si ya fue definido por el usuario.

    No modifica otros campos ni sobrescribe valores definidos por el usuario.

    Parámetros:
        session (Session): Sesión de SQLAlchemy para ejecutar las consultas y actualizaciones.
        id_sistema (int): Identificador del sistema cuyos controles se deben actualizar.
        forzar_actualizacion (bool): Si True, desactiva TODOS los controles (incluso manuales) y recalcula según nuevas reglas.
                                    Si False (default), preserva activaciones manuales (L_APLICA=1).

    Nueva lógica:
        1. Calcula el perfil del proyecto según las respuestas ADI.
        2. Activa solo los controles que cumplen TODAS estas condiciones:
           a) Están vinculados en IA_CONTIPADSQ a las respuestas ADI seleccionadas.
           b) Tienen PER_ID_PERFIL <= perfil_proyecto (perfil mínimo requerido).
           c) NO pertenecen a grupos excluidos en IA_CONACTNO.
    """
    try:

        # --- 1. INICIALIZACIÓN: Asegurar registros base en IA_DATCONTROL ---
        existe_registro = session.query(DatosControl).filter(DatosControl.SIST_ID_SISTEMA == id_sistema).first()
        if not existe_registro:
            max_id_data = session.query(func.max(DatosControl.ID_DATCONTROL)).scalar() or 0
            id_inicial_bloque = max_id_data + 100
            controles_activos = session.query(Control.ID_CONTROL).filter(Control.L_ESTADO == 1).all()
            for i, (id_control,) in enumerate(controles_activos):
                current_id = id_inicial_bloque + i * 100
                nuevo_dato_control = DatosControl(
                    ID_DATCONTROL=current_id,
                    SIST_ID_SISTEMA=id_sistema,
                    CON_ID_CONTROL=id_control,
                    L_ACTIVA=0
                )
                session.add(nuevo_dato_control)
        else:
            pass

        # --- 2. Obtener TODAS las respuestas del sistema (incluyendo múltiples por pregunta) ---
        # NOTA: Una pregunta puede tener múltiples respuestas (ej: P1 con opciones A,E)
        # Por eso obtenemos los IDs directamente en lugar de usar un diccionario que sobrescribiría
        query_ids_respuestas = (
            session.query(Respuesta.ID_RESPUESTA)
            .join(RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == Respuesta.ID_RESPUESTA)
            .filter(RespuestasProyecto.SIST_ID_SISTEMA == id_sistema)
        )
        ids_respuestas_sistema = [row.ID_RESPUESTA for row in query_ids_respuestas.all()]

        if not ids_respuestas_sistema:
            return

        # --- 3. Recalcular perfil del proyecto ---
        puntos_adi = calcular_puntuacion_adi(id_sistema)

        if puntos_adi is None:
            return

        # Buscar perfil correspondiente
        perfil_obj = obtener_perfil_por_puntuacion(session, puntos_adi)
        if not perfil_obj:
            return
        # Obtener ID de perfil
        id_perfil = perfil_obj.ID_PERFIL

        # --- 4. Obtener controles específicos vinculados a las respuestas seleccionadas en IA_CONTIPADSQ ---
        from models import ControlRespuesta

        controles_vinculados = set()
        query_controles_vinculados = (
            session.query(ControlRespuesta.CON_ID_CONTROL)
            .filter(ControlRespuesta.RESP_ID_RESP.in_(ids_respuestas_sistema))
            .distinct()
        )

        for row in query_controles_vinculados.all():
            controles_vinculados.add(row.CON_ID_CONTROL)


        # --- 5. Obtener grupos de control excluidos por respuestas ADI ---
        # LÓGICA PARA P1 MÚLTIPLE: Un grupo solo se excluye si TODAS las respuestas de P1 lo excluyen
        # Si al menos una respuesta de P1 NO excluye el grupo, entonces NO se excluye
        grupos_excluidos = set()

        if ids_respuestas_sistema:
            from models import ControlActivacionNo

            # Identificar respuestas de P1 (IDs 110-710 corresponden a opciones A-G de P1)
            ids_respuestas_p1 = [r for r in ids_respuestas_sistema if 110 <= r <= 710]

            if ids_respuestas_p1:
                # Obtener todos los grupos que podrían excluirse por alguna respuesta de P1
                query_grupos_potenciales = session.query(
                    ControlActivacionNo.CON_ID_GRUCONTROL
                ).filter(
                    and_(
                        ControlActivacionNo.CON_ID_GRUCONTROL.isnot(None),
                        ControlActivacionNo.PRE_ID_PREGUNTA == 110  # Solo exclusiones de P1
                    )
                ).distinct()

                grupos_potenciales = {row.CON_ID_GRUCONTROL for row in query_grupos_potenciales.all()}

                # Para cada grupo potencial, verificar si TODAS las respuestas de P1 lo excluyen
                for grupo in grupos_potenciales:
                    # Obtener qué respuestas de P1 excluyen este grupo
                    query_resp_excluyen = session.query(
                        ControlActivacionNo.RES_ID_RESPUESTA
                    ).filter(
                        and_(
                            ControlActivacionNo.CON_ID_GRUCONTROL == grupo,
                            ControlActivacionNo.PRE_ID_PREGUNTA == 110
                        )
                    )
                    resp_que_excluyen = {row.RES_ID_RESPUESTA for row in query_resp_excluyen.all()}

                    # Verificar si TODAS las respuestas de P1 seleccionadas excluyen este grupo
                    todas_excluyen = all(r in resp_que_excluyen for r in ids_respuestas_p1)

                    if todas_excluyen:
                        grupos_excluidos.add(grupo)

        else:
            pass

        # --- 6. Desactivar controles según modo forzar_actualizacion ---
        if forzar_actualizacion:
            # MODO FORZADO: Desactivar TODO (incluso manuales) y resetear L_MANUAL
            session.execute(
                update(DatosControl)
                .where(DatosControl.SIST_ID_SISTEMA == id_sistema)
                .values(L_ACTIVA=0, L_MANUAL=0)
            )
        else:
            # MODO PRESERVACIÓN: NO TOCAR los que tienen L_MANUAL=1
            session.execute(
                update(DatosControl)
                .where(
                    and_(
                        DatosControl.SIST_ID_SISTEMA == id_sistema,
                        or_(
                            DatosControl.L_MANUAL == 0,
                            DatosControl.L_MANUAL.is_(None)
                        )
                    )
                )
                .values(L_ACTIVA=0)
            )

            # Contar cuántos manuales hay
            manuales_count = session.query(func.count(DatosControl.ID_DATCONTROL)).filter(
                DatosControl.SIST_ID_SISTEMA == id_sistema,
                DatosControl.L_MANUAL == 1
            ).scalar()


        # --- 7. Activar controles que cumplen TODAS las condiciones:
        #        a) Vinculados en IA_CONTIPADSQ
        #        b) Perfil adecuado (PER_ID_PERFIL <= perfil_proyecto)
        #        c) NO excluidos por grupo de control
        if controles_vinculados:
            # Filtrar controles vinculados que cumplan perfil y NO pertenezcan a grupos excluidos
            query_controles_activar = (
                session.query(DatosControl.ID_DATCONTROL)
                .join(Control, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL)
                .filter(
                    DatosControl.SIST_ID_SISTEMA == id_sistema,
                    Control.L_ESTADO == 1,
                    Control.ID_CONTROL.in_(list(controles_vinculados)),
                    Control.PER_ID_PERFIL <= id_perfil,  # ✅ FILTRO DE PERFIL
                    or_(
                        Control.GRU_ID_CONTROL.notin_(list(grupos_excluidos)) if grupos_excluidos else True,
                        Control.GRU_ID_CONTROL.is_(None)
                    )
                )
            )
            controles_a_activar = [row.ID_DATCONTROL for row in query_controles_activar.all()]

            if controles_a_activar:
                # Activar NUEVOS controles (L_APLICA IS NULL)
                stmt_nuevos = update(DatosControl).where(
                    and_(
                        DatosControl.ID_DATCONTROL.in_(controles_a_activar),
                        DatosControl.L_APLICA.is_(None)
                    )
                ).values(L_ACTIVA=1, L_APLICA=1)
                session.execute(stmt_nuevos)

                # Activar controles YA evaluados (solo L_ACTIVA=1)
                stmt_evaluados = update(DatosControl).where(
                    and_(
                        DatosControl.ID_DATCONTROL.in_(controles_a_activar),
                        DatosControl.L_APLICA.isnot(None)
                    )
                ).values(L_ACTIVA=1)
                session.execute(stmt_evaluados)

            else:
                pass
        else:
            pass

        # --- 8. GARANTIZAR que controles manuales están activos ---
        # En modo PRESERVACIÓN, asegurar que L_MANUAL=1 → L_ACTIVA=1
        if not forzar_actualizacion:
            stmt_manuales = update(DatosControl).where(
                and_(
                    DatosControl.SIST_ID_SISTEMA == id_sistema,
                    DatosControl.L_MANUAL == 1
                )
            ).values(L_ACTIVA=1)
            result = session.execute(stmt_manuales)
            if result.rowcount > 0:
                pass



    except Exception as e:
        session.rollback()
        raise



def get_estado_componentes(id_sistema):
    """
    Obtiene el estado de avance de los diferentes componentes de un sistema dado su ID.
    Parámetros:
        id_sistema (int): Identificador único del sistema para el cual se desea obtener el estado de los componentes.
    Returns:
        list[dict]: Una lista de diccionarios, cada uno representando un componente con las siguientes claves:
            - "nombre": Nombre del componente.
            - "estado": Estado actual del componente ("Pendiente", "En progreso", "Completo", etc.).
            - "tiempo": Tiempo estimado para completar el componente.
            - "ruta": Ruta asociada al formulario o sección del componente.
    Notas:
        - Si no se proporciona un id_sistema válido o ocurre un error, se devuelven los valores por defecto.
        - Actualmente, la lógica detallada solo está implementada para los componentes "ADI" y "Elementos de Descripción".
        - Los estados de "Riesgos (AARR)", "Controles" y "EIPD" están pendientes de implementación.
    """

    session = Session()

    # Valores por defecto
    default_components = [
        {"nombre": "ADI", "estado": "Pendiente", "tiempo": "1-1.5 horas", "ruta": "/formulario/adi"},
        {"nombre": "Elementos de Descripción", "estado": "Pendiente", "tiempo": "6-8 horas", "ruta": "/formulario/adi_elementos"},
        {"nombre": "Riesgos (AARR)", "estado": "Pendiente", "tiempo": "Variable", "ruta": "/formulario/riesgos"},
        {"nombre": "Controles", "estado": "Pendiente", "tiempo": "Variable", "ruta": "/formulario/controles"},
        {"nombre": "EIPD", "estado": "En progreso", "tiempo": "1-2 horas", "ruta": "/formulario/resultados"},
        {"nombre": "Elaboración EIPD", "estado": "Pendiente", "tiempo": "", "ruta": None},
    ]

    try:
        # --- Validación de entrada ---
        if not id_sistema:
            # Si no hay ID, devolver por defecto
            return default_components

        # --- Estado Preguntas ADI ---
        total_preguntas = session.query(Pregunta).filter(Pregunta.L_ESTADO == 1).count()
        respondidas = session.query(RespuestasProyecto).filter(
            RespuestasProyecto.SIST_ID_SISTEMA == id_sistema
        ).count()

        # Lógica de estado para ADI robusta
        if total_preguntas is None or total_preguntas == 0:
            estado_adi = "Pendiente" # O "No Aplicable" si lo prefieres
        elif respondidas is None or respondidas == 0:
            estado_adi = "Pendiente"
        elif respondidas < total_preguntas:
            estado_adi = "En progreso"
        else: # respondidas >= total_preguntas
            estado_adi = "Completo"

        # --- Cálculo de Puntuación ADI ---
        # Obtener respuestas del sistema para calcular la puntuación
        respuestas = {}
        query_respuestas = (
            session.query(Pregunta.C_PREGUNTA, Respuesta.C_OPCION, Respuesta.N_PTOSBASE)
            .join(Respuesta, Respuesta.PRE_ID_PREGUNTA == Pregunta.ID_PREGUNTA)
            .join(RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == Respuesta.ID_RESPUESTA)
            .filter(RespuestasProyecto.SIST_ID_SISTEMA == id_sistema)
        )
        for cod_preg, opcion, puntos in query_respuestas:
            respuestas[cod_preg] = (opcion, puntos)

        # Cálculo de puntos ADI (manejo seguro de None)
        #puntos_adi = calcular_puntuacion_adi(id_sistema)


        # --- Estado Elementos de Descripción ---
        total_subelementos = session.query(SubElementosAdi).join(SubElementosAdi.elemento).filter(ElementosAdi.L_ESTADO == 1, SubElementosAdi.L_ESTADO == 1).count()
        completados = session.query(DatosElementosAdi).join(DatosElementosAdi.elemento).join(DatosElementosAdi.sub_elemento).filter(
            ElementosAdi.L_ESTADO == 1,
            SubElementosAdi.L_ESTADO == 1,
            DatosElementosAdi.SIST_ID_SISTEMA == id_sistema,
            DatosElementosAdi.T_DESCRIPCION.isnot(None)
        ).count()

        # Lógica de estado para Elementos de Descripción robusta
        if total_subelementos is None or total_subelementos == 0:
            estado_elem = "Pendiente" # O "No Aplicable"
        elif completados is None or completados == 0:
            estado_elem = "Pendiente"
        elif completados < total_subelementos:
            estado_elem = "En progreso"
        else: # completados >= total_subelementos
            estado_elem = "Completo"

        # --- Estado Riesgos (AARR) - LÓGICA ACTUALIZADA ---
        # Contar riesgos activos
        total_riesgos_activos = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1
        ).count()

        # Contar riesgos completos SOLO ENTRE LOS ACTIVOS
        riesgos_completos = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1,
            DatosRiesgo.L_APLICA.isnot(None),
            or_(
                and_(DatosRiesgo.L_APLICA == 0),  # Si no aplica, está completo
                and_(
                    DatosRiesgo.L_APLICA == 1,
                    DatosRiesgo.V_PROBABILIDAD.isnot(None),
                    DatosRiesgo.V_IMPACTO.isnot(None)
                )
            )
        ).count()

        # --- Lógica de estado ---
        if total_riesgos_activos == 0:
            estado_riesgos = "Completo"
        elif riesgos_completos == total_riesgos_activos:
            estado_riesgos = "Completo"
        elif riesgos_completos > 0:
            estado_riesgos = f"En progreso: {total_riesgos_activos - riesgos_completos} restantes"
        else:
            estado_riesgos = f"Pendiente: {total_riesgos_activos}"


        # --- Estado Controles ---
        total_controles_activos = session.query(DatosControl).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema,
            DatosControl.L_ACTIVA == 1
        ).count()


        # Contar controles completos SOLO ENTRE LOS ACTIVOS
        # Asumiendo que "completo" implica que L_APLICA ha sido definido (0 o 1)
        controles_completos = session.query(DatosControl).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema,
            DatosControl.L_ACTIVA == 1,
            DatosControl.L_APLICA.isnot(None) # No es NULL
        ).filter(
            or_(
                DatosControl.L_APLICA == 0,  # No aplica
                and_(
                    DatosControl.L_APLICA == 1,  # Aplica
                    func.length(DatosControl.T_ESPCLAUSULA) > 10  # Y tiene justificación
                )
            )
        ).count()

        # --- Lógica de estado para Controles ---
        if total_controles_activos == 0:
            estado_controles = "Completo" # No hay controles activos para evaluar
        elif controles_completos == total_controles_activos:
            estado_controles = "Completo"
        elif controles_completos > 0:
            estado_controles = f"En progreso: {total_controles_activos - controles_completos} restantes"
        else:
            estado_controles = f"Pendiente: {total_controles_activos}"


        estado_eipd = "Pendiente"
        elaboracion_eipd = "Pendiente"

        # Devolver todos los estados
        return [
            {"nombre": "ADI", "estado": estado_adi, "tiempo": "1-1.5 horas", "ruta": "/formulario/adi"},
            {"nombre": "Elementos de Descripción", "estado": estado_elem, "tiempo": "6-8 horas", "ruta": "/formulario/adi_elementos"},
            {"nombre": "Riesgos (AARR)", "estado": estado_riesgos, "tiempo": "Variable", "ruta": "/formulario/riesgos"},
            {"nombre": "Controles", "estado": estado_controles, "tiempo": "Variable", "ruta": "/formulario/controles"},
            {"nombre": "EIPD", "estado": estado_eipd, "tiempo": "1-2 horas", "ruta": "/formulario/resultados"},
            {"nombre": "Elaboración EIPD", "estado": elaboracion_eipd, "tiempo": "", "ruta": None},
        ]

    except Exception as e:
        # Registrar el error puede ser útil para depuración
        # En caso de cualquier error, devolver la lista por defecto
        return default_components

    finally:
        session.close()


def get_configuracion_automatica(id_sistema):
    """
    Calcula y devuelve la configuración automática detectada para un sistema/proyecto,
    obteniendo los perfiles de supervisión exclusivamente de la tabla IA_PERFIL.
        id_sistema (int): ID del sistema o proyecto para el que se calculará la configuración.
        dict: Diccionario con los siguientes datos calculados:
            - tipo_adquisicion (str): Tipo de adquisición detectado (P1).
            - perfil_supervision (str): Perfil de supervisión determinado según la puntuación ADI.
            - tiempo_estimado_perfil (str): Tiempo estimado asociado al perfil de supervisión.
            - necesidad_eipd (str): Indica si es necesaria la EIPD ("NECESARIA" o "NO NECESARIA").
            - grupos_control (str): Lista separada por comas de los grupos de control aplicables.
            - grupos_count (str): Número de grupos de controles aplicables.
            - riesgos_aarr (str): Número de riesgos AARR detectados.
            - controles_totales (str): Número total de controles aplicables.
            - tiempo_1_6 (str): Tiempo estimado para los puntos 1 a 6.
            - tiempo_aarr (str): Tiempo estimado para los riesgos AARR.
            - tiempo_controles (str): Tiempo estimado para los controles aplicables.
            - tiempo_total (str): Tiempo total estimado para la supervisión.
            - validaciones (list): Lista de validaciones automáticas realizadas, cada una como dict con:
                - icon (str): Icono de validación (ej. "✅", "⚠️").
                - msg (str): Mensaje descriptivo de la validación.
    Notas:
        - Si el id_sistema es inválido o ocurre un error, se devuelve un diccionario vacío.
        - La puntuación ADI se calcula en base a las respuestas del sistema y determina el perfil de supervisión.
        - Los grupos de control se determinan por las respuestas a las preguntas P7-P13 con opción 'B'.
        - Incluye validaciones automáticas sobre controles, riesgos, carga y puntuación ADI.
    """
    if not id_sistema:
        return {}

    session = None
    try:
        # Importaciones locales para evitar problemas de importación
        #from models import Session, Pregunta, Respuesta, RespuestasProyecto, Perfil, DatosRiesgo

        session = Session()

        # Asegurar riesgos activos antes de consultar
        # IMPORTANTE: forzar_actualizacion=True porque se está recalculando configuración (cambios en ADI)
        actualizar_riesgos_activos_por_p1(session, id_sistema, forzar_actualizacion=False)
        # Asegurar controles activos antes de consultar
        # IMPORTANTE: forzar_actualizacion=True porque se está recalculando configuración (cambios en ADI)
        actualizar_controles_activos_por_p1(session, id_sistema, forzar_actualizacion=False)
        session.commit()

        # Obtener respuestas del sistema
        respuestas = {}
        query_respuestas = (
            session.query(Pregunta.C_PREGUNTA, Respuesta.C_OPCION, Respuesta.N_PTOSBASE)
            .join(Respuesta, Respuesta.PRE_ID_PREGUNTA == Pregunta.ID_PREGUNTA)
            .join(RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == Respuesta.ID_RESPUESTA)
            .filter(RespuestasProyecto.SIST_ID_SISTEMA == id_sistema)
        )
        for cod_preg, opcion, puntos in query_respuestas:
            respuestas[cod_preg] = (opcion, puntos)

        # --- 1. Tipo de Adquisición (P1) - SELECCIÓN MÚLTIPLE ---
        # Obtener TODAS las respuestas seleccionadas para P1
        query_p1 = (
            session.query(Respuesta.C_OPCION, Respuesta.D_RESPUESTA)
            .join(RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == Respuesta.ID_RESPUESTA)
            .join(Pregunta, Pregunta.ID_PREGUNTA == Respuesta.PRE_ID_PREGUNTA)
            .filter(
                RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
                Pregunta.C_PREGUNTA == 'P1'
            )
            .order_by(Respuesta.C_OPCION)  # Ordenar alfabéticamente
        ).all()

        if query_p1:
            # Concatenar códigos de opción con ";"
            codigos = [row[0] for row in query_p1]
            tipo_adquisicion = ";".join(codigos)
            # Concatenar descripciones con ";"
            descripciones = [row[1] for row in query_p1]
            d_respuesta = ";".join(descripciones)
        else:
            tipo_adquisicion = "No respondida"
            d_respuesta = "Pendiente de respuesta a todas las preguntas del ADI"

        # --- 2. Cálculo de puntos ADI (manejo seguro de None) ---
        puntos_adi = calcular_puntuacion_adi(id_sistema)

        if puntos_adi is None:
            return {
                "tipo_adquisicion": "No respondida",
                "tipo_adquisicion_texto": "Pendiente de respuesta a todas las preguntas del ADI",
                "perfil_supervision": "Perfil no calculado",
                "tiempo_estimado_perfil": "—",
                "necesidad_eipd": "PENDIENTE",
                "grupos_control": "—",
                "grupos_count": "0 grupos",
                "riesgos_aarr": "0 riesgos",
                "controles_totales": "0 controles",
                "tiempo_1_6": "0",
                "tiempo_aarr": "0",
                "tiempo_controles": "0",
                "tiempo_total": "0 horas",
                "validaciones": [
                    {"icon": "⚠️", "msg": "Cuestionario ADI incompleto. Complete todas las preguntas."},
                    {"icon": "ℹ️", "msg": "Riesgos y controles no activados."}
                ]
            }

        # --- 3. Perfil de Supervisión (EXCLUSIVAMENTE desde BD) ---

        # Consulta DIRECTA a la base de datos (sin conversiones intermedias)
        perfil_obj = obtener_perfil_por_puntuacion(session, puntos_adi)
        if perfil_obj:
            perfil = perfil_obj.D_PERFIL
            tiempo_estimado_perfil = perfil_obj.TIEMPO_ESTIMADO or "No disponible"
        else:
            perfil = "No disponible"
            tiempo_estimado_perfil = "No disponible"

        # --- 4. Grupos de Control Aplicables (basado en controles activos en IA_DATCONTROL) ---
        # Contar los grupos de control distintos de los controles activos
        num_grupos = session.query(GrupoControl.ID_GRUCONTROL).distinct()\
            .join(Control, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL)\
            .join(DatosControl, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL)\
            .filter(
                DatosControl.SIST_ID_SISTEMA == id_sistema,
                DatosControl.L_ACTIVA == 1
            )\
            .count()

        # --- 5. Controles Totales ---
        total_controles_activos = session.query(DatosControl).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema,
            DatosControl.L_ACTIVA == 1
        ).count()
        controles = total_controles_activos


        # --- 6. Riesgos AARR - ACTUALIZADO CON CONTEO DE ACTIVOS ---
        # Contar riesgos activos DESPUÉS de la actualización
        total_riesgos_activos = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1
        ).count()
        riesgos = total_riesgos_activos # Mostrar el número de riesgos activos

        # --- 7. Tiempos ---
        tiempo_1_6 = 2.1
        tiempo_aarr = 0.5
        tiempo_controles = num_grupos * 0.5  # 0.5h por grupo
        tiempo_total = round(tiempo_1_6 + tiempo_aarr + tiempo_controles, 1)

        # --- 8. Validaciones Automáticas ---
        validaciones = []

        # Validación 1: Controles aplicables válidos
        if num_grupos > 0:
            validaciones.append({"icon": "✅", "msg": "Controles aplicables válidos"})
        else:
            validaciones.append({"icon": "⚠️", "msg": "Ningún control aplicable"})

        # Validación 2: Pocos riesgos
        if riesgos < 15:
            validaciones.append({"icon": "⚠️", "msg": f"Pocos riesgos aplicables ({riesgos})"})
        else:
            validaciones.append({"icon": "✅", "msg": f"Riesgos aplicables adecuados ({riesgos})"})

        # Validación 3: Carga equilibrada
        if 50 <= controles <= 60:
            validaciones.append({"icon": "✅", "msg": f"Carga preguntas equilibrada ({controles})"})
        else:
            validaciones.append({"icon": "⚠️", "msg": f"Carga desequilibrada ({controles})"})

        # Validación 4: Puntuación ADI válida
        if 0 <= puntos_adi <= 25:
            validaciones.append({"icon": "✅", "msg": "Puntuación ADI válida"})
        else:
            validaciones.append({"icon": "⚠️", "msg": "Puntuación ADI fuera de rango"})

        # Determinación de la Necesidad de EIPD

        necesidad_eipd = evaluar_necesidad_eipd_lambda(id_sistema, session)

        # 🆕 ACTUALIZAR DOCUMENTOS NECESARIOS según resultado de EIPD
        try:
            from documentos import actualizar_documentos_necesarios
            resumen_docs = actualizar_documentos_necesarios(session, id_sistema, necesidad_eipd)
            #print(f"✅ Documentos actualizados: {resumen_docs}")
            # Hacer commit de los cambios en documentos
            session.commit()
        except Exception as e:
            #print(f"⚠️ Error al actualizar documentos necesarios: {e}")
            # No fallar completamente si hay error en documentos
            session.rollback()

        # --- Devolver todos los datos ---
        return {
            "tipo_adquisicion": tipo_adquisicion,
            "tipo_adquisicion_texto": d_respuesta,
            "perfil_supervision": perfil,
            "tiempo_estimado_perfil": tiempo_estimado_perfil,
            "necesidad_eipd": necesidad_eipd,
            "grupos_control": f"{num_grupos} grupos",
            "grupos_count": f"{num_grupos} grupos de controles",
            "riesgos_aarr": f"{riesgos} riesgos",
            "controles_totales": f"{controles} controles",
            "tiempo_1_6": str(tiempo_1_6),
            "tiempo_aarr": str(tiempo_aarr),
            "tiempo_controles": str(tiempo_controles),
            "tiempo_total": f"{tiempo_total} horas",
            "validaciones": validaciones
        }

    except Exception:
        return {}
    finally:
        if session:
            session.close()

def get_ayuda_preguntas(pregunta_id):
    """
    Devuelve el texto de ayuda para una pregunta específica según su ID.

    Parámetros:
        pregunta_id (int): El ID de la pregunta para la cual se solicita la ayuda.

    Returns:
        str: Texto HTML con la ayuda correspondiente a la pregunta, o un mensaje por defecto si no existe ayuda.

    Notas:
        - Los IDs coinciden con ID_PREGUNTA en la tabla IA_ADIPREG.
        - El texto de ayuda se obtiene del campo T_AYUDA de la tabla IA_ADIPREG.
        - Si el ID no se encuentra o no tiene ayuda, se devuelve "No hay ayuda disponible para esta pregunta."
    """
    session = Session()
    try:
        # Buscar la pregunta por ID
        pregunta = session.query(Pregunta).filter(
            Pregunta.ID_PREGUNTA == pregunta_id
        ).first()

        # Si existe la pregunta y tiene texto de ayuda, devolverlo
        if pregunta and pregunta.T_AYUDA:
            return pregunta.T_AYUDA
        else:
            return "No hay ayuda disponible para esta pregunta."

    except Exception as e:
        return "No hay ayuda disponible para esta pregunta."
    finally:
        session.close()

def convertir_criticidad_a_nivel(criticidad):
    """
    Convierte un valor numérico de criticidad a su nivel textual de riesgo.
    Parámetros:
        criticidad (float | None): Valor numérico de criticidad. Puede ser None.
    Retorna:
        str: Nivel de riesgo correspondiente:
            - "CRÍTICO" si criticidad >= 15
            - "ALTO" si criticidad >= 9 y < 15
            - "MEDIO" si criticidad >= 5 y < 9
            - "BAJO" si criticidad > 0 y < 5
            - "—" si criticidad es None o <= 0
    Notas:
        - La función maneja valores None y negativos devolviendo "—".
        - Los valores de criticidad deben ser numéricos (float o int).
    """
    if criticidad is None:
        return "—"

    if criticidad >= 15:
        return "CRÍTICO"
    elif criticidad >= 9:
        return "ALTO"
    elif criticidad >= 5:
        return "MEDIO"
    elif criticidad > 0:
        return "BAJO"
    else:
        return "—"


def calcular_riesgo_residual(session, datos_riesgo, criticidad_inherente):
    """
    Calcula el riesgo residual para un registro de DatosRiesgo, considerando los controles asociados y su madurez.

    Para riesgos personalizados (RIE_ID_RIESGO = NULL) con V_RIERESID informado, usa el valor manual.
    Para riesgos normales o personalizados sin V_RIERESID, calcula basado en controles.

    Args:
        session: Sesión activa de SQLAlchemy.
        datos_riesgo: Instancia de DatosRiesgo (puede ser None para riesgos nuevos).
        criticidad_inherente: Valor numérico del riesgo inherente (criticidad).
    Returns:
        - riesgo_residual_numerico (float or None): Valor calculado del riesgo residual, redondeado a 2 decimales. Si no es posible calcular, retorna None.
        - nivel_riesgo_residual_texto (str): Nivel textual del riesgo residual, según la criticidad. Si no es posible calcular, retorna "—".
        - tuple: (riesgo_residual_numerico, nivel_riesgo_residual_texto)
    Notas:
        - Si no hay controles asociados o ocurre un error, el riesgo residual será igual al riesgo inherente.
        - El cálculo pondera la madurez de los controles activos y aplicables, ajustando el riesgo inherente según la efectividad de los controles.
        - La función maneja excepciones y retorna valores por defecto en caso de error.
    """
    try:
        if criticidad_inherente is None:
            return (None, "—")

        if datos_riesgo is None:
            return (criticidad_inherente, convertir_criticidad_a_nivel(criticidad_inherente))


        # ✅ NUEVO: Verificar si es un riesgo personalizado con V_RIERESID informado
        # Los riesgos personalizados se identifican por L_MANUAL=1
        if datos_riesgo.L_MANUAL == 1 and datos_riesgo.V_RIERESID is not None:

            # Obtener el valor del riesgo residual desde IA_VALDAT
            valor_residual = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == datos_riesgo.V_RIERESID
            ).first()

            if valor_residual:
                # Usar el C_VALOR como criticidad numérica del riesgo residual
                riesgo_residual_numerico = float(valor_residual.C_VALOR)
                nivel_residual_texto = valor_residual.D_VALOR

                return (riesgo_residual_numerico, nivel_residual_texto)
            else:
                pass
                # Continuar con cálculo normal

        # Variables para cálculo
        efectividad = 0.0
        peso_total = 0.0

        # Obtener y procesar controles
        controles_riesgo = session.query(RiesgoControl).filter(
            RiesgoControl.RIE_ID_RIESGO == datos_riesgo.RIE_ID_RIESGO
        ).all()

        for control_riesgo in controles_riesgo:
            peso = control_riesgo.PESO if control_riesgo.PESO is not None else 0
            if peso == 0:
                continue

            # Buscar DatosControl
            dato_control = session.query(DatosControl).filter(
                DatosControl.SIST_ID_SISTEMA == datos_riesgo.SIST_ID_SISTEMA,
                DatosControl.CON_ID_CONTROL == control_riesgo.CON_ID_CONTROL,
                DatosControl.L_ACTIVA == 1,
                DatosControl.L_APLICA == 1
            ).first()

            if not dato_control:
                continue

            # Obtener madurez
            madurez_valor = 1
            if dato_control.V_MADUREZ:
                valor_dato = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == dato_control.V_MADUREZ
                ).first()
                if valor_dato and valor_dato.C_VALOR is not None:
                    madurez_valor = valor_dato.C_VALOR

            # Acumular
            efectividad += (madurez_valor - 1) * peso
            peso_total += peso

        # Calcular riesgo residual
        if peso_total == 0:
            return (criticidad_inherente, convertir_criticidad_a_nivel(criticidad_inherente))

        epond = efectividad / peso_total
        factor_reduccion = 0.9 * (epond / 3.0)

        if factor_reduccion > 1:
            factor_reduccion = 1.0

        riesgo_residual = criticidad_inherente * (1 - factor_reduccion)
        riesgo_residual = round(riesgo_residual, 2)
        nivel_residual = convertir_criticidad_a_nivel(riesgo_residual)


        return (riesgo_residual, nivel_residual)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return (criticidad_inherente, convertir_criticidad_a_nivel(criticidad_inherente))

def get_riesgos_para_formulario(id_sistema, todos_riesgos=False):
    """"
    Obtiene los riesgos asociados a un sistema para su representación en un formulario.
    Args:
        id_sistema (int): Identificador del sistema para el cual se consultan los riesgos.
        todos_riesgos (bool, opcional): Si es True, retorna todos los riesgos definidos en el catálogo,
            incluyendo los que aún no han sido evaluados para el sistema, SIN FILTROS DE FASE.
            Si es False, retorna solo los riesgos activos y filtrados por fase visual. Por defecto es False.
    Returns:
        dict: Diccionario con la siguiente estructura:
            {
                "riesgos": list,  # Lista de riesgos enriquecidos con información de evaluación y controles
                "impactos": list,  # Lista de valores de impacto disponibles (id, valor, texto)
                "probabilidades": list,  # Lista de valores de probabilidad disponibles (id, valor, texto)
                "niveles_riesgo": list,  # Lista de niveles de riesgo (valor, texto)
                "modo_todos": bool,  # Indica si se retornaron todos los riesgos (True) o solo los activos (False)
                "todos_completos": bool,  # Indica si todos los riesgos aplicables están completamente evaluados
            }
        - "riesgos": Cada elemento es un diccionario con detalles del riesgo, su evaluación y controles.
        - "impactos" y "probabilidades": Listas de diccionarios con id, valor y texto para los dominios.
        - "niveles_riesgo": Lista de diccionarios con valor y texto para los niveles de riesgo.
        - "modo_todos": True si se consultaron todos los riesgos, False si solo los activos.
        - "todos_completos": True si todos los riesgos aplicables están completos, False si falta alguno.
    Notas:
        - Cada elemento de la lista "riesgos" contiene información detallada sobre el riesgo, su evaluación,
        controles de mitigación y estado de completitud.
        - El cálculo de criticidad y nivel de riesgo se realiza en base a los valores de impacto y probabilidad.
        - El campo "todos_completos" es útil para validar si el formulario puede considerarse finalizado.
        - En modo normal, solo se muestran riesgos cuya fase visual (N_FASEVISUAL) sea igual o anterior a la fase actual.
        - En modo "Ver Todos", se muestran TODOS los riesgos sin filtro de fase.
    """

    session = Session()
    try:
        # === 0. Fase actual ===
        fase_actual_orden = None
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if proyecto and proyecto.N_FASE:
            fase_conf = session.query(ConfiguracionFase).filter_by(ID_FASE=proyecto.N_FASE).first()
            if fase_conf:
                fase_actual_orden = fase_conf.N_ORDEN

        # === 1. Dominios ===
        def _valores(codigo):
            tipo = session.query(TiposDato).filter_by(C_TIPDAT=codigo).first()
            if not tipo:
                return []
            return (
                session.query(ValoresDato)
                .filter_by(TIDA_ID_TIPDAT=tipo.ID_TIPDAT)
                .order_by(ValoresDato.C_VALOR)
                .all()
            )

        impactos = [{"id": v.ID_VALDAT, "valor": v.C_VALOR, "texto": v.D_VALOR} for v in _valores("IMPA")]
        probabilidades = [{"id": v.ID_VALDAT, "valor": v.C_VALOR, "texto": v.D_VALOR} for v in _valores("PRO")]
        niveles = [{"id": v.ID_VALDAT, "valor": v.C_VALOR, "texto": v.D_VALOR} for v in _valores("NIVR")]


        # === Obtener valores de riesgo residual disponibles ===
        tipo_nivrie = session.query(TiposDato).filter_by(C_TIPDAT='NIVRIE').first()
        valores_riesgo = []
        if tipo_nivrie:
            valores_riesgo = [
                {
                    "id": v.ID_VALDAT,
                    "texto": v.D_VALOR,
                    "codigo": v.C_VALOR
                }
                for v in session.query(ValoresDato).filter_by(
                    TIDA_ID_TIPDAT=tipo_nivrie.ID_TIPDAT
                ).order_by(ValoresDato.C_VALOR.desc()).all()  # Ordenar de mayor a menor riesgo
            ]

        # === 2. Datos del sistema ===
        datos_riesgos = session.query(DatosRiesgo).filter_by(SIST_ID_SISTEMA=id_sistema).all()
        mapa_datos = {r.RIE_ID_RIESGO: r for r in datos_riesgos}

        # === 3. Consulta base ===
        subq_fase_visual = (
            session.query(ConfiguracionFase.N_ORDEN)
            .filter(ConfiguracionFase.ID_FASE == Riesgo.N_FASEVISUAL)
            .correlate(Riesgo)
            .scalar_subquery()
        )

        query = (
            session.query(DatosRiesgo, Riesgo, CategoriaRiesgo)
            .join(Riesgo, DatosRiesgo.RIE_ID_RIESGO == Riesgo.ID_RIESGO)
            .outerjoin(CategoriaRiesgo, Riesgo.CAT_ID_CATRIES == CategoriaRiesgo.ID_CATRIES)
            .filter(DatosRiesgo.SIST_ID_SISTEMA == id_sistema)
        )

        # 🔧 Solo filtrar por L_ACTIVA=1 si NO estamos en modo "Ver todos"
        if not todos_riesgos:
            query = query.filter(DatosRiesgo.L_ACTIVA == 1)

        if not todos_riesgos and fase_actual_orden is not None:
            query = query.filter(
                or_(
                    Riesgo.L_PERSONAL == 1,
                    Riesgo.N_FASEVISUAL.is_(None),
                    subq_fase_visual <= fase_actual_orden
                )
            )

        resultados = query.order_by(CategoriaRiesgo.ID_CATRIES, Riesgo.N_ORDVISU).all()

        # === 4. Controles ===
        def obtener_controles_riesgo(id_riesgo):
            controles = (
                session.query(Control.D_CONTROL)
                .join(RiesgoControl, Control.ID_CONTROL == RiesgoControl.CON_ID_CONTROL)
                .join(DatosControl, and_(
                    DatosControl.CON_ID_CONTROL == Control.ID_CONTROL,
                    DatosControl.SIST_ID_SISTEMA == id_sistema,
                    DatosControl.L_ACTIVA == 1
                ))
                .filter(RiesgoControl.RIE_ID_RIESGO == id_riesgo)
                .all()
            )
            return [c.D_CONTROL for c in controles]

        # === 4b. Clusters de cada riesgo ===
        def obtener_clusters_riesgo(id_riesgo):
            """
            Obtiene los códigos de cluster (C_CLUSTER) a los que pertenece un riesgo,
            ordenados por N_ORDVISU y unidos por ';'.
            """
            clusters = (
                session.query(ConfiguracionCluster.C_CLUSTER)
                .join(ConfiguracionRiesgoCluster,
                      ConfiguracionCluster.ID_CLUSTER == ConfiguracionRiesgoCluster.CLU_ID_CLUSTER)
                .filter(
                    ConfiguracionRiesgoCluster.RIE_ID_RIESGO == id_riesgo,
                    ConfiguracionCluster.L_ESTADO == 1
                )
                .order_by(ConfiguracionCluster.N_ORDVISU)
                .all()
            )
            return "; ".join([c.C_CLUSTER for c in clusters]) if clusters else ""

        # === 5. Construir lista ===
        normales, personalizados = [], []

        for dri, riesgo, categoria in resultados:
            # 🔧 CORRECCIÓN: Un riesgo es personal solo si L_PERSONAL=1 en IA_RIESGOS
            # NO debe confundirse con L_MANUAL que indica activación manual
            es_personal = bool(riesgo.L_PERSONAL == 1)

            impacto = next((v for v in impactos if v["id"] == dri.V_IMPACTO), None)
            prob = next((v for v in probabilidades if v["id"] == dri.V_PROBABILIDAD), None)

            criticidad = None
            if impacto and prob:
                cfg = session.query(ConfiguracionCriticidad).filter_by(V_IMPACTO=impacto["id"], V_PROBAB=prob["id"]).first()
                criticidad = cfg.N_CRITICIDAD if cfg else None

            nivel_riesgo = convertir_criticidad_a_nivel(criticidad)

            # 🔹 CÁLCULO DE RIESGO RESIDUAL
            if es_personal:
                # Para riesgos personalizados: usar el valor manual si existe
                if dri.V_RIERESID:
                    # Obtener el valor guardado manualmente
                    valor_residual = session.query(ValoresDato).filter_by(
                        ID_VALDAT=dri.V_RIERESID
                    ).first()
                    if valor_residual:
                        riesgo_residual = valor_residual.C_VALOR if valor_residual.C_VALOR else criticidad
                        nivel_residual = valor_residual.D_VALOR
                    else:
                        # Si no hay valor válido, usar inherente por defecto
                        riesgo_residual = criticidad
                        nivel_residual = nivel_riesgo
                else:
                    # Si no se ha establecido, usar inherente
                    riesgo_residual = criticidad
                    nivel_residual = nivel_riesgo

                # Obtener ID del valor residual para el combo
                id_riesgo_residual = dri.V_RIERESID
            else:
                # Para riesgos normales: calcular automáticamente
                riesgo_residual, nivel_residual = calcular_riesgo_residual(session, dri, criticidad)
                id_riesgo_residual = None  # No aplica para normales

            controles_mitigacion = obtener_controles_riesgo(riesgo.ID_RIESGO)

            # 🆕 Obtener clusters del riesgo
            clusters_riesgo = obtener_clusters_riesgo(riesgo.ID_RIESGO)

            # 🆕 Obtener el texto del nivel mínimo requerido
            minimo_requerido_texto = None
            if riesgo.N_RIERESMIN:
                valor_minimo = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == riesgo.N_RIERESMIN
                ).first()
                if valor_minimo:
                    minimo_requerido_texto = valor_minimo.D_VALOR

            item = {
                "id_dat_riesgo": dri.ID_DATRIES,
                "id_riesgo_original": riesgo.ID_RIESGO,
                # 🔹 COLUMNA "Riesgo":
                # - Si es riesgo personal Y tiene descripción personalizada: usar T_DESCRIPCION de IA_DATRIESGOS
                # - Si es riesgo personal SIN descripción: usar D_RIESGO de IA_RIESGOS
                # - Si es riesgo normal: usar D_RIESGO de IA_RIESGOS
                "descripcion_riesgo": (
                    dri.T_DESCRIPCION if (es_personal and dri.T_DESCRIPCION) else riesgo.D_RIESGO
                ),
                # 🔹 MODAL AYUDA: siempre la descripción original de IA_RIESGOS
                "descripcion_detallada": riesgo.T_DESCRIPCION,
                # 🔹 MODAL EDICIÓN: para personales, el campo T_DESCRIPCION de IA_DATRIESGOS
                "descripcion_editable": dri.T_DESCRIPCION if es_personal else None,
                "categoria": categoria.D_CATEGORIA if categoria else "",
                "base_normativa": riesgo.T_BASENORMATIVA,
                "aplica": int(dri.L_APLICA or 0),
                # 🔹 IDs para los selects de probabilidad e impacto
                "id_probabilidad": dri.V_PROBABILIDAD,
                "id_impacto": dri.V_IMPACTO,
                # 🔹 Justificaciones
                "justificacion_aplica": dri.T_JUSAPLICA or "",
                "justificacion_probabilidad": dri.T_JUSPROBABILIDAD or "",
                "justificacion_impacto": dri.T_JUSIMPACTO or "",
                "criticidad": criticidad,
                "nivel_riesgo": nivel_riesgo,
                "riesgo_residual": riesgo_residual,
                "nivel_residual": nivel_residual,
                # 🔹 ID del valor residual para el combo
                "id_riesgo_residual": id_riesgo_residual,
                "l_activa": int(dri.L_ACTIVA or 0),
                "es_riesgo_personalizado": es_personal,
                "controles_mitigacion": controles_mitigacion,
                "clusters": clusters_riesgo,  # 🆕 Códigos de clusters del riesgo
                # 🆕 NUEVO: Campos para validación de fase
                "n_rieresmin": riesgo.N_RIERESMIN,
                "riesgo_residual_valor": dri.V_RIERESID,
                "minimo_requerido_texto": minimo_requerido_texto,  # 🆕 TEXTO del mínimo
            }

            if es_personal:
                personalizados.append(item)
            else:
                normales.append(item)

        # === 6. Orden ===
        lista_final = normales + personalizados

        # === 7. Estadísticas ===
        estadisticas = {
            "total_activos": len([r for r in lista_final if r["l_activa"] == 1]),
            "total_aplicables": len([r for r in lista_final if r["aplica"] == 1]),
            "inherente": {"CRÍTICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0, "SIN VALORAR": 0},
            "residual": {"CRÍTICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0, "SIN VALORAR": 0}
        }

        for r in lista_final:
            if r["aplica"] != 1:
                continue
            inh = r.get("nivel_riesgo") or "SIN VALORAR"
            res = r.get("nivel_residual") or "SIN VALORAR"
            if inh not in estadisticas["inherente"]:
                inh = "SIN VALORAR"
            if res not in estadisticas["residual"]:
                res = "SIN VALORAR"
            estadisticas["inherente"][inh] += 1
            estadisticas["residual"][res] += 1

        # === 8. Calcular todos_completos usando los datos YA calculados ===
        # Obtener fase actual para determinar nivel de validación
        fase_actual, _ = obtener_fase_proyecto(id_sistema)
        nivel_fase = fase_actual.C_NIVELRIESG if fase_actual else None

        es_nivel_r = (nivel_fase == 'R')
        validar_residual = (nivel_fase and nivel_fase != 'I')

        # Mapa de niveles (escala invertida: menor valor = mayor criticidad)
        mapa_niveles = {'CRÍTICO': 1, 'ALTO': 2, 'MEDIO': 3, 'BAJO': 4}

        pendientes = 0
        total_validar = 0

        for r in lista_final:
            # Solo validar riesgos activos Y aplicables
            if r.get("l_activa") != 1 or r.get("aplica") != 1:
                continue

            tiene_inherente = r.get("id_impacto") and r.get("id_probabilidad")
            nivel_residual = r.get("nivel_residual")
            minimo_texto = r.get("minimo_requerido_texto")

            if es_nivel_r:
                # NIVEL R: Validar inherente Y residual con criterio especial

                # 1. Si no tiene inherente, es pendiente
                if not tiene_inherente:
                    total_validar += 1
                    pendientes += 1
                    continue

                # 2. Si no hay mínimo definido, NO requiere validación
                if not minimo_texto or minimo_texto in ('', 'None', 'null', None):
                    continue

                # 3. Este riesgo SÍ requiere validación
                total_validar += 1

                # 4. Si no hay nivel residual, es pendiente
                if not nivel_residual or nivel_residual in ('', '—', 'None', None):
                    pendientes += 1
                    continue

                # 5. Comparar usando escala invertida
                residual_num = mapa_niveles.get(nivel_residual)
                minimo_num = mapa_niveles.get(minimo_texto)

                if residual_num is not None and minimo_num is not None:
                    # El riesgo es pendiente si residual < mínimo (mayor criticidad)
                    if residual_num < minimo_num:
                        pendientes += 1
                else:
                    pendientes += 1

            elif validar_residual:
                # NIVEL M: Validar inherente Y residual básico
                total_validar += 1

                if not tiene_inherente:
                    pendientes += 1
                    continue

                # Verificar que tenga residual calculado
                if not nivel_residual or nivel_residual in ('', '—', 'None', None):
                    pendientes += 1
                    continue

                # Si hay mínimo definido, verificar que lo cumpla
                if minimo_texto and minimo_texto not in ('', 'None', 'null', None):
                    residual_num = mapa_niveles.get(nivel_residual)
                    minimo_num = mapa_niveles.get(minimo_texto)
                    if residual_num is not None and minimo_num is not None:
                        if residual_num < minimo_num:
                            pendientes += 1
            else:
                # NIVEL I: Solo validar impacto y probabilidad
                total_validar += 1
                if not tiene_inherente:
                    pendientes += 1

        todos_completos = (pendientes == 0 and total_validar > 0) or (total_validar == 0)
        porcentaje = 0 if total_validar == 0 else round((total_validar - pendientes) / total_validar * 100, 1)

        pendientes_info = {
            'pendientes': pendientes,
            'total': total_validar,
            'porcentaje': porcentaje
        }


        # === 9. Retornar ===
        return {
            "riesgos": lista_final,
            "impactos": impactos,
            "probabilidades": probabilidades,
            "niveles_riesgo": niveles,
            "valores_riesgo": valores_riesgo,  # 🔹 NUEVO: Valores para combo de riesgo residual
            "modo_todos": todos_riesgos,
            "todos_completos": todos_completos,
            "pendientes_info": pendientes_info,
            "estadisticas": estadisticas
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "riesgos": [],
            "impactos": [],
            "probabilidades": [],
            "niveles_riesgo": [],
            "valores_riesgo": [],  # 🔹 NUEVO
            "modo_todos": todos_riesgos,
            "todos_completos": False,
            "pendientes_info": {'pendientes': 0, 'total': 0, 'porcentaje': 0},
            "estadisticas": {
                "total_activos": 0,
                "total_aplicables": 0,
                "inherente": {"CRÍTICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0, "SIN VALORAR": 0},
                "residual": {"CRÍTICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0, "SIN VALORAR": 0}
            }
        }
    finally:
        session.close()

def crear_nueva_iteracion(id_sistema: int, id_elemento: int):
    """
    Crea una nueva iteración para un elemento específico en un sistema dado.
    También crea los registros correspondientes en IA_DATELEMADI y IA_DATELEMCONTR.
    """
    from models import DatosElementoControl

    session = Session()
    try:
        # 1. Encontrar la máxima N_ITERACION actual
        max_iteracion_data = session.query(func.max(DatosElementosAdi.N_ITERACION))\
                                    .filter(DatosElementosAdi.SIST_ID_SISTEMA == id_sistema,
                                            DatosElementosAdi.ELE_ID_ELEM == id_elemento)\
                                    .one()

        max_iteracion = max_iteracion_data[0] if max_iteracion_data[0] is not None else 0
        nueva_iteracion = max_iteracion + 1

        # 2. Encontrar el MÁXIMO ID_DATELEMADI en toda la tabla
        max_id_data = session.query(func.max(DatosElementosAdi.ID_DATELEMADI)).scalar()

        # El ID base será el máximo encontrado (o 0 si la tabla está vacía)
        id_base = max_id_data if max_id_data is not None else 0

        # El ID inicial de la nueva iteración (respetando el gap de 100)
        id_inicial_bloque = id_base + 100

        # 3. Encontrar todos los SubElementos asociados al Elemento
        subelementos = session.query(SubElementosAdi)\
                        .filter(SubElementosAdi.ELE_ID_ELEM == id_elemento)\
                        .order_by(SubElementosAdi.N_SUBORD)\
                        .all()

        if not subelementos:
            raise ValueError("No se encontraron subelementos para replicar en el elemento ID: " + str(id_elemento))

        # 4. Crear un nuevo registro en IA_DATELEMADI por cada subelemento
        for i, sub in enumerate(subelementos):
            current_id = id_inicial_bloque + i*100

            nuevo_dato_elem = DatosElementosAdi(
                ID_DATELEMADI=current_id,
                SIST_ID_SISTEMA=id_sistema,
                ELE_ID_ELEM=id_elemento,
                SUB_IDSUBELEM=sub.ID_SUBELEM,
                T_DESCRIPCION="",
                N_ITERACION=nueva_iteracion
            )
            session.add(nuevo_dato_elem)

        # Commit se realiza una sola vez para todos los registros con IDs únicos
        session.commit()

        return {
            "numero": nueva_iteracion,
            "subelementos": [
                {
                    "id_subelem": sub.ID_SUBELEM,
                    "descripcion": sub.D_SUBELEM
                } for sub in subelementos
            ]
        }

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_controles_para_formulario(id_sistema, todos_controles=False, id_riesgo_filtro=None, id_requisito_filtro=None):
    """
    Obtiene los controles para mostrar en el formulario de controles.
    Incluye información de riesgos asociados para permitir filtrado dinámico.

    Args:
        id_sistema: ID del sistema del proyecto
        todos_controles: Si True, muestra todos los controles (activos e inactivos)
        id_riesgo_filtro: Si se proporciona, en modo todos_controles filtra solo los controles
                         relacionados con este riesgo a través de IA_RIESCONTR
        id_requisito_filtro: Si se proporciona, filtra solo los controles relacionados
                            con este requisito a través de IA_CFGREQCONTR
    """
    session = Session()
    try:

        # === 0. Obtener fase actual del proyecto ===
        fase_actual_orden = None
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if proyecto and proyecto.N_FASE:
            fase_config = session.query(ConfiguracionFase).filter_by(
                ID_FASE=proyecto.N_FASE
            ).first()
            if fase_config:
                fase_actual_orden = fase_config.N_ORDEN

        # === 1. Cargar valores de dominio ===
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

        madurez_valores = _obtener_valores('MAD')
        madurez_list = [{"id": v.ID_VALDAT, "valor": v.C_VALOR, "texto": v.D_VALOR} for v in madurez_valores]

        # === 2. Cargar dominios para riesgos (impacto y probabilidad) ===
        impactos_list = []
        probabilidades_list = []
        tipos_dato = session.query(TiposDato).filter(TiposDato.C_TIPDAT.in_(['IMPA', 'PRO'])).all()
        tipos_dict = {t.C_TIPDAT: t for t in tipos_dato}
        if 'IMPA' in tipos_dict:
            impactos_list = session.query(ValoresDato).filter(ValoresDato.TIDA_ID_TIPDAT == tipos_dict['IMPA'].ID_TIPDAT).all()
        if 'PRO' in tipos_dict:
            probabilidades_list = session.query(ValoresDato).filter(ValoresDato.TIDA_ID_TIPDAT == tipos_dict['PRO'].ID_TIPDAT).all()

        impactos_dict = {v.ID_VALDAT: v for v in impactos_list}
        probabilidades_dict = {v.ID_VALDAT: v for v in probabilidades_list}

        # === 3. Obtener riesgos activos y aplicables del sistema CON DATOS DE RIESGO ===
        riesgos_db = session.query(
            DatosRiesgo,
            Riesgo,
            CategoriaRiesgo
        ).join(
            Riesgo, DatosRiesgo.RIE_ID_RIESGO == Riesgo.ID_RIESGO
        ).join(
            CategoriaRiesgo, Riesgo.CAT_ID_CATRIES == CategoriaRiesgo.ID_CATRIES
        ).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1,
            DatosRiesgo.L_APLICA == 1
        ).order_by(
            CategoriaRiesgo.ID_CATRIES,
            Riesgo.N_ORDVISU
        ).all()

        riesgos_list = []
        for dri, riesgo, categoria in riesgos_db:
            # --- Calcular criticidad inherente ---
            impacto_info = impactos_dict.get(dri.V_IMPACTO)
            prob_info = probabilidades_dict.get(dri.V_PROBABILIDAD)
            criticidad_inherente = None
            if impacto_info and prob_info:
                config_criticidad = session.query(ConfiguracionCriticidad).filter_by(
                    V_IMPACTO=dri.V_IMPACTO,
                    V_PROBAB=dri.V_PROBABILIDAD
                ).first()
                if config_criticidad:
                    criticidad_inherente = config_criticidad.N_CRITICIDAD

            nivel_inherente = convertir_criticidad_a_nivel(criticidad_inherente)

            # --- Calcular riesgo residual ---
            riesgo_residual, nivel_residual = calcular_riesgo_residual(session, dri, criticidad_inherente)

            riesgos_list.append({
                "id": riesgo.ID_RIESGO,
                "codigo": riesgo.C_RIESGO,
                "descripcion": riesgo.D_RIESGO,
                "categoria": categoria.D_CATEGORIA,
                "nivel_inherente": nivel_inherente,
                "nivel_residual": nivel_residual
            })

        # === 3b. Obtener requisitos activos del proyecto ===
        # 🔒 FILTRAR POR FASE: Solo requisitos con N_FASEVISUAL <= fase actual (usando N_ORDEN)
        requisitos_db = session.query(
            ConfiguracionRequisito,
            DatosRequisito
        ).join(
            DatosRequisito, DatosRequisito.REQ_ID_REQU == ConfiguracionRequisito.ID_REQ
        ).filter(
            DatosRequisito.SIST_ID_SISTEMA == id_sistema
        ).order_by(
            ConfiguracionRequisito.D_REQUISITO
        ).all()

        requisitos_list = []
        for req, dato_req in requisitos_db:
            # Verificar si el requisito es visible en la fase actual
            requisito_visible = False

            if req.N_FASEVISUAL is None:
                # Sin fase definida = siempre visible
                requisito_visible = True
            elif fase_actual_orden is not None:
                # Obtener el N_ORDEN de la fase visual del requisito
                fase_visual_req = session.query(ConfiguracionFase).filter_by(
                    ID_FASE=req.N_FASEVISUAL
                ).first()
                if fase_visual_req:
                    # El requisito es visible si su fase visual tiene N_ORDEN <= fase actual
                    requisito_visible = (fase_visual_req.N_ORDEN <= fase_actual_orden)

            if requisito_visible:
                requisitos_list.append({
                    "id": req.ID_REQ,
                    "denominacion": req.D_REQUISITO,
                    "base_normativa": req.T_BASENORMATIVA or "",
                    "descripcion": req.T_DESCRIPCION or ""
                })

        # Variable para determinar si mostrar el filtro de requisitos
        mostrar_filtro_requisitos = len(requisitos_list) > 0

        # === 4. Consultar controles con información de riesgos asociados ===
        query_controles = session.query(
            DatosControl,
            Control,
            GrupoControl
        ).join(
            Control, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL
        ).outerjoin(
            GrupoControl, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL
        ).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema
        )

        debug_manuales = session.query(DatosControl).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema,
            DatosControl.L_APLICA == 1
        ).all()

        for c in debug_manuales:
            pass


        # 🔒 FILTRAR POR FASE si NO es modo "todos_controles"
        if not todos_controles:
            query_controles = query_controles.filter(DatosControl.L_ACTIVA == 1)

            # 🔒 APLICAR FILTRO DE FASE: Solo grupos con N_FASEVISUAL <= fase actual
            if fase_actual_orden is not None:
                # Subconsulta para obtener N_ORDEN de la fase visual del grupo
                subq_fase_visual = (
                    session.query(ConfiguracionFase.N_ORDEN)
                    .filter(ConfiguracionFase.ID_FASE == GrupoControl.N_FASEVISUAL)
                    .correlate(GrupoControl)
                    .scalar_subquery()
                )

                query_controles = query_controles.filter(
                    or_(
                        GrupoControl.N_FASEVISUAL.is_(None),  # Sin fase definida = siempre visible
                        subq_fase_visual <= fase_actual_orden
                    )
                )

            # 🆕 FILTRAR POR RIESGO si se proporciona id_riesgo_filtro (TAMBIÉN EN MODO ACTIVOS)
            if id_riesgo_filtro:
                # Filtrar solo los controles relacionados con el riesgo especificado
                # a través de la tabla IA_RIESCONTR
                query_controles = query_controles.join(
                    RiesgoControl,
                    Control.ID_CONTROL == RiesgoControl.CON_ID_CONTROL
                ).filter(
                    RiesgoControl.RIE_ID_RIESGO == int(id_riesgo_filtro)
                )

            # 🆕 FILTRAR POR REQUISITO si se proporciona id_requisito_filtro (TAMBIÉN EN MODO ACTIVOS)
            if id_requisito_filtro:
                # Filtrar solo los controles relacionados con el requisito especificado
                # a través de la tabla IA_CFGREQCONTR
                query_controles = query_controles.join(
                    ConfiguracionRequisitoControl,
                    Control.ID_CONTROL == ConfiguracionRequisitoControl.REQ_ID_CONTROL
                ).filter(
                    ConfiguracionRequisitoControl.REQ_ID_REQU == int(id_requisito_filtro)
                )

            controles_completos = session.query(DatosControl).join(
                Control, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL
            ).outerjoin(
                GrupoControl, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL
            ).filter(
                DatosControl.SIST_ID_SISTEMA == id_sistema,
                DatosControl.L_ACTIVA == 1,
                DatosControl.L_APLICA.isnot(None)
            )

            # Aplicar el mismo filtro de fase para el conteo
            if fase_actual_orden is not None:
                subq_fase_visual_count = (
                    session.query(ConfiguracionFase.N_ORDEN)
                    .filter(ConfiguracionFase.ID_FASE == GrupoControl.N_FASEVISUAL)
                    .correlate(GrupoControl)
                    .scalar_subquery()
                )
                controles_completos = controles_completos.filter(
                    or_(
                        GrupoControl.N_FASEVISUAL.is_(None),
                        subq_fase_visual_count <= fase_actual_orden
                    )
                )

            controles_completos_count = controles_completos.count()

            total_controles_activos = session.query(DatosControl).join(
                Control, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL
            ).outerjoin(
                GrupoControl, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL
            ).filter(
                DatosControl.SIST_ID_SISTEMA == id_sistema,
                DatosControl.L_ACTIVA == 1
            )

            # Aplicar el mismo filtro de fase para el total
            if fase_actual_orden is not None:
                subq_fase_visual_total = (
                    session.query(ConfiguracionFase.N_ORDEN)
                    .filter(ConfiguracionFase.ID_FASE == GrupoControl.N_FASEVISUAL)
                    .correlate(GrupoControl)
                    .scalar_subquery()
                )
                total_controles_activos = total_controles_activos.filter(
                    or_(
                        GrupoControl.N_FASEVISUAL.is_(None),
                        subq_fase_visual_total <= fase_actual_orden
                    )
                )

            total_controles_activos_count = total_controles_activos.count()
            todos_completos = (total_controles_activos_count > 0) and (controles_completos_count == total_controles_activos_count)

            # 🆕 CALCULAR CONTROLES PENDIENTES Y TOTALES APLICABLES
            # Un control está pendiente si:
            # 1. No tiene V_MADUREZ informado, O
            # 2. Tiene V_MADUREZ pero es inferior al N_MADUMIN requerido

            # Obtener todos los controles activos y aplicables de la fase actual
            controles_evaluacion = session.query(
                DatosControl,
                Control
            ).join(
                Control, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL
            ).outerjoin(
                GrupoControl, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL
            ).filter(
                DatosControl.SIST_ID_SISTEMA == id_sistema,
                DatosControl.L_ACTIVA == 1,
                DatosControl.L_APLICA == 1
            )

            # Aplicar filtro de fase
            if fase_actual_orden is not None:
                subq_fase_visual_eval = (
                    session.query(ConfiguracionFase.N_ORDEN)
                    .filter(ConfiguracionFase.ID_FASE == GrupoControl.N_FASEVISUAL)
                    .correlate(GrupoControl)
                    .scalar_subquery()
                )
                controles_evaluacion = controles_evaluacion.filter(
                    or_(
                        GrupoControl.N_FASEVISUAL.is_(None),
                        subq_fase_visual_eval <= fase_actual_orden
                    )
                )

            controles_lista = controles_evaluacion.all()
            total_controles_aplicables = len(controles_lista)
            controles_pendientes = 0

            # Evaluar cada control
            for datos_control, control in controles_lista:
                control_completo = False

                # Si no tiene madurez informada → PENDIENTE
                if datos_control.V_MADUREZ is None:
                    controles_pendientes += 1
                    continue

                # Si tiene madurez, verificar si cumple el mínimo requerido
                if control.N_MADUMIN is not None:
                    # Obtener el C_VALOR de la madurez actual
                    valor_actual = session.query(ValoresDato).filter(
                        ValoresDato.ID_VALDAT == datos_control.V_MADUREZ
                    ).first()

                    # Obtener el C_VALOR del mínimo requerido
                    valor_minimo = session.query(ValoresDato).filter(
                        ValoresDato.ID_VALDAT == control.N_MADUMIN
                    ).first()

                    if valor_actual and valor_minimo:
                        madurez_actual_num = valor_actual.C_VALOR
                        madurez_minima_num = valor_minimo.C_VALOR

                        # Si la madurez actual es menor al mínimo → PENDIENTE
                        if madurez_actual_num < madurez_minima_num:
                            controles_pendientes += 1
                            continue
                        else:
                            # Cumple con el mínimo → COMPLETO
                            control_completo = True
                    else:
                        # Si no se encuentra algún valor, considerar PENDIENTE
                        controles_pendientes += 1
                        continue
                else:
                    # Si no tiene N_MADUMIN definido y tiene madurez informada → COMPLETO
                    control_completo = True

        else:
            # En modo "Ver Todos", no filtrar por fase ni por L_ACTIVA

            # 🆕 FILTRAR POR RIESGO si se proporciona id_riesgo_filtro
            if id_riesgo_filtro:
                # Filtrar solo los controles relacionados con el riesgo especificado
                # a través de la tabla IA_RIESCONTR
                query_controles = query_controles.join(
                    RiesgoControl,
                    Control.ID_CONTROL == RiesgoControl.CON_ID_CONTROL
                ).filter(
                    RiesgoControl.RIE_ID_RIESGO == int(id_riesgo_filtro)
                )

            # 🆕 FILTRAR POR REQUISITO si se proporciona id_requisito_filtro
            if id_requisito_filtro:
                # Filtrar solo los controles relacionados con el requisito especificado
                # a través de la tabla IA_CFGREQCONTR
                query_controles = query_controles.join(
                    ConfiguracionRequisitoControl,
                    Control.ID_CONTROL == ConfiguracionRequisitoControl.REQ_ID_CONTROL
                ).filter(
                    ConfiguracionRequisitoControl.REQ_ID_REQU == int(id_requisito_filtro)
                )

            todos_completos = False
            controles_pendientes = 0
            total_controles_aplicables = 0

        resultados = query_controles.order_by(
            GrupoControl.N_ORDVISUAL if GrupoControl.N_ORDVISUAL is not None else 0,
            Control.N_ORDVISUAL
        ).all()


        # === 5. Funciones auxiliares para riesgos por control ===
        def obtener_riesgos_ids_control(id_control):
            riesgos_ids = session.query(RiesgoControl.RIE_ID_RIESGO)\
                .filter(RiesgoControl.CON_ID_CONTROL == id_control)\
                .all()
            return [r.RIE_ID_RIESGO for r in riesgos_ids]

        def obtener_riesgos_control(id_control):
            riesgos = session.query(Riesgo.D_RIESGO)\
                .join(RiesgoControl, Riesgo.ID_RIESGO == RiesgoControl.RIE_ID_RIESGO)\
                .filter(RiesgoControl.CON_ID_CONTROL == id_control)\
                .all()
            return [r.D_RIESGO for r in riesgos]

        # === 6. Procesar controles ===
        controles_enriquecidos = []
        for dco, ctrl, grupo in resultados:
            intensidad_info = next((v for v in intensidades_list if v["id"] == dco.V_INTCONDES), None)
            madurez_info = next((v for v in madurez_list if v["id"] == dco.V_MADUREZ), None)

            if dco.L_APLICA is None:
                estado_evaluacion = "PENDIENTE"
            elif dco.L_APLICA == 1:
                if dco.T_ESPCLAUSULA and len(dco.T_ESPCLAUSULA.strip()) > 10:
                    estado_evaluacion = "COMPLETO"
                else:
                    estado_evaluacion = "PENDIENTE"
            elif dco.L_APLICA == 0:
                estado_evaluacion = "COMPLETO"
            else:
                estado_evaluacion = "PENDIENTE"

            riesgos_ids = obtener_riesgos_ids_control(ctrl.ID_CONTROL)
            riesgos_mitigados = obtener_riesgos_control(ctrl.ID_CONTROL)
            es_grupo_obligatorio = grupo.L_OBLIG if grupo and grupo.L_OBLIG == 1 else 0

            madurez_minima_valor = None
            if ctrl.N_MADUMIN:
                val_mad_min = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == ctrl.N_MADUMIN
                ).first()
                if val_mad_min:
                    madurez_minima_valor = val_mad_min.C_VALOR


            debe_validarse = False
            fase_eval_orden = None

            if grupo and grupo.N_FASEVAL and fase_actual_orden is not None:
                # Obtener el N_ORDEN de la fase de evaluación del grupo
                fase_eval_config = session.query(ConfiguracionFase).filter_by(
                    ID_FASE=grupo.N_FASEVAL
                ).first()

                if fase_eval_config:
                    fase_eval_orden = fase_eval_config.N_ORDEN
                    # El control debe validarse si estamos en o después de su fase de evaluación
                    debe_validarse = (fase_actual_orden >= fase_eval_orden)

            controles_enriquecidos.append({
                "id_dat_control": dco.ID_DATCONTROL,
                "id_control_original": ctrl.ID_CONTROL,
                "codigo_control": ctrl.C_CONTROL,
                "descripcion_control": ctrl.D_CONTROL,
                "grupo_control": grupo.D_CONTROL if grupo else "Sin Grupo",
                "descripcion_grupo": grupo.D_CONTROL if grupo else "Sin Grupo Asignado",
                "codigo_grupo_control": grupo.C_CONTROL if grupo else None,
                "l_activa": dco.L_ACTIVA,
                "l_aplica": dco.L_APLICA,
                "l_traslape": dco.L_TRASLAPLI,
                "v_intcondes": dco.V_INTCONDES,
                "intensidad_valor": intensidad_info["valor"] if intensidad_info else None,
                "intensidad_texto": intensidad_info["texto"] if intensidad_info else "—",
                "v_madurez": dco.V_MADUREZ,
                "madurez_valor": madurez_info["valor"] if madurez_info else None,
                "madurez_texto": madurez_info["texto"] if madurez_info else "—",
                "justificacion_clausula": dco.T_ESPCLAUSULA or "",
                "observaciones": dco.T_OBSERVACIONES or "",
                "descripcion_detallada": ctrl.D_DESCRIPCION or "",
                "instrucciones": ctrl.T_INSTRUCCIONES or "",
                "estado_evaluacion": estado_evaluacion,
                "riesgos_mitigados": riesgos_mitigados,
                "riesgos_ids": riesgos_ids,
                "madurez_minima_valor": madurez_minima_valor,
                "es_grupo_obligatorio": es_grupo_obligatorio,
                "debe_validarse_fase": debe_validarse,
                "fase_evaluacion_orden": fase_eval_orden
            })

        # === 7. Devolver resultado ===
        return {
            "controles": controles_enriquecidos,
            "intensidades_condiciones": intensidades_list,
            "madurez_valores": madurez_list,
            "riesgos_activos": riesgos_list,
            "requisitos_activos": requisitos_list,
            "mostrar_filtro_requisitos": mostrar_filtro_requisitos,
            "modo_todos": todos_controles,
            "todos_completos": todos_completos,
            "controles_pendientes": controles_pendientes if not todos_controles else 0,
            "total_controles_aplicables": total_controles_aplicables if not todos_controles else 0
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "controles": [],
            "intensidades_condiciones": [],
            "madurez_valores": [],
            "riesgos_activos": [],
            "requisitos_activos": [],
            "mostrar_filtro_requisitos": False,
            "modo_todos": todos_controles,
            "todos_completos": False,
            "controles_pendientes": 0,
            "total_controles_aplicables": 0
        }
    finally:
        session.close()


def validar_desactivacion_control(id_sistema, id_control):
    """
    Valida si se puede marcar un control como 'No aplica' (L_APLICA=0).
    Si desactivar este control dejaría algún riesgo activo y aplicable con menos controles
    de los mínimos requeridos (N_CONTRMIN), se lanza una excepción con el mensaje de error.

    EXCEPCIÓN: Se excluyen de la validación aquellos riesgos cuyo nivel de riesgo residual
    sea igual o inferior al nivel de riesgo residual mínimo permitido (N_RIERESMIN).
    """
    db_session = Session()
    try:
        # Paso 1: Obtener todos los riesgos asociados a este control
        riesgos_asociados = db_session.query(RiesgoControl.RIE_ID_RIESGO).filter(
            RiesgoControl.CON_ID_CONTROL == id_control
        ).all()

        if not riesgos_asociados:
            return

        lista_riesgos_ids = [r.RIE_ID_RIESGO for r in riesgos_asociados]

        # Paso 2: Obtener datos de riesgos activos y aplicables en este sistema con sus datos completos
        datos_riesgos_query = db_session.query(
            DatosRiesgo,
            Riesgo.N_CONTRMIN,
            Riesgo.N_RIERESMIN,
            Riesgo.C_RIESGO,
            Riesgo.D_RIESGO
        ).join(
            Riesgo, DatosRiesgo.RIE_ID_RIESGO == Riesgo.ID_RIESGO
        ).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.RIE_ID_RIESGO.in_(lista_riesgos_ids),
            DatosRiesgo.L_ACTIVA == 1,
            DatosRiesgo.L_APLICA == 1
        ).all()

        if not datos_riesgos_query:
            return

        # Paso 3: Filtrar riesgos que requieren validación (excluir los que ya cumplen el nivel mínimo)
        riesgos_a_verificar = {}

        for dr, n_contrmin, n_rieresmin, c_riesgo, d_riesgo in datos_riesgos_query:
            id_riesgo = dr.RIE_ID_RIESGO
            min_controles = n_contrmin or 1

            # 🔍 Calcular la criticidad inherente del riesgo (necesaria para calcular la residual)
            criticidad_inherente = None
            if dr.V_IMPACTO and dr.V_PROBABILIDAD:
                config_criticidad = db_session.query(ConfiguracionCriticidad).filter_by(
                    V_IMPACTO=dr.V_IMPACTO,
                    V_PROBAB=dr.V_PROBABILIDAD
                ).first()
                if config_criticidad:
                    criticidad_inherente = config_criticidad.N_CRITICIDAD

            # 🎯 Calcular la criticidad RESIDUAL del riesgo
            criticidad_residual = None
            nivel_residual_texto = None

            if criticidad_inherente is not None:
                # Usar la función existente para calcular el riesgo residual
                criticidad_residual, nivel_residual_texto = calcular_riesgo_residual(
                    db_session, dr, criticidad_inherente
                )

            # ✅ EXCLUSIÓN: Si el riesgo RESIDUAL es <= N_RIERESMIN, no requiere validación
            debe_excluirse = False
            if criticidad_residual is not None and n_rieresmin is not None:
                # Obtener el valor mínimo permitido desde IA_VALDAT
                valor_minimo = db_session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == n_rieresmin
                ).first()

                if valor_minimo:
                    # Obtener el C_VALOR del nivel residual desde IA_VALDAT
                    nivel_residual_bd = db_session.query(ValoresDato).filter(
                        ValoresDato.TIDA_ID_TIPDAT == valor_minimo.TIDA_ID_TIPDAT,
                        ValoresDato.D_VALOR == nivel_residual_texto
                    ).first()

                    if nivel_residual_bd:
                        # ⚠️ ESCALA INVERTIDA: CRÍTICO=1, ALTO=2, MEDIO=3, BAJO=4
                        # Si el nivel residual es MAYOR O IGUAL al mínimo permitido, se excluye
                        # Ejemplo: Si residual es BAJO(4) y mínimo es MEDIO(3), 4 >= 3 → se excluye
                        nivel_residual_numerico = nivel_residual_bd.C_VALOR
                        nivel_minimo_numerico = valor_minimo.C_VALOR

                        if nivel_residual_numerico >= nivel_minimo_numerico:
                            debe_excluirse = True

            if debe_excluirse:
                continue

            # Agregar el riesgo a la lista de verificación
            riesgos_a_verificar[id_riesgo] = {
                'min_controles': min_controles,
                'codigo': c_riesgo,
                'descripcion': d_riesgo,
                'criticidad_residual': criticidad_residual,
                'n_rieresmin': n_rieresmin
            }

        if not riesgos_a_verificar:
            return

        # Paso 4: Para cada riesgo que requiere validación, contar controles activos y aplicables
        for id_riesgo, info_riesgo in riesgos_a_verificar.items():
            min_controles = info_riesgo['min_controles']

            # Contar controles aplicables EXCLUYENDO el control que se quiere desactivar
            controles_aplicables = db_session.query(RiesgoControl.CON_ID_CONTROL).join(
                DatosControl, and_(
                    DatosControl.CON_ID_CONTROL == RiesgoControl.CON_ID_CONTROL,
                    DatosControl.SIST_ID_SISTEMA == id_sistema,
                    DatosControl.L_ACTIVA == 1,
                    DatosControl.L_APLICA == 1
                )
            ).filter(
                RiesgoControl.RIE_ID_RIESGO == id_riesgo,
                RiesgoControl.CON_ID_CONTROL != id_control
            ).all()

            total_controles_vivos = len(controles_aplicables)

            # --- DEPURACIÓN: Imprimir información detallada ---
            ids_controles = [c.CON_ID_CONTROL for c in controles_aplicables]

            # Si tras desactivar, el número cae por debajo del mínimo → ERROR
            if total_controles_vivos < min_controles:
                nombre_riesgo = f"{info_riesgo['codigo']} - {info_riesgo['descripcion']}"
                raise ValueError(f"No se puede desactivar el control ya que dejaría el riesgo '{nombre_riesgo}' sin posibilidad de mitigarse")

    finally:
        db_session.close()

def obtener_fase_proyecto(id_sistema):
    """
    Obtiene la fase actual de un proyecto.

    Args:
        id_sistema (int): ID del sistema/proyecto.

    Returns:
        tuple: (fase_actual, todas_fases) donde:
            - fase_actual: Objeto ConfiguracionFase o None
            - todas_fases: Lista de todas las fases ordenadas por N_ORDEN

    Raises:
        ValueError: Si el proyecto no existe.
    """
    session = Session()
    try:
        # Obtener el proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()

        if not proyecto:
            raise ValueError(f"Proyecto con ID {id_sistema} no encontrado")

        # Obtener la fase actual
        fase_actual = None
        if proyecto.N_FASE:
            fase_actual = session.query(ConfiguracionFase).filter_by(
                ID_FASE=proyecto.N_FASE
            ).first()

        # Obtener todas las fases ordenadas
        todas_fases = session.query(ConfiguracionFase).order_by(
            ConfiguracionFase.N_ORDEN.asc()
        ).all()

        return fase_actual, todas_fases

    finally:
        session.close()


def inicializar_controles_monitoreo(session, id_sistema):
    """
    Copia los controles activos del proyecto a la tabla de monitoreo IA_DATCONTMON.

    Solo se copian controles que:
    - Están activos (L_ACTIVA = 1 en IA_DATCONTROL)
    - Aplican al proyecto (L_APLICA = 1 en IA_DATCONTROL)
    - Pertenecen a un grupo de control con L_MONITOREO = 1 en IA_GRUCONTROL

    Args:
        session: Sesión activa de SQLAlchemy.
        id_sistema (int): ID del sistema/proyecto.

    Returns:
        int: Número de controles copiados a monitoreo.

    Nota:
        - La madurez inicial (V_MADINI) se copia desde V_MADUREZ de IA_DATCONTROL
        - Si ya existen registros en IA_DATCONTMON para este sistema, se eliminan primero
    """
    from models import DatosControl, Control, GrupoControl, DatosControlMonitoreo

    try:

        # 1. Obtener el ID del valor por defecto para V_ESTADO (C_VALOR=1, ESTMON)
        tipo_estado = session.query(TiposDato).filter(TiposDato.C_TIPDAT == 'ESTMON').first()

        if not tipo_estado:
            raise ValueError("No se encontró el tipo de dato 'ESTMON' en IA_TIPDAT")

        valor_estado_defecto = session.query(ValoresDato).filter(
            ValoresDato.TIDA_ID_TIPDAT == tipo_estado.ID_TIPDAT,
            ValoresDato.C_VALOR == 1
        ).first()

        if not valor_estado_defecto:
            raise ValueError("No se encontró el valor por defecto (C_VALOR=1) para el estado de monitoreo")

        id_estado_defecto = valor_estado_defecto.ID_VALDAT


        # 2. Eliminar registros previos de monitoreo para este sistema (por si se vuelve a ejecutar)
        registros_previos = session.query(DatosControlMonitoreo).filter(
            DatosControlMonitoreo.SIST_ID_SISTEMA == id_sistema
        ).delete()

        if registros_previos > 0:
            pass

        # 3. Obtener controles activos que pertenecen a grupos de monitoreo
        controles_monitoreo = session.query(
            DatosControl,
            Control,
            GrupoControl
        ).join(
            Control, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL
        ).join(
            GrupoControl, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL
        ).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema,
            DatosControl.L_ACTIVA == 1,
            DatosControl.L_APLICA == 1,
            GrupoControl.L_MONITOREO == 1
        ).all()

        if not controles_monitoreo:
            return 0

        # 4. Obtener el siguiente ID disponible en IA_DATCONTMON
        max_id = session.query(func.max(DatosControlMonitoreo.ID_DATCONTMON)).scalar()
        next_id = 110 if max_id is None else max_id + 100

        # 5. Crear registros en IA_DATCONTMON
        controles_creados = 0
        for dato_control, control, grupo in controles_monitoreo:
            nuevo_registro = DatosControlMonitoreo(
                ID_DATCONTMON=next_id,
                SIST_ID_SISTEMA=id_sistema,
                CON_ID_CONTROL=control.ID_CONTROL,
                V_ESTADO=id_estado_defecto,  # Valor por defecto obtenido
                T_RESP=None,    # Se asignará durante el monitoreo
                V_MADINI=int(dato_control.V_MADUREZ) if dato_control.V_MADUREZ else None,
                V_MADACT=int(dato_control.V_MADUREZ) if dato_control.V_MADUREZ else None, # ✅ La madurez actual inicia igual que la inicial
                V_MADOBJ=None,  # Se asignará durante el monitoreo
                T_DESC=None,    # Se asignará durante el monitoreo
                V_FREC=None,    # Se asignará durante el monitoreo
                F_PROXEJEC=None # Se calculará durante el monitoreo
            )

            session.add(nuevo_registro)
            next_id += 100
            controles_creados += 1


        return controles_creados

    except Exception as e:
        raise


def avanzar_fase_proyecto(id_sistema):
    """
    Avanza el proyecto a la siguiente fase según N_ORDEN.

    Args:
        id_sistema (int): ID del sistema/proyecto.

    Returns:
        dict: Diccionario con el resultado de la operación:
            {
                "success": bool,
                "mensaje": str,
                "fase_nueva": str (descripción de la nueva fase) o None,
                "controles_monitoreo": int (número de controles copiados) o None
            }

    Nota:
        - No se puede avanzar si la fase actual es de monitoreo (L_MONITOREO = 1)
        - Busca la siguiente fase por N_ORDEN
        - Actualiza IA_SISTEMA.N_FASE con el ID de la siguiente fase
        - Si la nueva fase es de monitoreo, copia controles activos a IA_DATCONTMON
        - Actualiza la situación de documentos que cumplan las condiciones específicas
    """
    from models import DatosDocumento, ConfiguracionDocumento

    session = Session()
    try:
        # Obtener el proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()

        if not proyecto:
            return {
                "success": False,
                "mensaje": "Proyecto no encontrado",
                "fase_nueva": None,
                "controles_monitoreo": None
            }

        # Verificar que tenga fase asignada
        if not proyecto.N_FASE:
            return {
                "success": False,
                "mensaje": "El proyecto no tiene una fase asignada",
                "fase_nueva": None,
                "controles_monitoreo": None
            }

        # Obtener la fase actual
        fase_actual = session.query(ConfiguracionFase).filter_by(
            ID_FASE=proyecto.N_FASE
        ).first()

        if not fase_actual:
            return {
                "success": False,
                "mensaje": "No se encontró la fase actual del proyecto",
                "fase_nueva": None,
                "controles_monitoreo": None
            }

        # Verificar que no sea fase de monitoreo
        if fase_actual.L_MONITOREO == 1:
            return {
                "success": False,
                "mensaje": "No se puede finalizar una fase de monitoreo",
                "fase_nueva": None,
                "controles_monitoreo": None
            }

        # Buscar la siguiente fase por N_ORDEN
        siguiente_fase = session.query(ConfiguracionFase).filter(
            ConfiguracionFase.N_ORDEN > fase_actual.N_ORDEN
        ).order_by(ConfiguracionFase.N_ORDEN.asc()).first()

        if not siguiente_fase:
            return {
                "success": False,
                "mensaje": "No hay más fases disponibles después de la actual",
                "fase_nueva": None,
                "controles_monitoreo": None
            }

        # 📄 ACTUALIZACIÓN DE SITUACIÓN DE DOCUMENTOS
        # Buscar documentos que cumplan las condiciones:
        # 1. L_NECESARIO = 1
        # 2. Fase de validación (N_FASEVAL) = fase actual del proyecto
        # 3. Situación actual (V_SITUACION) = situación final (V_SITFINAL) de su configuración
        documentos_a_actualizar = session.query(DatosDocumento).join(
            ConfiguracionDocumento,
            DatosDocumento.DD_ID_CFGDOCS == ConfiguracionDocumento.ID_CFGDOCS
        ).filter(
            DatosDocumento.SIST_ID_SISTEMA == id_sistema,
            DatosDocumento.L_NECESARIO == 1,
            ConfiguracionDocumento.N_FASEVAL == fase_actual.ID_FASE,
            DatosDocumento.V_SITUACION == ConfiguracionDocumento.V_SITFINAL
        ).all()

        # Actualizar la situación de cada documento que cumple las condiciones
        documentos_actualizados = 0
        for documento in documentos_a_actualizar:
            config_doc = session.query(ConfiguracionDocumento).filter_by(
                ID_CFGDOCS=documento.DD_ID_CFGDOCS
            ).first()

            if config_doc and config_doc.V_SITNOAPLICA:
                documento.V_SITUACION = config_doc.V_SITNOAPLICA
                documentos_actualizados += 1

        # 🔄 NUEVO: Si la siguiente fase es de monitoreo, inicializar controles
        controles_copiados = None
        if siguiente_fase.L_MONITOREO == 1:
            controles_copiados = inicializar_controles_monitoreo(session, id_sistema)

        # Actualizar el proyecto con la nueva fase
        proyecto.N_FASE = siguiente_fase.ID_FASE
        session.commit()

        # Construir mensaje según si se copiaron controles o no
        mensaje = f"Fase finalizada correctamente. Ahora estás en: {siguiente_fase.D_FASE}"
        if controles_copiados is not None and controles_copiados > 0:
            mensaje += f" - Se han inicializado {controles_copiados} controles para monitoreo"
        if documentos_actualizados > 0:
            mensaje += f" - Se han actualizado {documentos_actualizados} documento(s)"

        return {
            "success": True,
            "mensaje": mensaje,
            "fase_nueva": siguiente_fase.D_FASE,
            "controles_monitoreo": controles_copiados
        }

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "mensaje": f"Error al finalizar la fase: {str(e)}",
            "fase_nueva": None,
            "controles_monitoreo": None
        }

    finally:
        session.close()

def retroceder_fase_proyecto(id_sistema, session=None):
    """
    Retrocede el proyecto a la fase inmediatamente anterior a la actual,
    pero solo si la fase actual es de monitoreo (L_MONITOREO = 1).

    Args:
        id_sistema (int): ID del sistema/proyecto.
        session: Sesión de SQLAlchemy (opcional, si no se pasa, se crea una internamente).

    Returns:
        dict: Diccionario con el resultado de la operación:
            {"success": bool, "mensaje": str, "fase_anterior": str (descripción) o None}

    Nota:
        - Actualiza la situación de documentos que estén en V_SITFINAL a V_SITNOAPLICA
    """
    from models import Session as SessionClass, DatosDocumento, ConfiguracionDocumento
    from sqlalchemy import and_

    external_session = session is not None
    if not external_session:
        session = SessionClass()

    try:
        proyecto = session.query(Inicio).filter(Inicio.ID_SISTEMA == id_sistema).first()
        if not proyecto:
            return {"success": False, "mensaje": "Proyecto no encontrado."}

        # ⚠️ CORRECCIÓN AQUÍ: Usar N_FASE en lugar de FAS_ID_FASE
        fase_actual_id = proyecto.N_FASE
        if not fase_actual_id:
            return {"success": False, "mensaje": "Fase actual del proyecto no definida."}

        # Obtener información de la fase actual
        fase_actual_info = session.query(ConfiguracionFase).filter(ConfiguracionFase.ID_FASE == fase_actual_id).first()
        if not fase_actual_info:
            return {"success": False, "mensaje": "Configuración de la fase actual no encontrada."}

        if not fase_actual_info.L_MONITOREO:
            return {"success": False, "mensaje": f"La fase actual '{fase_actual_info.D_FASE}' no es una fase de monitoreo. No se puede salir."}

        # Obtener la fase inmediatamente anterior con N_ORDEN menor
        # 🔁 MODIFICACIÓN: Buscar cualquier fase anterior, sin excluir las de monitoreo
        fase_anterior_info = session.query(ConfiguracionFase).filter(
            ConfiguracionFase.N_ORDEN < fase_actual_info.N_ORDEN
        ).order_by(ConfiguracionFase.N_ORDEN.desc()).first()

        if not fase_anterior_info:
            return {"success": False, "mensaje": "No se encontró una fase anterior válida para retroceder."}

        # 📄 ACTUALIZACIÓN DE SITUACIÓN DE DOCUMENTOS AL SALIR DE MONITOREO
        # Buscar documentos que cumplan las condiciones:
        # 1. Situación actual (V_SITUACION) = situación final (V_SITFINAL) de su configuración
        # 2. Tiene definida una situación de "no aplica" (V_SITNOAPLICA) en su configuración
        documentos_a_actualizar = session.query(DatosDocumento).join(
            ConfiguracionDocumento,
            DatosDocumento.DD_ID_CFGDOCS == ConfiguracionDocumento.ID_CFGDOCS
        ).filter(
            DatosDocumento.SIST_ID_SISTEMA == id_sistema,
            DatosDocumento.V_SITUACION == ConfiguracionDocumento.V_SITFINAL,
            ConfiguracionDocumento.V_SITNOAPLICA.isnot(None)
        ).all()

        # Actualizar la situación de cada documento que cumple las condiciones
        documentos_actualizados = 0
        for documento in documentos_a_actualizar:
            config_doc = session.query(ConfiguracionDocumento).filter_by(
                ID_CFGDOCS=documento.DD_ID_CFGDOCS
            ).first()

            if config_doc and config_doc.V_SITNOAPLICA:
                documento.V_SITUACION = config_doc.V_SITNOAPLICA
                documentos_actualizados += 1

        # Actualizar la fase del proyecto a la anterior
        proyecto.N_FASE = fase_anterior_info.ID_FASE # ⚠️ CORRECCIÓN AQUÍ: Usar N_FASE en lugar de FAS_ID_FASE
        session.commit()

        if documentos_actualizados > 0:
            pass

        # Construir mensaje informativo
        mensaje = f"Fase del proyecto retrocedida a '{fase_anterior_info.D_FASE}'."
        if documentos_actualizados > 0:
            mensaje += f" Se han actualizado {documentos_actualizados} documento(s) a situación 'No Aplica'."

        return {
            "success": True,
            "mensaje": mensaje,
            "fase_anterior": fase_anterior_info.D_FASE
        }

    except Exception as e:
        session.rollback()
        import traceback
        traceback.print_exc()
        return {"success": False, "mensaje": f"Error interno al retroceder la fase: {str(e)}"}
    finally:
        if not external_session:
            session.close()

def validar_adi_completo(session, id_sistema):
    """
    Valida que todas las preguntas del ADI estén respondidas.

    Args:
        session: Sesión de SQLAlchemy
        id_sistema (int): ID del sistema

    Returns:
        dict: Información sobre el estado de validación del ADI
    """
    try:
        # Obtener todas las preguntas activas
        total_preguntas = session.query(Pregunta).filter(Pregunta.L_ESTADO == 1).count()

        if total_preguntas == 0:
            return {
                "cumple": True,
                "total": 0,
                "completados": 0,
                "pendientes": 0,
                "mensajes": [],
                "resumen": "No hay preguntas ADI configuradas"
            }

        # Contar preguntas con al menos una respuesta
        preguntas_respondidas = session.query(
            RespuestasProyecto.PRE_ID_PREGUNTA
        ).filter(
            RespuestasProyecto.SIST_ID_SISTEMA == id_sistema
        ).distinct().count()

        pendientes = total_preguntas - preguntas_respondidas
        cumple = (pendientes == 0)

        mensajes = []
        if not cumple:
            mensajes.append(f"Faltan {pendientes} pregunta(s) por responder en el ADI")


        return {
            "cumple": cumple,
            "total": total_preguntas,
            "completados": preguntas_respondidas,
            "pendientes": pendientes,
            "mensajes": mensajes,
            "resumen": f"{preguntas_respondidas}/{total_preguntas} preguntas respondidas"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "cumple": False,
            "total": 0,
            "completados": 0,
            "pendientes": 0,
            "mensajes": [f"Error al validar ADI: {str(e)}"],
            "resumen": "Error en validación"
        }



def validar_condiciones_cambio_fase(id_sistema):
    """
    Valida si se cumplen todas las condiciones necesarias para avanzar de fase.

    Retorna un diccionario con:
        - puede_avanzar (bool): Si cumple todas las condiciones
        - validaciones (dict): Estado de cada tipo de validación
        - mensajes (list): Mensajes descriptivos de lo que falta
        - elemento_bloqueante (str): Qué está bloqueando el avance

    Args:
        id_sistema (int): ID del sistema/proyecto

    Returns:
        dict: Información completa sobre el estado de validación
    """
    session = Session()
    try:
        # Obtener fase actual del proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto or not proyecto.N_FASE:
            return {
                "puede_avanzar": False,
                "validaciones": {},
                "mensajes": ["El proyecto no tiene una fase asignada"],
                "elemento_bloqueante": "Configuración de fase"
            }

        fase_actual = session.query(ConfiguracionFase).filter_by(
            ID_FASE=proyecto.N_FASE
        ).first()

        if not fase_actual:
            return {
                "puede_avanzar": False,
                "validaciones": {},
                "mensajes": ["No se encontró la configuración de la fase actual"],
                "elemento_bloqueante": "Configuración de fase"
            }


        fase_actual_orden = fase_actual.N_ORDEN
        validaciones = {}
        mensajes = []
        elemento_bloqueante = None

        # ========== VALIDACIÓN 0: ADI (SIEMPRE OBLIGATORIO) ==========
        adi_validacion = validar_adi_completo(session, id_sistema)
        validaciones["adi"] = adi_validacion

        if not adi_validacion["cumple"]:
            mensajes.extend(adi_validacion["mensajes"])
            if not elemento_bloqueante:
                elemento_bloqueante = "Cuestionario ADI"


        # ========== VALIDACIÓN 1: ELEMENTOS DE DESCRIPCIÓN ==========
        elementos_validacion = validar_elementos_descripcion(session, id_sistema, fase_actual_orden)
        validaciones["elementos"] = elementos_validacion

        if not elementos_validacion["cumple"]:
            mensajes.extend(elementos_validacion["mensajes"])
            if not elemento_bloqueante:
                elemento_bloqueante = "Elementos de Descripción"


        # ========== VALIDACIÓN 2: REQUISITOS RGPD ==========
        requisitos_validacion = validar_requisitos_fase(session, id_sistema, fase_actual)
        validaciones["requisitos"] = requisitos_validacion

        if not requisitos_validacion["cumple"]:
            mensajes.extend(requisitos_validacion["mensajes"])
            if not elemento_bloqueante:
                elemento_bloqueante = "Requisitos RGPD"


        # ========== VALIDACIÓN 3: RIESGOS  ==========
        nivel_riesgo_requerido = fase_actual.C_NIVELRIESG
        riesgos_validacion = validar_riesgos_fase(session, id_sistema, nivel_riesgo_requerido)
        validaciones["riesgos"] = riesgos_validacion

        if not riesgos_validacion["cumple"]:
            mensajes.extend(riesgos_validacion["mensajes"])
            if not elemento_bloqueante:
                elemento_bloqueante = "Riesgos"


        # ========== VALIDACIÓN 4: CONTROLES ==========
        controles_validacion = validar_controles_fase(session, id_sistema, fase_actual_orden)
        validaciones["controles"] = controles_validacion

        if not controles_validacion["cumple"]:
            mensajes.extend(controles_validacion["mensajes"])
            if not elemento_bloqueante:
                elemento_bloqueante = "Controles"


        # ========== VALIDACIÓN 4: DOCUMENTOS ==========
        documentos_validacion = validar_documentos_fase(session, id_sistema, fase_actual_orden)
        validaciones["documentos"] = documentos_validacion

        if not documentos_validacion["cumple"]:
            mensajes.extend(documentos_validacion["mensajes"])
            if not elemento_bloqueante:
                elemento_bloqueante = "Documentos"


        # ========== RESULTADO FINAL ==========
        puede_avanzar = all([
            validaciones["adi"]["cumple"],
            validaciones["elementos"]["cumple"],
            validaciones["requisitos"]["cumple"],
            validaciones["riesgos"]["cumple"],
            validaciones["controles"]["cumple"],
            validaciones["documentos"]["cumple"]
        ])

        if elemento_bloqueante:
            pass

        return {
            "puede_avanzar": puede_avanzar,
            "validaciones": validaciones,
            "mensajes": mensajes,
            "elemento_bloqueante": elemento_bloqueante,
            "fase_actual": {
                "nombre": fase_actual.D_FASE,
                "orden": fase_actual_orden
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "puede_avanzar": False,
            "validaciones": {},
            "mensajes": [f"Error al validar: {str(e)}"],
            "elemento_bloqueante": "Error del sistema"
        }
    finally:
        session.close()


def validar_elementos_descripcion(session, id_sistema, fase_actual_orden):
    """
    Valida que todos los elementos de descripción de la fase actual y anteriores
    estén completamente cumplimentados.
    """
    try:
        # Obtener elementos que deben estar evaluados
        elementos_a_evaluar = session.query(ElementosAdi).join(
            ConfiguracionFase, ElementosAdi.N_FASEVAL == ConfiguracionFase.ID_FASE
        ).filter(
            ElementosAdi.L_ESTADO == 1,
            ConfiguracionFase.N_ORDEN <= fase_actual_orden
        ).all()

        if not elementos_a_evaluar:
            return {
                "cumple": True,
                "total": 0,
                "completados": 0,
                "pendientes": 0,
                "mensajes": [],
                "resumen": "No hay elementos a evaluar"
            }


        elementos_completos = 0
        elementos_incompletos = 0

        for elemento in elementos_a_evaluar:
            # Obtener subelementos activos del elemento
            subelementos_activos = session.query(SubElementosAdi).filter(
                SubElementosAdi.ELE_ID_ELEM == elemento.ID_ELEM,
                SubElementosAdi.L_ESTADO == 1
            ).all()

            if not subelementos_activos:
                continue

            # Verificar si TODOS los subelementos del elemento están completos
            elemento_completo = True

            for subelemento in subelementos_activos:
                # Obtener todas las iteraciones de este elemento en el sistema
                datos_subelemento = session.query(DatosElementosAdi).filter(
                    DatosElementosAdi.SIST_ID_SISTEMA == id_sistema,
                    DatosElementosAdi.ELE_ID_ELEM == elemento.ID_ELEM,
                    DatosElementosAdi.SUB_IDSUBELEM == subelemento.ID_SUBELEM
                ).all()

                for dato in datos_subelemento:
                    # Verificar si tiene descripción no vacía
                    tiene_descripcion = (
                        dato.T_DESCRIPCION and
                        dato.T_DESCRIPCION.strip() != ""
                    )

                    if not tiene_descripcion:
                        elemento_completo = False
                        break

                if not elemento_completo:
                    break

            if elemento_completo:
                elementos_completos += 1
            else:
                elementos_incompletos += 1

        total_elementos = len(elementos_a_evaluar)
        cumple = (total_elementos > 0 and elementos_incompletos == 0)

        return {
            "cumple": cumple,
            "total": total_elementos,
            "completados": elementos_completos,
            "pendientes": elementos_incompletos,
            "mensajes": [],
            "resumen": f"{elementos_completos}/{total_elementos} elementos completados"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "cumple": False,
            "total": 0,
            "completados": 0,
            "pendientes": 0,
            "mensajes": [f"Error al validar elementos: {str(e)}"],
            "resumen": "Error en validación"
        }

def validar_riesgos_fase(session, id_sistema, nivel_riesgo_requerido):
    """
    Valida los riesgos según el nivel requerido por la fase actual.

    Args:
        session: Sesión de SQLAlchemy
        id_sistema (int): ID del sistema
        nivel_riesgo_requerido (str): 'I' (inherente), 'R' (residual), o None

    Returns:
        dict: Información sobre el estado de validación de riesgos
    """
    try:
        # Si no hay nivel requerido, la validación pasa automáticamente
        if not nivel_riesgo_requerido:
            return {
                "cumple": True,
                "total": 0,
                "completados": 0,
                "pendientes": 0,
                "mensajes": [],
                "resumen": "No se requiere validación de riesgos en esta fase",
                "requiere_validacion": False,
                "riesgo_global_bloquea": False,
                "nivel_riesgo_global": None
            }

        # Obtener riesgos activos y aplicables
        riesgos_a_evaluar = session.query(DatosRiesgo, Riesgo).join(
            Riesgo, DatosRiesgo.RIE_ID_RIESGO == Riesgo.ID_RIESGO
        ).filter(
            DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
            DatosRiesgo.L_ACTIVA == 1,
            DatosRiesgo.L_APLICA == 1
        ).all()

        if not riesgos_a_evaluar:
            return {
                "cumple": True,
                "total": 0,
                "completados": 0,
                "pendientes": 0,
                "mensajes": [],
                "resumen": "No hay riesgos activos que evaluar",
                "requiere_validacion": True,
                "riesgo_global_bloquea": False,
                "nivel_riesgo_global": None
            }

        total_riesgos = len(riesgos_a_evaluar)
        riesgos_completos = 0
        riesgos_pendientes = 0
        mensajes = []


        # Inicializar variables de riesgo global (solo se calculan para nivel 'R')
        riesgo_global_bloquea = False
        nivel_riesgo_global = None

        # VALIDACIÓN NIVEL "I" - RIESGO INHERENTE
        if nivel_riesgo_requerido == 'I':
            for datos_riesgo, riesgo in riesgos_a_evaluar:
                # Verificar que tenga probabilidad e impacto informados
                tiene_probabilidad = datos_riesgo.V_PROBABILIDAD is not None
                tiene_impacto = datos_riesgo.V_IMPACTO is not None

                if tiene_probabilidad and tiene_impacto:
                    riesgos_completos += 1
                else:
                    riesgos_pendientes += 1

            if riesgos_pendientes > 0:
                mensajes.append(f"{riesgos_pendientes} riesgo(s) sin probabilidad/impacto")

        # VALIDACIÓN NIVEL "R" - RIESGO RESIDUAL
        elif nivel_riesgo_requerido == 'R':

            for datos_riesgo, riesgo in riesgos_a_evaluar:

                # Primero verificar que tenga riesgo inherente
                tiene_probabilidad = datos_riesgo.V_PROBABILIDAD is not None
                tiene_impacto = datos_riesgo.V_IMPACTO is not None

                if not (tiene_probabilidad and tiene_impacto):
                    riesgos_pendientes += 1
                    continue

                # Calcular criticidad inherente
                config_criticidad = session.query(ConfiguracionCriticidad).filter_by(
                    V_IMPACTO=datos_riesgo.V_IMPACTO,
                    V_PROBAB=datos_riesgo.V_PROBABILIDAD
                ).first()

                if not config_criticidad:
                    riesgos_pendientes += 1
                    continue

                criticidad_inherente = config_criticidad.N_CRITICIDAD

                # Calcular riesgo residual
                riesgo_residual_valor, nivel_residual_texto = calcular_riesgo_residual(
                    session, datos_riesgo, criticidad_inherente
                )

                # Obtener el nivel mínimo requerido para este riesgo
                nivel_minimo_requerido_id = riesgo.N_RIERESMIN

                if nivel_minimo_requerido_id is None:
                    # Si no tiene mínimo definido, se considera válido
                    riesgos_completos += 1
                    continue

                # Obtener el valor de dato correspondiente al nivel mínimo
                valor_minimo = session.query(ValoresDato).filter(
                    ValoresDato.ID_VALDAT == nivel_minimo_requerido_id
                ).first()

                if not valor_minimo:
                    riesgos_pendientes += 1
                    continue


                # ⚠️ ESCALA INVERTIDA EN LA BD: Menor valor = Mayor criticidad
                # CRÍTICO=1, ALTO=2, MEDIO=3, BAJO=4
                # Por tanto, el riesgo residual debe ser MAYOR O IGUAL al mínimo
                # Ejemplo: Si mínimo es MEDIO (3), se aceptan: MEDIO (3) o BAJO (4)
                #          NO se aceptan: ALTO (2) o CRÍTICO (1)

                # Obtener el C_VALOR del riesgo residual desde la BD
                # Buscar el ValoresDato que corresponde al nivel residual calculado
                nivel_residual_bd = session.query(ValoresDato).filter(
                    ValoresDato.TIDA_ID_TIPDAT == valor_minimo.TIDA_ID_TIPDAT,
                    ValoresDato.D_VALOR == nivel_residual_texto
                ).first()

                if not nivel_residual_bd:
                    riesgos_pendientes += 1
                    continue

                nivel_residual_numerico = nivel_residual_bd.C_VALOR
                nivel_minimo_numerico = valor_minimo.C_VALOR


                # ✅ LÓGICA CORRECTA CON ESCALA INVERTIDA:
                # El riesgo residual debe ser MAYOR O IGUAL al nivel mínimo permitido
                # (porque menor número = mayor criticidad)
                if nivel_residual_numerico >= nivel_minimo_numerico:
                    riesgos_completos += 1
                else:
                    riesgos_pendientes += 1


            if riesgos_pendientes > 0:
                mensajes.append(f"{riesgos_pendientes} riesgo(s) con nivel residual superior al permitido")

            # ========== VALIDACIÓN ADICIONAL: RIESGO GLOBAL ==========
            # Solo para fases con nivel 'R', validar que el riesgo global no bloquee
            resultado_riesgo_global = calcular_riesgo_global(session, id_sistema)

            if resultado_riesgo_global and resultado_riesgo_global.get('nivel'):
                nivel_riesgo_global = resultado_riesgo_global['nivel']
                puede_avanzar_global = resultado_riesgo_global.get('puede_avanzar', True)


                if not puede_avanzar_global:
                    riesgo_global_bloquea = True
                    mensajes.append(f"Riesgo global {nivel_riesgo_global}: no permite avanzar de fase")

        cumple = (riesgos_pendientes == 0 and total_riesgos > 0)

        # Si el riesgo global bloquea, no se cumple aunque los riesgos individuales estén OK
        if nivel_riesgo_requerido == 'R' and riesgo_global_bloquea:
            cumple = False


        return {
            "cumple": cumple,
            "total": total_riesgos,
            "completados": riesgos_completos,
            "pendientes": riesgos_pendientes,
            "mensajes": mensajes,
            "resumen": f"{riesgos_completos}/{total_riesgos} riesgos validados",
            "requiere_validacion": True,
            "riesgo_global_bloquea": riesgo_global_bloquea if nivel_riesgo_requerido == 'R' else False,
            "nivel_riesgo_global": nivel_riesgo_global if nivel_riesgo_requerido == 'R' else None
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "cumple": False,
            "total": 0,
            "completados": 0,
            "pendientes": 0,
            "mensajes": [f"Error al validar riesgos: {str(e)}"],
            "resumen": "Error en validación",
            "requiere_validacion": True,
            "riesgo_global_bloquea": False,
            "nivel_riesgo_global": None
        }

def validar_controles_fase(session, id_sistema, fase_actual_orden):
    """
    Valida que todos los controles activos y aplicables cumplan con el nivel de madurez mínimo requerido.

    Args:
        session: Sesión de SQLAlchemy
        id_sistema (int): ID del sistema
        fase_actual_orden (int): Orden de la fase actual del proyecto

    Returns:
        dict: Información sobre el estado de validación de controles,
              incluyendo lista de IDs de controles que no cumplen
    """
    try:

        # Obtener controles que deben estar evaluados según la fase
        controles_a_evaluar = session.query(
            DatosControl,
            Control,
            GrupoControl
        ).join(
            Control, DatosControl.CON_ID_CONTROL == Control.ID_CONTROL
        ).join(
            GrupoControl, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL
        ).join(
            ConfiguracionFase, GrupoControl.N_FASEVAL == ConfiguracionFase.ID_FASE
        ).filter(
            DatosControl.SIST_ID_SISTEMA == id_sistema,
            DatosControl.L_ACTIVA == 1,
            DatosControl.L_APLICA == 1,
            ConfiguracionFase.N_ORDEN <= fase_actual_orden
        ).all()

        if not controles_a_evaluar:
            return {
                "cumple": True,
                "total": 0,
                "completados": 0,
                "pendientes": 0,
                "mensajes": [],
                "resumen": "No hay controles a evaluar",
                "controles_invalidos": [],  # ✅ NUEVA KEY
                "requiere_validacion": False  # ✅ NO SE REQUIERE VALIDACIÓN
            }

        total_controles = len(controles_a_evaluar)
        controles_completos = 0
        controles_pendientes = 0
        mensajes = []
        controles_invalidos = []  # ✅ LISTA DE IDs QUE NO CUMPLEN


        for datos_control, control, grupo in controles_a_evaluar:

            # Verificar que tenga madurez informada
            if datos_control.V_MADUREZ is None:
                controles_pendientes += 1
                controles_invalidos.append(datos_control.ID_DATCONTROL)  # ✅ AGREGAR A LA LISTA
                continue

            # Obtener el nivel de madurez mínimo requerido del control
            madurez_minima_requerida_id = control.N_MADUMIN

            if madurez_minima_requerida_id is None:
                controles_completos += 1
                continue

            # Obtener el valor de dato correspondiente al nivel mínimo requerido
            valor_minimo = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == madurez_minima_requerida_id
            ).first()

            if not valor_minimo:
                controles_pendientes += 1
                controles_invalidos.append(datos_control.ID_DATCONTROL)  # ✅ AGREGAR A LA LISTA
                continue

            # Obtener el valor de dato correspondiente a la madurez actual
            valor_actual = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == datos_control.V_MADUREZ
            ).first()

            if not valor_actual:
                controles_pendientes += 1
                controles_invalidos.append(datos_control.ID_DATCONTROL)  # ✅ AGREGAR A LA LISTA
                continue

            madurez_actual_numerico = valor_actual.C_VALOR
            madurez_minima_numerico = valor_minimo.C_VALOR


            # ✅ VALIDACIÓN: La madurez actual debe ser mayor o igual a la mínima
            if madurez_actual_numerico >= madurez_minima_numerico:
                controles_completos += 1
            else:
                controles_pendientes += 1
                controles_invalidos.append(datos_control.ID_DATCONTROL)  # ✅ AGREGAR A LA LISTA


        # Construir mensajes descriptivos
        if controles_pendientes > 0:
            mensajes.append(f"{controles_pendientes} control(es) sin madurez suficiente")

        cumple = (controles_pendientes == 0 and total_controles > 0)


        return {
            "cumple": cumple,
            "total": total_controles,
            "completados": controles_completos,
            "pendientes": controles_pendientes,
            "mensajes": mensajes,
            "resumen": f"{controles_completos}/{total_controles} controles validados",
            "controles_invalidos": controles_invalidos,  # ✅ RETORNAR LA LISTA
            "requiere_validacion": True  # ✅ SÍ SE REQUIERE VALIDACIÓN
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "cumple": False,
            "total": 0,
            "completados": 0,
            "pendientes": 0,
            "mensajes": [f"Error al validar controles: {str(e)}"],
            "resumen": "Error en validación",
            "controles_invalidos": [],  # ✅ LISTA VACÍA EN CASO DE ERROR
            "requiere_validacion": True  # ✅ ASUMIR QUE SÍ EN CASO DE ERROR
        }


def validar_documentos_fase(session, id_sistema, fase_actual_orden):
    """
    Valida que todos los documentos necesarios estén en situación final.

    Args:
        session: Sesión de SQLAlchemy
        id_sistema: ID del sistema
        fase_actual_orden: Orden de la fase actual

    Returns:
        dict con:
            - cumple (bool): Si todos los documentos necesarios están completos
            - requiere_validacion (bool): Si hay documentos que validar en esta fase
            - total (int): Total de documentos necesarios
            - completados (int): Documentos en situación final
            - pendientes (int): Documentos sin completar
            - mensajes (list): Lista de mensajes descriptivos
            - resumen (str): Resumen textual
    """
    try:
        from models import DatosDocumento, ConfiguracionDocumento, ConfiguracionFase, ValoresDato

        # Obtener documentos necesarios que deben ser evaluados en esta fase o antes
        documentos_necesarios = session.query(
            DatosDocumento,
            ConfiguracionDocumento
        ).join(
            ConfiguracionDocumento,
            DatosDocumento.DD_ID_CFGDOCS == ConfiguracionDocumento.ID_CFGDOCS
        ).join(
            ConfiguracionFase,
            ConfiguracionDocumento.N_FASEVAL == ConfiguracionFase.ID_FASE
        ).filter(
            DatosDocumento.SIST_ID_SISTEMA == id_sistema,
            DatosDocumento.L_NECESARIO == 1,  # Solo documentos marcados como necesarios
            ConfiguracionFase.N_ORDEN <= fase_actual_orden  # Que se evalúen en esta fase o antes
        ).all()

        if not documentos_necesarios:
            return {
                "cumple": True,
                "requiere_validacion": False,
                "total": 0,
                "completados": 0,
                "pendientes": 0,
                "mensajes": [],
                "resumen": "No hay documentos necesarios"
            }


        documentos_completos = 0
        documentos_pendientes = 0
        mensajes = []

        for dat_doc, cfg_doc in documentos_necesarios:
            # Obtener situación final esperada del documento
            situacion_final = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == cfg_doc.V_SITFINAL
            ).first()

            # Obtener situación actual del documento
            situacion_actual = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == dat_doc.V_SITUACION
            ).first()

            # Verificar si el documento cumple la condición de fase
            # El documento cumple si su N_ORDEN es >= al N_ORDEN de la situación final requerida
            cumple_condicion = False

            if situacion_actual and situacion_final:
                # Comparar por N_ORDEN: la situación actual debe ser igual o superior
                orden_actual = situacion_actual.N_ORDEN if situacion_actual.N_ORDEN is not None else 0
                orden_requerido = situacion_final.N_ORDEN if situacion_final.N_ORDEN is not None else 0
                cumple_condicion = orden_actual >= orden_requerido

            if cumple_condicion:
                documentos_completos += 1
                situacion_actual_txt = situacion_actual.D_VALOR if situacion_actual else "Desconocida"
                situacion_final_txt = situacion_final.D_VALOR if situacion_final else "Desconocida"
            else:
                documentos_pendientes += 1

                situacion_actual_txt = situacion_actual.D_VALOR if situacion_actual else "Desconocida"
                situacion_final_txt = situacion_final.D_VALOR if situacion_final else "Desconocida"

                mensaje = f"Documento '{cfg_doc.T_DESC}' está en situación '{situacion_actual_txt}' (se requiere al menos '{situacion_final_txt}')"
                mensajes.append(mensaje)

        cumple = documentos_pendientes == 0

        return {
            "cumple": cumple,
            "requiere_validacion": True,
            "total": len(documentos_necesarios),
            "completados": documentos_completos,
            "pendientes": documentos_pendientes,
            "mensajes": mensajes,
            "resumen": f"{documentos_completos}/{len(documentos_necesarios)} documentos completados"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "cumple": False,
            "requiere_validacion": True,
            "total": 0,
            "completados": 0,
            "pendientes": 0,
            "mensajes": [f"Error al validar documentos: {str(e)}"],
            "resumen": "Error en validación"
        }


def evaluar_necesidad_eipd_lambda(id_sistema, session):
    """
    Evalúa la necesidad de EIPD para un sistema usando reglas lambda parametrizables.

    Esta función obtiene las reglas activas de la base de datos y las evalúa
    en orden de prioridad usando expresiones lambda. Soporta reglas excluyentes
    que detienen la evaluación cuando se cumplen.

    Args:
        id_sistema (int): ID del sistema a evaluar
        session (Session): Sesión activa de SQLAlchemy

    Returns:
        str: Nivel de EIPD determinado:
            - "NECESARIA" - EIPD obligatoria
            - "RECOMENDADA" - EIPD recomendada como buena práctica
            - "NO NECESARIA" - EIPD no requerida
            - "PENDIENTE" - ADI incompleto o sin reglas activas

    Ejemplo:
        >>> session = Session()
        >>> nivel = evaluar_necesidad_eipd_lambda(123, session)
        >>> print(nivel)  # "NECESARIA"
        >>> session.close()

    Notas:
        - Las reglas se evalúan en orden ascendente por N_ORDEN
        - Si una regla con L_EXCLUYENTE=1 se cumple, se detiene la evaluación
        - Las expresiones lambda se evalúan de forma segura (validación AST)
        - Si no hay reglas activas o el ADI está incompleto, retorna "PENDIENTE"
        - El contexto se construye dinámicamente desde las respuestas existentes
    """
    try:
        # 1. Calcular puntuación ADI
        puntos_adi = calcular_puntuacion_adi(id_sistema)

        if puntos_adi is None:
            return "PENDIENTE"

        # 2. Obtener respuestas del ADI
        respuestas = {}
        query_respuestas = session.query(
            Pregunta.C_PREGUNTA,
            Respuesta.C_OPCION
        ).join(
            Respuesta, Respuesta.PRE_ID_PREGUNTA == Pregunta.ID_PREGUNTA
        ).join(
            RespuestasProyecto, RespuestasProyecto.RES_ID_RESPUESTA == Respuesta.ID_RESPUESTA
        ).filter(
            RespuestasProyecto.SIST_ID_SISTEMA == id_sistema,
            Pregunta.L_ESTADO == 1
        )

        for cod_pregunta, opcion in query_respuestas:
            if cod_pregunta in respuestas:
                # Para preguntas de selección múltiple (P4, P6, etc.)
                respuestas[cod_pregunta] += opcion
            else:
                respuestas[cod_pregunta] = opcion

        # 3. Crear contexto DINÁMICAMENTE - SIN HARDCODED
        # El contexto incluye automáticamente todas las preguntas que existen
        contexto = {
            'puntos': puntos_adi,
            'respuestas': respuestas  # Diccionario completo siempre disponible
        }

        # Agregar cada pregunta como clave individual en el contexto
        # Esto permite usar tanto ctx["P1"] como ctx["respuestas"]["P1"]
        for pregunta_codigo, pregunta_respuesta in respuestas.items():
            contexto[pregunta_codigo] = pregunta_respuesta

        # Resultado: contexto = {
        #     'puntos': 12.5,
        #     'respuestas': {'P1': 'A', 'P2': 'D', ...},
        #     'P1': 'A',
        #     'P2': 'D',
        #     'P3': 'C',
        #     ...
        #     'PX': 'Y'  <- funciona con cualquier código de pregunta
        # }


        # 4. Obtener reglas activas ordenadas - USANDO ORM
        reglas = session.query(ReglaEIPD).filter(
            ReglaEIPD.L_ACTIVA == 1
        ).order_by(
            ReglaEIPD.N_ORDEN.asc()
        ).all()

        if not reglas:
            return "PENDIENTE"

        # 5. Evaluar reglas en orden
        #print(f"\n{'='*70}")
        #print(f"🔍 EVALUACIÓN EIPD - Sistema {id_sistema}")
        #print(f"📊 Puntuación ADI: {puntos_adi}")
        #print(f"📋 Respuestas disponibles: {list(respuestas.keys())}")
        #print(f"{'='*70}\n")

        resultado_final = None

        for regla in reglas:
            # Ahora 'regla' es un objeto ReglaEIPD, no una tupla
            codigo = regla.C_CODIGO
            descripcion = regla.D_REGLA
            expresion = regla.T_EXPRESION
            v_resultado = regla.V_RESULTADO
            excluyente = regla.L_EXCLUYENTE

            # Obtener el nivel de EIPD asociado a esta regla
            resultado_valor = session.query(ValoresDato).filter(
                ValoresDato.ID_VALDAT == v_resultado
            ).first()

            if not resultado_valor:
        #       print(f"⚠️ No se encontró valor de resultado para regla {codigo}")
                continue

            nivel_regla = resultado_valor.D_VALOR

        #  print(f"📋 [{codigo}] {descripcion}")
        #  print(f"   Expresión: {expresion}")

            try:
                # Evaluar la expresión lambda de forma segura
                cumple = _evaluar_lambda_segura(expresion, contexto)

                if cumple:
        #         print(f"   ✅ CUMPLE → {nivel_regla}")

                    # Si no hay resultado previo, tomar este
                    if resultado_final is None:
                        resultado_final = nivel_regla

                    # Si la regla es excluyente, detener evaluación
                    if excluyente == 1:
            #            print(f"   🛑 Regla excluyente - Deteniendo evaluación")
                        break
                else:
            #print(f"   ❌ NO CUMPLE")
                    kk = 1

            except Exception as e:
                #print(f"   ⚠️ ERROR al evaluar: {e}")
                kk = 1

            #print()

        # 6. Resultado final
        if resultado_final is None:
            resultado_final = "NO NECESARIA"

        #print(f"{'='*70}")
        #print(f"📝 RESULTADO FINAL: {resultado_final}")
        #print(f"{'='*70}\n")

        return resultado_final

    except Exception as e:
        #print(f"❌ Error en evaluar_necesidad_eipd_lambda: {e}")
        import traceback
        traceback.print_exc()
        return "PENDIENTE"


def _evaluar_lambda_segura(expresion, contexto):
    """
    Evalúa una expresión lambda de forma segura mediante validación AST.

    Esta función parsea, valida, compila y EJECUTA una expresión lambda Python,
    asegurándose de que solo contenga operaciones permitidas y seguras.

    Args:
        expresion (str): Expresión lambda como string (ej: 'lambda ctx: ctx["puntos"] >= 10')
        contexto (dict): Diccionario con variables disponibles para la expresión

    Returns:
        bool: Resultado de ejecutar la lambda con el contexto proporcionado

    Raises:
        ValueError: Si la expresión contiene operaciones no permitidas
        Exception: Si hay error al evaluar o ejecutar la expresión

    Operaciones permitidas:
        - Comparaciones: ==, !=, <, >, <=, >=, in, not in
        - Lógicos: and, or, not
        - Aritméticos: +, -, *, /, %
        - Funciones: any, all, len, sum, min, max, abs, round
        - Estructuras: list, dict, tuple
        - Acceso a diccionarios y listas
        - List comprehensions
        - Generator expressions
        - Expresiones ternarias

    Operaciones bloqueadas:
        - Imports
        - Acceso a atributos (. operator)
        - Definición de funciones
        - Loops (for, while)
        - Try/except
        - Exec, eval, compile
        - Cualquier operación no explícitamente permitida

    Ejemplo:
        >>> ctx = {'puntos': 12.5, 'P5': ['A', 'B']}  # P5 = Dificultades RGPD (V022)
        >>> _evaluar_lambda_segura('lambda ctx: ctx["puntos"] >= 10', ctx)
        True
        >>> _evaluar_lambda_segura('lambda ctx: any(x in ctx["P5"] for x in ["A", "B", "G"])', ctx)
        True
        >>> ctx2 = {'puntos': 2.0}
        >>> _evaluar_lambda_segura('lambda ctx: ctx["puntos"] >= 10', ctx2)
        False
    """
    # Funciones built-in permitidas
    safe_builtins = {
        'any': any,
        'all': all,
        'len': len,
        'sum': sum,
        'min': min,
        'max': max,
        'abs': abs,
        'round': round,
    }

    try:
        # 1. Parsear la expresión a AST
        tree = ast.parse(expresion, mode='eval')

        # 2. Validar que solo contenga operaciones seguras
        if not _validar_ast_seguro(tree, safe_builtins):
            raise ValueError("Expresión contiene operaciones no permitidas")

        # 3. Compilar la expresión
        code = compile(tree, '<string>', 'eval')

        # 4. Evaluar para obtener la función lambda
        lambda_func = eval(code, {"__builtins__": safe_builtins}, {'ctx': contexto})

        # 5. EJECUTAR la lambda con el contexto
        resultado = lambda_func(contexto)

        # 6. Convertir a booleano
        return bool(resultado)

    except Exception as e:
        raise


def _validar_ast_seguro(tree, safe_builtins):
    """
    Valida que un árbol AST solo contenga nodos y operaciones seguras.

    Args:
        tree: Árbol AST a validar
        safe_builtins (dict): Diccionario con funciones permitidas

    Returns:
        bool: True si el AST es seguro, False en caso contrario

    Nodos permitidos:
        - Expression, Lambda, arguments, arg
        - Compare, BoolOp, UnaryOp, BinOp
        - Subscript, Index, List, Tuple, Dict
        - Constant, Name, Load
        - Operadores de comparación (Eq, NotEq, Lt, etc.)
        - Operadores lógicos (And, Or, Not)
        - Operadores aritméticos (Add, Sub, Mult, etc.)
        - Call, keyword
        - IfExp (expresiones ternarias)
        - ListComp, GeneratorExp, comprehension

    Nodos bloqueados:
        - Import, ImportFrom
        - Attribute (acceso a atributos con .)
        - FunctionDef, AsyncFunctionDef
        - ClassDef
        - For, While, With
        - Try, ExceptHandler
        - Global, Nonlocal
        - Exec, Eval
        - Cualquier otro no explícitamente permitido
    """
    # Nodos AST permitidos
    ALLOWED_NODES = (
        # Estructuras básicas
        ast.Expression, ast.Lambda, ast.arguments, ast.arg,

        # Operadores
        ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp,

        # Acceso a datos
        ast.Subscript, ast.List, ast.Tuple, ast.Dict,
        ast.Constant, ast.Name, ast.Load, ast.Store,

        # Operadores de comparación
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.In, ast.NotIn, ast.Is, ast.IsNot,

        # Operadores lógicos
        ast.And, ast.Or, ast.Not,

        # Operadores aritméticos
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow,

        # Llamadas a funciones
        ast.Call, ast.keyword,

        # Expresiones condicionales (ternarias)
        ast.IfExp,

        # List comprehensions y generator expressions
        ast.ListComp, ast.GeneratorExp, ast.comprehension,
    )

    # Python 3.9+ usa ast.Index de forma diferente
    import sys
    if sys.version_info >= (3, 9):
        # En Python 3.9+, ast.Index ya no se usa explícitamente
        pass
    else:
        # En Python 3.8 y anteriores, incluir ast.Index
        ALLOWED_NODES = ALLOWED_NODES + (ast.Index,)

    # Recorrer todos los nodos del árbol
    for node in ast.walk(tree):
        # Verificar que el nodo está en la lista permitida
        if not isinstance(node, ALLOWED_NODES):
            return False

        # Verificar llamadas a funciones
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name not in safe_builtins:
                    return False

    return True


def get_requisitos_para_formulario(id_sistema):
    """
    Obtiene todos los requisitos configurados para mostrar en el formulario,
    filtrando por fase de visualización y ordenados correctamente.

    Args:
        id_sistema (int): ID del sistema/proyecto actual

    Returns:
        tuple: (requisitos_data, fase_actual, instrumentos_contractuales)
            - requisitos_data: Lista de diccionarios con datos completos de cada requisito
            - fase_actual: Objeto ConfiguracionFase de la fase actual del proyecto
            - instrumentos_contractuales: Lista de valores para el combo de instrumentos
    """
    db_session = Session()
    try:
        # Obtener la fase actual del proyecto
        proyecto = db_session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto or not proyecto.N_FASE:
            return [], None, []

        fase_actual = db_session.query(ConfiguracionFase).filter_by(
            ID_FASE=proyecto.N_FASE
        ).first()

        if not fase_actual:
            return [], None, []

        fase_actual_orden = fase_actual.N_ORDEN

        # Obtener instrumentos contractuales para el combo
        # Buscar el tipo de dato por código "ICD"
        tipo_instrumento = db_session.query(TiposDato).filter_by(
            C_TIPDAT='ICD'
        ).first()

        instrumentos = []
        if tipo_instrumento:
            instrumentos = db_session.query(ValoresDato).filter_by(
                TIDA_ID_TIPDAT=tipo_instrumento.ID_TIPDAT
            ).order_by(ValoresDato.C_VALOR).all()
        else:
            pass

        # Consulta de requisitos activos
        requisitos = db_session.query(ConfiguracionRequisito).filter(
            ConfiguracionRequisito.L_ESTADO == 1
        ).all()


        # Filtrar por fase de visualización y ordenar
        requisitos_visibles = []
        for req in requisitos:
            # Obtener el orden de la fase visual del requisito
            if req.N_FASEVISUAL:
                fase_visual = db_session.query(ConfiguracionFase).filter_by(
                    ID_FASE=req.N_FASEVISUAL
                ).first()

                if fase_visual:
                    if fase_visual.N_ORDEN <= fase_actual_orden:
                        requisitos_visibles.append(req)
                    else:
                        pass
                else:
                    pass
            else:
                # Si no tiene fase visual definida, siempre es visible
                requisitos_visibles.append(req)

        # Ordenar por N_ORDVISU
        requisitos_visibles.sort(key=lambda r: r.N_ORDVISU if r.N_ORDVISU else 999999)


        # Construir datos completos para cada requisito
        requisitos_data = []
        for req in requisitos_visibles:
            # Obtener o crear datos del requisito para este proyecto
            dato_req = db_session.query(DatosRequisito).filter_by(
                SIST_ID_SISTEMA=id_sistema,
                REQ_ID_REQU=req.ID_REQ
            ).first()

            if not dato_req:
                # Si no existe, inicializar (esto no debería pasar si la inicialización funciona)

                # Obtener estados iniciales
                estado_planif_inicial = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                    C_TIPOESTADO='P',
                    L_INICIAL=1
                ).first()

                estado_cumpl_inicial = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                    C_TIPOESTADO='C',
                    L_INICIAL=1
                ).first()

                # Generar ID
                max_id = db_session.query(func.max(DatosRequisito.ID_DATREQ)).scalar() or 0
                nuevo_id = ((max_id // 100) + 1) * 100 + 10

                dato_req = DatosRequisito(
                    ID_DATREQ=nuevo_id,
                    SIST_ID_SISTEMA=id_sistema,
                    REQ_ID_REQU=req.ID_REQ,
                    L_APLICA=1 if req.L_APLICAOBLIG == 1 else None,
                    N_ESTPLANIF=estado_planif_inicial.ID_ESTREQ if estado_planif_inicial else None,
                    N_ESTCUMPL=estado_cumpl_inicial.ID_ESTREQ if estado_cumpl_inicial else None
                )
                db_session.add(dato_req)
                db_session.commit()

            # Determinar visibilidad y habilitación de campos según fase
            # Estado Planificación: visible si fase actual >= fase visual
            mostrar_estado_planif = True  # Ya se filtró por fase visual

            # 🆕 Verificar si el requisito tiene controles asociados
            tiene_controles = db_session.query(ConfiguracionRequisitoControl).filter_by(
                REQ_ID_REQU=req.ID_REQ
            ).count() > 0

            # Estado Planificación: habilitado solo si fase actual == fase validación planificación
            fase_val_planif = None
            habilitar_estado_planif = False
            if req.N_FASEVALPLANIF:
                fase_val_planif = db_session.query(ConfiguracionFase).filter_by(
                    ID_FASE=req.N_FASEVALPLANIF
                ).first()
                if fase_val_planif and fase_val_planif.N_ORDEN == fase_actual_orden:
                    habilitar_estado_planif = True

            # Estado Cumplimiento: visible y habilitado solo si fase actual == fase validación cumplimiento
            fase_val_cumpl = None
            mostrar_estado_cumpl = False
            habilitar_estado_cumpl = False
            if req.N_FASEVALCUMPL:
                fase_val_cumpl = db_session.query(ConfiguracionFase).filter_by(
                    ID_FASE=req.N_FASEVALCUMPL
                ).first()
                if fase_val_cumpl and fase_val_cumpl.N_ORDEN <= fase_actual_orden:
                    mostrar_estado_cumpl = True
                    if fase_val_cumpl.N_ORDEN == fase_actual_orden:
                        habilitar_estado_cumpl = True

            # Obtener estados disponibles
            estados_planif = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                C_TIPOESTADO='P'
            ).order_by(ConfiguracionEstadoRequisito.N_ORDVISU).all()

            estados_cumpl = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                C_TIPOESTADO='C'
            ).order_by(ConfiguracionEstadoRequisito.N_ORDVISU).all()

            # Determinar si mostrar botón de plan de mejora
            # 🆕 Ahora se usa L_PLANMEJORA independiente de L_JUSTOBLIG
            mostrar_plan_mejora = False
            if dato_req.N_ESTCUMPL:
                estado_cumpl_actual = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                    ID_ESTREQ=dato_req.N_ESTCUMPL
                ).first()
                if estado_cumpl_actual and estado_cumpl_actual.L_PLANMEJORA == 1:
                    mostrar_plan_mejora = True

            # Obtener el instrumento contractual actual
            instrumento_actual = None
            if dato_req.V_INSTRCONTR:
                instrumento_actual = db_session.query(ValoresDato).filter_by(
                    ID_VALDAT=dato_req.V_INSTRCONTR
                ).first()

            requisitos_data.append({
                'requisito': req,
                'dato': dato_req,
                'mostrar_estado_planif': mostrar_estado_planif,
                'habilitar_estado_planif': habilitar_estado_planif,
                'mostrar_estado_cumpl': mostrar_estado_cumpl,
                'habilitar_estado_cumpl': habilitar_estado_cumpl,
                'estados_planif': estados_planif,
                'estados_cumpl': estados_cumpl,
                'mostrar_plan_mejora': mostrar_plan_mejora,
                'instrumento_actual': instrumento_actual,
                'tiene_controles': tiene_controles  # 🆕 Indicador de controles asociados
            })

        # Determinar si se debe ocultar la cabecera de Estado Cumplimiento
        # Si NINGÚN requisito tiene mostrar_estado_cumpl = True, ocultar cabecera
        alguno_muestra_cumpl = any(item['mostrar_estado_cumpl'] for item in requisitos_data)
        ocultar_cabecera_cumpl = not alguno_muestra_cumpl

        # === CALCULAR RESUMEN POR ESTADOS ===

        # 1. Verificar si hay requisitos que muestran estado de planificación
        alguno_muestra_planif = any(item['mostrar_estado_planif'] for item in requisitos_data)

        # 2. Obtener todos los estados de planificación ordenados
        estados_planif_resumen = []
        if alguno_muestra_planif:
            estados_planif_resumen = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                C_TIPOESTADO='P'
            ).order_by(ConfiguracionEstadoRequisito.N_ORDVISU).all()

            # Contar requisitos por cada estado de planificación
            # Solo cuenta requisitos con L_APLICA definido (excluye "Por decidir")
            for estado in estados_planif_resumen:
                estado.cantidad = sum(
                    1 for item in requisitos_data
                    if item['dato'].L_APLICA is not None
                    and item['dato'].N_ESTPLANIF == estado.ID_ESTREQ
                )

        # 3. Verificar si hay requisitos que muestran estado de cumplimiento
        alguno_muestra_cumpl_resumen = alguno_muestra_cumpl

        # 4. Obtener todos los estados de cumplimiento ordenados
        estados_cumpl_resumen = []
        if alguno_muestra_cumpl_resumen:
            estados_cumpl_resumen = db_session.query(ConfiguracionEstadoRequisito).filter_by(
                C_TIPOESTADO='C'
            ).order_by(ConfiguracionEstadoRequisito.N_ORDVISU).all()

            # Contar requisitos aplicables por cada estado de cumplimiento
            for estado in estados_cumpl_resumen:
                estado.cantidad = sum(
                    1 for item in requisitos_data
                    if item['dato'].L_APLICA == 1
                    and item['dato'].N_ESTCUMPL == estado.ID_ESTREQ
                )

        return (
            requisitos_data,
            fase_actual,
            instrumentos,
            ocultar_cabecera_cumpl,
            alguno_muestra_planif,
            estados_planif_resumen,
            alguno_muestra_cumpl_resumen,
            estados_cumpl_resumen
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return [], None, [], True, False, [], False, []
    finally:
        db_session.close()


def validar_requisitos_fase(session, id_sistema, fase_actual):
    """
    Valida que los requisitos cumplan los criterios para avanzar de fase.

    Lógica de validación:
    0. VALIDACIÓN GLOBAL: Todos los requisitos con L_APLICA = NULL o L_APLICA = 0 sin justificación
       - Los "Por decidir" (L_APLICA = NULL) se marcan SIEMPRE como INVÁLIDOS
       - Los "No aplica" (L_APLICA = 0) sin T_JUSTAPLICA se marcan como INVÁLIDOS
       - Independientemente de si corresponden a la fase actual o no

    1. VALIDACIÓN PRIORITARIA (para requisitos de fase actual): L_APLICA debe estar definido
       - Si L_APLICA IS NULL ('Por decidir') → INVÁLIDO
       - Solo se evalúan requisitos con L_APLICA = 1 (Sí)

    2. Si fase_actual coincide con N_FASEVALPLANIF del requisito:
       - El estado de planificación debe tener L_AVANCEFASE = 1
       - Si L_NOAPLICA = 1 y L_JUSTOBLIG = 1 → T_JUSTAPLICA debe estar informado
       - Si L_NOAPLICA = 0 y L_JUSTOBLIG = 1 → T_JUSTPLANIF debe estar informado

    3. Si fase_actual coincide con N_FASEVALCUMPL del requisito:
       - El estado de cumplimiento debe tener L_AVANCEFASE = 1
       - Si L_JUSTOBLIG = 1 del estado → T_JUSTCUMPL debe estar informado

    Args:
        session: Sesión de SQLAlchemy
        id_sistema: ID del proyecto
        fase_actual: Objeto ConfiguracionFase de la fase actual

    Returns:
        dict con:
            - cumple (bool): True si todos los requisitos cumplen criterios
            - total (int): Total de requisitos a evaluar
            - completados (int): Requisitos que cumplen criterios
            - pendientes (int): Requisitos que NO cumplen criterios (incluye "Por decidir" y "No aplica" sin justif.)
            - mensajes (list): Mensajes descriptivos
            - resumen (str): Resumen textual
            - requisitos_invalidos (list): IDs de requisitos que NO cumplen (incluye TODOS los "Por decidir" y "No aplica" sin justif.)
            - requiere_validacion (bool): Si se requiere validación en esta fase
    """
    try:

        # Obtener todos los requisitos del catálogo que son visibles en esta fase
        # IMPORTANTE: Incluye requisitos con L_APLICA = 1 (Sí) Y L_APLICA IS NULL (Por decidir)
        # Los que tienen L_APLICA = 0 (No) se excluyen porque no aplican
        requisitos_a_evaluar = session.query(
            DatosRequisito,
            ConfiguracionRequisito
        ).join(
            ConfiguracionRequisito,
            DatosRequisito.REQ_ID_REQU == ConfiguracionRequisito.ID_REQ
        ).filter(
            DatosRequisito.SIST_ID_SISTEMA == id_sistema,
            ConfiguracionRequisito.L_ESTADO == 1,  # Solo requisitos activos
            DatosRequisito.L_APLICA != 0,  # Excluir solo los que NO aplican (L_APLICA = 0)
            or_(
                ConfiguracionRequisito.N_FASEVALPLANIF == fase_actual.ID_FASE,
                ConfiguracionRequisito.N_FASEVALCUMPL == fase_actual.ID_FASE
            )
        ).all()

        if not requisitos_a_evaluar:
            return {
                "cumple": True,
                "total": 0,
                "completados": 0,
                "pendientes": 0,
                "mensajes": [],
                "resumen": "No hay requisitos a evaluar",
                "requisitos_invalidos": [],
                "motivos_invalidos": {},  # 🆕 Diccionario vacío
                "requiere_validacion": False
            }

        total_requisitos = len(requisitos_a_evaluar)
        requisitos_completos = 0
        requisitos_pendientes = 0
        mensajes = []
        requisitos_invalidos = []
        motivos_invalidos = {}  # 🆕 Diccionario para almacenar motivos específicos por ID


        for dato_req, config_req in requisitos_a_evaluar:

            cumple_criterios = False

            # VALIDACIÓN PRIORITARIA: Verificar si L_APLICA está definido
            if dato_req.L_APLICA is None:
                requisitos_pendientes += 1
                requisitos_invalidos.append(dato_req.ID_DATREQ)
                motivos_invalidos[dato_req.ID_DATREQ] = "Indique si el requisito aplica o no"
                continue

            # CASO 1: Validar estado de PLANIFICACIÓN
            if config_req.N_FASEVALPLANIF == fase_actual.ID_FASE:

                if dato_req.N_ESTPLANIF is None:
                    requisitos_pendientes += 1
                    requisitos_invalidos.append(dato_req.ID_DATREQ)
                    motivos_invalidos[dato_req.ID_DATREQ] = "Debe seleccionar un estado de planificación"
                    continue

                # Obtener el estado de planificación
                estado_planif = session.query(ConfiguracionEstadoRequisito).filter(
                    ConfiguracionEstadoRequisito.ID_ESTREQ == dato_req.N_ESTPLANIF
                ).first()

                if not estado_planif:
                    requisitos_pendientes += 1
                    requisitos_invalidos.append(dato_req.ID_DATREQ)
                    motivos_invalidos[dato_req.ID_DATREQ] = "Estado de planificación no válido"
                    continue


                # Verificar L_AVANCEFASE
                if estado_planif.L_AVANCEFASE != 1:
                    requisitos_pendientes += 1
                    requisitos_invalidos.append(dato_req.ID_DATREQ)
                    motivos_invalidos[dato_req.ID_DATREQ] = f"El estado '{estado_planif.D_ESTADO}' no permite avance de fase"
                    continue

                # Verificar justificación según L_NOAPLICA y L_JUSTOBLIG
                # 🆕 L_JUSTOBLIG ahora controla qué justificación es obligatoria:
                #    - Si L_NOAPLICA = 1: L_JUSTOBLIG controla T_JUSTAPLICA
                #    - Si L_NOAPLICA = 0: L_JUSTOBLIG controla T_JUSTPLANIF
                if estado_planif.L_NOAPLICA == 1:
                    # Estado "No Aplica": L_JUSTOBLIG controla si T_JUSTAPLICA es obligatoria
                    if estado_planif.L_JUSTOBLIG == 1:
                        if not dato_req.T_JUSTAPLICA or not dato_req.T_JUSTAPLICA.strip():
                            requisitos_pendientes += 1
                            requisitos_invalidos.append(dato_req.ID_DATREQ)
                            motivos_invalidos[dato_req.ID_DATREQ] = "Debe indicar una justificación de aplicabilidad"
                            continue
                        else:
                            pass
                    else:
                        pass
                else:
                    # Estado normal: L_JUSTOBLIG controla si T_JUSTPLANIF es obligatoria
                    if estado_planif.L_JUSTOBLIG == 1:
                        if not dato_req.T_JUSTPLANIF or not dato_req.T_JUSTPLANIF.strip():
                            requisitos_pendientes += 1
                            requisitos_invalidos.append(dato_req.ID_DATREQ)
                            motivos_invalidos[dato_req.ID_DATREQ] = "Debe indicar una justificación de planificación"
                            continue
                        else:
                            pass

                # Si llega aquí, cumple todos los criterios
                cumple_criterios = True

            # CASO 2: Validar estado de CUMPLIMIENTO
            elif config_req.N_FASEVALCUMPL == fase_actual.ID_FASE:

                if dato_req.N_ESTCUMPL is None:
                    requisitos_pendientes += 1
                    requisitos_invalidos.append(dato_req.ID_DATREQ)
                    motivos_invalidos[dato_req.ID_DATREQ] = "Debe seleccionar un estado de cumplimiento"
                    continue

                # Obtener el estado de cumplimiento
                estado_cumpl = session.query(ConfiguracionEstadoRequisito).filter(
                    ConfiguracionEstadoRequisito.ID_ESTREQ == dato_req.N_ESTCUMPL
                ).first()

                if not estado_cumpl:
                    requisitos_pendientes += 1
                    requisitos_invalidos.append(dato_req.ID_DATREQ)
                    motivos_invalidos[dato_req.ID_DATREQ] = "Estado de cumplimiento no válido"
                    continue


                # Verificar L_AVANCEFASE
                if estado_cumpl.L_AVANCEFASE != 1:
                    requisitos_pendientes += 1
                    requisitos_invalidos.append(dato_req.ID_DATREQ)
                    motivos_invalidos[dato_req.ID_DATREQ] = f"El estado '{estado_cumpl.D_ESTADO}' no permite avance de fase"
                    continue

                # Verificar L_JUSTOBLIG (justificación de cumplimiento)
                if estado_cumpl.L_JUSTOBLIG == 1:
                    if not dato_req.T_JUSTCUMPL or not dato_req.T_JUSTCUMPL.strip():
                        requisitos_pendientes += 1
                        requisitos_invalidos.append(dato_req.ID_DATREQ)
                        motivos_invalidos[dato_req.ID_DATREQ] = "Debe indicar una justificación de cumplimiento"
                        continue
                    else:
                        pass

                # Si llega aquí, cumple todos los criterios
                cumple_criterios = True

            # Contabilizar resultado
            if cumple_criterios:
                requisitos_completos += 1
            else:
                requisitos_pendientes += 1
                requisitos_invalidos.append(dato_req.ID_DATREQ)
                if dato_req.ID_DATREQ not in motivos_invalidos:
                    motivos_invalidos[dato_req.ID_DATREQ] = "No cumple criterios de verificación"


        # IMPORTANTE: Añadir TODOS los requisitos con L_APLICA = NULL (Por decidir)
        # independientemente de si se validan en esta fase o no
        requisitos_por_decidir_todos = session.query(DatosRequisito).join(
            ConfiguracionRequisito,
            DatosRequisito.REQ_ID_REQU == ConfiguracionRequisito.ID_REQ
        ).filter(
            DatosRequisito.SIST_ID_SISTEMA == id_sistema,
            ConfiguracionRequisito.L_ESTADO == 1,
            DatosRequisito.L_APLICA.is_(None)  # Solo "Por decidir"
        ).all()

        # Añadir a la lista de inválidos (sin duplicados)
        ids_por_decidir_adicionales = [r.ID_DATREQ for r in requisitos_por_decidir_todos
                                       if r.ID_DATREQ not in requisitos_invalidos]

        if ids_por_decidir_adicionales:
            requisitos_invalidos.extend(ids_por_decidir_adicionales)
            requisitos_pendientes += len(ids_por_decidir_adicionales)
            # 🆕 Añadir motivos para los requisitos "Por decidir" adicionales
            for id_req in ids_por_decidir_adicionales:
                motivos_invalidos[id_req] = "Indique si el requisito aplica o no"

        # IMPORTANTE 2: Añadir requisitos con L_APLICA = 0 (No aplica) sin justificación
        # 🆕 Solo si el estado de planificación tiene L_JUSTOBLIG = 1
        requisitos_no_aplica = session.query(DatosRequisito).join(
            ConfiguracionRequisito,
            DatosRequisito.REQ_ID_REQU == ConfiguracionRequisito.ID_REQ
        ).filter(
            DatosRequisito.SIST_ID_SISTEMA == id_sistema,
            ConfiguracionRequisito.L_ESTADO == 1,
            DatosRequisito.L_APLICA == 0,  # Solo "No aplica"
            or_(
                DatosRequisito.T_JUSTAPLICA.is_(None),
                DatosRequisito.T_JUSTAPLICA == ''
            )
        ).all()

        # Filtrar solo los que tienen estado con L_JUSTOBLIG = 1
        ids_no_aplica_sin_just = []
        for req in requisitos_no_aplica:
            if req.ID_DATREQ in requisitos_invalidos:
                continue  # Ya está marcado como inválido

            # Verificar si el estado de planificación requiere justificación
            requiere_justificacion = True  # Por defecto, sí requiere
            if req.N_ESTPLANIF:
                estado_planif = session.query(ConfiguracionEstadoRequisito).filter(
                    ConfiguracionEstadoRequisito.ID_ESTREQ == req.N_ESTPLANIF
                ).first()
                if estado_planif and estado_planif.L_NOAPLICA == 1:
                    # Es un estado "No aplica", usar su L_JUSTOBLIG
                    requiere_justificacion = (estado_planif.L_JUSTOBLIG == 1)

            if requiere_justificacion:
                ids_no_aplica_sin_just.append(req.ID_DATREQ)

        if ids_no_aplica_sin_just:
            requisitos_invalidos.extend(ids_no_aplica_sin_just)
            requisitos_pendientes += len(ids_no_aplica_sin_just)
            # Añadir motivos para los requisitos "No aplica" sin justificación
            for id_req in ids_no_aplica_sin_just:
                motivos_invalidos[id_req] = "Debe indicar una justificación de aplicabilidad"
        else:
            pass

        # Construir mensajes descriptivos
        if requisitos_pendientes > 0:
            mensajes.append(f"{requisitos_pendientes} requisito(s) sin verificar")

        cumple = (requisitos_pendientes == 0 and total_requisitos > 0)


        return {
            "cumple": cumple,
            "total": total_requisitos,
            "completados": requisitos_completos,
            "pendientes": requisitos_pendientes,
            "mensajes": mensajes,
            "resumen": f"{requisitos_completos}/{total_requisitos} requisitos validados",
            "requisitos_invalidos": requisitos_invalidos,
            "motivos_invalidos": motivos_invalidos,  # 🆕 Diccionario con motivos específicos por ID
            "requiere_validacion": True
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "cumple": False,
            "total": 0,
            "completados": 0,
            "pendientes": 0,
            "mensajes": [f"Error al validar requisitos: {str(e)}"],
            "resumen": "Error en validación",
            "requisitos_invalidos": [],
            "motivos_invalidos": {},  # 🆕 Diccionario vacío
            "requiere_validacion": True
        }


def validar_requisito_individual(session, id_dato_req, id_sistema):
    """
    Valida un requisito individual para determinar si cumple criterios de avance.
    Se usa para actualización en tiempo real de la validación visual.

    Lógica de validación:
    1. VALIDACIÓN: L_APLICA debe estar definido
       - Si L_APLICA IS NULL ('Por decidir') → INVÁLIDO

    2. VALIDACIÓN: Si L_APLICA = 0 ('No aplica')
       - Debe tener T_JUSTAPLICA informado
       - Si falta justificación → INVÁLIDO

    3. Si está en fase de planificación:
       - N_ESTPLANIF debe estar informado
       - Estado debe tener L_AVANCEFASE = 1
       - Si L_NOAPLICA = 1 y L_JUSTOBLIG = 1 → T_JUSTAPLICA requerido
       - Si L_NOAPLICA = 0 y L_JUSTOBLIG = 1 → T_JUSTPLANIF requerido

    4. Si está en fase de cumplimiento:
       - N_ESTCUMPL debe estar informado
       - Estado debe tener L_AVANCEFASE = 1
       - Si L_JUSTOBLIG = 1 → T_JUSTCUMPL requerido

    Args:
        session: Sesión de SQLAlchemy
        id_dato_req: ID del registro en IA_DATEREQUISITOS
        id_sistema: ID del sistema/proyecto

    Returns:
        dict con:
            - valido (bool): True si cumple criterios
            - motivo (str): Razón si no es válido
    """
    try:
        # Obtener el requisito
        dato_req = session.query(DatosRequisito).join(
            ConfiguracionRequisito,
            DatosRequisito.REQ_ID_REQU == ConfiguracionRequisito.ID_REQ
        ).filter(
            DatosRequisito.ID_DATREQ == id_dato_req,
            DatosRequisito.SIST_ID_SISTEMA == id_sistema
        ).first()

        if not dato_req:
            return {"valido": False, "motivo": "Requisito no encontrado"}

        # VALIDACIÓN 1: L_APLICA debe estar definido
        if dato_req.L_APLICA is None:
            return {"valido": False, "motivo": "Indique si el requisito aplica o no"}

        # VALIDACIÓN 2: Si L_APLICA = 0 (No aplica), verificar si requiere justificación
        # 🆕 Ahora consultamos el estado de planificación para ver si L_JUSTOBLIG = 1
        if dato_req.L_APLICA == 0:
            # Buscar el estado de planificación actual (debería ser "No aplica")
            if dato_req.N_ESTPLANIF:
                estado_planif = session.query(ConfiguracionEstadoRequisito).filter(
                    ConfiguracionEstadoRequisito.ID_ESTREQ == dato_req.N_ESTPLANIF
                ).first()

                # Si el estado tiene L_NOAPLICA = 1, usar su L_JUSTOBLIG para decidir
                if estado_planif and estado_planif.L_NOAPLICA == 1:
                    if estado_planif.L_JUSTOBLIG == 1:
                        # Solo exigir justificación si L_JUSTOBLIG = 1
                        if not dato_req.T_JUSTAPLICA or dato_req.T_JUSTAPLICA.strip() == '':
                            return {"valido": False, "motivo": "Debe indicar una justificación de aplicabilidad"}
                    # Si L_JUSTOBLIG = 0, no se requiere justificación
                    return {"valido": True, "motivo": "No aplica (sin justificación requerida)"}

            # Fallback: si no hay estado o no es "No aplica", exigir justificación por defecto
            if not dato_req.T_JUSTAPLICA or dato_req.T_JUSTAPLICA.strip() == '':
                return {"valido": False, "motivo": "Debe indicar una justificación de aplicabilidad"}
            return {"valido": True, "motivo": "No aplica (con justificación)"}

        # Obtener fase actual (función definida en este mismo módulo)
        fase_actual, _ = obtener_fase_proyecto(id_sistema)

        if not fase_actual:
            return {"valido": False, "motivo": "No se pudo determinar fase actual"}

        # Obtener configuración del requisito
        config_req = session.query(ConfiguracionRequisito).filter(
            ConfiguracionRequisito.ID_REQ == dato_req.REQ_ID_REQU
        ).first()

        if not config_req:
            return {"valido": False, "motivo": "Configuración de requisito no encontrada"}

        # VALIDACIÓN 2: Si está en fase de planificación
        if config_req.N_FASEVALPLANIF == fase_actual.ID_FASE:
            if dato_req.N_ESTPLANIF is None:
                return {"valido": False, "motivo": "Debe seleccionar un estado de planificación"}

            estado_planif = session.query(ConfiguracionEstadoRequisito).filter(
                ConfiguracionEstadoRequisito.ID_ESTREQ == dato_req.N_ESTPLANIF
            ).first()

            if not estado_planif:
                return {"valido": False, "motivo": "Estado de planificación no válido"}

            if estado_planif.L_AVANCEFASE != 1:
                return {"valido": False, "motivo": f"El estado '{estado_planif.D_ESTADO}' no permite avance de fase"}

            # 🆕 Verificar justificación según L_NOAPLICA y L_JUSTOBLIG
            # L_JUSTOBLIG controla qué justificación es obligatoria:
            #    - Si L_NOAPLICA = 1: L_JUSTOBLIG controla T_JUSTAPLICA
            #    - Si L_NOAPLICA = 0: L_JUSTOBLIG controla T_JUSTPLANIF
            if estado_planif.L_NOAPLICA == 1:
                # Estado "No Aplica": L_JUSTOBLIG controla si T_JUSTAPLICA es obligatoria
                if estado_planif.L_JUSTOBLIG == 1:
                    if not dato_req.T_JUSTAPLICA or dato_req.T_JUSTAPLICA.strip() == '':
                        return {"valido": False, "motivo": "Debe indicar una justificación de aplicabilidad"}
            else:
                # Estado normal: L_JUSTOBLIG controla si T_JUSTPLANIF es obligatoria
                if estado_planif.L_JUSTOBLIG == 1:
                    if not dato_req.T_JUSTPLANIF or dato_req.T_JUSTPLANIF.strip() == '':
                        return {"valido": False, "motivo": "Debe indicar una justificación de planificación"}

            return {"valido": True, "motivo": "Cumple criterios de planificación"}

        # VALIDACIÓN 3: Si está en fase de cumplimiento
        if config_req.N_FASEVALCUMPL == fase_actual.ID_FASE:
            if dato_req.N_ESTCUMPL is None:
                return {"valido": False, "motivo": "Debe seleccionar un estado de cumplimiento"}

            estado_cumpl = session.query(ConfiguracionEstadoRequisito).filter(
                ConfiguracionEstadoRequisito.ID_ESTREQ == dato_req.N_ESTCUMPL
            ).first()

            if not estado_cumpl:
                return {"valido": False, "motivo": "Estado de cumplimiento no válido"}

            if estado_cumpl.L_AVANCEFASE != 1:
                return {"valido": False, "motivo": f"El estado '{estado_cumpl.D_ESTADO}' no permite avance de fase"}

            # Verificar justificación si es obligatoria
            if estado_cumpl.L_JUSTOBLIG == 1:
                if not dato_req.T_JUSTCUMPL or dato_req.T_JUSTCUMPL.strip() == '':
                    return {"valido": False, "motivo": "Debe indicar una justificación de cumplimiento"}

            return {"valido": True, "motivo": "Cumple criterios de cumplimiento"}

        # Si no está en ninguna fase de validación, se considera válido
        return {"valido": True, "motivo": "No requiere validación en esta fase"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"valido": False, "motivo": f"Error al validar: {str(e)}"}



def obtener_parametros_riesgo_global(session):
    """
    Obtiene todos los parámetros de configuración del riesgo global.

    Returns:
        dict: Diccionario con C_PARAMETRO como clave y el registro completo como valor.
    """
    parametros = session.query(ConfiguracionRiesgoGlobal).filter(
        ConfiguracionRiesgoGlobal.L_ESTADO == 1
    ).all()

    return {p.C_PARAMETRO: p for p in parametros}


def obtener_clusters_activos(session):
    """
    Obtiene todos los clusters de riesgos activos.

    Returns:
        list: Lista de ConfiguracionCluster activos.
    """
    return session.query(ConfiguracionCluster).filter(
        ConfiguracionCluster.L_ESTADO == 1
    ).order_by(ConfiguracionCluster.N_ORDVISU).all()


def _obtener_nivel_residual_riesgo(session, datos_riesgo):
    """
    Calcula el nivel de riesgo residual para un DatosRiesgo.

    Esta función calcula el nivel residual al vuelo, igual que hace el resto del sistema.

    Args:
        session: Sesión SQLAlchemy.
        datos_riesgo: Instancia de DatosRiesgo.

    Returns:
        str: Nivel residual ('CRÍTICO', 'ALTO', 'MEDIO', 'BAJO') o None si no se puede calcular.
    """
    try:
        # Verificar que tenga probabilidad e impacto
        if datos_riesgo.V_PROBABILIDAD is None or datos_riesgo.V_IMPACTO is None:
            return None

        # Obtener criticidad inherente de ConfiguracionCriticidad
        config_criticidad = session.query(ConfiguracionCriticidad).filter_by(
            V_IMPACTO=datos_riesgo.V_IMPACTO,
            V_PROBAB=datos_riesgo.V_PROBABILIDAD
        ).first()

        if not config_criticidad or config_criticidad.N_CRITICIDAD is None:
            return None

        criticidad_inherente = config_criticidad.N_CRITICIDAD

        # Calcular riesgo residual usando la función existente
        riesgo_residual_num, nivel_residual_texto = calcular_riesgo_residual(
            session, datos_riesgo, criticidad_inherente
        )

        return nivel_residual_texto

    except Exception as e:
        return None


def calcular_riesgo_global(session, sistema_id):
    """
    Calcula el nivel de riesgo global para un sistema/proyecto.

    Esta función se ejecuta al vuelo cada vez que se necesita mostrar
    el nivel de riesgo global o validar el cambio de fase.

    IMPORTANTE:
    - Solo calcula si la fase actual tiene C_NIVELRIESG = 'R' (Residual)
    - Calcula el riesgo residual al vuelo para cada riesgo,
      no depende del campo V_RIERESID almacenado.

    Args:
        session: Sesión SQLAlchemy activa.
        sistema_id: ID del sistema/proyecto.

    Returns:
        dict: Diccionario con la estructura:
            {
                'nivel': str,           # 'BAJO', 'MEDIO', 'ALTO', 'CRITICO' o None
                'nivel_config': obj,    # Registro de ConfiguracionRiesgoGlobal del nivel
                'causa': str,           # 'RIESGO_INDIVIDUAL', 'FACTORES_AGRAVANTES' o None
                'factores': list,       # Lista de factores agravantes activos
                'metricas': dict,       # Métricas del cálculo
                'puede_avanzar': bool   # True si puede pasar a siguiente fase
            }
    """

    # 0. Verificar que la fase actual requiere cálculo de riesgo residual
    sistema = session.query(Inicio).filter(Inicio.ID_SISTEMA == sistema_id).first()
    if not sistema:
        return {
            'nivel': None,
            'nivel_config': None,
            'causa': None,
            'factores': [],
            'metricas': {
                'total_aplicables': 0,
                'criticos': 0,
                'altos': 0,
                'medios': 0,
                'bajos': 0,
                'pct_medio': 0
            },
            'puede_avanzar': False,
            'mensaje': 'Sistema no encontrado'
        }

    # Obtener la fase actual
    fase_actual = None
    if sistema.N_FASE:
        fase_actual = session.query(ConfiguracionFase).filter(
            ConfiguracionFase.ID_FASE == sistema.N_FASE
        ).first()

    # Verificar si la fase requiere nivel de riesgo Residual
    if not fase_actual or fase_actual.C_NIVELRIESG != 'R':
        nivel_riesgo = fase_actual.C_NIVELRIESG if fase_actual else None
        return {
            'nivel': None,
            'nivel_config': None,
            'causa': None,
            'factores': [],
            'metricas': {
                'total_aplicables': 0,
                'criticos': 0,
                'altos': 0,
                'medios': 0,
                'bajos': 0,
                'pct_medio': 0
            },
            'puede_avanzar': True,
            'mensaje': 'El riesgo global solo se calcula en fases con nivel de riesgo Residual'
        }


    # 1. Obtener parámetros de configuración
    params = obtener_parametros_riesgo_global(session)

    # 2. Obtener riesgos del proyecto que aplican
    riesgos_datos = session.query(DatosRiesgo).filter(
        DatosRiesgo.SIST_ID_SISTEMA == sistema_id,
        DatosRiesgo.L_APLICA == 1  # Solo riesgos que aplican
    ).all()


    # 3. Calcular nivel residual para cada riesgo
    # Estructura: lista de tuplas (DatosRiesgo, nivel_residual_texto)
    riesgos_con_nivel = []
    for dr in riesgos_datos:
        nivel_residual = _obtener_nivel_residual_riesgo(session, dr)
        if nivel_residual and nivel_residual != "—":
            riesgos_con_nivel.append((dr, nivel_residual))

    if not riesgos_con_nivel:
        return {
            'nivel': None,
            'nivel_config': None,
            'causa': None,
            'factores': [],
            'metricas': {
                'total_aplicables': 0,
                'criticos': 0,
                'altos': 0,
                'medios': 0,
                'bajos': 0,
                'pct_medio': 0
            },
            'puede_avanzar': False,
            'mensaje': 'No hay riesgos evaluados'
        }

    # 4. Contar por nivel residual
    conteo = {'CRITICO': 0, 'ALTO': 0, 'MEDIO': 0, 'BAJO': 0}

    for dr, nivel_texto in riesgos_con_nivel:
        nivel_upper = nivel_texto.upper() if nivel_texto else ''
        if 'CRITICO' in nivel_upper or 'CRÍTICO' in nivel_upper:
            conteo['CRITICO'] += 1
        elif 'ALTO' in nivel_upper:
            conteo['ALTO'] += 1
        elif 'MEDIO' in nivel_upper:
            conteo['MEDIO'] += 1
        elif 'BAJO' in nivel_upper:
            conteo['BAJO'] += 1

    total_evaluados = len(riesgos_con_nivel)

    # Métricas básicas
    metricas = {
        'total_aplicables': total_evaluados,
        'criticos': conteo['CRITICO'],
        'altos': conteo['ALTO'],
        'medios': conteo['MEDIO'],
        'bajos': conteo['BAJO'],
        'pct_medio': round((conteo['MEDIO'] / total_evaluados) * 100, 1) if total_evaluados > 0 else 0
    }

    # 5. Aplicar jerarquía de niveles

    # Caso: Hay riesgos CRÍTICOS
    if conteo['CRITICO'] > 0:
        nivel_config = params.get('NIVEL_CRITICO')
        return {
            'nivel': 'CRITICO',
            'nivel_config': nivel_config,
            'causa': 'RIESGO_INDIVIDUAL',
            'factores': [{
                'tipo': 'RIESGO_CRITICO',
                'cantidad': conteo['CRITICO'],
                'detalle': f"{conteo['CRITICO']} riesgo(s) con nivel residual CRÍTICO"
            }],
            'metricas': metricas,
            'puede_avanzar': False if nivel_config and nivel_config.L_BLOQUEAFASE == 1 else True,
            'mensaje': nivel_config.T_MENSAJE if nivel_config else ''
        }

    # Caso: Hay riesgos ALTOS
    if conteo['ALTO'] > 0:
        nivel_config = params.get('NIVEL_ALTO')
        return {
            'nivel': 'ALTO',
            'nivel_config': nivel_config,
            'causa': 'RIESGO_INDIVIDUAL',
            'factores': [{
                'tipo': 'RIESGO_ALTO',
                'cantidad': conteo['ALTO'],
                'detalle': f"{conteo['ALTO']} riesgo(s) con nivel residual ALTO"
            }],
            'metricas': metricas,
            'puede_avanzar': False if nivel_config and nivel_config.L_BLOQUEAFASE == 1 else True,
            'mensaje': nivel_config.T_MENSAJE if nivel_config else ''
        }

    # 6. Todos son MEDIO o BAJO -> Evaluar factores agravantes
    factores_activos = []

    # Factor 1: Concentración (>70% en MEDIO)
    umbral_concentracion = params.get('FACTOR_CONCENTRACION')
    if umbral_concentracion and umbral_concentracion.N_VALOR:
        pct_umbral = umbral_concentracion.N_VALOR
        if metricas['pct_medio'] > pct_umbral:
            factores_activos.append({
                'tipo': 'CONCENTRACION',
                'cantidad': conteo['MEDIO'],
                'total': total_evaluados,
                'porcentaje': metricas['pct_medio'],
                'umbral': pct_umbral,
                'detalle': f"Alta concentración: {conteo['MEDIO']} de {total_evaluados} riesgos ({metricas['pct_medio']}%) en MEDIO",
                'color': umbral_concentracion.C_COLOR
            })

    # Factor 2: Clusters que superan umbral
    clusters_problema = _evaluar_clusters(session, sistema_id, riesgos_con_nivel)
    for cluster_info in clusters_problema:
        factores_activos.append({
            'tipo': 'CLUSTER',
            'cluster_id': cluster_info['id'],
            'cluster_codigo': cluster_info['codigo'],
            'cluster_nombre': cluster_info['nombre'],
            'cantidad': cluster_info['medios'],
            'umbral': cluster_info['umbral'],
            'detalle': f"Cluster {cluster_info['codigo']}: {cluster_info['medios']} riesgos MEDIO (umbral: {cluster_info['umbral']})",
            'color': params.get('FACTOR_CLUSTER').C_COLOR if params.get('FACTOR_CLUSTER') else '#FF5722'
        })

    # Factor 3: Riesgos específicos del proyecto (>=2 en MEDIO)
    umbral_especificos = params.get('FACTOR_ESPECIFICOS')
    if umbral_especificos and umbral_especificos.N_VALOR:
        # Contar riesgos específicos (L_PERSONAL = 1) que están en MEDIO
        especificos_medio = 0
        for dr, nivel_texto in riesgos_con_nivel:
            if dr.riesgo and dr.riesgo.L_PERSONAL == 1:
                if nivel_texto and 'MEDIO' in nivel_texto.upper():
                    especificos_medio += 1

        if especificos_medio >= umbral_especificos.N_VALOR:
            factores_activos.append({
                'tipo': 'ESPECIFICOS',
                'cantidad': especificos_medio,
                'umbral': int(umbral_especificos.N_VALOR),
                'detalle': f"Riesgos específicos del proyecto: {especificos_medio} en nivel MEDIO",
                'color': umbral_especificos.C_COLOR
            })

    # 7. Determinar nivel final
    if factores_activos:
        nivel_config = params.get('NIVEL_ALTO')
        return {
            'nivel': 'ALTO',
            'nivel_config': nivel_config,
            'causa': 'FACTORES_AGRAVANTES',
            'factores': factores_activos,
            'metricas': metricas,
            'puede_avanzar': False if nivel_config and nivel_config.L_BLOQUEAFASE == 1 else True,
            'mensaje': nivel_config.T_MENSAJE if nivel_config else ''
        }

    # Sin factores agravantes
    if conteo['MEDIO'] > 0:
        nivel_config = params.get('NIVEL_MEDIO')
        return {
            'nivel': 'MEDIO',
            'nivel_config': nivel_config,
            'causa': None,
            'factores': [],
            'metricas': metricas,
            'puede_avanzar': True if nivel_config and nivel_config.L_BLOQUEAFASE == 0 else False,
            'mensaje': nivel_config.T_MENSAJE if nivel_config else ''
        }

    # Todos en BAJO
    nivel_config = params.get('NIVEL_BAJO')
    return {
        'nivel': 'BAJO',
        'nivel_config': nivel_config,
        'causa': None,
        'factores': [],
        'metricas': metricas,
        'puede_avanzar': True,
        'mensaje': nivel_config.T_MENSAJE if nivel_config else ''
    }


def _evaluar_clusters(session, sistema_id, riesgos_con_nivel):
    """
    Evalúa qué clusters superan su umbral de riesgos MEDIO.

    Args:
        session: Sesión SQLAlchemy.
        sistema_id: ID del sistema.
        riesgos_con_nivel: Lista de tuplas (DatosRiesgo, nivel_residual_texto).

    Returns:
        list: Lista de clusters que superan su umbral.
    """
    clusters_problema = []

    # Obtener clusters activos
    clusters = obtener_clusters_activos(session)

    # Obtener IDs de riesgos evaluados que están en MEDIO
    riesgos_medio_ids = []
    for dr, nivel_texto in riesgos_con_nivel:
        if nivel_texto and 'MEDIO' in nivel_texto.upper():
            riesgos_medio_ids.append(dr.RIE_ID_RIESGO)

    if not riesgos_medio_ids:
        return clusters_problema

    for cluster in clusters:
        # Obtener riesgos de este cluster que están en el proyecto y en MEDIO
        riesgos_cluster = session.query(ConfiguracionRiesgoCluster).filter(
            ConfiguracionRiesgoCluster.CLU_ID_CLUSTER == cluster.ID_CLUSTER,
            ConfiguracionRiesgoCluster.RIE_ID_RIESGO.in_(riesgos_medio_ids)
        ).count()

        # Comparar con umbral
        if riesgos_cluster >= cluster.N_UMBRAL:
            clusters_problema.append({
                'id': cluster.ID_CLUSTER,
                'codigo': cluster.C_CLUSTER,
                'nombre': cluster.D_CLUSTER,
                'medios': riesgos_cluster,
                'umbral': cluster.N_UMBRAL
            })

    return clusters_problema


def obtener_riesgos_por_cluster(session, sistema_id, cluster_id):
    """
    Obtiene los riesgos de un cluster específico para un sistema.
    Útil para el filtrado desde el panel de diagnóstico.

    Args:
        session: Sesión SQLAlchemy.
        sistema_id: ID del sistema.
        cluster_id: ID del cluster.

    Returns:
        list: Lista de DatosRiesgo del cluster.
    """
    # Obtener IDs de riesgos del cluster
    riesgos_cluster_ids = [
        rc.RIE_ID_RIESGO for rc in session.query(ConfiguracionRiesgoCluster).filter(
            ConfiguracionRiesgoCluster.CLU_ID_CLUSTER == cluster_id
        ).all()
    ]

    # Obtener datos de riesgo del sistema que pertenecen al cluster
    return session.query(DatosRiesgo).filter(
        DatosRiesgo.SIST_ID_SISTEMA == sistema_id,
        DatosRiesgo.RIE_ID_RIESGO.in_(riesgos_cluster_ids),
        DatosRiesgo.L_APLICA == 1
    ).all()


def obtener_riesgos_especificos_medio(session, sistema_id):
    """
    Obtiene los riesgos específicos del proyecto que están en nivel MEDIO.
    Útil para el filtrado desde el panel de diagnóstico.

    Args:
        session: Sesión SQLAlchemy.
        sistema_id: ID del sistema.

    Returns:
        list: Lista de tuplas (DatosRiesgo, nivel_residual) específicos en MEDIO.
    """
    # Obtener todos los riesgos del sistema que aplican
    riesgos = session.query(DatosRiesgo).filter(
        DatosRiesgo.SIST_ID_SISTEMA == sistema_id,
        DatosRiesgo.L_APLICA == 1
    ).all()

    # Filtrar los específicos (L_PERSONAL=1) que están en MEDIO
    resultado = []
    for dr in riesgos:
        if dr.riesgo and dr.riesgo.L_PERSONAL == 1:
            nivel_residual = _obtener_nivel_residual_riesgo(session, dr)
            if nivel_residual and 'MEDIO' in nivel_residual.upper():
                resultado.append((dr, nivel_residual))

    return resultado


def validar_riesgo_global_para_cambio_fase(session, sistema_id, fase_destino):
    """
    Valida si el riesgo global permite el cambio a una fase específica.

    Args:
        session: Sesión SQLAlchemy.
        sistema_id: ID del sistema.
        fase_destino: Número de la fase destino.

    Returns:
        dict: {
            'valido': bool,
            'riesgo_global': dict (resultado de calcular_riesgo_global),
            'mensaje': str
        }
    """
    params = obtener_parametros_riesgo_global(session)

    # Verificar si esta transición requiere validación de riesgo global
    fase_destino_config = params.get('FASE_DESTINO')

    # Solo validar si vamos a la fase configurada (por defecto fase 4)
    if fase_destino_config and fase_destino != int(fase_destino_config.N_VALOR):
        return {
            'valido': True,
            'riesgo_global': None,
            'mensaje': 'Esta transición no requiere validación de riesgo global'
        }

    # Calcular riesgo global
    resultado = calcular_riesgo_global(session, sistema_id)

    if resultado['puede_avanzar']:
        return {
            'valido': True,
            'riesgo_global': resultado,
            'mensaje': f"Nivel de riesgo global: {resultado['nivel']}. {resultado['mensaje']}"
        }
    else:
        return {
            'valido': False,
            'riesgo_global': resultado,
            'mensaje': f"No es posible avanzar a Fase {fase_destino}. {resultado['mensaje']}"
        }


def obtener_info_clusters_sistema(session, sistema_id):
    """
    Obtiene información resumida de todos los clusters para un sistema.
    Útil para mostrar el estado de cada cluster en la UI.

    Returns:
        list: Lista de diccionarios con info de cada cluster.
    """
    clusters = obtener_clusters_activos(session)
    resultado = []

    for cluster in clusters:
        # Obtener IDs de riesgos del cluster
        riesgos_cluster_ids = [
            rc.RIE_ID_RIESGO for rc in session.query(ConfiguracionRiesgoCluster).filter(
                ConfiguracionRiesgoCluster.CLU_ID_CLUSTER == cluster.ID_CLUSTER
            ).all()
        ]

        # Obtener datos de riesgos del cluster que aplican al sistema
        datos_riesgos = session.query(DatosRiesgo).filter(
            DatosRiesgo.SIST_ID_SISTEMA == sistema_id,
            DatosRiesgo.RIE_ID_RIESGO.in_(riesgos_cluster_ids),
            DatosRiesgo.L_APLICA == 1
        ).all()

        total_cluster = len(datos_riesgos)

        # Contar riesgos en MEDIO (calculando al vuelo)
        medios_cluster = 0
        for dr in datos_riesgos:
            nivel_residual = _obtener_nivel_residual_riesgo(session, dr)
            if nivel_residual and 'MEDIO' in nivel_residual.upper():
                medios_cluster += 1

        resultado.append({
            'id': cluster.ID_CLUSTER,
            'codigo': cluster.C_CLUSTER,
            'nombre': cluster.D_CLUSTER,
            'umbral': cluster.N_UMBRAL,
            'total_riesgos': total_cluster,
            'riesgos_medio': medios_cluster,
            'supera_umbral': medios_cluster >= cluster.N_UMBRAL
        })

    return resultado
