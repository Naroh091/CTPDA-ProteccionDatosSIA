
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
Módulo para exportaciones de datos del sistema SupervisionSIA.

Incluye funciones para:
- Exportar informe de mitigación de riesgos a Excel
- Exportar informe de requisitos de cumplimiento a Excel
- Exportar datos de controles de monitoreo a CSV
- Exportar elementos de descripción a HTML y PDF
"""

import os
import sys
import csv
import subprocess
import tempfile
import shutil
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import and_, func

from models import (
    Session, Inicio, DatosRiesgo, Riesgo, CategoriaRiesgo,
    DatosControl, Control, GrupoControl, RiesgoControl,
    ValoresDato, TiposDato, ConfiguracionCriticidad,
    DatosControlMonitoreo, DatosActividadMonitoreo,
    ElementosAdi, SubElementosAdi, DatosElementosAdi, ConfiguracionFase,
    ConfiguracionRequisito, DatosRequisito, ConfiguracionEstadoRequisito,
    ConfiguracionRequisitoControl
)
from controllers import convertir_criticidad_a_nivel, calcular_riesgo_residual
import config


def calcular_altura_fila(worksheet, fila, anchos_columnas, font_size=10, altura_minima=15, altura_maxima=409):
    """
    Calcula la altura necesaria para una fila basándose en el contenido de sus celdas.
    
    Args:
        worksheet: Hoja de trabajo de Excel
        fila: Número de fila a evaluar
        anchos_columnas: Dict con anchos de columnas {letra: ancho}
        font_size: Tamaño de fuente (por defecto 10)
        altura_minima: Altura mínima de la fila (por defecto 15)
        altura_maxima: Altura máxima permitida por Excel (por defecto 409)
    
    Returns:
        float: Altura calculada para la fila
    """
    altura_necesaria = altura_minima
    
    # Caracteres aproximados por unidad de ancho de columna
    chars_por_unidad = 1.2
    
    # Altura aproximada por línea de texto
    altura_por_linea = font_size * 1.5
    
    for celda in worksheet[fila]:
        if celda.value is None:
            continue
            
        valor = str(celda.value)
        if not valor.strip():
            continue
        
        # Obtener el ancho de la columna
        col_letter = get_column_letter(celda.column)
        
        # Manejar celdas combinadas
        ancho_total = 0
        if worksheet.merged_cells:
            for rango_combinado in worksheet.merged_cells.ranges:
                if celda.coordinate in rango_combinado:
                    # Sumar anchos de todas las columnas combinadas
                    for col in range(rango_combinado.min_col, rango_combinado.max_col + 1):
                        letra = get_column_letter(col)
                        ancho_total += anchos_columnas.get(letra, 10)
                    break
        
        # Si no está combinada, usar el ancho de su columna
        if ancho_total == 0:
            ancho_total = anchos_columnas.get(col_letter, 10)
        
        # Calcular caracteres por línea
        chars_por_linea = max(1, int(ancho_total * chars_por_unidad))
        
        # Contar líneas necesarias considerando saltos de línea explícitos
        lineas_totales = 0
        for linea in valor.split('\n'):
            if linea:
                lineas_necesarias = max(1, (len(linea) + chars_por_linea - 1) // chars_por_linea)
                lineas_totales += lineas_necesarias
            else:
                lineas_totales += 1
        
        # Calcular altura para esta celda
        altura_celda = max(altura_minima, lineas_totales * altura_por_linea)
        altura_necesaria = max(altura_necesaria, altura_celda)
    
    return min(altura_necesaria, altura_maxima)


def ajustar_alturas_filas(worksheet, anchos_columnas, filas_inicio=1, filas_fin=None, font_size=10, altura_minima=15):
    """
    Ajusta la altura de todas las filas en el rango especificado.
    
    Args:
        worksheet: Hoja de trabajo de Excel
        anchos_columnas: Dict con anchos de columnas {letra: ancho}
        filas_inicio: Primera fila a ajustar (por defecto 1)
        filas_fin: Última fila a ajustar (por defecto última fila con datos)
        font_size: Tamaño de fuente (por defecto 10)
        altura_minima: Altura mínima de la fila (por defecto 15)
    """
    if filas_fin is None:
        filas_fin = worksheet.max_row
    
    for fila in range(filas_inicio, filas_fin + 1):
        altura = calcular_altura_fila(
            worksheet, 
            fila, 
            anchos_columnas, 
            font_size=font_size,
            altura_minima=altura_minima
        )
        worksheet.row_dimensions[fila].height = altura


def exportar_mitigacion_riesgos(id_sistema, output_dir):
    """
    Genera un archivo Excel con el informe de mitigación de riesgos.

    Estructura del Excel:
    - Un bloque por cada riesgo activo, aplicable y no personal
    - Cada bloque incluye: datos del riesgo, justificaciones y controles asociados

    Args:
        id_sistema (int): ID del sistema/proyecto
        output_dir (str): Directorio donde guardar el archivo

    Returns:
        dict: Resultado con 'exito', 'archivo' (ruta completa) y 'mensaje'
    """
    session = Session()
    try:
        # 1. Obtener información del proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto:
            return {"exito": False, "mensaje": "Proyecto no encontrado"}

        nombre_proyecto = proyecto.D_NOMPROYEC or f"Proyecto_{id_sistema}"
        # Limpiar nombre para el archivo
        nombre_limpio = "".join(c for c in nombre_proyecto if c.isalnum() or c in (' ', '-', '_')).strip()
        nombre_limpio = nombre_limpio.replace(' ', '_')[:50]  # Limitar longitud

        # 2. Generar nombre del archivo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_archivo = f"RM_{nombre_limpio}_{timestamp}.xlsx"
        ruta_completa = os.path.join(output_dir, nombre_archivo)

        # 3. Obtener los valores de dominio necesarios
        tipo_impacto = session.query(TiposDato).filter_by(C_TIPDAT="IMPA").first()
        tipo_prob = session.query(TiposDato).filter_by(C_TIPDAT="PRO").first()
        tipo_madurez = session.query(TiposDato).filter_by(C_TIPDAT="MAD").first()

        valores_impacto = {}
        valores_prob = {}
        valores_madurez = {}

        if tipo_impacto:
            for v in session.query(ValoresDato).filter_by(TIDA_ID_TIPDAT=tipo_impacto.ID_TIPDAT).all():
                valores_impacto[v.ID_VALDAT] = v.D_VALOR

        if tipo_prob:
            for v in session.query(ValoresDato).filter_by(TIDA_ID_TIPDAT=tipo_prob.ID_TIPDAT).all():
                valores_prob[v.ID_VALDAT] = v.D_VALOR

        if tipo_madurez:
            for v in session.query(ValoresDato).filter_by(TIDA_ID_TIPDAT=tipo_madurez.ID_TIPDAT).all():
                valores_madurez[v.ID_VALDAT] = v.D_VALOR

        # 4. Obtener riesgos activos, aplicables y NO personales (L_PERSONAL != 1)
        riesgos_query = (
            session.query(DatosRiesgo, Riesgo, CategoriaRiesgo)
            .join(Riesgo, DatosRiesgo.RIE_ID_RIESGO == Riesgo.ID_RIESGO)
            .outerjoin(CategoriaRiesgo, Riesgo.CAT_ID_CATRIES == CategoriaRiesgo.ID_CATRIES)
            .filter(
                DatosRiesgo.SIST_ID_SISTEMA == id_sistema,
                DatosRiesgo.L_ACTIVA == 1,
                DatosRiesgo.L_APLICA == 1,
                Riesgo.L_PERSONAL != 1  # Excluir riesgos personales/específicos
            )
            .order_by(CategoriaRiesgo.ID_CATRIES, Riesgo.N_ORDVISU)
        )

        riesgos_data = riesgos_query.all()

        if not riesgos_data:
            return {"exito": False, "mensaje": "No hay riesgos aplicables para exportar"}

        # 5. Crear el libro Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Riesgos Mitigados"

        # Definir estilos
        estilo_titulo_riesgo = Font(bold=True, size=12, color="FFFFFF")
        fondo_titulo_riesgo = PatternFill("solid", fgColor="2F5496")

        estilo_cabecera = Font(bold=True, size=10, color="FFFFFF")
        fondo_cabecera = PatternFill("solid", fgColor="4472C4")

        estilo_cabecera_controles = Font(bold=True, size=10, color="FFFFFF")
        fondo_cabecera_controles = PatternFill("solid", fgColor="70AD47")

        estilo_subtitulo = Font(bold=True, size=10, italic=True, color="595959")
        fondo_subtitulo = PatternFill("solid", fgColor="D9E2F3")

        borde_thin = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        alineacion_centro = Alignment(horizontal='center', vertical='center', wrap_text=True)
        alineacion_izquierda = Alignment(horizontal='left', vertical='center', wrap_text=True)

        # 6. Configurar anchos de columnas
        anchos_columnas = {
            'A': 12,   # ID / ID Control
            'B': 55,   # Descripción
            'C': 15,   # Probabilidad / Grupo
            'D': 15,   # Impacto / Madurez
            'E': 15,   # R. Inherente / Implementación
            'F': 15,   # R. Residual
        }
        for col, ancho in anchos_columnas.items():
            ws.column_dimensions[col].width = ancho

        fila_actual = 1

        # 7. Procesar cada riesgo
        for datos_riesgo, riesgo, categoria in riesgos_data:
            codigo_riesgo = riesgo.C_RIESGO or f"R{riesgo.ID_RIESGO:02d}"

            # === TÍTULO DEL RIESGO ===
            celda_titulo = ws.cell(row=fila_actual, column=1, value=f"RIESGO {codigo_riesgo}")
            celda_titulo.font = estilo_titulo_riesgo
            celda_titulo.fill = fondo_titulo_riesgo
            celda_titulo.alignment = alineacion_centro  # Centrado
            ws.merge_cells(start_row=fila_actual, start_column=1, end_row=fila_actual, end_column=6)
            for col in range(1, 7):
                ws.cell(row=fila_actual, column=col).border = borde_thin
                ws.cell(row=fila_actual, column=col).fill = fondo_titulo_riesgo
            fila_actual += 1

            # === CABECERA DE DATOS DEL RIESGO ===
            cabeceras_riesgo = ['ID', 'Descripción del Riesgo', 'Probabilidad', 'Impacto', 'R. Inherente', 'R. Residual']
            for col, cab in enumerate(cabeceras_riesgo, 1):
                celda = ws.cell(row=fila_actual, column=col, value=cab)
                celda.font = estilo_cabecera
                celda.fill = fondo_cabecera
                celda.alignment = alineacion_centro
                celda.border = borde_thin
            fila_actual += 1

            # === DATOS DEL RIESGO ===
            # Obtener valores de probabilidad e impacto
            prob_texto = valores_prob.get(datos_riesgo.V_PROBABILIDAD, "—")
            impacto_texto = valores_impacto.get(datos_riesgo.V_IMPACTO, "—")

            # Calcular criticidad (riesgo inherente)
            criticidad = None
            if datos_riesgo.V_IMPACTO and datos_riesgo.V_PROBABILIDAD:
                cfg_crit = session.query(ConfiguracionCriticidad).filter_by(
                    V_IMPACTO=datos_riesgo.V_IMPACTO,
                    V_PROBAB=datos_riesgo.V_PROBABILIDAD
                ).first()
                if cfg_crit:
                    criticidad = cfg_crit.N_CRITICIDAD

            nivel_inherente = convertir_criticidad_a_nivel(criticidad)

            # Calcular riesgo residual
            riesgo_residual_num, nivel_residual = calcular_riesgo_residual(session, datos_riesgo, criticidad)

            datos_fila = [
                codigo_riesgo,
                riesgo.D_RIESGO or "—",
                prob_texto,
                impacto_texto,
                nivel_inherente,
                nivel_residual
            ]

            for col, valor in enumerate(datos_fila, 1):
                celda = ws.cell(row=fila_actual, column=col, value=valor)
                celda.alignment = alineacion_centro if col != 2 else alineacion_izquierda
                celda.border = borde_thin
            fila_actual += 1

            # === CABECERA DE JUSTIFICACIONES (dinámico según config) ===
            # Determinar qué justificaciones mostrar
            justificaciones_visibles = []

            # Justif. Aplica siempre visible
            justificaciones_visibles.append({
                'nombre': 'Justif. Aplica',
                'texto': datos_riesgo.T_JUSAPLICA or ""
            })

            # Justif. Impacto según config
            if config.VER_JUST_IMPACTO == 1:
                justificaciones_visibles.append({
                    'nombre': 'Justif. Impacto',
                    'texto': datos_riesgo.T_JUSIMPACTO or ""
                })

            # Justif. Probabilidad según config
            if config.VER_JUST_PROB == 1:
                justificaciones_visibles.append({
                    'nombre': 'Justif. Probabilidad',
                    'texto': datos_riesgo.T_JUSPROBABILIDAD or ""
                })

            # Calcular distribución de columnas según cantidad de justificaciones
            num_justificaciones = len(justificaciones_visibles)
            if num_justificaciones == 3:
                # 3 justificaciones: cada una ocupa 2 columnas (A-B, C-D, E-F)
                distribuciones = [(1, 2), (3, 4), (5, 6)]
            elif num_justificaciones == 2:
                # 2 justificaciones: cada una ocupa 3 columnas (A-C, D-F)
                distribuciones = [(1, 3), (4, 6)]
            else:  # num_justificaciones == 1
                # 1 justificación: ocupa 6 columnas (A-F)
                distribuciones = [(1, 6)]

            # Escribir cabeceras de justificaciones
            for idx, (justif, (col_inicio, col_fin)) in enumerate(zip(justificaciones_visibles, distribuciones)):
                ws.merge_cells(start_row=fila_actual, start_column=col_inicio, end_row=fila_actual, end_column=col_fin)
                celda = ws.cell(row=fila_actual, column=col_inicio, value=justif['nombre'])
                celda.font = estilo_subtitulo
                celda.fill = fondo_subtitulo
                celda.alignment = alineacion_centro
                for col in range(col_inicio, col_fin + 1):
                    ws.cell(row=fila_actual, column=col).border = borde_thin
                    ws.cell(row=fila_actual, column=col).fill = fondo_subtitulo

            fila_actual += 1

            # === TEXTO DE JUSTIFICACIONES ===
            # Calcular altura de fila basada en el texto más largo
            max_len = max(len(justif['texto']) for justif in justificaciones_visibles)
            altura_fila = max(45, min(max_len // 2, 120))

            # Escribir textos de justificaciones
            for idx, (justif, (col_inicio, col_fin)) in enumerate(zip(justificaciones_visibles, distribuciones)):
                ws.merge_cells(start_row=fila_actual, start_column=col_inicio, end_row=fila_actual, end_column=col_fin)
                celda = ws.cell(row=fila_actual, column=col_inicio, value=justif['texto'] if justif['texto'] else "—")
                celda.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
                for col in range(col_inicio, col_fin + 1):
                    ws.cell(row=fila_actual, column=col).border = borde_thin

            # Ajustar altura de fila
            ws.row_dimensions[fila_actual].height = altura_fila
            fila_actual += 1

            # === TÍTULO SECCIÓN CONTROLES ===
            celda_tit_control = ws.cell(row=fila_actual, column=1, value="CONTROLES APLICADOS PARA MITIGACIÓN")
            celda_tit_control.font = estilo_cabecera_controles
            celda_tit_control.fill = fondo_cabecera_controles
            celda_tit_control.alignment = alineacion_centro  # Centrado
            ws.merge_cells(start_row=fila_actual, start_column=1, end_row=fila_actual, end_column=6)
            for col in range(1, 7):
                ws.cell(row=fila_actual, column=col).border = borde_thin
                ws.cell(row=fila_actual, column=col).fill = fondo_cabecera_controles
            fila_actual += 1

            # === CABECERA DE CONTROLES (con E-F fusionadas para Implementación) ===
            cabeceras_control = ['ID Control', 'Descripción del Control', 'Grupo', 'Madurez']
            for col, cab in enumerate(cabeceras_control, 1):
                celda = ws.cell(row=fila_actual, column=col, value=cab)
                celda.font = estilo_cabecera
                celda.fill = fondo_cabecera
                celda.alignment = alineacion_centro
                celda.border = borde_thin

            # Fusionar E-F para "Implementación"
            ws.merge_cells(start_row=fila_actual, start_column=5, end_row=fila_actual, end_column=6)
            celda_impl = ws.cell(row=fila_actual, column=5, value="Implementación")
            celda_impl.font = estilo_cabecera
            celda_impl.fill = fondo_cabecera
            celda_impl.alignment = alineacion_centro
            for col in [5, 6]:
                ws.cell(row=fila_actual, column=col).border = borde_thin
                ws.cell(row=fila_actual, column=col).fill = fondo_cabecera
            fila_actual += 1

            # === OBTENER CONTROLES ASOCIADOS AL RIESGO ===
            controles_riesgo = (
                session.query(Control, GrupoControl, DatosControl)
                .join(RiesgoControl, Control.ID_CONTROL == RiesgoControl.CON_ID_CONTROL)
                .join(GrupoControl, Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL)
                .join(DatosControl, and_(
                    DatosControl.CON_ID_CONTROL == Control.ID_CONTROL,
                    DatosControl.SIST_ID_SISTEMA == id_sistema
                ))
                .filter(
                    RiesgoControl.RIE_ID_RIESGO == riesgo.ID_RIESGO,
                    DatosControl.L_ACTIVA == 1,
                    DatosControl.L_APLICA == 1
                )
                .order_by(Control.C_CONTROL)
                .all()
            )

            if controles_riesgo:
                for control, grupo, dato_control in controles_riesgo:
                    madurez_texto = valores_madurez.get(dato_control.V_MADUREZ, "—") if dato_control.V_MADUREZ else "—"
                    implementacion = dato_control.T_OBSERVACIONES or ""

                    # Columnas A-D
                    datos_control_fila = [
                        control.C_CONTROL or f"C{control.ID_CONTROL:03d}",
                        control.D_CONTROL or "—",
                        grupo.D_CONTROL if grupo else "—",
                        madurez_texto
                    ]

                    for col, valor in enumerate(datos_control_fila, 1):
                        celda = ws.cell(row=fila_actual, column=col, value=valor)
                        celda.alignment = alineacion_centro if col != 2 else alineacion_izquierda
                        celda.border = borde_thin

                    # Fusionar E-F para Implementación
                    ws.merge_cells(start_row=fila_actual, start_column=5, end_row=fila_actual, end_column=6)
                    celda_impl_dato = ws.cell(row=fila_actual, column=5, value=implementacion)
                    celda_impl_dato.alignment = alineacion_izquierda
                    for col in [5, 6]:
                        ws.cell(row=fila_actual, column=col).border = borde_thin

                    fila_actual += 1
            else:
                # Si no hay controles
                celda_sin_ctrl = ws.cell(row=fila_actual, column=1, value="Sin controles aplicados")
                celda_sin_ctrl.alignment = alineacion_centro
                ws.merge_cells(start_row=fila_actual, start_column=1, end_row=fila_actual, end_column=6)
                for col in range(1, 7):
                    ws.cell(row=fila_actual, column=col).border = borde_thin
                fila_actual += 1

            # 2 filas en blanco entre bloques de riesgo
            fila_actual += 2

        # 8. Guardar el archivo
        wb.save(ruta_completa)

        return {
            "exito": True,
            "archivo": ruta_completa,
            "nombre_archivo": nombre_archivo,
            "mensaje": f"Exportación completada: {len(riesgos_data)} riesgos exportados"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"exito": False, "mensaje": f"Error al exportar: {str(e)}"}
    finally:
        session.close()


def exportar_controles_monitoreo_csv(id_sistema, output_dir):
    """
    Genera un archivo CSV con los datos de controles de monitoreo.

    Exporta todos los registros de IA_DATCONTMON para el sistema,
    decodificando los campos relacionados (mostrando descripciones en lugar de IDs).

    Args:
        id_sistema (int): ID del sistema/proyecto
        output_dir (str): Directorio donde guardar el archivo

    Returns:
        dict: Resultado con 'exito', 'archivo' (ruta completa) y 'mensaje'
    """
    session = Session()
    try:
        # 1. Obtener información del proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto:
            return {"exito": False, "mensaje": "Proyecto no encontrado"}

        nombre_proyecto = proyecto.D_NOMPROYEC or f"Proyecto_{id_sistema}"
        # Limpiar nombre para el archivo
        nombre_limpio = "".join(c for c in nombre_proyecto if c.isalnum() or c in (' ', '-', '_')).strip()
        nombre_limpio = nombre_limpio.replace(' ', '_')[:50]

        # 2. Generar nombre del archivo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_archivo = f"CM_{nombre_limpio}_{timestamp}.csv"
        ruta_completa = os.path.join(output_dir, nombre_archivo)

        # 3. Obtener todos los registros de DatosControlMonitoreo para este sistema
        registros = (
            session.query(DatosControlMonitoreo)
            .filter(DatosControlMonitoreo.SIST_ID_SISTEMA == id_sistema)
            .all()
        )

        if not registros:
            return {"exito": False, "mensaje": "No hay datos de monitoreo para exportar"}

        # 4. Crear diccionario de valores decodificados
        # Obtener todos los ValoresDato necesarios
        valores_dat = {}
        for v in session.query(ValoresDato).all():
            valores_dat[v.ID_VALDAT] = v.D_VALOR

        # Obtener todos los controles
        controles = {}
        for c in session.query(Control).all():
            controles[c.ID_CONTROL] = {
                'codigo': c.C_CONTROL,
                'descripcion': c.D_CONTROL
            }

        # 5. Obtener fechas de última ejecución para cada control de monitoreo
        # Consulta para obtener la fecha máxima de ejecución por ID_DATCONTMON
        ultimas_ejecuciones = {}
        ejecuciones_query = (
            session.query(
                DatosActividadMonitoreo.ACT_ID_CONTMON,
                func.max(DatosActividadMonitoreo.F_EJECUCION).label('ultima_fecha')
            )
            .filter(DatosActividadMonitoreo.SIST_ID_SISTEMA == id_sistema)
            .group_by(DatosActividadMonitoreo.ACT_ID_CONTMON)
            .all()
        )
        for id_contmon, ultima_fecha in ejecuciones_query:
            ultimas_ejecuciones[id_contmon] = ultima_fecha

        # 6. Definir cabeceras del CSV
        cabeceras = [
            'Código Control',
            'Descripción Control',
            'Estado',
            'Responsable',
            'Madurez Inicial',
            'Madurez Actual',
            'Madurez Objetivo',
            'Descripción',
            'Frecuencia',
            'Última Ejecución',
            'Próxima Ejecución'
        ]

        # 7. Crear el archivo CSV
        with open(ruta_completa, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)

            # Escribir cabeceras
            writer.writerow(cabeceras)

            # Escribir datos
            for reg in registros:
                # Decodificar valores
                control_info = controles.get(reg.CON_ID_CONTROL, {'codigo': '—', 'descripcion': '—'})

                # Obtener fecha de última ejecución (puede no haber)
                fecha_ultima_ejec = ultimas_ejecuciones.get(reg.ID_DATCONTMON, '—') or '—'

                fila = [
                    control_info['codigo'] or '—',
                    control_info['descripcion'] or '—',
                    valores_dat.get(reg.V_ESTADO, '—') if reg.V_ESTADO else '—',
                    reg.T_RESP or '—',
                    valores_dat.get(reg.V_MADINI, '—') if reg.V_MADINI else '—',
                    valores_dat.get(reg.V_MADACT, '—') if reg.V_MADACT else '—',
                    valores_dat.get(reg.V_MADOBJ, '—') if reg.V_MADOBJ else '—',
                    reg.T_DESC or '—',
                    valores_dat.get(reg.V_FREC, '—') if reg.V_FREC else '—',
                    fecha_ultima_ejec,
                    reg.F_PROXEJEC or '—'
                ]
                writer.writerow(fila)

        return {
            "exito": True,
            "archivo": ruta_completa,
            "nombre_archivo": nombre_archivo,
            "mensaje": f"Exportación completada: {len(registros)} registros exportados"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"exito": False, "mensaje": f"Error al exportar: {str(e)}"}
    finally:
        session.close()


def _buscar_wkhtmltopdf():
    """
    Busca el ejecutable wkhtmltopdf en diferentes ubicaciones.

    Returns:
        str: Ruta al ejecutable wkhtmltopdf o None si no se encuentra
    """
    # Buscar en el directorio temporal de PyInstaller
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
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

    posibles_rutas = [
        os.path.join(base_dir, 'bin', 'wkhtmltopdf.exe'),
        os.path.join(base_dir, 'wkhtmltopdf.exe'),
        os.path.join(os.getcwd(), 'bin', 'wkhtmltopdf.exe'),
    ]

    for ruta in posibles_rutas:
        if os.path.isfile(ruta):
            return ruta

    # Buscar en el PATH del sistema
    wkhtmltopdf_system = shutil.which('wkhtmltopdf')
    if wkhtmltopdf_system:
        return wkhtmltopdf_system

    return None


def exportar_elementos_descripcion_html(id_sistema, output_dir):
    """
    Genera un archivo HTML con los elementos de descripción del proyecto.

    Args:
        id_sistema (int): ID del sistema/proyecto
        output_dir (str): Directorio donde guardar el archivo

    Returns:
        dict: Resultado con 'exito', 'archivo', 'html' (contenido) y 'mensaje'
    """
    from sqlalchemy import or_

    session = Session()
    try:
        # 1. Obtener información del proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto:
            return {"exito": False, "mensaje": "Proyecto no encontrado"}

        nombre_proyecto = proyecto.D_NOMPROYEC or f"Proyecto_{id_sistema}"
        nombre_limpio = "".join(c for c in nombre_proyecto if c.isalnum() or c in (' ', '-', '_')).strip()
        nombre_limpio = nombre_limpio.replace(' ', '_')[:50]

        # 2. Generar nombre del archivo
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_archivo = f"ED_{nombre_limpio}_{timestamp}.html"
        ruta_completa = os.path.join(output_dir, nombre_archivo)

        # 3. Obtener fase actual del proyecto para filtrar elementos
        fase_actual_orden = None
        if proyecto.N_FASE:
            fase_config = session.query(ConfiguracionFase).filter_by(
                ID_FASE=proyecto.N_FASE
            ).first()
            if fase_config:
                fase_actual_orden = fase_config.N_ORDEN

        # 4. Obtener elementos activos filtrados por fase
        query_elementos = session.query(ElementosAdi).filter(ElementosAdi.L_ESTADO == 1)

        if fase_actual_orden is not None:
            subq_fase_visual = (
                session.query(ConfiguracionFase.N_ORDEN)
                .filter(ConfiguracionFase.ID_FASE == ElementosAdi.N_FASEVISUAL)
                .correlate(ElementosAdi)
                .scalar_subquery()
            )
            query_elementos = query_elementos.filter(
                or_(
                    ElementosAdi.N_FASEVISUAL.is_(None),
                    subq_fase_visual <= fase_actual_orden
                )
            )

        elementos = query_elementos.order_by(ElementosAdi.N_ORDEN.asc()).all()

        if not elementos:
            return {"exito": False, "mensaje": "No hay elementos de descripción para exportar"}

        # 5. Obtener definiciones (datos de elementos)
        definiciones_raw = session.query(DatosElementosAdi).filter_by(
            SIST_ID_SISTEMA=id_sistema
        ).all()

        # Crear diccionario de definiciones: (ID_ELEM, N_ITERACION, ID_SUBELEM) -> T_DESCRIPCION
        definiciones = {}
        for d in definiciones_raw:
            clave = (d.ELE_ID_ELEM, d.N_ITERACION, d.SUB_IDSUBELEM)
            definiciones[clave] = d.T_DESCRIPCION or ""

        # 6. Construir estructura de datos
        elementos_data = []
        for elemento in elementos:
            # Obtener iteraciones para este elemento
            iteraciones = (
                session.query(DatosElementosAdi.N_ITERACION)
                .filter(
                    DatosElementosAdi.ELE_ID_ELEM == elemento.ID_ELEM,
                    DatosElementosAdi.SIST_ID_SISTEMA == id_sistema
                )
                .distinct()
                .all()
            )

            if not iteraciones:
                continue

            # Obtener subelementos activos
            subelementos = [s for s in elemento.sub_elementos if s.L_ESTADO == 1]
            subelementos = sorted(subelementos, key=lambda s: s.N_SUBORD)

            iteraciones_data = []
            for (n_iter,) in iteraciones:
                subs_data = []
                for sub in subelementos:
                    clave = (elemento.ID_ELEM, n_iter, sub.ID_SUBELEM)
                    descripcion = definiciones.get(clave, "").strip()
                    subs_data.append({
                        'nombre': sub.D_SUBELEM,
                        'descripcion': descripcion if descripcion else "—"
                    })

                # Obtener primera descripción para título de iteración
                primera_desc = ""
                if subelementos:
                    clave_primera = (elemento.ID_ELEM, n_iter, subelementos[0].ID_SUBELEM)
                    primera_desc = definiciones.get(clave_primera, "").strip()

                iteraciones_data.append({
                    'n_iteracion': n_iter,
                    'primera_descripcion': primera_desc,
                    'subelementos': subs_data
                })

            elementos_data.append({
                'codigo': elemento.C_ELEMENTO,
                'nombre': elemento.D_ELEMENTO,
                'es_multiple': elemento.L_MULTIPLE == 1,
                'iteraciones': iteraciones_data
            })

        # 7. Generar HTML
        fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")

        html_content = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elementos de Descripción - {nombre_proyecto}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 40px;
            color: #333;
            line-height: 1.6;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #0d6efd;
        }}
        .header h1 {{
            color: #0d6efd;
            margin-bottom: 10px;
        }}
        .header .proyecto {{
            font-size: 1.2em;
            color: #555;
        }}
        .header .fecha {{
            font-size: 0.9em;
            color: #888;
        }}
        .elemento {{
            margin-bottom: 30px;
            page-break-inside: avoid;
        }}
        .elemento-header {{
            background-color: #0d6efd;
            color: white;
            padding: 10px 15px;
            border-radius: 5px 5px 0 0;
            font-size: 1.1em;
        }}
        .elemento-header .codigo {{
            font-weight: bold;
            margin-right: 10px;
        }}
        .iteracion {{
            border: 1px solid #dee2e6;
            border-top: none;
            margin-bottom: 0;
        }}
        .iteracion-header {{
            background-color: #e9ecef;
            padding: 8px 15px;
            font-weight: bold;
            border-bottom: 1px solid #dee2e6;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            border: 1px solid #dee2e6;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
            width: 40%;
        }}
        td {{
            width: 60%;
        }}
        .sin-datos {{
            color: #6c757d;
            font-style: italic;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            text-align: center;
            font-size: 0.9em;
            color: #888;
        }}
        @media print {{
            body {{
                margin: 20px;
            }}
            .elemento {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Elementos de Descripción</h1>
        <div class="proyecto">{nombre_proyecto}</div>
        <div class="fecha">Generado el {fecha_generacion}</div>
    </div>
'''

        for elem in elementos_data:
            html_content += f'''
    <div class="elemento">
        <div class="elemento-header">
            <span class="codigo">ELEMENTO {elem['codigo']}:</span>
            {elem['nombre']}
        </div>
'''
            for iter_data in elem['iteraciones']:
                # Si hay múltiples iteraciones o es múltiple, mostrar encabezado de iteración
                if len(elem['iteraciones']) > 1 or elem['es_multiple']:
                    titulo_iter = iter_data['primera_descripcion'] if iter_data['primera_descripcion'] else f"Tratamiento {iter_data['n_iteracion']}"
                    html_content += f'''
        <div class="iteracion">
            <div class="iteracion-header">{titulo_iter}</div>
            <table>
'''
                else:
                    html_content += '''
        <div class="iteracion">
            <table>
'''

                for sub in iter_data['subelementos']:
                    desc_class = 'sin-datos' if sub['descripcion'] == '—' else ''
                    html_content += f'''
                <tr>
                    <th>{sub['nombre']}</th>
                    <td class="{desc_class}">{sub['descripcion']}</td>
                </tr>
'''

                html_content += '''
            </table>
        </div>
'''

            html_content += '''
    </div>
'''

        html_content += f'''
    <div class="footer">
        Protección de Datos en Sistemas de IA - Consejo de Transparencia y Protección de Datos de Andalucía
    </div>
</body>
</html>
'''

        # 8. Guardar archivo
        with open(ruta_completa, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return {
            "exito": True,
            "archivo": ruta_completa,
            "nombre_archivo": nombre_archivo,
            "html": html_content,
            "mensaje": f"Exportación completada: {len(elementos_data)} elementos exportados"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"exito": False, "mensaje": f"Error al exportar: {str(e)}"}
    finally:
        session.close()


def exportar_elementos_descripcion_pdf(id_sistema, output_dir):
    """
    Genera un archivo PDF con los elementos de descripción del proyecto.
    Usa un formato compacto donde el nombre del subelemento es una cabecera
    y la descripción ocupa todo el ancho.

    Args:
        id_sistema (int): ID del sistema/proyecto
        output_dir (str): Directorio donde guardar el archivo

    Returns:
        dict: Resultado con 'exito', 'archivo', 'pdf' (bytes) y 'mensaje'
    """
    from sqlalchemy import or_

    session = Session()
    try:
        # 1. Obtener información del proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto:
            return {"exito": False, "mensaje": "Proyecto no encontrado"}

        nombre_proyecto = proyecto.D_NOMPROYEC or f"Proyecto_{id_sistema}"
        nombre_limpio = "".join(c for c in nombre_proyecto if c.isalnum() or c in (' ', '-', '_')).strip()
        nombre_limpio = nombre_limpio.replace(' ', '_')[:50]

        # 2. Generar nombre del archivo
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_archivo_html = f"ED_{nombre_limpio}_{timestamp}_temp.html"
        nombre_archivo_pdf = f"ED_{nombre_limpio}_{timestamp}.pdf"
        ruta_html = os.path.join(output_dir, nombre_archivo_html)
        ruta_pdf = os.path.join(output_dir, nombre_archivo_pdf)

        # 3. Obtener fase actual del proyecto para filtrar elementos
        fase_actual_orden = None
        if proyecto.N_FASE:
            fase_config = session.query(ConfiguracionFase).filter_by(
                ID_FASE=proyecto.N_FASE
            ).first()
            if fase_config:
                fase_actual_orden = fase_config.N_ORDEN

        # 4. Obtener elementos activos filtrados por fase
        query_elementos = session.query(ElementosAdi).filter(ElementosAdi.L_ESTADO == 1)

        if fase_actual_orden is not None:
            subq_fase_visual = (
                session.query(ConfiguracionFase.N_ORDEN)
                .filter(ConfiguracionFase.ID_FASE == ElementosAdi.N_FASEVISUAL)
                .correlate(ElementosAdi)
                .scalar_subquery()
            )
            query_elementos = query_elementos.filter(
                or_(
                    ElementosAdi.N_FASEVISUAL.is_(None),
                    subq_fase_visual <= fase_actual_orden
                )
            )

        elementos = query_elementos.order_by(ElementosAdi.N_ORDEN.asc()).all()

        if not elementos:
            return {"exito": False, "mensaje": "No hay elementos de descripción para exportar"}

        # 5. Obtener definiciones (datos de elementos)
        definiciones_raw = session.query(DatosElementosAdi).filter_by(
            SIST_ID_SISTEMA=id_sistema
        ).all()

        definiciones = {}
        for d in definiciones_raw:
            clave = (d.ELE_ID_ELEM, d.N_ITERACION, d.SUB_IDSUBELEM)
            definiciones[clave] = d.T_DESCRIPCION or ""

        # 6. Construir estructura de datos
        elementos_data = []
        for elemento in elementos:
            iteraciones = (
                session.query(DatosElementosAdi.N_ITERACION)
                .filter(
                    DatosElementosAdi.ELE_ID_ELEM == elemento.ID_ELEM,
                    DatosElementosAdi.SIST_ID_SISTEMA == id_sistema
                )
                .distinct()
                .all()
            )

            if not iteraciones:
                continue

            subelementos = [s for s in elemento.sub_elementos if s.L_ESTADO == 1]
            subelementos = sorted(subelementos, key=lambda s: s.N_SUBORD)

            iteraciones_data = []
            for (n_iter,) in iteraciones:
                subs_data = []
                for sub in subelementos:
                    clave = (elemento.ID_ELEM, n_iter, sub.ID_SUBELEM)
                    descripcion = definiciones.get(clave, "").strip()
                    subs_data.append({
                        'nombre': sub.D_SUBELEM,
                        'descripcion': descripcion if descripcion else "—"
                    })

                primera_desc = ""
                if subelementos:
                    clave_primera = (elemento.ID_ELEM, n_iter, subelementos[0].ID_SUBELEM)
                    primera_desc = definiciones.get(clave_primera, "").strip()

                iteraciones_data.append({
                    'n_iteracion': n_iter,
                    'primera_descripcion': primera_desc,
                    'subelementos': subs_data
                })

            elementos_data.append({
                'codigo': elemento.C_ELEMENTO,
                'nombre': elemento.D_ELEMENTO,
                'es_multiple': elemento.L_MULTIPLE == 1,
                'iteraciones': iteraciones_data
            })

        # 7. Generar HTML con formato compacto para PDF
        fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")

        html_content = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elementos de Descripción - {nombre_proyecto}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 40px;
            color: #333;
            line-height: 1.6;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #0d6efd;
        }}
        .header h1 {{
            color: #0d6efd;
            margin-bottom: 10px;
        }}
        .header .proyecto {{
            font-size: 1.2em;
            color: #555;
        }}
        .header .fecha {{
            font-size: 0.9em;
            color: #888;
        }}
        .elemento {{
            margin-bottom: 25px;
            page-break-inside: avoid;
        }}
        .elemento-header {{
            background-color: #0d6efd;
            color: white;
            padding: 10px 15px;
            border-radius: 5px 5px 0 0;
            font-size: 1.1em;
        }}
        .elemento-header .codigo {{
            font-weight: bold;
            margin-right: 10px;
        }}
        .iteracion {{
            border: 1px solid #dee2e6;
            border-top: none;
            margin-bottom: 0;
        }}
        /* Cabecera de iteración: fondo gris oscuro, borde izquierdo azul */
        .iteracion-header {{
            background-color: #6c757d;
            color: white;
            padding: 8px 15px;
            font-weight: bold;
            border-bottom: 1px solid #dee2e6;
            border-left: 4px solid #0d6efd;
        }}
        .contenido-iteracion {{
            padding: 10px 15px;
        }}
        /* Cabecera de subelemento: fondo claro, borde izquierdo verde */
        .subelemento-header {{
            background-color: #f8f9fa;
            padding: 8px 12px;
            font-weight: 600;
            color: #495057;
            border-left: 3px solid #28a745;
            border-bottom: 1px solid #e9ecef;
            margin-top: 10px;
        }}
        .subelemento-header:first-child {{
            margin-top: 0;
        }}
        /* Contenido de descripción: todo el ancho */
        .subelemento-contenido {{
            padding: 10px 12px 15px 12px;
            border-bottom: 1px solid #e9ecef;
            text-align: justify;
        }}
        .subelemento-contenido:last-child {{
            border-bottom: none;
        }}
        .sin-datos {{
            color: #6c757d;
            font-style: italic;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            text-align: center;
            font-size: 0.9em;
            color: #888;
        }}
        @media print {{
            body {{
                margin: 20px;
            }}
            .elemento {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Elementos de Descripción</h1>
        <div class="proyecto">{nombre_proyecto}</div>
        <div class="fecha">Generado el {fecha_generacion}</div>
    </div>
'''

        for elem in elementos_data:
            html_content += f'''
    <div class="elemento">
        <div class="elemento-header">
            <span class="codigo">ELEMENTO {elem['codigo']}:</span>
            {elem['nombre']}
        </div>
'''
            for iter_data in elem['iteraciones']:
                # Si hay múltiples iteraciones o es múltiple, mostrar encabezado de iteración
                if len(elem['iteraciones']) > 1 or elem['es_multiple']:
                    titulo_iter = iter_data['primera_descripcion'] if iter_data['primera_descripcion'] else f"Tratamiento {iter_data['n_iteracion']}"
                    html_content += f'''
        <div class="iteracion">
            <div class="iteracion-header">{titulo_iter}</div>
            <div class="contenido-iteracion">
'''
                else:
                    html_content += '''
        <div class="iteracion">
            <div class="contenido-iteracion">
'''

                # Subelementos con formato compacto: cabecera + contenido a ancho completo
                for sub in iter_data['subelementos']:
                    desc_class = 'sin-datos' if sub['descripcion'] == '—' else ''
                    html_content += f'''
                <div class="subelemento-header">{sub['nombre']}</div>
                <div class="subelemento-contenido {desc_class}">{sub['descripcion']}</div>
'''

                html_content += '''
            </div>
        </div>
'''

            html_content += '''
    </div>
'''

        html_content += f'''
    <div class="footer">
        Protección de Datos en Sistemas de IA - Consejo de Transparencia y Protección de Datos de Andalucía
    </div>
</body>
</html>
'''

        # 8. Guardar HTML temporal
        with open(ruta_html, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # 9. Buscar wkhtmltopdf
        wkhtmltopdf_path = _buscar_wkhtmltopdf()

        if not wkhtmltopdf_path:
            # Limpiar HTML temporal
            try:
                os.unlink(ruta_html)
            except:
                pass
            return {
                "exito": False,
                "mensaje": "No se encontró wkhtmltopdf.exe. Por favor, colóquelo en la carpeta 'bin' de la aplicación."
            }

        try:
            # 10. Ejecutar wkhtmltopdf
            comando = [
                wkhtmltopdf_path,
                '--quiet',
                '--enable-local-file-access',
                '--page-size', 'A4',
                '--margin-top', '20mm',
                '--margin-bottom', '20mm',
                '--margin-left', '20mm',
                '--margin-right', '20mm',
                '--encoding', 'UTF-8',
                ruta_html,
                ruta_pdf
            ]

            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=30
            )

            if resultado.returncode != 0:
                error_msg = resultado.stderr if resultado.stderr else "Error desconocido"
                return {
                    "exito": False,
                    "mensaje": f"Error al generar PDF: {error_msg}"
                }

            # 11. Leer el PDF generado
            with open(ruta_pdf, 'rb') as pdf_file:
                pdf_bytes = pdf_file.read()

            return {
                "exito": True,
                "archivo": ruta_pdf,
                "nombre_archivo": nombre_archivo_pdf,
                "pdf": pdf_bytes,
                "mensaje": f"Exportación completada: {len(elementos_data)} elementos exportados a PDF"
            }

        finally:
            # Eliminar el HTML temporal
            try:
                os.unlink(ruta_html)
            except:
                pass

    except subprocess.TimeoutExpired:
        return {
            "exito": False,
            "mensaje": "Timeout al generar PDF. El documento puede ser demasiado grande."
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"exito": False, "mensaje": f"Error al exportar: {str(e)}"}
    finally:
        session.close()


def exportar_requisitos_cumplimiento(id_sistema, output_dir):
    """
    Genera un archivo Excel con el informe de requisitos de cumplimiento.

    Estructura del Excel:
    - Un bloque por cada requisito aplicable (L_APLICA = 1) y activo (L_ESTADO = 1)
    - Cada bloque incluye: datos del requisito, justificaciones de planificación y cumplimiento,
      controles asociados activos y aplicables, y plan de mejora si corresponde (L_JUSTOBLIG = 1)

    Args:
        id_sistema (int): ID del sistema/proyecto
        output_dir (str): Directorio donde guardar el archivo

    Returns:
        dict: Resultado con 'exito', 'archivo' (ruta completa), 'nombre_archivo' y 'mensaje'
    """
    session = Session()

    try:
        # 1. Obtener información del proyecto
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=id_sistema).first()
        if not proyecto:
            return {
                "exito": False,
                "mensaje": "No se encontró el proyecto especificado"
            }

        nombre_proyecto = proyecto.D_NOMPROYEC or f"Proyecto_{id_sistema}"
        # Limpiar nombre para el archivo
        nombre_limpio = "".join(c for c in nombre_proyecto if c.isalnum() or c in (' ', '-', '_')).strip()
        nombre_limpio = nombre_limpio.replace(' ', '_')[:50]  # Limitar longitud

        # 2. Generar nombre del archivo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_archivo = f"RC_{nombre_limpio}_{timestamp}.xlsx"
        ruta_completa = os.path.join(output_dir, nombre_archivo)

        # 3. Obtener TODOS los requisitos activos (L_ESTADO = 1) - incluye los que aplican y no aplican
        requisitos_data = session.query(
            DatosRequisito,
            ConfiguracionRequisito
        ).join(
            ConfiguracionRequisito,
            DatosRequisito.REQ_ID_REQU == ConfiguracionRequisito.ID_REQ
        ).filter(
            DatosRequisito.SIST_ID_SISTEMA == id_sistema,
            # NO filtrar por L_APLICA - mostrar todos los requisitos
            ConfiguracionRequisito.L_ESTADO == 1  # Solo requisitos activos
        ).order_by(
            ConfiguracionRequisito.N_ORDVISU
        ).all()

        if not requisitos_data:
            return {
                "exito": False,
                "mensaje": "No hay requisitos para este proyecto"
            }

        # 3.5. Obtener valores de madurez de la BD
        tipo_madurez = session.query(TiposDato).filter_by(C_TIPDAT="MAD").first()
        valores_madurez = {}

        if tipo_madurez:
            for v in session.query(ValoresDato).filter_by(TIDA_ID_TIPDAT=tipo_madurez.ID_TIPDAT).all():
                valores_madurez[v.ID_VALDAT] = v.D_VALOR

        # 4. Crear nuevo libro de Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Requisitos Cumplimiento"

        # 5. Configurar anchos de columna (A-E, sin usar F)
        ws.column_dimensions['A'].width = 15
        ws.column_dimensions['B'].width = 50
        ws.column_dimensions['C'].width = 25
        ws.column_dimensions['D'].width = 25
        ws.column_dimensions['E'].width = 40

        # 6. Definir estilos
        titulo_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        titulo_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="B4C7E7", end_color="B4C7E7", fill_type="solid")
        header_font = Font(bold=True, size=10)
        subtitulo_font = Font(bold=True, size=10)
        mejora_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

        borde = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        alineacion_centro = Alignment(horizontal='center', vertical='center', wrap_text=True)
        alineacion_izquierda = Alignment(horizontal='left', vertical='center', wrap_text=True)
        alineacion_izquierda_top = Alignment(horizontal='left', vertical='top', wrap_text=True)

        fila_actual = 1

        # 7. Iterar sobre cada requisito
        for dato_req, config_req in requisitos_data:
            # Determinar si aplica o no
            aplica = dato_req.L_APLICA == 1

            # ===== SECCIÓN: TÍTULO DEL REQUISITO =====
            ws.merge_cells(f'A{fila_actual}:E{fila_actual}')
            cell = ws[f'A{fila_actual}']
            titulo_requisito = f"REQUISITO {config_req.C_REQUISITO}"
            if not aplica:
                titulo_requisito += " (NO APLICA)"
            cell.value = titulo_requisito
            cell.fill = titulo_fill
            cell.font = titulo_font
            cell.alignment = alineacion_centro
            cell.border = borde
            for col in range(1, 6):  # A-E
                ws.cell(row=fila_actual, column=col).border = borde
                ws.cell(row=fila_actual, column=col).fill = titulo_fill
            fila_actual += 1

            # ===== SECCIÓN: CABECERA DE DATOS =====
            if aplica:
                # Para requisitos que APLICAN: mostrar Estado Planificación y Estado Cumplimiento
                headers = ['ID', 'Descripción del Requisito', 'Base Normativa', 'Estado Planificación', 'Estado Cumplimiento']
            else:
                # Para requisitos que NO APLICAN: solo mostrar hasta Base Normativa
                headers = ['ID', 'Descripción del Requisito', 'Base Normativa']

            for col_idx, header in enumerate(headers, start=1):
                cell = ws.cell(row=fila_actual, column=col_idx)
                cell.value = header
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = alineacion_centro
                cell.border = borde
            fila_actual += 1

            # ===== SECCIÓN: DATOS DEL REQUISITO =====
            if aplica:
                # Obtener estado de planificación
                estado_planif = None
                if dato_req.N_ESTPLANIF:
                    estado_planif = session.query(ConfiguracionEstadoRequisito).filter_by(
                        ID_ESTREQ=dato_req.N_ESTPLANIF
                    ).first()

                estado_planif_texto = estado_planif.D_ESTADO.upper() if estado_planif else "SIN EVALUAR"

                # Obtener estado de cumplimiento
                estado_cumpl = None
                if dato_req.N_ESTCUMPL:
                    estado_cumpl = session.query(ConfiguracionEstadoRequisito).filter_by(
                        ID_ESTREQ=dato_req.N_ESTCUMPL
                    ).first()

                estado_cumpl_texto = estado_cumpl.D_ESTADO.upper() if estado_cumpl else "SIN EVALUAR"

                valores = [
                    config_req.C_REQUISITO,
                    config_req.D_REQUISITO,
                    config_req.T_BASENORMATIVA or "",
                    estado_planif_texto,
                    estado_cumpl_texto
                ]
            else:
                # Para NO APLICA: solo 3 columnas
                valores = [
                    config_req.C_REQUISITO,
                    config_req.D_REQUISITO,
                    config_req.T_BASENORMATIVA or ""
                ]

            for col_idx, valor in enumerate(valores, start=1):
                cell = ws.cell(row=fila_actual, column=col_idx)
                cell.value = valor
                cell.alignment = alineacion_izquierda
                cell.border = borde
            fila_actual += 1

            # ===== SECCIÓN: DESCRIPCIÓN COMPLETA =====
            if config_req.T_DESCRIPCION:
                ws.merge_cells(f'A{fila_actual}:E{fila_actual}')
                cell = ws[f'A{fila_actual}']
                cell.value = config_req.T_DESCRIPCION
                cell.alignment = alineacion_izquierda_top
                cell.border = borde
                for col in range(1, 6):  # A-E
                    ws.cell(row=fila_actual, column=col).border = borde
                fila_actual += 1

            if aplica:
                # ===== PARA REQUISITOS QUE APLICAN: PLANIFICACIÓN Y VERIFICACIÓN =====

                # PLANIFICACIÓN (FASE 2)
                ws.merge_cells(f'A{fila_actual}:B{fila_actual}')
                cell = ws[f'A{fila_actual}']
                cell.value = "Planificación (Fase 2)"
                cell.font = subtitulo_font
                cell.alignment = alineacion_izquierda
                cell.border = borde
                for col in [1, 2]:
                    ws.cell(row=fila_actual, column=col).border = borde

                ws.merge_cells(f'C{fila_actual}:E{fila_actual}')
                cell = ws[f'C{fila_actual}']
                cell.value = dato_req.T_JUSTPLANIF or "No documentado"
                cell.alignment = alineacion_izquierda_top
                cell.border = borde
                for col in range(3, 6):  # C-E
                    ws.cell(row=fila_actual, column=col).border = borde
                fila_actual += 1

                # VERIFICACIÓN (FASE 3)
                ws.merge_cells(f'A{fila_actual}:B{fila_actual}')
                cell = ws[f'A{fila_actual}']
                cell.value = "Verificación (Fase 3)"
                cell.font = subtitulo_font
                cell.alignment = alineacion_izquierda
                cell.border = borde
                for col in [1, 2]:
                    ws.cell(row=fila_actual, column=col).border = borde

                ws.merge_cells(f'C{fila_actual}:E{fila_actual}')
                cell = ws[f'C{fila_actual}']
                cell.value = dato_req.T_JUSTCUMPL or "No documentado"
                cell.alignment = alineacion_izquierda_top
                cell.border = borde
                for col in range(3, 6):  # C-E
                    ws.cell(row=fila_actual, column=col).border = borde
                fila_actual += 1

                # Fila en blanco
                fila_actual += 1

                # ===== SECCIÓN: CONTROLES ASOCIADOS (solo para APLICA) =====
                ws.merge_cells(f'A{fila_actual}:E{fila_actual}')
                cell = ws[f'A{fila_actual}']
                cell.value = "CONTROLES ASOCIADOS"
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = alineacion_centro
                cell.border = borde
                for col in range(1, 6):  # A-E
                    ws.cell(row=fila_actual, column=col).border = borde
                    ws.cell(row=fila_actual, column=col).fill = header_fill
                fila_actual += 1

                # Cabecera de controles
                control_headers = ['ID Control', 'Descripción del Control', 'Grupo', 'Madurez', 'Observaciones Implementación']
                for col_idx, header in enumerate(control_headers, start=1):
                    cell = ws.cell(row=fila_actual, column=col_idx)
                    cell.value = header
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = alineacion_centro
                    cell.border = borde
                fila_actual += 1

                # Obtener controles asociados activos y aplicables
                controles_asociados = session.query(
                    Control,
                    GrupoControl,
                    DatosControl
                ).join(
                    ConfiguracionRequisitoControl,
                    Control.ID_CONTROL == ConfiguracionRequisitoControl.REQ_ID_CONTROL
                ).outerjoin(
                    GrupoControl,
                    Control.GRU_ID_CONTROL == GrupoControl.ID_GRUCONTROL
                ).outerjoin(
                    DatosControl,
                    (DatosControl.CON_ID_CONTROL == Control.ID_CONTROL) &
                    (DatosControl.SIST_ID_SISTEMA == id_sistema)
                ).filter(
                    ConfiguracionRequisitoControl.REQ_ID_REQU == config_req.ID_REQ,
                    Control.L_ESTADO == 1  # Solo controles activos
                ).all()

                # Filtrar solo los que aplican al proyecto
                controles_filtrados = []
                for control, grupo, dato_control in controles_asociados:
                    if dato_control and dato_control.L_APLICA == 1:
                        controles_filtrados.append((control, grupo, dato_control))

                if controles_filtrados:
                    for control, grupo, dato_control in controles_filtrados:
                        # Obtener madurez usando el diccionario de valores de la BD
                        madurez_texto = valores_madurez.get(dato_control.V_MADUREZ, "—") if dato_control and dato_control.V_MADUREZ else "—"

                        # Datos del control
                        control_valores = [
                            control.C_CONTROL,
                            control.D_CONTROL,
                            grupo.D_CONTROL if grupo else "—",
                            madurez_texto,
                            dato_control.T_OBSERVACIONES if dato_control and dato_control.T_OBSERVACIONES else ""
                        ]

                        for col_idx, valor in enumerate(control_valores, start=1):
                            cell = ws.cell(row=fila_actual, column=col_idx)
                            cell.value = valor
                            cell.alignment = alineacion_izquierda_top
                            cell.border = borde
                        fila_actual += 1
                else:
                    # Sin controles asociados
                    ws.merge_cells(f'A{fila_actual}:E{fila_actual}')
                    cell = ws[f'A{fila_actual}']
                    cell.value = "No hay controles asociados activos y aplicables"
                    cell.alignment = Alignment(horizontal='center', vertical='center', italic=True)
                    cell.border = borde
                    for col in range(1, 6):  # A-E
                        ws.cell(row=fila_actual, column=col).border = borde
                    fila_actual += 1

                # ===== SECCIÓN: PLAN DE MEJORA (solo si L_JUSTOBLIG = 1) =====
                # Verificar si el estado actual tiene L_JUSTOBLIG = 1
                if estado_cumpl and estado_cumpl.L_JUSTOBLIG == 1:
                    fila_actual += 1  # Espacio
                    ws.merge_cells(f'A{fila_actual}:B{fila_actual}')
                    cell = ws[f'A{fila_actual}']
                    cell.value = "Plan de Mejora"
                    cell.font = subtitulo_font
                    cell.fill = mejora_fill
                    cell.alignment = alineacion_izquierda
                    cell.border = borde
                    for col in [1, 2]:
                        ws.cell(row=fila_actual, column=col).border = borde
                        ws.cell(row=fila_actual, column=col).fill = mejora_fill

                    ws.merge_cells(f'C{fila_actual}:E{fila_actual}')
                    cell = ws[f'C{fila_actual}']
                    cell.value = dato_req.T_PLANMEJORA or "No documentado"
                    cell.alignment = alineacion_izquierda_top
                    cell.border = borde
                    for col in range(3, 6):  # C-E
                        ws.cell(row=fila_actual, column=col).border = borde
                    fila_actual += 1

            else:
                # ===== PARA REQUISITOS QUE NO APLICAN: JUSTIFICACIÓN NO APLICA =====
                ws.merge_cells(f'A{fila_actual}:B{fila_actual}')
                cell = ws[f'A{fila_actual}']
                cell.value = "Justificación No Aplica"
                cell.font = subtitulo_font
                cell.alignment = alineacion_izquierda
                cell.border = borde
                for col in [1, 2]:
                    ws.cell(row=fila_actual, column=col).border = borde

                ws.merge_cells(f'C{fila_actual}:E{fila_actual}')
                cell = ws[f'C{fila_actual}']
                cell.value = dato_req.T_JUSTAPLICA or "No documentado"
                cell.alignment = alineacion_izquierda_top
                cell.border = borde
                for col in range(3, 6):  # C-E
                    ws.cell(row=fila_actual, column=col).border = borde
                fila_actual += 1

            # Espacios entre requisitos
            fila_actual += 2

        # 8. Ajustar altura de todas las filas automáticamente
        anchos_columnas = {'A': 15, 'B': 50, 'C': 25, 'D': 25, 'E': 40}
        ajustar_alturas_filas(ws, anchos_columnas, font_size=10, altura_minima=15)

        # 9. Guardar archivo
        wb.save(ruta_completa)

        return {
            "exito": True,
            "mensaje": f"Informe de requisitos generado correctamente",
            "archivo": ruta_completa,
            "nombre_archivo": nombre_archivo
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "exito": False,
            "mensaje": f"Error al generar el informe: {str(e)}"
        }

    finally:
        session.close()
