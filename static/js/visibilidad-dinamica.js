
/**
 * Aplicación para la protección de datos en Sistemas IA
 * Copyright (C) 2025-2026 Consejo de Transparencia y Protección de Datos de Andalucía
 *
 *
 * Este programa se distribuye bajo la Licencia Pública de la Unión Europea,
 * versión 1.2 (EUPL v1.2), disponible en:
 * https://eupl.eu/1.2/es/
 *
 * Este programa se distribuye con la esperanza de que sea útil,
 * pero SIN NINGUNA GARANTÍA; sin siquiera la garantía implícita de
 * COMERCIABILIDAD o APTITUD PARA UN PROPÓSITO PARTICULAR.
 * Consulte el texto completo de la licencia en el archivo LICENCIA.txt.
 */

/**
 * Sistema de Visibilidad Dinámica para SupervisionSIA v2.0
 *
 * OPTIMIZADO: Misma filosofía que ayuda-contextual.js
 * - UNA sola petición para obtener todas las reglas del formulario
 * - Procesa SOLO los elementos definidos en la BD
 * - Usa selectores CSS eficientes para prefijos ([id^="prefijo"])
 * - Sin delay: respuestas ADI vienen directamente del servidor
 */
(function() {
    'use strict';

    const configCache = {};
    let respuestasADI = {};

    /**
     * Obtener el nombre del formulario actual.
     */
    function obtenerFormularioActual() {
        const bodyFormulario = document.body.dataset.formulario;
        if (bodyFormulario) {
            return bodyFormulario;
        }

        const path = window.location.pathname;

        const matchFormulario = path.match(/\/formulario\/([^\/]+)/);
        if (matchFormulario) {
            return `formulario_${matchFormulario[1]}`;
        }

        const urlMap = {
            '/ayuda': 'ayuda_base',
            '/manual_uso': 'formulario_manual_uso',
            '/editar_documento': 'editar_documento',
            '/seleccion_proyecto': 'seleccion_proyecto',
            '/proyectos': 'seleccion_proyecto',
            '/inicio': 'inicio',
            '/': 'index'
        };

        if (urlMap[path]) {
            return urlMap[path];
        }

        const segments = path.split('/').filter(s => s.length > 0);
        if (segments.length > 0 && segments[0].length > 3) {
            return segments[0];
        }

        return 'index';
    }

    /**
     * Cargar configuraciones de visibilidad desde el servidor.
     * UNA sola petición por formulario (cacheada).
     */
    async function cargarConfiguraciones(formulario) {
        if (configCache[formulario]) {
            return configCache[formulario];
        }

        try {
            const response = await fetch(`/api/visibilidad/config/${formulario}`);

            if (!response.ok) {
                configCache[formulario] = [];
                return [];
            }

            const configs = await response.json();
            configCache[formulario] = configs;
            return configs;

        } catch (error) {
            return [];
        }
    }

    /**
     * Evaluar una condición JavaScript de forma segura.
     */
    function evaluarCondicion(condicion, respuestas) {
        try {
            const evaluador = new Function('respuestas', `
                'use strict';
                try {
                    return ${condicion};
                } catch (e) {
                    return false;
                }
            `);
            return evaluador(respuestas) === true;
        } catch (error) {
            return false;
        }
    }

    /**
     * OPTIMIZADO: Buscar elementos usando selectores CSS eficientes.
     * - Para prefijos: usa [id^="prefijo"] (muy eficiente)
     * - Para IDs exactos: usa getElementById (lo más rápido)
     */
    function buscarElementos(elementoId) {
        // Si termina en '-', es un prefijo
        if (elementoId.endsWith('-')) {
            // OPTIMIZADO: Usar selector CSS de prefijo en lugar de iterar todo el DOM
            const prefijo = elementoId.slice(0, -1); // Quitar el '-' final
            return Array.from(document.querySelectorAll(`[id^="${prefijo}-"]`));
        } else {
            // ID exacto: getElementById es lo más rápido
            const elem = document.getElementById(elementoId);
            return elem ? [elem] : [];
        }
    }

    /**
     * Aplicar acción sobre elementos.
     * Sistema de reversión inteligente: solo revierte cambios propios.
     */
    function aplicarAccionAElementos(elementos, accion, aplicar) {
        elementos.forEach(elemento => {
            switch(accion.toLowerCase()) {
                case 'ocultar':
                    if (aplicar) {
                        if (!elemento.dataset.displayOriginal) {
                            elemento.dataset.displayOriginal = elemento.style.display || '';
                        }
                        elemento.style.display = 'none';
                        elemento.dataset.ocultoDinamico = 'true';
                    } else if (elemento.dataset.ocultoDinamico === 'true') {
                        elemento.style.display = elemento.dataset.displayOriginal || '';
                        delete elemento.dataset.ocultoDinamico;
                        delete elemento.dataset.displayOriginal;
                    }
                    break;

                case 'mostrar':
                    if (aplicar) {
                        elemento.style.display = elemento.dataset.displayOriginal || '';
                        delete elemento.dataset.ocultoDinamico;
                        elemento.dataset.mostradoDinamico = 'true';
                    } else if (elemento.dataset.mostradoDinamico === 'true') {
                        elemento.style.display = 'none';
                        delete elemento.dataset.mostradoDinamico;
                    }
                    break;

                case 'deshabilitar':
                    if (aplicar) {
                        if (elemento.dataset.deshabilitadoDinamico !== 'true') {
                            elemento.dataset.disabledOriginal = elemento.disabled ? 'true' : 'false';
                        }
                        elemento.disabled = true;
                        elemento.classList.add('disabled');
                        elemento.dataset.deshabilitadoDinamico = 'true';
                    } else if (elemento.dataset.deshabilitadoDinamico === 'true') {
                        elemento.disabled = elemento.dataset.disabledOriginal === 'true';
                        elemento.classList.remove('disabled');
                        delete elemento.dataset.deshabilitadoDinamico;
                    }
                    break;

                case 'habilitar':
                    if (aplicar) {
                        elemento.disabled = false;
                        elemento.classList.remove('disabled');
                        elemento.dataset.habilitadoDinamico = 'true';
                    } else if (elemento.dataset.habilitadoDinamico === 'true') {
                        elemento.disabled = true;
                        delete elemento.dataset.habilitadoDinamico;
                    }
                    break;
            }
        });
    }

    /**
     * FUNCIÓN PRINCIPAL - VERSIÓN OPTIMIZADA
     * Misma filosofía que ayuda-contextual.js:
     * 1. Una petición para obtener todas las reglas
     * 2. Iterar SOLO sobre las reglas de la BD
     * 3. Buscar elementos específicos para cada regla
     */
    async function aplicarConfiguraciones() {
        const startTime = performance.now();
        const formulario = obtenerFormularioActual();

        // Obtener respuestas ADI del objeto global (cargado desde servidor)
        respuestasADI = window.respuestasADI || {};

        if (Object.keys(respuestasADI).length === 0) {
            return;
        }

        // PASO 1: Obtener TODAS las reglas del formulario en UNA petición
        const configs = await cargarConfiguraciones(formulario);

        if (configs.length === 0) {
            return;
        }

        // Ordenar por prioridad
        configs.sort((a, b) => (a.prioridad || 100) - (b.prioridad || 100));

        // PASO 2: Para cada regla, buscar los elementos y aplicar acción
        let reglasAplicadas = 0;
        let elementosAfectados = 0;

        for (const config of configs) {
            if (!config.l_activo) continue;

            const condicionCumplida = evaluarCondicion(config.condicion, respuestasADI);
            const elementos = buscarElementos(config.elemento_id);

            if (elementos.length > 0) {
                aplicarAccionAElementos(elementos, config.accion, condicionCumplida);

                if (condicionCumplida) {
                    reglasAplicadas++;
                    elementosAfectados += elementos.length;
                }
            }
        }

        const endTime = performance.now();
        const tiempoTotal = (endTime - startTime).toFixed(0);

    }

    /**
     * Inicializar sistema.
     */
    function inicializar() {
        // Ejecutar inmediatamente - respuestas ya están cargadas del servidor
        aplicarConfiguraciones();
    }

    // Inicializar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', inicializar);
    } else {
        inicializar();
    }

    // API pública
    window.VisibilidadDinamica = {
        actualizar: aplicarConfiguraciones,
        evaluarCondicion: (condicion) => evaluarCondicion(condicion, respuestasADI),
        getFormularioActual: obtenerFormularioActual,
        limpiarCache: () => {
            Object.keys(configCache).forEach(key => delete configCache[key]);
        }
    };


})();
