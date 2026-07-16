
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
 * Sistema de ayuda contextual para SupervisionSIA v3.0 - OPTIMIZADO
 *
 * CAMBIO PRINCIPAL v3.0:
 * En lugar de escanear todo el DOM y consultar elemento por elemento,
 * ahora se obtienen TODAS las ayudas del formulario en una sola petición
 * y luego se buscan los elementos correspondientes en el DOM.
 * Esto reduce drásticamente el tiempo de carga.
 *
 * - Añade iconos de ayuda verdes solo donde hay contenido
 * - Click en icono muestra tooltip estilo modal (TIPO C)
 * - Modal arrastrable y redimensionable
 * - Solo se cierra con la X
 * - Guarda posición y tamaño por cada ayuda
 * - TIPO I: Ayuda inline con collapse
 * - TIPO T: Ayuda como tooltip al pasar el cursor
 */
(function() {
    'use strict';

    let tooltipTimer = null;
    let currentTooltip = null;
    let tooltipActivo = false;
    let currentAyudaId = null; // ID de la ayuda actual para guardar posición
    let posicionModificada = false; // Flag para saber si se movió o redimensionó
    const DELAY_MS = 1500;
    const ayudasDisponibles = {}; // Cache de ayudas

    // Variables para tooltip tipo T
    let currentTooltipT = null;
    let tooltipTTimerShow = null;  // Timer para mostrar
    let tooltipTTimerHide = null;  // Timer para ocultar (separado)
    const TOOLTIP_T_DELAY_SHOW = 200; // ms antes de mostrar
    const TOOLTIP_T_DELAY_HIDE = 100; // ms antes de ocultar

    // Obtener el nombre del formulario actual
    function obtenerFormularioActual() {
        // 1. Primero intentar obtener del atributo data-formulario en body
        const bodyFormulario = document.body.dataset.formulario;
        if (bodyFormulario) {
            return bodyFormulario;
        }

        // 2. Si no, intentar detectar desde la URL
        const path = window.location.pathname;

        // 3. Intentar detectar formulario con patrón /formulario/{nombre}
        const matchFormulario = path.match(/\/formulario\/([^\/]+)/);
        if (matchFormulario) {
            const formulario = `formulario_${matchFormulario[1]}`;
            return formulario;
        }

        // 4. Detectar páginas especiales por path completo
        const urlMap = {
            '/ayuda': 'ayuda_base',
            '/manual_uso': 'formulario_manual_uso',
            '/editar_documento': 'editar_documento',
            '/seleccion_proyecto': 'seleccion_proyecto',
            '/proyectos': 'seleccion_proyecto',
            '/inicio': 'inicio',
            '/': 'index'
        };

        // Intentar coincidencia exacta
        if (urlMap[path]) {
            return urlMap[path];
        }

        // 5. Detectar por segmentos de URL
        const segments = path.split('/').filter(s => s.length > 0);

        if (segments.length > 0) {
            const firstSegment = segments[0];

            for (const [url, formulario] of Object.entries(urlMap)) {
                if (url.includes(firstSegment) && firstSegment.length > 0) {
                    return formulario;
                }
            }

            if (firstSegment.length > 3) {
                return firstSegment;
            }
        }

        return 'index';
    }

    // =========================================================================
    // NUEVA FUNCIÓN: Obtener todas las ayudas del formulario en una sola petición
    // =========================================================================
    async function obtenerTodasLasAyudas(formulario) {
        const startTime = performance.now();

        try {
            // Intentar primero con el formulario tal cual
            let response = await fetch(`/api/ayuda-contexto/formulario/${formulario}`);
            let data = await response.json();

            // DEBUG: Ver qué devuelve el servidor
            if (data.ayudas && data.ayudas.length > 0) {
            }

            // Si no encontró ayudas y el formulario NO empieza con "formulario_", reintentar
            if ((!data.success || !data.ayudas || data.ayudas.length === 0) && !formulario.startsWith('formulario_')) {
                const formularioConPrefijo = `formulario_${formulario}`;
                response = await fetch(`/api/ayuda-contexto/formulario/${formularioConPrefijo}`);
                data = await response.json();
            }

            const endTime = performance.now();

            if (data.success && data.ayudas) {
                return data.ayudas;
            } else {
                return [];
            }
        } catch (error) {
            return [];
        }
    }

    // Cargar posición guardada del modal
    function cargarPosicionGuardada(ayudaData, tooltip, elemento) {

        const tienePos_X = ayudaData.pos_x !== null && ayudaData.pos_x !== undefined && typeof ayudaData.pos_x === 'number';
        const tienePos_Y = ayudaData.pos_y !== null && ayudaData.pos_y !== undefined && typeof ayudaData.pos_y === 'number';
        const tieneWidth = ayudaData.width !== null && ayudaData.width !== undefined && typeof ayudaData.width === 'number' && ayudaData.width > 0;
        const tieneHeight = ayudaData.height !== null && ayudaData.height !== undefined && typeof ayudaData.height === 'number' && ayudaData.height > 0;

        if (!tienePos_X || !tienePos_Y || !tieneWidth || !tieneHeight) {
            return false;
        }


        const maxWidth = window.innerWidth - 50;
        const maxHeight = window.innerHeight - 50;

        let width = Math.min(ayudaData.width, maxWidth);
        let height = Math.min(ayudaData.height, maxHeight);

        width = Math.max(width, 300);
        height = Math.max(height, 100);

        let posX = ayudaData.pos_x;
        let posY = ayudaData.pos_y;

        if (posX + width > window.innerWidth) {
            posX = window.innerWidth - width - 10;
        }

        if (posY + height > window.innerHeight) {
            posY = window.innerHeight - height - 10;
        }

        if (posX < 0) posX = 10;
        if (posY < 0) posY = 10;

        tooltip.style.position = 'fixed';
        tooltip.style.left = posX + 'px';
        tooltip.style.top = posY + 'px';
        tooltip.style.width = width + 'px';
        tooltip.style.height = height + 'px';
        tooltip.style.zIndex = '10000';
        tooltip.style.minWidth = '300px';
        tooltip.style.minHeight = '100px';

        return true;
    }

    // Guardar posición y tamaño del modal
    async function guardarPosicionTamaño(tooltip) {

        if (!currentAyudaId) {
            return;
        }

        const rect = tooltip.getBoundingClientRect();

        const nuevaPosicion = {
            pos_x: Math.round(tooltip.offsetLeft),
            pos_y: Math.round(tooltip.offsetTop),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            screen_width: window.innerWidth
        };

        const datos = {
            id: currentAyudaId,
            ...nuevaPosicion
        };


        try {
            const response = await fetch('/api/ayuda-contexto/guardar-posicion', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(datos)
            });

            const result = await response.json();
            if (result.success) {

                // IMPORTANTE: Actualizar el caché Y los _ayudaData de los iconos
                // en lugar de invalidar (eliminar) el caché
                for (let cacheKey in ayudasDisponibles) {
                    if (ayudasDisponibles[cacheKey] && ayudasDisponibles[cacheKey].id === currentAyudaId) {
                        // Actualizar el caché con los nuevos valores
                        ayudasDisponibles[cacheKey].pos_x = nuevaPosicion.pos_x;
                        ayudasDisponibles[cacheKey].pos_y = nuevaPosicion.pos_y;
                        ayudasDisponibles[cacheKey].width = nuevaPosicion.width;
                        ayudasDisponibles[cacheKey].height = nuevaPosicion.height;
                        ayudasDisponibles[cacheKey].screen_width = nuevaPosicion.screen_width;
                        break;
                    }
                }

                // También actualizar el _ayudaData de todos los iconos con este ID
                document.querySelectorAll('.ayuda-icono').forEach(icono => {
                    if (icono._ayudaData && icono._ayudaData.id === currentAyudaId) {
                        icono._ayudaData.pos_x = nuevaPosicion.pos_x;
                        icono._ayudaData.pos_y = nuevaPosicion.pos_y;
                        icono._ayudaData.width = nuevaPosicion.width;
                        icono._ayudaData.height = nuevaPosicion.height;
                        icono._ayudaData.screen_width = nuevaPosicion.screen_width;
                    }
                });

            } else {
            }
        } catch (error) {
        }
    }

    // Crear tooltip estilo modal (TIPO C)
    function crearTooltip(ayudaData, elemento) {
        eliminarTooltip();

        posicionModificada = false;

        const tooltip = document.createElement('div');
        tooltip.className = 'ayuda-contextual-tooltip-modal';

        tooltip.innerHTML = `
            <div class="ayuda-modal-header">
                <h6 class="ayuda-modal-title">
                    <i class="bi bi-info-circle-fill me-2"></i>Ayuda
                </h6>
                <button type="button" class="ayuda-modal-close">
                    <i class="bi bi-x-lg"></i>
                </button>
            </div>
            <div class="ayuda-modal-body">
                ${ayudaData.ayuda}
            </div>
            <div class="ayuda-modal-resize-handle"></div>
        `;

        // DEBUG: Verificar que ayudaData tiene el ID

        currentAyudaId = ayudaData.id;

        const posicionCargada = cargarPosicionGuardada(ayudaData, tooltip, elemento);

        if (!posicionCargada) {
            const rect = elemento.getBoundingClientRect();
            tooltip.style.position = 'fixed';
            tooltip.style.left = `${rect.left}px`;
            tooltip.style.top = `${rect.bottom + 8}px`;
            tooltip.style.zIndex = '10000';
            tooltip.style.minWidth = '300px';
            tooltip.style.minHeight = '100px';
            tooltip.style.width = '400px';
            tooltip.style.height = '250px';
        }

        document.body.appendChild(tooltip);
        currentTooltip = tooltip;

        const btnCerrar = tooltip.querySelector('.ayuda-modal-close');
        btnCerrar.addEventListener('click', async function(e) {
            e.stopPropagation();
            if (posicionModificada) {
                await guardarPosicionTamaño(tooltip);
            }
            eliminarTooltip();
        });

        hacerArrastrable(tooltip);
        hacerRedimensionable(tooltip);

        if (!posicionCargada) {
            setTimeout(() => {
                const tooltipRect = tooltip.getBoundingClientRect();
                const rect = elemento.getBoundingClientRect();

                if (tooltipRect.right > window.innerWidth - 10) {
                    tooltip.style.left = `${window.innerWidth - tooltipRect.width - 10}px`;
                }
                if (tooltipRect.left < 10) {
                    tooltip.style.left = '10px';
                }

                if (tooltipRect.bottom > window.innerHeight - 10) {
                    tooltip.style.top = `${rect.top - tooltipRect.height - 8}px`;
                }
            }, 10);
        }
    }

    // Función para hacer el tooltip arrastrable
    function hacerArrastrable(tooltip) {
        const header = tooltip.querySelector('.ayuda-modal-header');
        let isDragging = false;
        let currentX;
        let currentY;
        let initialX;
        let initialY;

        header.addEventListener('mousedown', function(e) {
            if (e.target.closest('.ayuda-modal-close')) {
                return;
            }

            isDragging = true;
            initialX = e.clientX - tooltip.offsetLeft;
            initialY = e.clientY - tooltip.offsetTop;

            header.classList.add('grabbing');
            e.preventDefault();
        });

        document.addEventListener('mousemove', function(e) {
            if (isDragging) {
                e.preventDefault();
                currentX = e.clientX - initialX;
                currentY = e.clientY - initialY;

                const maxX = window.innerWidth - tooltip.offsetWidth;
                const maxY = window.innerHeight - tooltip.offsetHeight;

                currentX = Math.max(0, Math.min(currentX, maxX));
                currentY = Math.max(0, Math.min(currentY, maxY));

                tooltip.style.left = currentX + 'px';
                tooltip.style.top = currentY + 'px';

                posicionModificada = true;
            }
        });

        document.addEventListener('mouseup', function() {
            if (isDragging) {
                isDragging = false;
                header.classList.remove('grabbing');
            }
        });
    }

    // Función para hacer el tooltip redimensionable
    function hacerRedimensionable(tooltip) {
        const bordes = ['top', 'right', 'bottom', 'left', 'top-left', 'top-right', 'bottom-left', 'bottom-right'];

        bordes.forEach(borde => {
            const resizer = document.createElement('div');
            resizer.className = `resize-handle-${borde}`;
            resizer.dataset.borde = borde;
            tooltip.appendChild(resizer);
        });

        let isResizing = false;
        let currentResizer = null;
        let startX, startY, startWidth, startHeight, startLeft, startTop;

        tooltip.querySelectorAll('[class^="resize-handle-"]').forEach(handle => {
            handle.addEventListener('mousedown', function(e) {
                isResizing = true;
                currentResizer = this.dataset.borde;
                startX = e.clientX;
                startY = e.clientY;
                startWidth = tooltip.offsetWidth;
                startHeight = tooltip.offsetHeight;
                startLeft = tooltip.offsetLeft;
                startTop = tooltip.offsetTop;
                e.preventDefault();
            });
        });

        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;

            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            const minWidth = 300;
            const minHeight = 100;

            switch(currentResizer) {
                case 'right':
                    tooltip.style.width = Math.max(minWidth, startWidth + dx) + 'px';
                    break;
                case 'left':
                    {
                        const newWidth = Math.max(minWidth, startWidth - dx);
                        if (newWidth > minWidth) {
                            tooltip.style.width = newWidth + 'px';
                            tooltip.style.left = (startLeft + dx) + 'px';
                        }
                    }
                    break;
                case 'bottom':
                    tooltip.style.height = Math.max(minHeight, startHeight + dy) + 'px';
                    break;
                case 'top':
                    {
                        const newHeight = Math.max(minHeight, startHeight - dy);
                        if (newHeight > minHeight) {
                            tooltip.style.height = newHeight + 'px';
                            tooltip.style.top = (startTop + dy) + 'px';
                        }
                    }
                    break;
                case 'bottom-right':
                    {
                        const newWidth = Math.max(minWidth, startWidth + dx);
                        const newHeight = Math.max(minHeight, startHeight + dy);
                        tooltip.style.width = newWidth + 'px';
                        tooltip.style.height = newHeight + 'px';
                    }
                    break;
                case 'bottom-left':
                    {
                        const newWidth = Math.max(minWidth, startWidth - dx);
                        const newHeight = Math.max(minHeight, startHeight + dy);
                        if (newWidth > minWidth) {
                            tooltip.style.width = newWidth + 'px';
                            tooltip.style.left = (startLeft + dx) + 'px';
                        }
                        tooltip.style.height = newHeight + 'px';
                    }
                    break;
                case 'top-right':
                    {
                        const newWidth = Math.max(minWidth, startWidth + dx);
                        const newHeight = Math.max(minHeight, startHeight - dy);
                        tooltip.style.width = newWidth + 'px';
                        if (newHeight > minHeight) {
                            tooltip.style.height = newHeight + 'px';
                            tooltip.style.top = (startTop + dy) + 'px';
                        }
                    }
                    break;
                case 'top-left':
                    {
                        const newWidth = Math.max(minWidth, startWidth - dx);
                        const newHeight = Math.max(minHeight, startHeight - dy);
                        if (newWidth > minWidth) {
                            tooltip.style.width = newWidth + 'px';
                            tooltip.style.left = (startLeft + dx) + 'px';
                        }
                        if (newHeight > minHeight) {
                            tooltip.style.height = newHeight + 'px';
                            tooltip.style.top = (startTop + dy) + 'px';
                        }
                    }
                    break;
            }

            posicionModificada = true;
        });

        document.addEventListener('mouseup', function() {
            if (isResizing) {
                isResizing = false;
                currentResizer = null;
            }
        });
    }

    // Eliminar tooltip actual (TIPO C)
    function eliminarTooltip() {
        if (currentTooltip) {
            currentTooltip.remove();
            currentTooltip = null;
            tooltipActivo = false;
            currentAyudaId = null;
            posicionModificada = false;
        }
    }

    // =========================================================================
    // TIPO T: TOOLTIP AL PASAR EL CURSOR
    // =========================================================================

    function crearTooltipT(ayudaData, elemento) {
        eliminarTooltipT();

        const tooltip = document.createElement('div');
        tooltip.className = 'ayuda-tooltip-t';
        tooltip.innerHTML = ayudaData.ayuda;

        document.body.appendChild(tooltip);
        currentTooltipT = tooltip;

        posicionarTooltipT(tooltip, elemento);

        requestAnimationFrame(() => {
            tooltip.classList.add('ayuda-tooltip-t-visible');
        });

    }

    function posicionarTooltipT(tooltip, elemento) {
        const rect = elemento.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();

        let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
        let top = rect.top - tooltipRect.height - 8;

        let arrowPosition = 'bottom';

        if (top < 10) {
            top = rect.bottom + 8;
            arrowPosition = 'top';
        }

        if (left + tooltipRect.width > window.innerWidth - 10) {
            left = window.innerWidth - tooltipRect.width - 10;
        }

        if (left < 10) {
            left = 10;
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;

        tooltip.classList.remove('arrow-top', 'arrow-bottom');
        tooltip.classList.add(`arrow-${arrowPosition}`);
    }

    function eliminarTooltipT(inmediato = false) {
        if (tooltipTTimerHide) {
            clearTimeout(tooltipTTimerHide);
            tooltipTTimerHide = null;
        }

        if (currentTooltipT) {
            if (inmediato) {
                currentTooltipT.remove();
                currentTooltipT = null;
            } else {
                currentTooltipT.classList.remove('ayuda-tooltip-t-visible');
                const tooltipToRemove = currentTooltipT;
                currentTooltipT = null;
                setTimeout(() => {
                    if (tooltipToRemove && tooltipToRemove.parentNode) {
                        tooltipToRemove.remove();
                    }
                }, 150);
            }
        }
    }

    function configurarTooltipT(elemento, ayudaData) {
        elemento.classList.add('tiene-ayuda-tooltip-t');
        elemento._ayudaDataT = ayudaData;

        elemento.addEventListener('mouseenter', function(e) {
            if (tooltipTTimerHide) {
                clearTimeout(tooltipTTimerHide);
                tooltipTTimerHide = null;
            }

            if (tooltipTTimerShow) {
                clearTimeout(tooltipTTimerShow);
            }

            const self = this;
            tooltipTTimerShow = setTimeout(() => {
                eliminarTooltipT(true);
                crearTooltipT(self._ayudaDataT, self);
                tooltipTTimerShow = null;
            }, TOOLTIP_T_DELAY_SHOW);
        });

        elemento.addEventListener('mouseleave', function(e) {
            if (tooltipTTimerShow) {
                clearTimeout(tooltipTTimerShow);
                tooltipTTimerShow = null;
            }

            tooltipTTimerHide = setTimeout(() => {
                eliminarTooltipT(false);
                tooltipTTimerHide = null;
            }, TOOLTIP_T_DELAY_HIDE);
        });

        elemento.addEventListener('focus', function(e) {
            if (tooltipTTimerHide) {
                clearTimeout(tooltipTTimerHide);
                tooltipTTimerHide = null;
            }
            if (tooltipTTimerShow) {
                clearTimeout(tooltipTTimerShow);
                tooltipTTimerShow = null;
            }
            eliminarTooltipT(true);
            crearTooltipT(this._ayudaDataT, this);
        });

        elemento.addEventListener('blur', function(e) {
            if (tooltipTTimerShow) {
                clearTimeout(tooltipTTimerShow);
                tooltipTTimerShow = null;
            }
            eliminarTooltipT(false);
        });

    }

    // =========================================================================
    // FIN TIPO T
    // =========================================================================

    // Obtener ayuda del servidor (para uso individual, ej: al hacer click)
    async function obtenerAyuda(formulario, control) {
        const cacheKey = `${formulario}_${control}`;

        if (ayudasDisponibles[cacheKey] !== undefined) {
            return ayudasDisponibles[cacheKey];
        }

        try {
            const response = await fetch(`/api/ayuda-contexto/${formulario}/${control}`);
            const data = await response.json();

            if (data.success && data.ayuda) {
                ayudasDisponibles[cacheKey] = data;
                return data;
            } else {
                if (!formulario.startsWith('formulario_')) {
                    const formularioConPrefijo = `formulario_${formulario}`;
                    const cacheKeyConPrefijo = `${formularioConPrefijo}_${control}`;


                    const response2 = await fetch(`/api/ayuda-contexto/${formularioConPrefijo}/${control}`);
                    const data2 = await response2.json();

                    if (data2.success && data2.ayuda) {
                        ayudasDisponibles[cacheKeyConPrefijo] = data2;
                        ayudasDisponibles[cacheKey] = data2;
                        return data2;
                    }
                }

                ayudasDisponibles[cacheKey] = null;
                return null;
            }
        } catch (error) {
            ayudasDisponibles[cacheKey] = null;
            return null;
        }
    }

    // Crear elemento inline con collapse para ayuda tipo I
    function crearElementoInline(elemento, ayudaData) {
        const collapseId = `collapse-${ayudaData.id}`;
        const titulo = elemento.dataset.ayudaTitulo || '';
        const iniciarColapsado = elemento.dataset.ayudaCollapsed === 'true';

        const ariaExpanded = iniciarColapsado ? 'false' : 'true';
        const headerCollapsedClass = iniciarColapsado ? 'collapsed' : '';
        const collapseShowClass = iniciarColapsado ? '' : 'show';

        const inlineContainer = document.createElement('div');
        inlineContainer.className = 'ayuda-inline-container mb-3';

        inlineContainer.innerHTML = `
            <div class="card border-info">
                <div class="card-header bg-info bg-opacity-10 py-2 ${headerCollapsedClass}" style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${ariaExpanded}" aria-controls="${collapseId}">
                    <div class="d-flex align-items-center">
                        <i class="bi bi-chevron-down text-info me-2"></i>
                        <i class="bi bi-info-circle-fill me-2"></i>
                        ${titulo ? `<span class="text-info fw-semibold">${titulo}</span>` : ''}
                    </div>
                </div>
                <div class="collapse ${collapseShowClass}" id="${collapseId}">
                    <div class="card-body bg-light ayuda-inline-content">
                        ${ayudaData.ayuda}
                    </div>
                </div>
            </div>
        `;

        elemento.insertAdjacentElement('afterend', inlineContainer);

        const header = inlineContainer.querySelector('[data-bs-toggle="collapse"]');
        const chevron = inlineContainer.querySelector('.bi-chevron-down');
        const collapseElement = inlineContainer.querySelector(`#${collapseId}`);

        if (iniciarColapsado) {
            chevron.style.transform = 'rotate(-90deg)';
        }

        if (collapseElement) {
            collapseElement.addEventListener('show.bs.collapse', function() {
                chevron.style.transform = 'rotate(0deg)';
                header.setAttribute('aria-expanded', 'true');
                header.classList.remove('collapsed');
            });

            collapseElement.addEventListener('hide.bs.collapse', function() {
                chevron.style.transform = 'rotate(-90deg)';
                header.setAttribute('aria-expanded', 'false');
                header.classList.add('collapsed');
            });
        }

    }

    // Crear icono de ayuda (TIPO C)
    function crearIconoAyuda(elemento, control, ayudaData) {
        const icono = document.createElement('i');
        icono.className = 'bi bi-info-circle text-primary ayuda-icono';
        icono.dataset.control = control;
        icono.title = 'Click para ver ayuda';
        icono.style.cursor = 'pointer';
        icono.style.marginLeft = '5px';

        // Guardar los datos de ayuda en el icono para acceso rápido
        icono._ayudaData = ayudaData;

        icono.addEventListener('click', async function(e) {
            e.stopPropagation();


            // Si tenemos los datos guardados, usarlos directamente
            if (this._ayudaData) {
                crearTooltip(this._ayudaData, this);
                tooltipActivo = true;
            } else {
                // Fallback: obtener del servidor
                const formulario = obtenerFormularioActual();
                const cacheKey = `${formulario}_${control}`;
                delete ayudasDisponibles[cacheKey];

                const ayudaDataFresh = await obtenerAyuda(formulario, control);
                if (ayudaDataFresh) {
                    crearTooltip(ayudaDataFresh, this);
                    tooltipActivo = true;
                }
            }
        });

        return icono;
    }

    // =========================================================================
    // NUEVA FUNCIÓN: Aplicar ayuda a un elemento específico
    // =========================================================================
    function aplicarAyudaAElemento(elemento, ayudaData) {
        const control = ayudaData.control;

        if (ayudaData.tipo === 'C') {
            // TIPO C: Ayuda contextual con modal
            const icono = crearIconoAyuda(elemento, control, ayudaData);

            if (elemento.tagName === 'TH') {
                elemento.appendChild(document.createTextNode(' '));
                elemento.appendChild(icono);
            } else if (elemento.tagName === 'TR') {
                const primeraCelda = elemento.querySelector('td:first-child');
                if (primeraCelda) {
                    const boton = primeraCelda.querySelector('button');
                    const divBoton = primeraCelda.querySelector('div.mt-2, div:has(button)');

                    if (boton && divBoton) {
                        const espacio = document.createTextNode(' ');
                        primeraCelda.insertBefore(espacio, divBoton);
                        primeraCelda.insertBefore(icono, divBoton);
                    } else {
                        primeraCelda.appendChild(document.createTextNode(' '));
                        primeraCelda.appendChild(icono);
                    }
                }
            } else {
                elemento.style.position = 'relative';
                elemento.appendChild(icono);
            }
        } else if (ayudaData.tipo === 'I') {
            // TIPO I: Ayuda inline con collapse
            crearElementoInline(elemento, ayudaData);
        } else if (ayudaData.tipo === 'T') {
            // TIPO T: Ayuda como tooltip al pasar el cursor
            configurarTooltipT(elemento, ayudaData);
        }

    }

    // =========================================================================
    // FUNCIÓN PRINCIPAL DE INICIALIZACIÓN - VERSIÓN OPTIMIZADA v3.1
    // v3.1: Corregido para aplicar ayudas a MÚLTIPLES elementos con el mismo control
    //       (ej: tablas dinámicas donde varias filas tienen el mismo grupo de control)
    // =========================================================================
    async function inicializar() {
        const startTime = performance.now();
        const formulario = obtenerFormularioActual();


        // PASO 1: Obtener TODAS las ayudas del formulario en UNA sola petición
        const ayudas = await obtenerTodasLasAyudas(formulario);

        if (ayudas.length === 0) {
            return;
        }

        // PASO 2: Para cada ayuda, buscar TODOS los elementos correspondientes en el DOM
        let ayudasAplicadas = 0;
        let elementosConAyuda = 0;

        for (const ayuda of ayudas) {
            const control = ayuda.control;

            // Cachear la ayuda
            const cacheKey = `${formulario}_${control}`;
            const ayudaData = {
                success: true,
                id: ayuda.id,
                tipo: ayuda.tipo,
                ayuda: ayuda.ayuda,
                control: ayuda.control,
                pos_x: ayuda.pos_x,
                pos_y: ayuda.pos_y,
                width: ayuda.width,
                height: ayuda.height,
                screen_width: ayuda.screen_width
            };
            ayudasDisponibles[cacheKey] = ayudaData;

            // Buscar TODOS los elementos en el DOM que coincidan
            // Usamos un array para recolectar todos los elementos encontrados
            let elementos = [];

            // 1. Buscar por ID exacto (solo puede haber uno)
            const elementoPorId = document.getElementById(control);
            if (elementoPorId) {
                elementos.push(elementoPorId);
            }

            // 2. Buscar TODOS los elementos por data-ayuda-control
            const elementosPorControl = document.querySelectorAll(`[data-ayuda-control="${control}"]`);
            elementosPorControl.forEach(el => {
                if (!elementos.includes(el)) {
                    elementos.push(el);
                }
            });

            // 3. Buscar TODOS los elementos por data-ayuda-inline
            const elementosPorInline = document.querySelectorAll(`[data-ayuda-inline="${control}"]`);
            elementosPorInline.forEach(el => {
                if (!elementos.includes(el)) {
                    elementos.push(el);
                }
            });

            // 4. Buscar TODOS los elementos por data-ayuda-tooltip
            const elementosPorTooltip = document.querySelectorAll(`[data-ayuda-tooltip="${control}"]`);
            elementosPorTooltip.forEach(el => {
                if (!elementos.includes(el)) {
                    elementos.push(el);
                }
            });

            // Aplicar la ayuda a TODOS los elementos encontrados
            if (elementos.length > 0) {
                ayudasAplicadas++;
                elementos.forEach(elemento => {
                    aplicarAyudaAElemento(elemento, ayudaData);
                    elementosConAyuda++;
                });

                if (elementos.length > 1) {
                }
            } else {
            }
        }

        const endTime = performance.now();
        const tiempoTotal = (endTime - startTime).toFixed(0);

    }

    // Inicializar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', inicializar);
    } else {
        inicializar();
    }

    // Limpiar al cerrar página
    window.addEventListener('beforeunload', function() {
        eliminarTooltip();
        if (tooltipTTimerShow) {
            clearTimeout(tooltipTTimerShow);
            tooltipTTimerShow = null;
        }
        if (tooltipTTimerHide) {
            clearTimeout(tooltipTTimerHide);
            tooltipTTimerHide = null;
        }
        eliminarTooltipT(true);
    });

    // =========================================================================
    // API PÚBLICA: Funciones expuestas para elementos dinámicos
    // =========================================================================

    /**
     * Procesa un elemento dinámico para añadirle ayuda contextual.
     * Útil para botones creados con JavaScript después de la inicialización.
     */
    async function procesarElementoDinamico(elemento, controlOverride) {
        if (typeof elemento === 'string') {
            elemento = document.querySelector(elemento);
        }

        if (!elemento) {
            return false;
        }

        const controlRaw = controlOverride ||
                          elemento.dataset.ayudaTooltip ||
                          elemento.dataset.ayudaControl ||
                          elemento.dataset.ayudaInline ||
                          elemento.id;

        if (!controlRaw) {
            return false;
        }

        const control = controlRaw.trim();
        const formulario = elemento.dataset.formularioManual || obtenerFormularioActual();


        const ayudaData = await obtenerAyuda(formulario, control);

        if (ayudaData) {

            if (ayudaData.tipo === 'C') {
                const icono = crearIconoAyuda(elemento, control, ayudaData);
                elemento.style.position = 'relative';
                elemento.appendChild(icono);
            } else if (ayudaData.tipo === 'I') {
                crearElementoInline(elemento, ayudaData);
            } else if (ayudaData.tipo === 'T') {
                configurarTooltipT(elemento, ayudaData);
            }
            return true;
        } else {
            return false;
        }
    }

    // Exponer API pública
    window.AyudaContextual = {
        procesar: procesarElementoDinamico,
        getFormularioActual: obtenerFormularioActual
    };

})();
