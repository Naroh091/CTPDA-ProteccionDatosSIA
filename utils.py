
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

from models import Session, ValoresDato, TiposDato
from sqlalchemy import and_
import config


def get_valor_actual_verbd():
    """
    Recupera el único registro de la tabla IA_VALDAT que cumple con las siguientes condiciones:
    - Su tipo de dato (IA_TIPDAT) tiene el código 'VERBD'.
    - Su valor textual (C_VALOR_TEXT) es 'ACTUAL'.

    Returns:
        str: El valor D_VALOR del registro que coincide con la búsqueda.
        Retorna config.VERSION_BD_INICIAL si no se encuentra ningún registro.
    """
    db_session = Session()
    try:
        # Realiza una consulta uniendo las tablas ValoresDato y TiposDato.
        # Filtra por el código del tipo de dato y el valor textual del dato.
        registro = db_session.query(ValoresDato)\
            .join(TiposDato)\
            .filter(
                and_(
                    TiposDato.C_TIPDAT == 'VERBD',
                    ValoresDato.C_VALOR_TEXT == 'ACTUAL'  # Corregido: era C_VALOR, debe ser C_VALOR_TEXT
                )
            )\
            .first()  # Usa .first() para obtener un único resultado o None.

        if registro is None:
            version_db = config.VERSION_BD_INICIAL
        else:
            version_db = registro.D_VALOR

        return version_db
    finally:
        db_session.close()
