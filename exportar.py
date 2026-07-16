
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

# exportar.py

from flask import Blueprint, request, send_file, abort
from sqlalchemy.orm import Session as ORMSession
from io import BytesIO
import pyzipper as zipfile
import json
from datetime import datetime
import config

from models import (
    engine,
    Session,
    Base,
    Pregunta,
    Respuesta,
    Inicio,
    RespuestasProyecto,
    ElementosAdi,
    SubElementosAdi,
    DatosElementosAdi,
    Perfil,
    Riesgo,
    RiesgoAdiRespuesta,
    DatosRiesgo,
    CategoriaRiesgo,
    TiposDato,
    ValoresDato,
    ConfiguracionCriticidad,
    ConfiguracionFase,
    Control,
    GrupoControl,
    ControlActivacionNo,
    ControlRespuesta,
    DatosControl,
    RiesgoControl,
    DatosElementoControl,
    DatosControlMonitoreo,
    DatosActividadMonitoreo,
    AyudaContexto,
    ConfiguracionDocumento,
    ConfiguracionDatoDocumento,
    RelacionDocumentoElemento,
    DatosDocumento,
    DatosElementoDocumento,
    # ============================================
    # NUEVAS TABLAS AÑADIDAS
    # ============================================
    DatosRequisito,
    ConfiguracionIncompatibilidad,
    ReglaEIPD,
    ConfiguracionVisibilidad,
    ConfiguracionRequisito,
    ConfiguracionEstadoRequisito,
    ConfiguracionRequisitoControl,
    ConfiguracionCluster,
    ConfiguracionRiesgoCluster,
    ConfiguracionRiesgoGlobal
)

exportar_proyecto_db = Blueprint("exportar_proyecto", __name__)

def write_json_from_query(zipf, filename, column_names, rows):
    data_list = []
    for row in rows:
        row_dict = dict(zip(column_names, row))
        data_list.append(row_dict)

    json_data = json.dumps(data_list, indent=4, ensure_ascii=False)
    zipf.writestr(filename, json_data)

@exportar_proyecto_db.route("/exportar-proyecto", methods=["POST"])
def exportar_proyecto():
    proyecto_id = request.form.get("proyecto_id")


    if not proyecto_id:
        return abort(400, description="ID del proyecto no proporcionado")

    try:
        proyecto_id = int(proyecto_id)
    except ValueError:
        return abort(400, description="ID del proyecto inválido")

    session = Session()

    # 1. Obtener el proyecto para acceder a D_NOMPROYEC
    proyecto = session.query(Inicio).filter_by(ID_SISTEMA=proyecto_id).first()

    # 2. Verificar si el proyecto existe
    if not proyecto:
        session.close()
        return abort(404, description=f"Proyecto con ID {proyecto_id} no encontrado")

    buffer = BytesIO()

    nombre_proyecto = proyecto.D_NOMPROYEC.replace(" ", "_").replace("/", "-").strip()
    nombre_zip = f"SIA_{nombre_proyecto}_exp.zip"

    contrasena = bytes(config.CONTRASENA_EXPORTACION, 'utf-8')

    with zipfile.AESZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        encryption=zipfile.WZ_AES
    ) as zipf:
        zipf.setpassword(contrasena)

        # ============================================
        # ARCHIVO DE METADATOS DE VERSIÓN
        # ============================================
        meta_version = {
            "VERSION_APP": config.VERSION_APLICACION,
            "VERSION_BD": config.VERSION_BD_INICIAL,
            "F_EXPORTACION": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "NOMBRE_APP": "SupervisionSIA",
            "PROYECTO_ID": proyecto_id,
            "PROYECTO_NOMBRE": proyecto.D_NOMPROYEC
        }
        meta_version_json = json.dumps(meta_version, indent=4, ensure_ascii=False)
        zipf.writestr("META_VERSION.json", meta_version_json)

        # ============================================
        # DATOS DEL PROYECTO ESPECÍFICO
        # ============================================

        # 1. Tabla IA_SISTEMA (Inicio)
        proyecto = session.query(Inicio).filter_by(ID_SISTEMA=proyecto_id).first()
        cols = ["ID_SISTEMA", "D_NOMPROYEC", "F_INI", "T_DPD", "T_ESTADO_PROYEC", "N_FASE"]
        if proyecto:
            rows = [
                (proyecto.ID_SISTEMA, proyecto.D_NOMPROYEC, proyecto.F_INI,
                 proyecto.T_DPD, proyecto.T_ESTADO_PROYEC, proyecto.N_FASE)
            ]
        else:
            rows = []
        write_json_from_query(zipf, "IA_SISTEMA.json", cols, rows)

        # 2. Respuestas de proyecto (IA_SISTEMAADI)
        respuestas = session.query(RespuestasProyecto).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = ["ID_SISTEMAADI", "SIST_ID_SISTEMA", "PRE_ID_PREGUNTA", "RES_ID_RESPUESTA"]
        rows = [
            (r.ID_SISTEMAADI, r.SIST_ID_SISTEMA, r.PRE_ID_PREGUNTA, r.RES_ID_RESPUESTA)
            for r in respuestas
        ]
        write_json_from_query(zipf, "IA_SISTEMAADI.json", cols, rows)

        # 3. DatosElementosAdi (IA_DATELEMADI)
        datos_elem = session.query(DatosElementosAdi).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = ["ID_DATELEMADI", "SIST_ID_SISTEMA", "ELE_ID_ELEM", "SUB_IDSUBELEM", "T_DESCRIPCION", "N_ITERACION"]
        rows = [
            (e.ID_DATELEMADI, e.SIST_ID_SISTEMA, e.ELE_ID_ELEM, e.SUB_IDSUBELEM, e.T_DESCRIPCION, e.N_ITERACION)
            for e in datos_elem
        ]
        write_json_from_query(zipf, "IA_DATELEMADI.json", cols, rows)

        # 4. DatosRiesgo (IA_DATRIESGOS) - ACTUALIZADO con L_MANUAL, T_DESCRIPCION, V_RIERESID
        datos_ries = session.query(DatosRiesgo).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATRIES", "SIST_ID_SISTEMA", "RIE_ID_RIESGO", "L_APLICA",
            "T_JUSAPLICA", "V_PROBABILIDAD", "T_JUSPROBABILIDAD", "V_IMPACTO",
            "T_JUSIMPACTO", "L_ACTIVA", "L_MANUAL", "T_DESCRIPCION", "V_RIERESID"
        ]
        rows = [
            (dr.ID_DATRIES, dr.SIST_ID_SISTEMA, dr.RIE_ID_RIESGO, dr.L_APLICA,
             dr.T_JUSAPLICA, dr.V_PROBABILIDAD, dr.T_JUSPROBABILIDAD, dr.V_IMPACTO,
             dr.T_JUSIMPACTO, dr.L_ACTIVA, dr.L_MANUAL, dr.T_DESCRIPCION, dr.V_RIERESID)
            for dr in datos_ries
        ]
        write_json_from_query(zipf, "IA_DATRIESGOS.json", cols, rows)

        # 5. DatosControl (IA_DATCONTROL) - ACTUALIZADO con L_MANUAL
        datos_control = session.query(DatosControl).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATCONTROL", "SIST_ID_SISTEMA", "CON_ID_CONTROL", "L_ACTIVA",
            "L_APLICA", "L_TRASLAPLI", "V_INTCONDES", "T_ESPCLAUSULA",
            "T_OBSERVACIONES", "V_MADUREZ", "L_MANUAL"
        ]
        rows = [
            (dc.ID_DATCONTROL, dc.SIST_ID_SISTEMA, dc.CON_ID_CONTROL, dc.L_ACTIVA,
             dc.L_APLICA, dc.L_TRASLAPLI, dc.V_INTCONDES, dc.T_ESPCLAUSULA,
             dc.T_OBSERVACIONES, dc.V_MADUREZ, dc.L_MANUAL)
            for dc in datos_control
        ]
        write_json_from_query(zipf, "IA_DATCONTROL.json", cols, rows)

        # 6. DatosElementoControl (IA_DATELEMCONTR)
        datos_elem_control = session.query(DatosElementoControl).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATELEMCONTR", "SIST_ID_SISTEMA", "ELE_ID_ELEM", "L_TRASLAPLI",
            "V_INTSCONDES", "T_ESPCLAUSULA", "N_ITERACION"
        ]
        rows = [
            (dec.ID_DATELEMCONTR, dec.SIST_ID_SISTEMA, dec.ELE_ID_ELEM, dec.L_TRASLAPLI,
             dec.V_INTSCONDES, dec.T_ESPCLAUSULA, dec.N_ITERACION)
            for dec in datos_elem_control
        ]
        write_json_from_query(zipf, "IA_DATELEMCONTR.json", cols, rows)

        # 7. DatosControlMonitoreo (IA_DATCONTMON)
        datos_control_mon = session.query(DatosControlMonitoreo).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATCONTMON", "SIST_ID_SISTEMA", "CON_ID_CONTROL", "V_ESTADO",
            "T_RESP", "V_MADINI", "V_MADACT", "V_MADOBJ", "T_DESC",
            "V_FREC", "F_PROXEJEC"
        ]
        rows = [
            (dcm.ID_DATCONTMON, dcm.SIST_ID_SISTEMA, dcm.CON_ID_CONTROL, dcm.V_ESTADO,
             dcm.T_RESP, dcm.V_MADINI, dcm.V_MADACT, dcm.V_MADOBJ, dcm.T_DESC,
             dcm.V_FREC, dcm.F_PROXEJEC)
            for dcm in datos_control_mon
        ]
        write_json_from_query(zipf, "IA_DATCONTMON.json", cols, rows)

        # 8. DatosActividadMonitoreo (IA_DATACTMONIT)
        datos_act_mon = session.query(DatosActividadMonitoreo).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATACTMONIT", "SIST_ID_SISTEMA", "ACT_ID_CONTMON",
            "F_EJECUCION", "T_DESCEJEC"
        ]
        rows = [
            (dam.ID_DATACTMONIT, dam.SIST_ID_SISTEMA, dam.ACT_ID_CONTMON,
             dam.F_EJECUCION, dam.T_DESCEJEC)
            for dam in datos_act_mon
        ]
        write_json_from_query(zipf, "IA_DATACTMONIT.json", cols, rows)

        # 9. DatosDocumento (IA_DATDOCS)
        datos_docs = session.query(DatosDocumento).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATDOCS", "SIST_ID_SISTEMA", "DD_ID_CFGDOCS",
            "V_SITUACION", "T_OBSERVACIONES", "L_NECESARIO"
        ]
        rows = [
            (dd.ID_DATDOCS, dd.SIST_ID_SISTEMA, dd.DD_ID_CFGDOCS,
             dd.V_SITUACION, dd.T_OBSERVACIONES, dd.L_NECESARIO)
            for dd in datos_docs
        ]
        write_json_from_query(zipf, "IA_DATDOCS.json", cols, rows)

        # 10. DatosElementoDocumento (IA_DATELEMDOCS)
        datos_elem_docs = session.query(DatosElementoDocumento).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATELEMDOCS", "SIST_ID_SISTEMA", "DED_ID_DATDOCS",
            "DED_ID_CFGDATDOCS", "T_DATO"
        ]
        rows = [
            (ded.ID_DATELEMDOCS, ded.SIST_ID_SISTEMA, ded.DED_ID_DATDOCS,
             ded.DED_ID_CFGDATDOCS, ded.T_DATO)
            for ded in datos_elem_docs
        ]
        write_json_from_query(zipf, "IA_DATELEMDOCS.json", cols, rows)

        # ============================================
        # 11. DatosRequisito (IA_DATEREQUISITOS) - NUEVA TABLA
        # ============================================
        datos_requisitos = session.query(DatosRequisito).filter_by(SIST_ID_SISTEMA=proyecto_id).all()
        cols = [
            "ID_DATREQ", "SIST_ID_SISTEMA", "REQ_ID_REQU", "L_APLICA",
            "T_JUSTAPLICA", "N_ESTPLANIF", "T_JUSTPLANIF", "N_ESTCUMPL",
            "T_JUSTCUMPL", "L_TRASLAPLI", "V_INSTRCONTR", "T_OBSPLIEGO",
            "T_PLANMEJORA"
        ]
        rows = [
            (dreq.ID_DATREQ, dreq.SIST_ID_SISTEMA, dreq.REQ_ID_REQU, dreq.L_APLICA,
             dreq.T_JUSTAPLICA, dreq.N_ESTPLANIF, dreq.T_JUSTPLANIF, dreq.N_ESTCUMPL,
             dreq.T_JUSTCUMPL, dreq.L_TRASLAPLI, dreq.V_INSTRCONTR, dreq.T_OBSPLIEGO,
             dreq.T_PLANMEJORA)
            for dreq in datos_requisitos
        ]
        write_json_from_query(zipf, "IA_DATEREQUISITOS.json", cols, rows)

        # ============================================
        # TABLAS DE METADATOS / CONFIGURACIÓN (completas)
        # ============================================

        # 12. Preguntas (IA_ADIPREG)
        preguntas = session.query(Pregunta).all()
        cols = ["ID_PREGUNTA", "C_PREGUNTA", "D_PREGUNTA", "L_ESTADO", "N_TIPCAMPO", "T_AYUDA"]
        rows = [
            (p.ID_PREGUNTA, p.C_PREGUNTA, p.D_PREGUNTA, p.L_ESTADO, p.N_TIPCAMPO, p.T_AYUDA)
            for p in preguntas
        ]
        write_json_from_query(zipf, "IA_ADIPREG.json", cols, rows)

        # 13. Respuestas (IA_ADIRESP)
        resp = session.query(Respuesta).all()
        cols = [
            "ID_RESPUESTA", "PRE_ID_PREGUNTA", "C_OPCION", "D_RESPUESTA",
            "N_PTOSBASE", "N_MULTIPLICADOR", "N_ADICIONAL", "L_ESTADO", "N_AMPLIVULNER"
        ]
        rows = [
            (r.ID_RESPUESTA, r.PRE_ID_PREGUNTA, r.C_OPCION, r.D_RESPUESTA,
             r.N_PTOSBASE, r.N_MULTIPLICADOR, r.N_ADICIONAL, r.L_ESTADO, r.N_AMPLIVULNER)
            for r in resp
        ]
        write_json_from_query(zipf, "IA_ADIRESP.json", cols, rows)

        # 14. ElementosAdi (IA_ELEMENADI) - ACTUALIZADO con C_ELEMENTO
        elems = session.query(ElementosAdi).all()
        cols = [
            "ID_ELEM", "C_ELEMENTO", "N_ORDEN", "D_ELEMENTO", "T_TIEMPO",
            "T_CRITICIDAD", "T_IMPORTA", "L_ESTADO", "L_MULTIPLE",
            "N_FASEVISUAL", "N_FASEVAL"
        ]
        rows = [
            (e.ID_ELEM, e.C_ELEMENTO, e.N_ORDEN, e.D_ELEMENTO, e.T_TIEMPO,
             e.T_CRITICIDAD, e.T_IMPORTA, e.L_ESTADO, e.L_MULTIPLE,
             e.N_FASEVISUAL, e.N_FASEVAL)
            for e in elems
        ]
        write_json_from_query(zipf, "IA_ELEMENADI.json", cols, rows)

        # 15. SubElementosAdi (IA_SUBELEMENADI)
        subs = session.query(SubElementosAdi).all()
        cols = ["ID_SUBELEM", "ELE_ID_ELEM", "N_SUBORD", "D_SUBELEM", "L_ESTADO"]
        rows = [
            (s.ID_SUBELEM, s.ELE_ID_ELEM, s.N_SUBORD, s.D_SUBELEM, s.L_ESTADO)
            for s in subs
        ]
        write_json_from_query(zipf, "IA_SUBELEMENADI.json", cols, rows)

        # 16. Perfiles (IA_PERFIL)
        perfiles = session.query(Perfil).all()
        cols = ["ID_PERFIL", "D_PERFIL", "N_PTOSMIN", "N_PTOSMAX", "TIEMPO_ESTIMADO", "T_DESCRIPCION"]
        rows = [
            (pf.ID_PERFIL, pf.D_PERFIL, pf.N_PTOSMIN, pf.N_PTOSMAX,
             pf.TIEMPO_ESTIMADO, pf.T_DESCRIPCION)
            for pf in perfiles
        ]
        write_json_from_query(zipf, "IA_PERFIL.json", cols, rows)

        # 17. Riesgos (IA_RIESGOS) - ACTUALIZADO con L_PERSONAL
        riesgos = session.query(Riesgo).all()
        cols = [
            "ID_RIESGO", "C_RIESGO", "CAT_ID_CATRIES", "D_RIESGO", "T_DESCRIPCION",
            "PER_ID_PERFIL", "ACTIVACION_AUTOMATICA", "T_BASENORMATIVA", "L_ESTADO",
            "N_ORDVISU", "N_FASEVISUAL", "N_FASEVAL", "N_RIERESMIN", "N_CONTRMIN", "L_PERSONAL"
        ]
        rows = [
            (r.ID_RIESGO, r.C_RIESGO, r.CAT_ID_CATRIES, r.D_RIESGO, r.T_DESCRIPCION,
             r.PER_ID_PERFIL, r.ACTIVACION_AUTOMATICA, r.T_BASENORMATIVA, r.L_ESTADO,
             r.N_ORDVISU, r.N_FASEVISUAL, r.N_FASEVAL, r.N_RIERESMIN, r.N_CONTRMIN, r.L_PERSONAL)
            for r in riesgos
        ]
        write_json_from_query(zipf, "IA_RIESGOS.json", cols, rows)

        # 18. RiesgoAdiRespuesta (IA_RIESGTIPADSQ) - ACTUALIZADO con PRE_ID_PREGUNTA
        rar = session.query(RiesgoAdiRespuesta).all()
        cols = ["ID_RIESGTIPADQS", "RIE_ID_RIESGO", "RESP_ID_RESP", "PRE_ID_PREGUNTA"]
        rows = [
            (r.ID_RIESGTIPADQS, r.RIE_ID_RIESGO, r.RESP_ID_RESP, r.PRE_ID_PREGUNTA)
            for r in rar
        ]
        write_json_from_query(zipf, "IA_RIESGTIPADSQ.json", cols, rows)

        # 19. CategoriaRiesgo (IA_CATRIESGOS)
        cat = session.query(CategoriaRiesgo).all()
        cols = ["ID_CATRIES", "D_CATEGORIA", "N_SUBCAT"]
        rows = [
            (c.ID_CATRIES, c.D_CATEGORIA, c.N_SUBCAT)
            for c in cat
        ]
        write_json_from_query(zipf, "IA_CATRIESGOS.json", cols, rows)

        # 20. TiposDato (IA_TIPDAT)
        td = session.query(TiposDato).all()
        cols = ["ID_TIPDAT", "C_TIPDAT", "D_TIPDAT"]
        rows = [
            (t.ID_TIPDAT, t.C_TIPDAT, t.D_TIPDAT)
            for t in td
        ]
        write_json_from_query(zipf, "IA_TIPDAT.json", cols, rows)

        # 21. ValoresDato (IA_VALDAT) - ACTUALIZADO con C_VALOR_TEXT
        vd = session.query(ValoresDato).all()
        cols = ["ID_VALDAT", "TIDA_ID_TIPDAT", "C_VALOR", "C_VALOR_TEXT", "D_VALOR", "OBS"]
        rows = [
            (v.ID_VALDAT, v.TIDA_ID_TIPDAT, v.C_VALOR, v.C_VALOR_TEXT, v.D_VALOR, v.OBS)
            for v in vd
        ]
        write_json_from_query(zipf, "IA_VALDAT.json", cols, rows)

        # 22. ConfiguracionCriticidad (IA_CFGCRITICIDAD)
        cfg_crit = session.query(ConfiguracionCriticidad).all()
        cols = ["ID_CRITIC", "V_IMPACTO", "V_PROBAB", "N_CRITICIDAD"]
        rows = [
            (cc.ID_CRITIC, cc.V_IMPACTO, cc.V_PROBAB, cc.N_CRITICIDAD)
            for cc in cfg_crit
        ]
        write_json_from_query(zipf, "IA_CFGCRITICIDAD.json", cols, rows)

        # 23. ConfiguracionFase (IA_CFGFASES) - ACTUALIZADO con C_NIVELRIESG
        cfg_fases = session.query(ConfiguracionFase).all()
        cols = [
            "ID_FASE", "C_FASE", "D_FASE", "T_INSTRUCIONES", "N_ORDEN",
            "L_MONITOREO", "T_INSTRCAMFASE", "C_NIVELRIESG"
        ]
        rows = [
            (cf.ID_FASE, cf.C_FASE, cf.D_FASE, cf.T_INSTRUCIONES, cf.N_ORDEN,
             cf.L_MONITOREO, cf.T_INSTRCAMFASE, cf.C_NIVELRIESG)
            for cf in cfg_fases
        ]
        write_json_from_query(zipf, "IA_CFGFASES.json", cols, rows)

        # 24. Control (IA_CONTROLES) - ACTUALIZADO con N_MADUMIN y D_DESCMONITOR
        controles = session.query(Control).all()
        cols = [
            "ID_CONTROL", "C_CONTROL", "D_CONTROL", "GRU_ID_CONTROL",
            "PER_ID_PERFIL", "L_ORIENTA", "L_ESTADO", "N_ORDVISUAL",
            "D_DESCRIPCION", "T_INSTRUCCIONES", "N_MADUMIN", "D_DESCMONITOR"
        ]
        rows = [
            (c.ID_CONTROL, c.C_CONTROL, c.D_CONTROL, c.GRU_ID_CONTROL,
             c.PER_ID_PERFIL, c.L_ORIENTA, c.L_ESTADO, c.N_ORDVISUAL,
             c.D_DESCRIPCION, c.T_INSTRUCCIONES, c.N_MADUMIN, c.D_DESCMONITOR)
            for c in controles
        ]
        write_json_from_query(zipf, "IA_CONTROLES.json", cols, rows)

        # 25. GrupoControl (IA_GRUCONTROL)
        grupos = session.query(GrupoControl).all()
        cols = [
            "ID_GRUCONTROL", "C_CONTROL", "D_CONTROL", "N_ORDVISUAL",
            "L_OBLIG", "N_FASEVISUAL", "N_FASEVAL", "L_MONITOREO"
        ]
        rows = [
            (g.ID_GRUCONTROL, g.C_CONTROL, g.D_CONTROL, g.N_ORDVISUAL,
             g.L_OBLIG, g.N_FASEVISUAL, g.N_FASEVAL, g.L_MONITOREO)
            for g in grupos
        ]
        write_json_from_query(zipf, "IA_GRUCONTROL.json", cols, rows)

        # 26. ControlRespuesta (IA_CONTIPADSQ)
        control_resp = session.query(ControlRespuesta).all()
        cols = ["ID_CONTIPADQS", "CON_ID_CONTROL", "RESP_ID_RESP"]
        rows = [
            (cr.ID_CONTIPADQS, cr.CON_ID_CONTROL, cr.RESP_ID_RESP)
            for cr in control_resp
        ]
        write_json_from_query(zipf, "IA_CONTIPADSQ.json", cols, rows)

        # 27. RiesgoControl (IA_RIESCONTR)
        riesgo_control = session.query(RiesgoControl).all()
        cols = ["ID_RIESCONTR", "RIE_ID_RIESGO", "CON_ID_CONTROL", "PESO", "T_JUSTIFICACION"]
        rows = [
            (rc.ID_RIESCONTR, rc.RIE_ID_RIESGO, rc.CON_ID_CONTROL, rc.PESO, rc.T_JUSTIFICACION)
            for rc in riesgo_control
        ]
        write_json_from_query(zipf, "IA_RIESCONTR.json", cols, rows)

        # 28. AyudaContexto (IA_AYUDACONTEXTO) - ACTUALIZADO con campos de posición
        ayudas = session.query(AyudaContexto).all()
        cols = [
            "ID_AYUDACONTEXTO", "C_FORMULARIO", "C_CONTROL", "T_AYUDA",
            "C_TIPO", "L_ESTADO", "N_POS_X", "N_POS_Y", "N_WIDTH",
            "N_HEIGHT", "N_SCREEN_WIDTH"
        ]
        rows = [
            (a.ID_AYUDACONTEXTO, a.C_FORMULARIO, a.C_CONTROL, a.T_AYUDA,
             a.C_TIPO, a.L_ESTADO, a.N_POS_X, a.N_POS_Y, a.N_WIDTH,
             a.N_HEIGHT, a.N_SCREEN_WIDTH)
            for a in ayudas
        ]
        write_json_from_query(zipf, "IA_AYUDACONTEXTO.json", cols, rows)

        # 29. ConfiguracionDocumento (IA_CFGDOCS)
        cfg_docs = session.query(ConfiguracionDocumento).all()
        cols = [
            "ID_CFGDOCS", "T_DESC", "T_INSTRUC", "V_TIPODOC",
            "T_PLANTILLA", "N_FASEVISUAL", "N_FASEVAL", "N_ORDVISU"
        ]
        rows = [
            (cd.ID_CFGDOCS, cd.T_DESC, cd.T_INSTRUC, cd.V_TIPODOC,
             cd.T_PLANTILLA, cd.N_FASEVISUAL, cd.N_FASEVAL, cd.N_ORDVISU)
            for cd in cfg_docs
        ]
        write_json_from_query(zipf, "IA_CFGDOCS.json", cols, rows)

        # 30. ConfiguracionDatoDocumento (IA_CFGDATDOCS) - ACTUALIZADO con L_EDITABLE
        cfg_dat_docs = session.query(ConfiguracionDatoDocumento).all()
        cols = [
            "ID_CFGDATDOCS", "DD_ID_CFGDOCS", "DD_ID_CFGDD_SUP", "C_DATO",
            "D_DESC", "T_INSTR", "T_EXPLANT", "T_EXPLPOST", "N_ORDEN",
            "L_OBLIG", "N_ANID", "L_EDITABLE"
        ]
        rows = [
            (cdd.ID_CFGDATDOCS, cdd.DD_ID_CFGDOCS, cdd.DD_ID_CFGDD_SUP, cdd.C_DATO,
             cdd.D_DESC, cdd.T_INSTR, cdd.T_EXPLANT, cdd.T_EXPLPOST, cdd.N_ORDEN,
             cdd.L_OBLIG, cdd.N_ANID, cdd.L_EDITABLE)
            for cdd in cfg_dat_docs
        ]
        write_json_from_query(zipf, "IA_CFGDATDOCS.json", cols, rows)

        # 31. RelacionDocumentoElemento (IA_CFGRELDOCEL)
        rel_doc_elem = session.query(RelacionDocumentoElemento).all()
        cols = [
            "ID_CFGRELDOCEL", "RDE_ID_CFGDATDOCS", "RDE_ID_SUBELEM",
            "RDE_ID_CFGCATDOCSREL", "L_AUTO"
        ]
        rows = [
            (rde.ID_CFGRELDOCEL, rde.RDE_ID_CFGDATDOCS, rde.RDE_ID_SUBELEM,
             rde.RDE_ID_CFGCATDOCSREL, rde.L_AUTO)
            for rde in rel_doc_elem
        ]
        write_json_from_query(zipf, "IA_CFGRELDOCEL.json", cols, rows)

        # ============================================
        # NUEVAS TABLAS DE CONFIGURACIÓN
        # ============================================

        # 32. ControlActivacionNo (IA_CONACTNO)
        ctrl_act_no = session.query(ControlActivacionNo).all()
        cols = ["ID_CONACTNO", "CON_ID_GRUCONTROL", "PRE_ID_PREGUNTA", "RES_ID_RESPUESTA"]
        rows = [
            (can.ID_CONACTNO, can.CON_ID_GRUCONTROL, can.PRE_ID_PREGUNTA, can.RES_ID_RESPUESTA)
            for can in ctrl_act_no
        ]
        write_json_from_query(zipf, "IA_CONACTNO.json", cols, rows)

        # 33. ConfiguracionIncompatibilidad (IA_CFGINCOMPADI)
        cfg_incompat = session.query(ConfiguracionIncompatibilidad).all()
        cols = [
            "ID_CFGINCOMPADI", "T_DESC", "RES_ID_RESP_UNO",
            "RES_ID_RESP_DOS", "C_TIPOINCOMP", "T_MENSAJE"
        ]
        rows = [
            (ci.ID_CFGINCOMPADI, ci.T_DESC, ci.RES_ID_RESP_UNO,
             ci.RES_ID_RESP_DOS, ci.C_TIPOINCOMP, ci.T_MENSAJE)
            for ci in cfg_incompat
        ]
        write_json_from_query(zipf, "IA_CFGINCOMPADI.json", cols, rows)

        # 34. ReglaEIPD (IA_CFGREGLASEIPD)
        reglas_eipd = session.query(ReglaEIPD).all()
        cols = [
            "ID_REGLA", "C_CODIGO", "D_REGLA", "T_EXPRESION",
            "V_RESULTADO", "N_ORDEN", "L_ACTIVA", "L_EXCLUYENTE", "T_NOTAS"
        ]
        rows = [
            (re.ID_REGLA, re.C_CODIGO, re.D_REGLA, re.T_EXPRESION,
             re.V_RESULTADO, re.N_ORDEN, re.L_ACTIVA, re.L_EXCLUYENTE, re.T_NOTAS)
            for re in reglas_eipd
        ]
        write_json_from_query(zipf, "IA_CFGREGLASEIPD.json", cols, rows)

        # 35. ConfiguracionVisibilidad (IA_CFGVISIBILIDAD)
        cfg_visib = session.query(ConfiguracionVisibilidad).all()
        cols = [
            "ID_CFGVISIBILIDAD", "C_FORMULARIO", "C_ELEMENTO_ID", "C_TIPO_ELEM",
            "T_CONDICION", "C_ACCION", "N_PRIORIDAD", "T_DESCRIPCION", "L_ACTIVO"
        ]
        rows = [
            (cv.ID_CFGVISIBILIDAD, cv.C_FORMULARIO, cv.C_ELEMENTO_ID, cv.C_TIPO_ELEM,
             cv.T_CONDICION, cv.C_ACCION, cv.N_PRIORIDAD, cv.T_DESCRIPCION, cv.L_ACTIVO)
            for cv in cfg_visib
        ]
        write_json_from_query(zipf, "IA_CFGVISIBILIDAD.json", cols, rows)

        # 36. ConfiguracionRequisito (IA_CFGREQUISITOS)
        cfg_req = session.query(ConfiguracionRequisito).all()
        cols = [
            "ID_REQ", "C_REQUISITO", "D_REQUISITO", "T_DESCRIPCION",
            "L_APLICAOBLIG", "T_BASENORMATIVA", "L_ESTADO", "N_ORDVISU",
            "N_FASEVISUAL", "N_FASEVALPLANIF", "N_FASEVALCUMPL"
        ]
        rows = [
            (cr.ID_REQ, cr.C_REQUISITO, cr.D_REQUISITO, cr.T_DESCRIPCION,
             cr.L_APLICAOBLIG, cr.T_BASENORMATIVA, cr.L_ESTADO, cr.N_ORDVISU,
             cr.N_FASEVISUAL, cr.N_FASEVALPLANIF, cr.N_FASEVALCUMPL)
            for cr in cfg_req
        ]
        write_json_from_query(zipf, "IA_CFGREQUISITOS.json", cols, rows)

        # 37. ConfiguracionEstadoRequisito (IA_CFGESTREQ)
        cfg_est_req = session.query(ConfiguracionEstadoRequisito).all()
        cols = [
            "ID_ESTREQ", "C_ESTADO", "D_ESTADO", "T_DESCRIPCION",
            "C_TIPOESTADO", "N_ORDVISU", "L_AVANCEFASE", "L_JUSTOBLIG",
            "L_INICIAL", "L_NOAPLICA"
        ]
        rows = [
            (cer.ID_ESTREQ, cer.C_ESTADO, cer.D_ESTADO, cer.T_DESCRIPCION,
             cer.C_TIPOESTADO, cer.N_ORDVISU, cer.L_AVANCEFASE, cer.L_JUSTOBLIG,
             cer.L_INICIAL, cer.L_NOAPLICA)
            for cer in cfg_est_req
        ]
        write_json_from_query(zipf, "IA_CFGESTREQ.json", cols, rows)

        # 38. ConfiguracionRequisitoControl (IA_CFGREQCONTR)
        cfg_req_ctrl = session.query(ConfiguracionRequisitoControl).all()
        cols = ["ID_REQCONTR", "REQ_ID_REQU", "REQ_ID_CONTROL"]
        rows = [
            (crc.ID_REQCONTR, crc.REQ_ID_REQU, crc.REQ_ID_CONTROL)
            for crc in cfg_req_ctrl
        ]
        write_json_from_query(zipf, "IA_CFGREQCONTR.json", cols, rows)

        # 39. ConfiguracionCluster (IA_CFGCLUSTERS)
        cfg_clusters = session.query(ConfiguracionCluster).all()
        cols = [
            "ID_CLUSTER", "C_CLUSTER", "D_CLUSTER", "T_DESCRIPCION",
            "N_UMBRAL", "N_ORDVISU", "L_ESTADO"
        ]
        rows = [
            (cc.ID_CLUSTER, cc.C_CLUSTER, cc.D_CLUSTER, cc.T_DESCRIPCION,
             cc.N_UMBRAL, cc.N_ORDVISU, cc.L_ESTADO)
            for cc in cfg_clusters
        ]
        write_json_from_query(zipf, "IA_CFGCLUSTERS.json", cols, rows)

        # 40. ConfiguracionRiesgoCluster (IA_CFGRIESCLUSTER)
        cfg_ries_cluster = session.query(ConfiguracionRiesgoCluster).all()
        cols = ["ID_RIESCLUSTER", "RIE_ID_RIESGO", "CLU_ID_CLUSTER"]
        rows = [
            (crc.ID_RIESCLUSTER, crc.RIE_ID_RIESGO, crc.CLU_ID_CLUSTER)
            for crc in cfg_ries_cluster
        ]
        write_json_from_query(zipf, "IA_CFGRIESCLUSTER.json", cols, rows)

        # 41. ConfiguracionRiesgoGlobal (IA_CFGRIESGLOBAL)
        cfg_ries_global = session.query(ConfiguracionRiesgoGlobal).all()
        cols = [
            "ID_CFGRIESGLOBAL", "C_PARAMETRO", "C_GRUPO", "D_PARAMETRO",
            "N_VALOR", "T_VALOR", "C_COLOR", "L_BLOQUEAFASE",
            "T_MENSAJE", "N_ORDVISU", "L_ESTADO"
        ]
        rows = [
            (crg.ID_CFGRIESGLOBAL, crg.C_PARAMETRO, crg.C_GRUPO, crg.D_PARAMETRO,
             crg.N_VALOR, crg.T_VALOR, crg.C_COLOR, crg.L_BLOQUEAFASE,
             crg.T_MENSAJE, crg.N_ORDVISU, crg.L_ESTADO)
            for crg in cfg_ries_global
        ]
        write_json_from_query(zipf, "IA_CFGRIESGLOBAL.json", cols, rows)

    session.close()

    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=nombre_zip
    )
