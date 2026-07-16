
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

/* ============================================================================
 * COMPONENTE JAVASCRIPT - RIESGO GLOBAL
 * Añadir a static/js/ o incluir en el template
 * ============================================================================ */

/**
 * Módulo para gestión del Riesgo Global
 */
const RiesgoGlobal = {

    sistemaId: null,
    ultimoCalculo: null,
    panelVisible: false,

    /**
     * Inicializa el componente de riesgo global
     * @param {number} sistemaId - ID del sistema actual
     */
    init: function(sistemaId) {
        this.sistemaId = sistemaId;
        this.cargarRiesgoGlobal();
        this.configurarEventos();
    },

    /**
     * Carga el cálculo de riesgo global desde el servidor
     */
    cargarRiesgoGlobal: function() {
        if (!this.sistemaId) return;

        fetch(`/api/sistema/${this.sistemaId}/riesgo-global`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.ultimoCalculo = data.data;
                    this.actualizarBadge(data.data);
                    this.actualizarPanelDiagnostico(data.data);
                } else {
                }
            })
            .catch(error => {
            });
    },

    /**
     * Actualiza el badge de riesgo global en la cabecera
     * @param {Object} datos - Datos del cálculo
     */
    actualizarBadge: function(datos) {
        const badge = document.getElementById('badge-riesgo-global');
        if (!badge) return;

        if (!datos.nivel) {
            badge.innerHTML = `
                <span class="badge bg-secondary">
                    <i class="bi bi-question-circle me-1"></i>Sin evaluar
                </span>`;
            return;
        }

        const iconos = {
            'BAJO': 'bi-shield-check',
            'MEDIO': 'bi-shield-exclamation',
            'ALTO': 'bi-shield-x',
            'CRITICO': 'bi-exclamation-triangle-fill'
        };

        badge.innerHTML = `
            <span class="badge" style="background-color: ${datos.color}; cursor: pointer;"
                  onclick="RiesgoGlobal.togglePanel()"
                  title="Clic para ver diagnóstico">
                <i class="bi ${iconos[datos.nivel] || 'bi-shield'} me-1"></i>
                Riesgo Global: ${datos.nivel}
                ${datos.factores && datos.factores.length > 0 ?
                    `<span class="badge bg-dark ms-1">${datos.factores.length}</span>` : ''}
            </span>`;

        // Añadir clase de animación si hay factores agravantes
        if (datos.factores && datos.factores.length > 0) {
            badge.querySelector('.badge').classList.add('badge-pulse');
        }
    },

    /**
     * Actualiza el panel lateral de diagnóstico
     * @param {Object} datos - Datos del cálculo
     */
    actualizarPanelDiagnostico: function(datos) {
        const panel = document.getElementById('panel-diagnostico-riesgo');
        if (!panel) return;

        let html = '';

        // Cabecera del panel
        html += `
            <div class="diagnostico-header" style="background-color: ${datos.color || '#6c757d'}20;
                 border-left: 4px solid ${datos.color || '#6c757d'}; padding: 15px; margin-bottom: 15px;">
                <h5 class="mb-1">
                    <i class="bi bi-graph-up-arrow me-2"></i>Nivel de Riesgo Global
                </h5>
                <h3 class="mb-0" style="color: ${datos.color}">${datos.nivel || 'Sin evaluar'}</h3>
                <small class="text-muted">${datos.mensaje || ''}</small>
            </div>`;

        // Métricas
        if (datos.metricas) {
            html += `
                <div class="metricas-riesgo mb-3">
                    <h6><i class="bi bi-bar-chart me-2"></i>Métricas</h6>
                    <div class="row g-2">
                        <div class="col-6">
                            <div class="metrica-card text-center p-2 border rounded">
                                <div class="h4 mb-0">${datos.metricas.total_aplicables}</div>
                                <small class="text-muted">Riesgos evaluados</small>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="metrica-card text-center p-2 border rounded">
                                <div class="h4 mb-0">${datos.metricas.pct_medio}%</div>
                                <small class="text-muted">en MEDIO</small>
                            </div>
                        </div>
                    </div>
                    <div class="row g-2 mt-1">
                        <div class="col-3">
                            <div class="text-center p-1 rounded" style="background: #C0000020">
                                <strong>${datos.metricas.criticos}</strong>
                                <br><small>Crít.</small>
                            </div>
                        </div>
                        <div class="col-3">
                            <div class="text-center p-1 rounded" style="background: #ED7D3120">
                                <strong>${datos.metricas.altos}</strong>
                                <br><small>Altos</small>
                            </div>
                        </div>
                        <div class="col-3">
                            <div class="text-center p-1 rounded" style="background: #FFC00020">
                                <strong>${datos.metricas.medios}</strong>
                                <br><small>Medios</small>
                            </div>
                        </div>
                        <div class="col-3">
                            <div class="text-center p-1 rounded" style="background: #00B05020">
                                <strong>${datos.metricas.bajos}</strong>
                                <br><small>Bajos</small>
                            </div>
                        </div>
                    </div>
                </div>`;
        }

        // Factores agravantes
        if (datos.factores && datos.factores.length > 0) {
            html += `
                <div class="factores-agravantes mb-3">
                    <h6><i class="bi bi-exclamation-diamond me-2"></i>Factores Agravantes Activos</h6>
                    <div class="list-group list-group-flush">`;

            datos.factores.forEach(factor => {
                let icono = 'bi-exclamation-circle';
                let accion = '';

                switch(factor.tipo) {
                    case 'CONCENTRACION':
                        icono = 'bi-pie-chart';
                        accion = `onclick="RiesgoGlobal.filtrarRiesgosMedio()"`;
                        break;
                    case 'CLUSTER':
                        icono = 'bi-diagram-3';
                        accion = `onclick="RiesgoGlobal.filtrarPorCluster(${factor.cluster_id})"`;
                        break;
                    case 'ESPECIFICOS':
                        icono = 'bi-person-badge';
                        accion = `onclick="RiesgoGlobal.filtrarEspecificos()"`;
                        break;
                    case 'RIESGO_CRITICO':
                    case 'RIESGO_ALTO':
                        icono = 'bi-shield-x';
                        accion = `onclick="RiesgoGlobal.filtrarPorNivel('${factor.tipo.replace('RIESGO_', '')}')"`;
                        break;
                }

                html += `
                    <a href="#" class="list-group-item list-group-item-action"
                       style="border-left: 3px solid ${factor.color || '#dc3545'}" ${accion}>
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <i class="bi ${icono} me-2"></i>
                                <strong>${factor.tipo}</strong>
                            </div>
                            <i class="bi bi-chevron-right"></i>
                        </div>
                        <small class="text-muted">${factor.detalle}</small>
                    </a>`;
            });

            html += `</div></div>`;
        } else if (datos.nivel) {
            html += `
                <div class="alert alert-success">
                    <i class="bi bi-check-circle me-2"></i>
                    No hay factores agravantes activos
                </div>`;
        }

        // Indicador de avance de fase
        html += `
            <div class="avance-fase mt-3 p-3 border rounded">
                <h6><i class="bi bi-arrow-right-circle me-2"></i>Avance a Fase 4</h6>
                ${datos.puede_avanzar ?
                    `<span class="badge bg-success"><i class="bi bi-check-lg me-1"></i>Permitido</span>` :
                    `<span class="badge bg-danger"><i class="bi bi-x-lg me-1"></i>Bloqueado</span>`
                }
            </div>`;

        panel.innerHTML = html;
    },

    /**
     * Muestra/oculta el panel de diagnóstico
     */
    togglePanel: function() {
        const panel = document.getElementById('panel-diagnostico-container');
        if (!panel) return;

        this.panelVisible = !this.panelVisible;

        if (this.panelVisible) {
            panel.classList.add('show');
            panel.style.display = 'block';
        } else {
            panel.classList.remove('show');
            panel.style.display = 'none';
        }
    },

    /**
     * Filtra la tabla de riesgos por nivel MEDIO
     */
    filtrarRiesgosMedio: function() {
        // Implementar según la estructura de tu tabla de riesgos
        if (typeof filtrarTablaRiesgos === 'function') {
            filtrarTablaRiesgos('nivel', 'MEDIO');
        }
        this.togglePanel();
    },

    /**
     * Filtra la tabla de riesgos por un cluster específico
     * @param {number} clusterId - ID del cluster
     */
    filtrarPorCluster: function(clusterId) {

        fetch(`/api/sistema/${this.sistemaId}/riesgo-global/cluster/${clusterId}/riesgos`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Resaltar los riesgos del cluster en la tabla
                    this.resaltarRiesgos(data.data.map(r => r.riesgo_id));
                }
            });

        this.togglePanel();
    },

    /**
     * Filtra la tabla para mostrar riesgos específicos del proyecto
     */
    filtrarEspecificos: function() {

        fetch(`/api/sistema/${this.sistemaId}/riesgo-global/especificos`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.resaltarRiesgos(data.data.map(r => r.riesgo_id));
                }
            });

        this.togglePanel();
    },

    /**
     * Filtra por nivel de riesgo
     * @param {string} nivel - 'CRITICO', 'ALTO', etc.
     */
    filtrarPorNivel: function(nivel) {
        if (typeof filtrarTablaRiesgos === 'function') {
            filtrarTablaRiesgos('nivel', nivel);
        }
        this.togglePanel();
    },

    /**
     * Resalta filas de riesgos específicos en la tabla
     * @param {Array} riesgoIds - Lista de IDs de riesgo a resaltar
     */
    resaltarRiesgos: function(riesgoIds) {
        // Quitar resaltados anteriores
        document.querySelectorAll('.riesgo-row.resaltado').forEach(row => {
            row.classList.remove('resaltado');
        });

        // Resaltar nuevos
        riesgoIds.forEach(id => {
            const row = document.querySelector(`.riesgo-row[data-riesgo-id="${id}"]`);
            if (row) {
                row.classList.add('resaltado');
                // Scroll al primer elemento
                if (id === riesgoIds[0]) {
                    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
        });
    },

    /**
     * Refresca el cálculo (llamar después del auto-guardado si cambió V_RIERESID)
     */
    refrescar: function() {
        this.cargarRiesgoGlobal();
    },

    /**
     * Configura los event listeners
     */
    configurarEventos: function() {
        // Cerrar panel al hacer clic fuera
        document.addEventListener('click', (e) => {
            const panel = document.getElementById('panel-diagnostico-container');
            const badge = document.getElementById('badge-riesgo-global');

            if (this.panelVisible && panel && badge) {
                if (!panel.contains(e.target) && !badge.contains(e.target)) {
                    this.togglePanel();
                }
            }
        });
    }
};


/* ============================================================================
 * INTEGRACIÓN CON AUTO-GUARDADO
 * Modificar tu función de auto-guardado existente
 * ============================================================================ */

/*
// Ejemplo de integración en tu función de auto-guardado:

function autoGuardarRiesgo(sistemaId, datos) {
    fetch(`/api/sistema/${sistemaId}/guardar-riesgo`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(datos)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Solo refrescar si cambió algo relevante para el riesgo global
            if (data.actualizar_riesgo_global) {
                RiesgoGlobal.refrescar();
            }
        }
    });
}
*/


/* ============================================================================
 * CSS ADICIONAL (añadir a style.css)
 * ============================================================================ */
/*
.badge-pulse {
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(237, 125, 49, 0.4); }
    70% { box-shadow: 0 0 0 10px rgba(237, 125, 49, 0); }
    100% { box-shadow: 0 0 0 0 rgba(237, 125, 49, 0); }
}

#panel-diagnostico-container {
    position: fixed;
    right: 0;
    top: 60px;
    width: 350px;
    height: calc(100vh - 60px);
    background: white;
    box-shadow: -2px 0 10px rgba(0,0,0,0.1);
    z-index: 1040;
    overflow-y: auto;
    padding: 15px;
    transform: translateX(100%);
    transition: transform 0.3s ease;
}

#panel-diagnostico-container.show {
    transform: translateX(0);
}

.riesgo-row.resaltado {
    background-color: #fff3cd !important;
    animation: highlight-fade 3s ease;
}

@keyframes highlight-fade {
    0% { background-color: #ffc107; }
    100% { background-color: #fff3cd; }
}

.metrica-card {
    background: #f8f9fa;
}

.list-group-item:hover {
    background-color: #f8f9fa;
}
*/
