
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

// ============================================================================
// SISTEMA DE AUTO-CIERRE MEJORADO CON HEARTBEAT
// ============================================================================
// Versión robusta que combina detección activa y pasiva de cierre
(function () {
  'use strict';

  // ========== CONFIGURACIÓN ==========
  // Valores inyectados desde config.py vía base.html, con valores por defecto
  const HEARTBEAT_INTERVAL = (window.HEARTBEAT_CONFIG && window.HEARTBEAT_CONFIG.HEARTBEAT_INTERVAL) || 5000;
  const NAVIGATION_TIMEOUT = (window.HEARTBEAT_CONFIG && window.HEARTBEAT_CONFIG.NAVIGATION_TIMEOUT) || 2000;

  // ========== VARIABLES DE ESTADO ==========
  let heartbeatInterval = null;
  let navegacionEnProgreso = false;
  let ultimaNavegacion = 0;
  let heartbeatActivo = false;  // Flag para saber si el heartbeat está corriendo

  // ========== FUNCIONES DE HEARTBEAT ==========

  /**
   * Enviar heartbeat al backend con manejo de errores mejorado
   */
  function sendHeartbeat() {

    fetch('/heartbeat', {
      method: 'POST',
      keepalive: true,
      headers: {
        'Content-Type': 'application/json'
      }
    }).catch((error) => {
      // Log silencioso de errores (puede ser que el servidor ya se cerró)
      // console.error('Error en heartbeat:', error);
    });
  }

  /**
   * Iniciar envío periódico de heartbeats
   */
  function startHeartbeat() {
    if (!heartbeatInterval && !heartbeatActivo) {
      heartbeatActivo = true;
      sendHeartbeat();  // Enviar inmediatamente
      heartbeatInterval = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
    }
  }

  /**
   * Detener envío de heartbeats
   */
  function stopHeartbeat() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
      heartbeatActivo = false;
    }
  }

  // ========== PAGE VISIBILITY API ==========
  // Detecta cuando la pestaña se oculta/muestra para manejar mejor los heartbeats
  // Los navegadores ralentizan setInterval en pestañas en background (de ~3s a ~15s)

  /**
   * Maneja cambios de visibilidad de la pestaña
   * Cuando la pestaña vuelve a ser visible, envía heartbeat inmediato
   */
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden && heartbeatActivo) {
      // Pestaña volvió a ser visible y heartbeat está activo
      sendHeartbeat();
    } else if (document.hidden) {
    }
  });

  // ========== FUNCIONES DE CIERRE ==========

  /**
   * Función mejorada para enviar señal de cierre con múltiples métodos
   * Usa estrategia de "dispara y olvida" para máxima confiabilidad
   */
  function enviarSenalCierre() {

    // Método 1: sendBeacon (MÁS CONFIABLE para eventos unload)
    // Este método está diseñado específicamente para enviar datos al cerrar
    try {
      const url = '/heartbeat_end';
      const beaconResult = navigator.sendBeacon(url, new Blob([''], { type: 'application/json' }));
    } catch (e) {
    }

    // Método 2: fetch con keepalive (RESPALDO)
    // keepalive permite que la petición sobreviva al cierre de la página
    try {
      fetch('/heartbeat_end', {
        method: 'POST',
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      }).then(() => {
      }).catch(e => {
      });
    } catch (e) {
    }

    // Método 3: XMLHttpRequest síncrono (ÚLTIMO RECURSO)
    // Deprecado pero funciona, bloquea hasta completar
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/heartbeat_end', false); // false = síncrono
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(JSON.stringify({}));
    } catch (e) {
    }

  }

  /**
   * Detectar si el evento es un cierre real o navegación interna
   * Retorna true solo si es un cierre real de pestaña/navegador
   */
  function esCierreReal() {
    const tiempoDesdeUltimaNav = Date.now() - ultimaNavegacion;

    // Si hay navegación en progreso o acaba de ocurrir, NO es cierre real
    if (navegacionEnProgreso || tiempoDesdeUltimaNav < NAVIGATION_TIMEOUT) {
      return false;
    }

    return true;
  }

  // ========== DETECCIÓN DE NAVEGACIÓN INTERNA ==========

  /**
   * Marcar que hay una navegación en progreso
   * Esto evita falsos positivos de cierre
   */
  function marcarNavegacion() {
    navegacionEnProgreso = true;
    ultimaNavegacion = Date.now();

    // Restablecer después de un timeout
    setTimeout(() => {
      navegacionEnProgreso = false;
    }, NAVIGATION_TIMEOUT + 1000); // Extra de seguridad
  }

  // Detectar clics en enlaces y botones
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a');
    const button = e.target.closest('button');

    if (link || button) {
      marcarNavegacion();
    }
  }, true); // useCapture = true para detectar antes que otros handlers

  // Detectar envío de formularios
  document.addEventListener('submit', (e) => {
    marcarNavegacion();
  }, true);

  // ========== INTERCEPTAR AJAX ==========

  // Interceptar fetch global
  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    // Solo marcar navegación si NO es un heartbeat
    const url = args[0];
    if (typeof url === 'string' && !url.includes('/heartbeat')) {
      marcarNavegacion();
    }

    return originalFetch.apply(this, args);
  };

  // Interceptar XMLHttpRequest
  const originalXHROpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    // Solo marcar navegación si NO es un heartbeat
    if (typeof url === 'string' && !url.includes('/heartbeat')) {
      marcarNavegacion();
    }
    return originalXHROpen.apply(this, [method, url, ...rest]);
  };

  // ========== DETECTAR CAMBIOS DE URL ==========

  let ultimaURL = window.location.href;
  setInterval(() => {
    if (window.location.href !== ultimaURL) {
      marcarNavegacion();
      ultimaURL = window.location.href;
    }
  }, 100);

  // ========== EVENTOS DE CIERRE DEL NAVEGADOR ==========
  //
  // NOTA: Sistema menos sensible para evitar falsos positivos.
  // Si el usuario inicia el gesto de cerrar pero cancela (arrastrando fuera),
  // NO se enviará señal de cierre prematura.
  // El servidor detectará el cierre real por timeout si no hay heartbeats.
  //

  /**
   * beforeunload - Se ejecuta ANTES de descargar la página
   *
   * IMPORTANTE: Este evento se dispara cuando el usuario INICIA el cierre,
   * incluso si luego lo cancela. Por eso NO enviamos señal aquí.
   * Solo detenemos el heartbeat; si el usuario cancela, se reanudará.
   */
  window.addEventListener('beforeunload', (event) => {
    if (!esCierreReal()) {
      return;  // No hacer nada si es navegación interna
    }

    // Solo detenemos heartbeat temporalmente, NO enviamos señal de cierre
    // Si el usuario cancela, el heartbeat se reanudará en visibilitychange
    stopHeartbeat();

    // NO retornar ningún valor - evita el diálogo de confirmación
  });

  /**
   * pagehide - Evento moderno más confiable
   *
   * CRÍTICO: Solo enviamos señal de cierre si event.persisted === false
   * Esto indica que la página realmente se está cerrando y no se guardará en bfcache.
   */
  window.addEventListener('pagehide', (event) => {
    if (!esCierreReal()) {
      return;
    }

    // event.persisted indica si la página se guardará en bfcache (navegación atrás/adelante)
    // Si es true, NO es un cierre real - la página podría volver
    if (event.persisted) {
      return;
    }

    enviarSenalCierre();
  });

  /**
   * visibilitychange - Detectar cuando la pestaña se oculta/muestra
   *
   * IMPORTANTE: Si el usuario canceló el cierre (arrastró fuera del X),
   * la pestaña volverá a ser visible y reanudaremos el heartbeat.
   */
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      startHeartbeat();
    } else {
      // NO detenemos el heartbeat aquí, solo cuando se cierra realmente
    }
  });

  // ========== INICIALIZACIÓN ==========

  /**
   * CRÍTICO: Iniciar heartbeat INMEDIATAMENTE
   * No esperar a DOMContentLoaded o load para máxima confiabilidad
   */
  startHeartbeat();

  // NOTA: La gestión de controles y pliego se realiza más abajo en el archivo
  // en la función handleTraslapeChange dentro del $(document).ready()

})();





// --- DOCUMENT READY ---
$(document).ready(function () {
  // Verificar el estado inicial del proyecto al cargar
  verificarEstado();
  // Verificar el estado cada vez que se cambie un campo del formulario
  $("#nombre_proyecto, #fecha_inicio, #dpd_responsable").on("input change", verificarEstado);
  // Manejar el evento de selección de proyecto para eliminar
  $(document).on('click', '#btn-eliminar', function () {
    const proyectoId = $("#proyecto_id").val(); // Obtiene el ID del proyecto del select
    if (!proyectoId) { // Si no hay proyecto seleccionado
      alert("Selecciona un proyecto para eliminar."); // Muestra alerta
      return; // Sale de la función
    }

    // 👇 MODIFICACIÓN: Mostrar el modal de confirmación en lugar de confirm() 👇
    // Guardar el ID del proyecto en una variable global temporal o en un atributo del modal
    window.proyectoIdAEliminar = proyectoId;

    // Mostrar el modal de Bootstrap 5
    const eliminarModal = new bootstrap.Modal(document.getElementById('confirmarEliminarModal'));
    eliminarModal.show();
    // 👆 FIN DE LA MODIFICACIÓN 👆
  });

  // 👇 AÑADIR ESTE NUEVO BLOQUE PARA MANEJAR LA CONFIRMACIÓN DEL MODAL 👇
  // Manejar el evento de clic en el botón "Eliminar" dentro del modal
  $(document).on('click', '#confirmarEliminarBtn', function () {
    // Obtener el ID del proyecto guardado previamente
    const proyectoId = window.proyectoIdAEliminar;

    // Referencia al modal
    const eliminarModalElement = document.getElementById('confirmarEliminarModal');
    const eliminarModalInstance = bootstrap.Modal.getInstance(eliminarModalElement);

    // Función para ejecutar la eliminación AJAX
    function ejecutarEliminacion() {
      // Deshabilitar el botón de eliminar del formulario principal y mostrar spinner
      const $btnEliminarPrincipal = $('#btn-eliminar');
      $btnEliminarPrincipal.prop('disabled', true); // Deshabilitar botón
      $btnEliminarPrincipal.html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Eliminando...');

      // Realizar la solicitud AJAX para eliminar el proyecto
      $.ajax({
        url: `/eliminar-proyecto/${proyectoId}`,
        method: "POST",
        success: function (response) {
          if (response.success && response.redirect) {
            // Redirigir a la vista de selección de proyecto
            window.location.href = response.redirect;
          } else {
            // Mostrar un mensaje de error si no hay redirección
            alert("El proyecto fue eliminado, pero ocurrió un error inesperado.");
            (function(){ var u=new URL(window.location.href); u.searchParams.set("_t",Date.now()); window.location.href=u.toString(); })(); // Recargar la página como fallback
          }
        },
        error: function (xhr) {
          alert("Error al eliminar el proyecto: " + (xhr.responseJSON?.error || "Servidor no disponible"));
        },
        complete: function () {
          // Habilitar el botón de eliminar del formulario principal y restaurar texto
          const $btnEliminarPrincipal = $('#btn-eliminar');
          $btnEliminarPrincipal.prop('disabled', false); // Habilitar botón
          $btnEliminarPrincipal.text("Eliminar proyecto seleccionado"); // Restaurar texto original
        }
      });
    }

    // Cerrar el modal
    eliminarModalInstance.hide(); // Esto inicia la transición de ocultado

    // Escuchar el evento 'hidden.bs.modal' para saber cuándo el modal ha desaparecido completamente
    eliminarModalElement.addEventListener('hidden.bs.modal', ejecutarEliminacion, { once: true });
    // { once: true } asegura que el listener se ejecute solo una vez y luego se elimine
  });

  // Manejar el evento de cambio en las observaciones
  $(".observacion-textarea").on("input", function () {
    const value = $(this).val().trim();
    $(this)
      .removeClass("bg-light-success bg-light-danger")
      .addClass(value ? "bg-light-success" : "bg-light-danger");
  }).trigger("input");
  // Auto-resize dinámico
  $(".observacion-textarea").each(function () {
    this.setAttribute("style", "height:" + this.scrollHeight + "px;overflow-y:hidden;");
  }).on("input", function () {
    this.style.height = "auto";
    this.style.height = (this.scrollHeight) + "px";
  });
  // Actualizar todos los estados al cargar
  actualizarTodos();
  // Escuchar cambios en los textarea
  $(".observacion-textarea").on("input", function () {
    const idElem = $(this).data("idelem");
    const nIteracion = $(this).data("niteracion");
    if (nIteracion !== undefined) {
      actualizarEstadoElemento(idElem, nIteracion);
    }
    actualizarEstadoElementoGlobal(idElem);
  });
  // Manejar el evento de clic en el botón de ADI
  $('[id^="botonADI"]').on('click', function () {
    const $icon = $(this).find('i[id^="iconoADI"]');
    setTimeout(() => {
      $icon.toggleClass('bi-chevron-down bi-chevron-up');
    }, 150);
  });
  // Función para recargar solo la tabla
  function recargarTablaConfiguracion() {
    $.ajax({
      url: window.location.href,
      type: 'GET',
      success: function (data) {
        const temp = document.createElement('div');
        temp.innerHTML = data;
        const nuevaTabla = temp.querySelector('#tabla-configuracion');
        if (nuevaTabla) {
          $('#tabla-configuracion').replaceWith(nuevaTabla);
        }
      },
      error: function () {
      }
    });
  }
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('exito') === '1') {
    recargarTablaConfiguracion();
  }
  // Cerrar modal con tecla ESC
  $(document).on('keydown', function (event) {
    if (event.key === 'Escape') {
      $('#modalAyuda').modal('hide');
    }
  });
  // Cerrar modal haciendo clic fuera del contenido
  $(document).on('click', '#modalAyuda', function (event) {
    if (event.target.id === 'modalAyuda') {
      cerrarModal();
    }
  });
  // ========== MANEJO DE RIESGOS ==========
  $(document).on('change', '.aplica-select-riesgo', function () {
    // Si monitoreo está activo, no hacer nada que habilite/deshabilite campos
    if (typeof monitoreoActivo !== 'undefined' && monitoreoActivo) {
      // Opcionalmente, puedes resetear el valor si intentan cambiarlo
      // this.value = this.getAttribute('data-original-value') || this.options[0].value;
      return; // Salir de la función
    }

    const $fila = $(this).closest('tr');
    const aplica = this.value === '1';
    const idRiesgo = $(this).data('id-riesgo');

    if (!aplica) {
      $fila.find('td').addClass('fila-no-aplica');
    } else {
      $fila.find('td').removeClass('fila-no-aplica');
    }

    // DESHABILITA/HABILITA campos según 'aplica', PERO SOLO SI 'monitoreoActivo' es false o no está definido
    $fila.find('select, textarea').not(this).prop('disabled', !aplica);

    if (!aplica) {
      $(`[data-bs-target="#modalJustifAplica${idRiesgo}"],[data-bs-target="#modalJustifImpacto${idRiesgo}"],[data-bs-target="#modalJustifProb${idRiesgo}"]`)
        .prop('disabled', true)
        .addClass('disabled')
        .attr('title', 'No aplica - Justificación bloqueada')
        .css({ 'opacity': '0.6', 'cursor': 'not-allowed' });
    } else {
      $(`[data-bs-target="#modalJustifAplica${idRiesgo}"],[data-bs-target="#modalJustifImpacto${idRiesgo}"],[data-bs-target="#modalJustifProb${idRiesgo}"]`)
        .prop('disabled', false)
        .removeClass('disabled')
        .removeAttr('title')
        .css({ 'opacity': '1', 'cursor': 'pointer' });
    }

    // 🆕 ACTUALIZAR ATRIBUTO DATA
    $fila.attr('data-l-aplica', this.value);

    // 🆕 REAPLICAR FILTRO SI ESTÁ ACTIVO
    if (typeof reaplicarFiltroSiActivo === 'function') {
      reaplicarFiltroSiActivo();
    }

    // Actualizar el botón "Mitigar Riesgo"
    actualizarBotonMitigar(idRiesgo);

    // Guardar el cambio automáticamente
    guardarCambioAuto(idRiesgo, 'aplica', this.value, 'riesgo');

    // Actualizar resumen de riesgos
    actualizarResumenRiesgos();
  });

  // ====== CREAR RIESGO PERSONALIZADO ======
  $(document).on("click", "#btn-crear-riesgo", function () {
    if (typeof monitoreoActivo !== "undefined" && monitoreoActivo) {
      alert("No se pueden crear riesgos personalizados durante la fase de monitoreo.");
      return;
    }

    // Obtener el mensaje de confirmación desde la base de datos
    $.ajax({
      url: "/obtener-mensaje-confirmacion-riesgo",
      method: "GET",
      success: function (resp) {
        if (resp.success) {
          // Insertar el mensaje HTML formateado en el modal de confirmación
          $("#contenidoMensajeConfirmacion").html(resp.mensaje);

          // Mostrar el modal de confirmación
          const modalConfirmacion = new bootstrap.Modal(document.getElementById("modalConfirmacionRiesgoEspecifico"));
          modalConfirmacion.show();
        } else {
          // Si no se puede obtener el mensaje, mostrar error
          alert("⚠️ " + (resp.message || "No se pudo cargar el mensaje de confirmación."));
        }
      },
      error: function (xhr) {
        alert("❌ Error al cargar el mensaje de confirmación: " + (xhr.responseJSON?.message || "Servidor no disponible."));
      }
    });
  });

  // Nuevo manejador para el botón de confirmar en el modal de confirmación
  $(document).on("click", "#btnConfirmarCreacionRiesgo", function () {
    // Cerrar el modal de confirmación
    const modalConfirmacion = bootstrap.Modal.getInstance(document.getElementById("modalConfirmacionRiesgoEspecifico"));
    if (modalConfirmacion) {
      modalConfirmacion.hide();
    }

    // Esperar a que el modal se cierre completamente antes de abrir el siguiente
    document.getElementById("modalConfirmacionRiesgoEspecifico").addEventListener('hidden.bs.modal', function (e) {
      // Abrir el modal para capturar la descripción del riesgo
      const modalRiesgo = new bootstrap.Modal(document.getElementById("modalRiesgoPersonal"));
      $("#descripcionRiesgo").val(""); // Limpiar el textarea antes de abrir
      modalRiesgo.show();
    }, { once: true });
  });

  $(document).on("click", "#btnAceptarRiesgo", function () {
    const descripcion = $("#descripcionRiesgo").val().trim();
    if (!descripcion) {
      alert("Debe introducir una descripción antes de continuar.");
      return;
    }

    $.ajax({
      url: "/crear-riesgo-personalizado",
      method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ descripcion }),
      success: function (resp) {
        if (resp.success) {
          // Ocultar el modal de entrada
          const modalEntrada = bootstrap.Modal.getInstance(document.getElementById("modalRiesgoPersonal"));
          if (modalEntrada) {
            modalEntrada.hide();
          }

          // Actualizar el mensaje de confirmación si es necesario
          $('#mensajeConfirmacionRiesgo').text((resp.message || 'Riesgo personalizado creado correctamente.')); // Si el backend envía un mensaje personalizado

          // Mostrar el modal de confirmación
          const modalConfirmacion = new bootstrap.Modal(document.getElementById("modalConfirmarRiesgoPersonal"));
          modalConfirmacion.show();

          // Opcional: Recargar la página después de cerrar el modal de confirmación
          // Escuchar el evento 'hidden.bs.modal' para recargar solo cuando el usuario cierre el modal
          document.getElementById('modalConfirmarRiesgoPersonal').addEventListener('hidden.bs.modal', function (e) {
            (function(){ var u=new URL(window.location.href); u.searchParams.set("_t",Date.now()); window.location.href=u.toString(); })();
          }, { once: true }); // 'once: true' asegura que el listener se ejecute solo una vez

        } else {
          // Manejar error del backend (mensaje de error)
          alert("⚠️ " + (resp.message || "Error desconocido al crear el riesgo."));
        }
      },
      error: function (xhr) {
        // Manejar error de red o servidor
        alert("❌ Error al crear el riesgo: " + (xhr.responseJSON?.message || "Servidor no disponible."));
      },
    });
  });


  // ESTE BLOQUE APLICA LA LÓGICA INICIAL AL CARGAR LA PÁGINA
  // SOLO SI monitoreoActivo es FALSE o no está definido
  if (typeof monitoreoActivo === 'undefined' || !monitoreoActivo) {
    $('.aplica-select-riesgo').each(function () {
      const $fila = $(this).closest('tr');
      const aplica = this.value === '1';
      const idRiesgo = $(this).data('id-riesgo');

      if (!aplica) {
        $fila.find('td').addClass('fila-no-aplica');
      } else {
        $fila.find('td').removeClass('fila-no-aplica');
      }

      // DESHABILITA/HABILITA campos según 'aplica', PERO SOLO SI 'monitoreoActivo' es false o no está definido
      $fila.find('select, textarea').not(this).prop('disabled', !aplica);

      if (!aplica) {
        $(`[data-bs-target="#modalJustifAplica${idRiesgo}"],[data-bs-target="#modalJustifImpacto${idRiesgo}"],[data-bs-target="#modalJustifProb${idRiesgo}"]`)
          .prop('disabled', true)
          .addClass('disabled')
          .attr('title', 'No aplica - Justificación bloqueada')
          .css({ 'opacity': '0.6', 'cursor': 'not-allowed' });
      } else {
        $(`[data-bs-target="#modalJustifAplica${idRiesgo}"],[data-bs-target="#modalJustifImpacto${idRiesgo}"],[data-bs-target="#modalJustifProb${idRiesgo}"]`)
          .prop('disabled', false)
          .removeClass('disabled')
          .removeAttr('title')
          .css({ 'opacity': '1', 'cursor': 'pointer' });
      }
    });
  } else {
    // Si monitoreo está activo, asegurarse de que los selects de aplica también estén deshabilitados
    // (esto debería hacerlo Jinja2, pero por si acaso)
    $('.aplica-select-riesgo').prop('disabled', true);
    // Opcional: Aplicar estilos de deshabilitado a otros campos si Jinja2 no lo hizo por CSS
    // $('.fila-riesgo select, .fila-riesgo textarea').not('.aplica-select-riesgo').prop('disabled', true);
  }

  function obtenerNivelRiesgo(criticidad) {
    if (criticidad >= 15) return { texto: "CRÍTICO", clase: "text-danger fw-bold" };
    if (criticidad >= 9) return { texto: "ALTO", clase: "text-warning fw-bold" };
    if (criticidad >= 5) return { texto: "MEDIO", clase: "text-info" };
    if (criticidad > 0) return { texto: "BAJO", clase: "text-success" };
    return { texto: "—", clase: "" };
  }

  function actualizarCriticidad(idRiesgo) {
    const $impactoSelect = $(`.select-impacto[data-id-riesgo="${idRiesgo}"]`);
    const $probabilidadSelect = $(`.select-probabilidad[data-id-riesgo="${idRiesgo}"]`);
    const $celdaCriticidad = $(`.celda-criticidad[data-id-riesgo="${idRiesgo}"]`);
    const $celdaNivel = $(`.celda-nivel[data-id-riesgo="${idRiesgo}"] span`);
    const $celdaValorResidual = $(`.celda-valor-residual[data-id-riesgo="${idRiesgo}"]`);
    const $celdaNivelResidual = $(`.celda-nivel-residual[data-id-riesgo="${idRiesgo}"] span`);
    const $fila = $impactoSelect.closest('tr');

    const idImpacto = $impactoSelect.val(); // Este es el ID_VALDAT
    const idProbabilidad = $probabilidadSelect.val(); // Este es el ID_VALDAT

    // Mostrar un estado temporal mientras se calcula
    $celdaCriticidad.text("..."); // o un spinner
    $celdaNivel.text("...").attr('class', '');
    $celdaValorResidual.text("...");
    $celdaNivelResidual.text("...").attr('class', '');

    if (idImpacto && idProbabilidad) {
      $.ajax({
        url: '/api/calcular-criticidad-riesgo', // Endpoint que creaste en app.py
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
          id_riesgo: idRiesgo, // Puede no ser necesario, dependiendo del endpoint
          id_impacto: idImpacto,
          id_probabilidad: idProbabilidad
        }),
        success: function (response) {
          if (response.success && response.criticidad !== undefined) {
            const criticidad = response.criticidad;
            // Reutilizar la función JS para obtener el nivel
            // Asegúrate de que el formato devuelto por el backend coincida
            // o adapta esta parte si el backend devuelve el nivel completo
            // const nivelInfo = obtenerNivelRiesgo(criticidad); // Opción 1: Calcular nivel en JS
            const nivelInfo = response.nivel; // Opción 2: Recibir nivel del backend

            // Actualizar la interfaz con los valores calculados por el backend
            $celdaCriticidad.text(criticidad);
            $celdaNivel.text(nivelInfo.texto).attr('class', nivelInfo.clase);
            // Para el residual, asumimos que sin controles activos, es igual al inherente
            // o que el backend lo calcularía de forma diferente en tiempo real (menos probable aquí)
                    $.ajax({
                        url: '/api/calcular-riesgo-residual',
                        method: 'POST',
                        contentType: 'application/json',
                        data: JSON.stringify({
                            id_registro: idRiesgo,
                            criticidad_inherente: criticidad
                        }),
                        success: function (responseResidual) {
                            if (responseResidual.success) {
                                const riesgoResidual = responseResidual.riesgo_residual;
                                const nivelResidual = responseResidual.nivel_residual;
            // Si tu backend en el endpoint calcula un nivel_residual, úsalo en su lugar
                                $celdaValorResidual.text(riesgoResidual !== null ? riesgoResidual : '—');
                                $celdaNivelResidual.text(nivelResidual.texto).attr('class', nivelResidual.clase);

                                // 🆕 ACTUALIZAR ATRIBUTOS DATA DE LA FILA
                                $fila.attr('data-riesgo-residual-numerico', riesgoResidual !== null ? riesgoResidual : '');
                                $fila.attr('data-riesgo-residual-texto', nivelResidual.texto || '');

                                // 🆕 REAPLICAR FILTRO SI ESTÁ ACTIVO
                                if (typeof reaplicarFiltroSiActivo === 'function') {
                                  reaplicarFiltroSiActivo();
                                }

                                // 🆕 REFRESCAR RIESGO GLOBAL
                                if (typeof RiesgoGlobal !== 'undefined' && RiesgoGlobal.refrescar) {
                                  RiesgoGlobal.refrescar();
                                }
                            } else {
                                $celdaValorResidual.text("Err");
                                $celdaNivelResidual.text("Err").attr('class', 'text-danger');
                            }
                        },
                        error: function (xhr, status, error) {
                            $celdaValorResidual.text("Err");
                            $celdaNivelResidual.text("Err").attr('class', 'text-danger');
                        }
                    });

          } else {
            $celdaCriticidad.text("Err");
            $celdaNivel.text("Err").attr('class', 'text-danger');
                    $celdaValorResidual.text("Err");
            $celdaNivelResidual.text("Err").attr('class', 'text-danger');
          }
        },
        error: function (xhr, status, error) {
          $celdaCriticidad.text("Err");
          $celdaNivel.text("Err").attr('class', 'text-danger');
          $celdaValorResidual.text("Err");
          $celdaNivelResidual.text("Err").attr('class', 'text-danger');
        }
      });
    } else {
      // Si falta impacto o probabilidad, mostrar guiones Y limpiar atributos data
      $celdaCriticidad.text("—");
      $celdaNivel.text("—").attr('class', '');
      $celdaValorResidual.text("—");
      $celdaNivelResidual.text("—").attr('class', '');

      // 🆕 LIMPIAR ATRIBUTOS DATA cuando se borran valores
      $fila.attr('data-riesgo-residual-numerico', '');
      $fila.attr('data-riesgo-residual-texto', '');

      // 🆕 REAPLICAR FILTRO SI ESTÁ ACTIVO
      if (typeof reaplicarFiltroSiActivo === 'function') {
        reaplicarFiltroSiActivo();
      }
    }
  }


  // Modificar el evento change para llamar a la nueva función
  $(document).on('change', '.select-impacto, .select-probabilidad', function () {
    const idRiesgo = $(this).data('id-riesgo');
    const $fila = $(this).closest('tr');

    // 🆕 ACTUALIZAR ATRIBUTOS DATA
    if ($(this).hasClass('select-impacto')) {
      $fila.attr('data-v-impacto', $(this).val());
      guardarCambioAuto(idRiesgo, 'impacto', $(this).val(), 'riesgo');
    } else if ($(this).hasClass('select-probabilidad')) {
      $fila.attr('data-v-probabilidad', $(this).val());
      guardarCambioAuto(idRiesgo, 'probabilidad', $(this).val(), 'riesgo');
    }

    // Llamar a la nueva función que calcula via AJAX
    actualizarCriticidad(idRiesgo);
    setTimeout(() => {
      actualizarResumenRiesgos();
    }, 500);
  });

  // ========== MANEJO DE CONTROLES ==========
  // SOLO SI monitoreoActivo es FALSE o no está definido
  if (typeof monitoreoActivo === 'undefined' || !monitoreoActivo) {
    $('.aplica-select-control').each(function () {
      const $fila = $(this).closest('tr');
      const aplica = this.value === '1';
      const idControl = $(this).data('id-control');

      if (!aplica) {
        $fila.find('td').addClass('fila-no-aplica');
      } else {
        $fila.find('td').removeClass('fila-no-aplica');
      }

      // DESHABILITA/HABILITA campos según 'aplica', PERO SOLO SI 'monitoreoActivo' es false o no está definido
      $fila.find('select, textarea').not(this).prop('disabled', !aplica);

      if (!aplica) {
        $(`[data-bs-target="#modalJustifClausula${idControl}"],[data-bs-target="#modalObservaciones${idControl}"]`)
          .prop('disabled', true)
          .addClass('disabled')
          .attr('title', 'No aplica - Justificación/Observaciones bloqueadas')
          .css({ 'opacity': '0.6', 'cursor': 'not-allowed' });
      } else {
        $(`[data-bs-target="#modalJustifClausula${idControl}"],[data-bs-target="#modalObservaciones${idControl}"]`)
          .prop('disabled', false)
          .removeClass('disabled')
          .removeAttr('title')
          .css({ 'opacity': '1', 'cursor': 'pointer' });
      }
    });
  } else {
    // Si monitoreo está activo, asegurarse de que los selects de aplica también estén deshabilitados
    // (esto debería hacerlo Jinja2, pero por si acaso)
    $('.aplica-select-control').prop('disabled', true);
  }

  // Manejar cambios en el select "Aplica" (Evento `change`)
  $(document).on('change', '.aplica-select-control', function () {
    // Si monitoreo está activo, no hacer nada que habilite/deshabilite campos
    if (typeof monitoreoActivo !== 'undefined' && monitoreoActivo) {
      return; // Salir de la función
    }

    const $fila = $(this).closest('tr');
    const aplica = this.value === '1';
    const idControl = $(this).data('id-control');

    if (!aplica) {
      $fila.find('td').addClass('fila-no-aplica');
    } else {
      $fila.find('td').removeClass('fila-no-aplica');
    }

    // DESHABILITA/HABILITA campos según 'aplica', PERO SOLO SI 'monitoreoActivo' es false o no está definido
    $fila.find('select, textarea').not(this).prop('disabled', !aplica);

    if (!aplica) {
      $(`[data-bs-target="#modalJustifClausula${idControl}"],[data-bs-target="#modalObservaciones${idControl}"]`)
        .prop('disabled', true)
        .addClass('disabled')
        .attr('title', 'No aplica - Justificación/Observaciones bloqueadas')
        .css({ 'opacity': '0.6', 'cursor': 'not-allowed' });
    } else {
      $(`[data-bs-target="#modalJustifClausula${idControl}"],[data-bs-target="#modalObservaciones${idControl}"]`)
        .prop('disabled', false)
        .removeClass('disabled')
        .removeAttr('title')
        .css({ 'opacity': '1', 'cursor': 'pointer' });
    }

    // 🆕 VALIDAR EN TIEMPO REAL
    validarControlEnTiempoReal(idControl);

    guardarCambioAuto(idControl, 'aplica', this.value, 'control');
  });

  // Manejar cambios en el select "¿Se traslada a pliego?" (Evento `change`)
  $(document).on('change', '.pliego-select', function () {
    const idControl = $(this).data('id-control');
    const valor = $(this).val();

    // Si monitoreo está activo, no hacer nada que habilite/deshabilite campos
    if (typeof monitoreoActivo !== 'undefined' && monitoreoActivo) {
      return; // Salir de la función
    }

    // Llamar a la función que actualiza los campos relacionados
    handleTraslapeChange(this);

    // Guardar el cambio
    guardarCambioAuto(idControl, 'pliego', valor, 'control');
  });

// FUNCIÓN QUE ACTUALIZA CAMPOS RELACIONADOS CON "¿SE TRASLADA A PLIEGO?" (MODIFICADA)
  // Esta función se llama al cargar la página y al cambiar el select de pliego
  function handleTraslapeChange(selectElement) {
    // Si monitoreo está activo, no hacer nada que habilite/deshabilite campos
    if (typeof monitoreoActivo !== 'undefined' && monitoreoActivo) {
      // Asegurarse de que los campos relacionados estén deshabilitados si monitoreo es true
      const controlId = selectElement.dataset.idControl;
      if (controlId) {
        const intensidadSelect = document.querySelector(`select[name="intensidad_${controlId}"]`);
        // Botón de Traslado a pliegos (justificación clausula)
        const justifButton = document.querySelector(`button[data-bs-target="#modalJustifClausula${controlId}"]`);
        const justifTextarea = document.querySelector(`#modalJustifClausula${controlId} textarea[name^="jus_clausula_"]`);
        // Botón de Implementación (observaciones)
        const observButton = document.querySelector(`button[data-bs-target="#modalObservaciones${controlId}"]`);
        const observTextarea = document.querySelector(`#modalObservaciones${controlId} textarea[name^="observaciones_"]`);

        if (intensidadSelect) {
          intensidadSelect.disabled = true;
          intensidadSelect.style.opacity = '0.6';
          intensidadSelect.style.cursor = 'not-allowed';
          intensidadSelect.style.backgroundColor = '#f8f9fa';
          intensidadSelect.style.pointerEvents = 'none';
        }
        if (justifButton) {
          justifButton.disabled = true;
          justifButton.style.opacity = '0.6';
          justifButton.style.cursor = 'not-allowed';
          justifButton.title = 'Fase de monitoreo - Edición bloqueada';
        }
        if (justifTextarea) {
          justifTextarea.disabled = true;
          justifTextarea.readOnly = true;
        }
        if (observButton) {
          observButton.disabled = true;
          observButton.style.opacity = '0.6';
          observButton.style.cursor = 'not-allowed';
          observButton.title = 'Fase de monitoreo - Edición bloqueada';
        }
        if (observTextarea) {
          observTextarea.disabled = true;
          observTextarea.readOnly = true;
        }
      }
      return; // Salir de la función
    }

    const selectedValue = selectElement.value;
    const controlId = selectElement.dataset.idControl;

    if (!controlId) {
      return;
    }

    // Buscar los elementos relacionados
    const intensidadSelect = document.querySelector(`select[name="intensidad_${controlId}"]`);
    // Botón de Traslado a pliegos (justificación clausula) - SE DESHABILITA SI NO SE TRASLADA
    const justifButton = document.querySelector(`button[data-bs-target="#modalJustifClausula${controlId}"]`);
    const justifTextarea = document.querySelector(`#modalJustifClausula${controlId} textarea[name^="jus_clausula_"]`);
    // Botón de Implementación (observaciones) - SIEMPRE HABILITADO (independiente del traslado a pliego)
    // const observButton = document.querySelector(`button[data-bs-target="#modalObservaciones${controlId}"]`);
    // const observTextarea = document.querySelector(`#modalObservaciones${controlId} textarea[name^="observaciones_"]`);

    if (selectedValue === "0") { // No se traslada a pliego
      // Deshabilitar Intensidad
      if (intensidadSelect) {
        intensidadSelect.disabled = true;
        intensidadSelect.classList.add('fila-no-aplica');
        intensidadSelect.style.opacity = '0.6';
        intensidadSelect.style.cursor = 'not-allowed';
        intensidadSelect.style.backgroundColor = '#f8f9fa';
        intensidadSelect.style.pointerEvents = 'none';
      }
      // Deshabilitar botón "Traslado a pliegos" (justificación clausula)
      if (justifButton) {
        justifButton.disabled = true;
        justifButton.classList.add('fila-no-aplica');
        justifButton.style.opacity = '0.6';
        justifButton.style.cursor = 'not-allowed';
        justifButton.title = 'No aplica - No se traslada a pliego';
      }
      if (justifTextarea) {
        justifTextarea.disabled = true;
        justifTextarea.readOnly = true;
      }
      // El botón "Implementación" (observaciones) permanece habilitado - NO SE MODIFICA
    } else { // Sí se traslada a pliego (o no seleccionado aún)
      // Habilitar Intensidad
      if (intensidadSelect) {
        intensidadSelect.disabled = false;
        intensidadSelect.classList.remove('fila-no-aplica');
        intensidadSelect.style.opacity = '1';
        intensidadSelect.style.cursor = 'pointer';
        intensidadSelect.style.backgroundColor = '';
        intensidadSelect.style.pointerEvents = 'auto';
      }
      // Habilitar botón "Traslado a pliegos" (justificación clausula)
      if (justifButton) {
        justifButton.disabled = false;
        justifButton.classList.remove('fila-no-aplica');
        justifButton.style.opacity = '1';
        justifButton.style.cursor = 'pointer';
        justifButton.removeAttribute('title');
      }
      if (justifTextarea) {
        justifTextarea.disabled = false;
        justifTextarea.readOnly = false;
      }
      // El botón "Implementación" (observaciones) permanece habilitado - NO SE MODIFICA
    }
  }

  // Aplicar el estado inicial de "¿Se traslada a pliego?" al cargar la página
  // SOLO SI monitoreoActivo es FALSE o no está definido
  if (typeof monitoreoActivo === 'undefined' || !monitoreoActivo) {
    // Esperar un frame adicional para asegurar que los valores de Jinja están aplicados
    requestAnimationFrame(() => {
      const pliegoSelects = document.querySelectorAll('.pliego-select');
      pliegoSelects.forEach(select => {
        handleTraslapeChange(select); // Aplicar estado inicial
        // Añadir listener para cambios futuros
        select.addEventListener('change', () => handleTraslapeChange(select));
      });
    });
  } else {
    // Si monitoreo está activo, asegurarse de que los selects de pliego también estén deshabilitados
    // (esto debería hacerlo Jinja2, pero por si acaso)
    $('.pliego-select').prop('disabled', true);
    // Asegurar que campos relacionados estén deshabilitados también
    $('.select-intensidad').prop('disabled', true).css({ 'opacity': '0.6', 'cursor': 'not-allowed', 'background-color': '#f8f9fa', 'pointer-events': 'none' });
    $('.observaciones-textarea').prop('disabled', true).css({ 'opacity': '0.6', 'cursor': 'not-allowed' }).attr('title', 'Fase de monitoreo - Edición bloqueada');
    // Asegurar que textareas de observaciones en modales estén deshabilitadas
    $('.modal textarea[name^="observaciones_"]').prop('disabled', true).prop('readOnly', true);
  }

  $(document).on('change', '.select-intensidad', function () {
    const idControl = $(this).data('id-control');
    const valor = $(this).val();
    guardarCambioAuto(idControl, 'intensidad', valor, 'control');
  });

  $(document).on('input', '.observaciones-textarea', function () {
    const idControl = $(this).data('id-control');
    const valor = $(this).val();
    guardarCambioAuto(idControl, 'observaciones', valor, 'control');
  });

  $(document).on('change', '.select-madurez', function () {
    const idControl = $(this).data('id-control');
    const valor = $(this).val();

    // 🆕 VALIDAR EN TIEMPO REAL
    validarControlEnTiempoReal(idControl);

    guardarCambioAuto(idControl, 'madurez', valor, 'control');
  });

  window.mostrarAyuda = function (preguntaId) {
    $.get('/formulario/adi/ayuda/' + preguntaId)
      .done(function (data) {
        $('#graficoAyuda').html(data.ayuda || 'No hay ayuda disponible para esta pregunta.');
        $('#modalAyuda').modal('show');
      })
      .fail(function () {
        $('#graficoAyuda').html('Error al cargar la ayuda.');
        $('#modalAyuda').modal('show');
      });
  };
  window.cerrarModal = function () {
    $('#modalAyuda').modal('hide');
  };

  // --- ACORDEÓN PARA ITERACIONES ---
  $(document).on('click', '.fila-elemento-principal', function () {
    const idElem = $(this).data('idelem');
    const $icon = $(this).find('.toggle-iteraciones');
    const $subfilas = $(`tr.fila-iteracion[data-idelem='${idElem}']`);
    if ($subfilas.length === 0) return;
    const isVisible = $subfilas.first().is(':visible');
    if (isVisible) {
      $subfilas.hide();
      $icon.removeClass('bi-chevron-up').addClass('bi-chevron-down');
    } else {
      $subfilas.show();
      $icon.removeClass('bi-chevron-down').addClass('bi-chevron-up');
    }
  });

  // Manejar cambios en el select "¿Se traslada a pliego?"
  $(document).on('change', '.auto-save-control-pliego', function () {
    const $selectPliego = $(this);
    const idControl = $selectPliego.data('id-datelemcontr');
    const valorPliego = $selectPliego.val();

    const $selectIntensidad = $(`.select-intensidad[data-id-datelemcontr="${idControl}"]`);
    const $btnObservaciones = $(`.btn-observaciones-pliego[data-bs-target="#modalClausulaElem${idControl}"]`);

    // Forzar actualización en el próximo frame
    requestAnimationFrame(() => {
      // Forzar recarga visual temporal
      const $grupo = $selectIntensidad.add($btnObservaciones);

      if (valorPliego === "0") {
        $grupo.each(function () {
          const $element = $(this);
          if ($element.is('select')) {
            $element.prop('disabled', true)
              .addClass('fila-no-aplica')
              .css({
                'opacity': '0.6',
                'cursor': 'not-allowed',
                'background-color': '#f8f9fa',
                'pointer-events': 'none'
              });
          } else if ($element.is('button')) {
            $element.prop('disabled', true)
              .addClass('fila-no-aplica')
              .css({
                'opacity': '0.6',
                'cursor': 'not-allowed'
              })
              .attr('title', 'No aplica - Observaciones bloqueadas');
          }
        });
      } else {
        $grupo.each(function () {
          const $element = $(this);
          if ($element.is('select')) {
            $element.prop('disabled', false)
              .removeClass('fila-no-aplica')
              .css({
                'opacity': '1',
                'cursor': 'pointer',
                'background-color': '',
                'pointer-events': 'auto'
              });
          } else if ($element.is('button')) {
            $element.prop('disabled', false)
              .removeClass('fila-no-aplica')
              .css({
                'opacity': '1',
                'cursor': 'pointer'
              })
              .removeAttr('title');
          }
        });
      }
    });
  });

  // Inicializar el estado según el valor actual al cargar
  $('.auto-save-control-pliego').each(function () {
    const $selectPliego = $(this);
    const valorPliego = $selectPliego.val();

    if (valorPliego === "0") {
      const idControl = $selectPliego.data('id-datelemcontr');
      const $selectIntensidad = $(`.select-intensidad[data-id-datelemcontr="${idControl}"]`);
      const $btnObservaciones = $(`.btn-observaciones-pliego[data-bs-target="#modalClausulaElem${idControl}"]`);

      // Forzar actualización en el próximo frame para sincronizar visualmente
      requestAnimationFrame(() => {
        $selectIntensidad.prop('disabled', true)
          .addClass('fila-no-aplica')
          .css({
            'opacity': '0.6',
            'cursor': 'not-allowed',
            'background-color': '#f8f9fa',
            'pointer-events': 'none'
          });

        $btnObservaciones.prop('disabled', true)
          .addClass('fila-no-aplica')
          .css({
            'opacity': '0.6',
            'cursor': 'not-allowed'
          })
          .attr('title', 'No aplica - Observaciones bloqueadas');
      });
    }
  });

  // ✨ NUEVO: Filtrado de controles por riesgo
  // 🔄 MODIFICADO: Ahora desactiva el filtro de requisito cuando se selecciona un riesgo
  function filtrarControlesPorRiesgo(esEvento = true) {
    const riesgoSeleccionado = $('#filtro-riesgo').val();
    let controlesVisibles = 0;

    // 🆕 Si se selecciona un riesgo específico (no "Mostrar todos") y es un evento de usuario
    // verificar si hay filtro de requisito activo en URL y navegar para eliminarlo
    if (esEvento && riesgoSeleccionado && riesgoSeleccionado !== '') {
      const urlParams = new URLSearchParams(window.location.search);
      const tieneRequisitoFiltro = urlParams.has('id_requisito_filtro');
      
      if (tieneRequisitoFiltro) {
        
        // Construir nueva URL sin el parámetro id_requisito_filtro pero con id_riesgo_filtro
        urlParams.delete('id_requisito_filtro');
        urlParams.set('id_riesgo_filtro', riesgoSeleccionado);
        
        // Guardar el riesgo en sessionStorage para mantenerlo tras la recarga
        sessionStorage.setItem('riesgo_a_mitigar', riesgoSeleccionado);
        
        // Navegar a la nueva URL (esto recargará sin el filtro de requisito)
        const nuevaUrl = window.location.pathname + '?' + urlParams.toString();
        window.location.href = nuevaUrl;
        return; // Salir, la página se recargará
      }
      
      // Resetear el select de requisito visualmente si existe (sin disparar su evento de cambio)
      const $filtroRequisito = $('#filtro-requisito');
      if ($filtroRequisito.length > 0 && $filtroRequisito.val() !== '') {
        $filtroRequisito.val('');
      }
    }

    if (!riesgoSeleccionado || riesgoSeleccionado === '') {
      // Mostrar todos
      $('.fila-control').each(function () {
        $(this).fadeIn(300);
        controlesVisibles++;
      });
    } else {
      // Filtrar
      $('.fila-control').each(function () {
        const $fila = $(this);
        const riesgosIds = $fila.data('riesgos-ids');


        let riesgosArray = [];

        // CAMBIO 1: Convertir SIEMPRE a string primero
        const riesgosStr = String(riesgosIds || '');

        if (riesgosStr.trim() !== '') {
          riesgosArray = riesgosStr.split(',').map(id => id.trim()).filter(id => id !== '');
        }

        // CAMBIO 2: Logs y normalización
        const riesgoStr = String(riesgoSeleccionado).trim();
        const perteneceAlRiesgo = riesgosArray.includes(riesgoStr);

        if (perteneceAlRiesgo) {
          $fila.fadeIn(300);
          controlesVisibles++;
        } else {
          $fila.fadeOut(300);
        }
      });
    }

    // Actualizar contador con animación
    $('#total-controles').fadeOut(200, function () {
      $(this).text(controlesVisibles).fadeIn(200);
    });

    // Mensaje si no hay resultados
    setTimeout(() => {
      if (controlesVisibles === 0 && $('#fila-sin-resultados').length === 0) {
        $('#tabla-controles tbody').append(
          '<tr id="fila-sin-resultados" class="table-warning" style="display: none;">' +
          '<td colspan="8" class="text-center py-4">' +
          '<i class="bi bi-exclamation-triangle-fill text-warning fs-3"></i><br>' +
          '<strong>No hay controles asociados a este riesgo</strong>' +
          '</td></tr>'
        );
        $('#fila-sin-resultados').fadeIn(300);
      } else if (controlesVisibles > 0) {
        $('#fila-sin-resultados').fadeOut(300, function () {
          $(this).remove();
        });
      }
    }, 350);

    // CAMBIO 3: Logs adicionales
  }

  // Evento de cambio
  $('#filtro-riesgo').on('change', function() {
    filtrarControlesPorRiesgo(true);
  });

  // Estilos de transición
  $('.fila-control').css('transition', 'all 0.3s ease');


  // FILTRADO AUTOMÁTICO AL CARGAR DESDE RIESGOS O DESDE URL
  function aplicarFiltroAutomatico() {
    // 🆕 Primero verificar si hay un id_riesgo_filtro en la URL (modo Ver Todos)
    const urlParams = new URLSearchParams(window.location.search);
    const riesgoDesdeURL = urlParams.get('id_riesgo_filtro');

    if (riesgoDesdeURL && $('#filtro-riesgo').length > 0) {
      const $filtroSelect = $('#filtro-riesgo');

      if ($filtroSelect.find('option[value="' + riesgoDesdeURL + '"]').length > 0) {
        $filtroSelect.val(riesgoDesdeURL);
        // 🔄 MODIFICADO: Llamar directamente sin disparar navegación (false = no es evento de usuario)
        filtrarControlesPorRiesgo(false);
        return; // Ya aplicamos el filtro, no necesitamos revisar sessionStorage
      }
    }

    // Si no hay filtro en URL, revisar sessionStorage (comportamiento original)
    const riesgoDesdeStorage = sessionStorage.getItem('riesgo_a_mitigar');

    if (riesgoDesdeStorage && $('#filtro-riesgo').length > 0) {
      const $filtroSelect = $('#filtro-riesgo');

      if ($filtroSelect.find('option[value="' + riesgoDesdeStorage + '"]').length > 0) {
        $filtroSelect.val(riesgoDesdeStorage);
        // 🔄 MODIFICADO: Llamar directamente sin disparar navegación (false = no es evento de usuario)
        filtrarControlesPorRiesgo(false);
        sessionStorage.removeItem('riesgo_a_mitigar');
      } else {
        sessionStorage.removeItem('riesgo_a_mitigar');
      }
    }
  }

  // Ejecutar inmediatamente
  aplicarFiltroAutomatico();


  // ========== ACTUALIZACIÓN EN TIEMPO REAL DEL CUADRO RESUMEN ==========
  function actualizarResumenRiesgos() {
    let totalActivos = 0;
    let totalAplicables = 0;
    let inherente = { "CRÍTICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0, "SIN_VALORAR": 0 };
    let residual = { "CRÍTICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0, "SIN_VALORAR": 0 };


    // Recorrer todas las filas de riesgos
    $('tr[data-id-riesgo]').each(function () {
      const $fila = $(this);
      const idRiesgo = $fila.data('id-riesgo');

      // ✅ CORRECCIÓN: Solo contar si L_ACTIVA = 1
      const lActiva = parseInt($fila.data('l-activa'));

      // Si la fila no está activa en BD, saltarla
      if (lActiva !== 1) {
        return; // equivalent to 'continue' in jQuery each
      }

      // Contar riesgo activo (solo los que tienen L_ACTIVA=1)
      totalActivos++;

      // Obtener valor de "¿Aplica?"
      const aplica = $fila.find('.aplica-select-riesgo').val();

      if (aplica === "1") {
        totalAplicables++;

        // Obtener nivel inherente
        const nivelInherente = $fila.find('.celda-nivel span').text().trim();
        if (inherente.hasOwnProperty(nivelInherente)) {
          inherente[nivelInherente]++;
        } else if (nivelInherente === "" || nivelInherente === "—" || !nivelInherente) {
          // Riesgo sin valoración inherente
          inherente["SIN_VALORAR"]++;
        }

        // Obtener nivel residual
        const nivelResidual = $fila.find('.celda-nivel-residual span').text().trim();
        if (residual.hasOwnProperty(nivelResidual)) {
          residual[nivelResidual]++;
        } else if (nivelResidual === "" || nivelResidual === "—" || !nivelResidual) {
          // Riesgo sin valoración residual
          residual["SIN_VALORAR"]++;
        }
      }
    });

    // Actualizar totales
    $('#resumen-total-activos').text(totalActivos);
    $('#resumen-total-aplicables').text(totalAplicables);
    $('#resumen-no-aplicables').text(totalActivos - totalAplicables);

    // Actualizar inherentes
    $('#resumen-inh-critico').text(inherente["CRÍTICO"]);
    $('#resumen-inh-alto').text(inherente["ALTO"]);
    $('#resumen-inh-medio').text(inherente["MEDIO"]);
    $('#resumen-inh-bajo').text(inherente["BAJO"]);
    $('#resumen-inh-sin-valorar').text(inherente["SIN_VALORAR"]);

    // Actualizar residuales
    $('#resumen-res-critico').text(residual["CRÍTICO"]);
    $('#resumen-res-alto').text(residual["ALTO"]);
    $('#resumen-res-medio').text(residual["MEDIO"]);
    $('#resumen-res-bajo').text(residual["BAJO"]);
    $('#resumen-res-sin-valorar').text(residual["SIN_VALORAR"]);

    // Calcular efectividad de controles
    const totalInh = inherente["CRÍTICO"] + inherente["ALTO"] + inherente["MEDIO"] + inherente["BAJO"];
    const totalRes = residual["CRÍTICO"] + residual["ALTO"] + residual["MEDIO"] + residual["BAJO"];

    if (totalInh > 0) {
      const reduccion = ((1 - totalRes / totalInh) * 100).toFixed(1);
      $('#resumen-efectividad').text(reduccion + '%');
    } else {
      $('#resumen-efectividad').text('N/A');
    }

    // Actualizar completitud
    const todosCompletos = verificarCompletitudRiesgos();
    if (todosCompletos) {
      $('#resumen-completitud').html('<i class="bi bi-check-circle-fill"></i> 100%')
        .removeClass('text-warning').addClass('text-success');
    } else {
      $('#resumen-completitud').html('<i class="bi bi-hourglass-split"></i> Pendiente')
        .removeClass('text-success').addClass('text-warning');
    }

    actualizarBarrasProgreso();
  }

  // Función auxiliar para verificar completitud
  function verificarCompletitudRiesgos() {
    let todosCompletos = true;

    $('tr[data-id-riesgo]').each(function () {
      const $fila = $(this);
      const aplica = $fila.find('.aplica-select-riesgo').val();

      if (aplica === "1") {
        const impacto = $fila.find('.select-impacto').val();
        const probabilidad = $fila.find('.select-probabilidad').val();

        // Verificar que tenga impacto y probabilidad
        if (!impacto || !probabilidad) {
          todosCompletos = false;
          return false; // Salir del bucle
        }
      }
    });

    return todosCompletos;
  }

  if ($('tr[data-id-riesgo]').length > 0) {
    actualizarResumenRiesgos();
  }

  // Inicializar estado de los botones "Mitigar Riesgo"
  $('.mitigar-riesgo-btn').each(function () {
    const idDatRiesgo = $(this).data('id-dat-riesgo');
    actualizarBotonMitigar(idDatRiesgo);
  });

  // 🆕 VALIDACIÓN INICIAL AL CARGAR LA PÁGINA
  // Ejecutar validación para todos los controles visibles
  $('.fila-control[data-id-control]').each(function() {
    const idControl = $(this).data('id-control');
    validarControlEnTiempoReal(idControl);
  });

});

// --- FUNCIONES GLOBALES ---
function verificarEstado() {
  const nombre = $("#nombre_proyecto").val()?.trim() || "";
  const fecha = $("#fecha_inicio").val()?.trim() || "";
  const dpd = $("#dpd_responsable").val()?.trim() || "";
  const todosRellenos = nombre && fecha && dpd;
  $("#estado_proyecto").val(todosRellenos ? "Configurado" : "Pendiente de configuración");
}

function actualizarEstadoElementoGlobal(idElem) {
  const textareas = $(`textarea[data-idelem='${idElem}']`);
  const total = textareas.length;
  let completados = 0;
  textareas.each(function () {
    if ($(this).val().trim() !== "") {
      completados++;
    }
  });
  let estado = "PENDIENTE";
  let icono = "⏳";
  let clase = "text-secondary";
  if (completados === total && total > 0) {
    estado = "COMPLETADO";
    icono = "✅";
    clase = "text-success";
  } else if (completados > 0) {
    estado = "EN PROGRESO";
    icono = "📝";
    clase = "text-primary";
  }
  const filaPrincipal = $(`tr[data-idelem='${idElem}']:not([data-niteracion])`);
  if (filaPrincipal.length) {
    filaPrincipal.find(".estado")
      .text(`${icono} ${estado}`)
      .removeClass("text-secondary text-primary text-success")
      .addClass(clase);
    filaPrincipal.find(".progreso").text(`${completados}/${total}`);
  }
}

function actualizarEstadoElemento(idElem, nIteracion) {
  const textareas = $(`textarea[data-idelem='${idElem}'][data-niteracion='${nIteracion}']`);
  const total = textareas.length;
  let completados = 0;
  textareas.each(function () {
    if ($(this).val().trim() !== "") {
      completados++;
    }
  });
  let estado = "PENDIENTE";
  let icono = "⏳";
  let clase = "text-secondary";
  if (completados === total) {
    estado = "COMPLETADO";
    icono = "✅";
    clase = "text-success";
  } else if (completados > 0) {
    estado = "EN PROGRESO";
    icono = "📝";
    clase = "text-primary";
  }
  const fila = $(`tr[data-idelem='${idElem}'][data-niteracion='${nIteracion}']`);
  fila.find(".estado")
    .text(`${icono} ${estado}`)
    .removeClass("text-secondary text-primary text-success")
    .addClass(clase);
  fila.find(".progreso").text(`${completados}/${total}`);
}

function actualizarTodos() {
  const elementos = new Set();
  $("textarea[data-idelem]").each(function () {
    const idElem = $(this).data("idelem");
    elementos.add(idElem);
  });
  elementos.forEach(idElem => {
    actualizarEstadoElementoGlobal(idElem);
    const iteraciones = new Set();
    $(`textarea[data-idelem='${idElem}']`).each(function () {
      const nIter = $(this).data("niteracion");
      if (nIter !== undefined) iteraciones.add(nIter);
    });
    iteraciones.forEach(nIter => {
      actualizarEstadoElemento(idElem, nIter);
    });
  });
}

// Función para guardar cambios automáticamente (genérica)
function guardarCambioAuto(idRegistro, campo, valor, tipo) {
  const claveSolicitud = `${idRegistro}_${campo}_${tipo}`;
  if (window.guardandoCampos && window.guardandoCampos[claveSolicitud]) {
    return;
  }
  if (!window.guardandoCampos) {
    window.guardandoCampos = {};
  }
  window.guardandoCampos[claveSolicitud] = true;

  // --- NUEVO: Capturar el elemento select ANTES de enviar la petición ---
  let selectElement = null;
  if (tipo === 'control' && campo === 'aplica') {
    selectElement = document.querySelector(`.aplica-select-control[data-id-control="${idRegistro}"]`);
  }

  let urlEndpoint = '';
  if (tipo === 'riesgo') {
    urlEndpoint = '/guardar-cambio-riesgo';
  } else if (tipo === 'control') {
    urlEndpoint = '/guardar-cambio-control';
  } else {
    delete window.guardandoCampos[claveSolicitud];
    return;
  }

  fetch(urlEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      id_registro: idRegistro,
      campo: campo,
      valor: valor
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {

        // 🆕 Refrescar Riesgo Global si cambió un campo que afecta al cálculo
        if (tipo === 'riesgo' && campo === 'aplica') {
          if (typeof RiesgoGlobal !== 'undefined' && RiesgoGlobal.refrescar) {
            RiesgoGlobal.refrescar();
          }
        }
      } else {
        // --- NUEVO: Revertir el cambio en la UI y disparar el evento 'change' ---
        if (selectElement) {
          selectElement.value = '1'; // Forzar a "Sí"
          // Disparar el evento 'change' manualmente para actualizar la UI
          const event = new Event('change', { bubbles: true });
          selectElement.dispatchEvent(event);
        }
        // Mostrar el modal de error
        const modalError = new bootstrap.Modal(document.getElementById('modalErrorValidacion'));
        document.getElementById('mensajeErrorValidacion').textContent = data.error;
        modalError.show();
      }
    })
    .catch(error => {
      // --- NUEVO: Revertir el cambio en la UI en caso de error de red ---
      if (selectElement) {
        selectElement.value = '1'; // Forzar a "Sí"
        // Disparar el evento 'change' manualmente para actualizar la UI
        const event = new Event('change', { bubbles: true });
        selectElement.dispatchEvent(event);
      }
    })
    .finally(() => {
      delete window.guardandoCampos[claveSolicitud];
    });
}

function updateModalTextarea(fieldName, modalId, tipo) {
  const modal = document.getElementById(modalId);
  if (!modal) {
    return;
  }
  const textarea = modal.querySelector(`textarea[name="${fieldName}"]`);
  if (!textarea) {
    return;
  }
  const value = textarea.value.trim();
  const button = document.querySelector(`button[data-bs-target="#${modalId}"]`);
  if (button) {
    if (value) {
      button.textContent = value.length > 40 ? value.substring(0, 37) + '...' : value;
    } else {
      button.innerHTML = '<em>No hay justificación</em>';
    }
  }
  let idRegistro, campo;
  if (fieldName.startsWith('jus_clausula_')) {
    campo = 'jus_clausula';
    idRegistro = fieldName.replace('jus_clausula_', '');
    guardarCambioAuto(idRegistro, campo, value, 'control');
  }
  else if (fieldName.startsWith('observaciones_')) {
    campo = 'observaciones';
    idRegistro = fieldName.replace('observaciones_', '');
    guardarCambioAuto(idRegistro, campo, value, 'control');
  }
  else if (fieldName.startsWith('jus_aplica_')) {
    campo = 'jus_aplica';
    idRegistro = fieldName.replace('jus_aplica_', '');
    guardarCambioAuto(idRegistro, campo, value, 'riesgo');
  }
  else if (fieldName.startsWith('jus_impacto_')) {
    campo = 'jus_impacto';
    idRegistro = fieldName.replace('jus_impacto_', '');
    guardarCambioAuto(idRegistro, campo, value, 'riesgo');
  }
  else if (fieldName.startsWith('jus_prob_')) {
    campo = 'jus_prob';
    idRegistro = fieldName.replace('jus_prob_', '');
    guardarCambioAuto(idRegistro, campo, value, 'riesgo');
  }
  else {
  }
  const modalInstance = bootstrap.Modal.getInstance(modal);
  if (modalInstance) {
    modalInstance.hide();
  } else {
    $(modal).modal('hide');
  }
}

function actualizarBotonMitigar(idDatRiesgo) {
  // Buscar ambos tipos de botones: normales y personalizados
  const $botonNormal = $(`.mitigar-riesgo-btn[data-id-dat-riesgo="${idDatRiesgo}"]`);
  const $botonPersonal = $(`.mitigar-riesgo-personal-btn[data-id-dat-riesgo="${idDatRiesgo}"]`);
  const $selectAplica = $(`.aplica-select-riesgo[data-id-riesgo="${idDatRiesgo}"]`);

  if ($selectAplica.length === 0) {
    return;
  }

  const aplica = $selectAplica.val() === '1';

  // Actualizar botón normal (riesgos no personalizados)
  if ($botonNormal.length) {
    if (aplica) {
      // Mostrar y habilitar el botón
      $botonNormal.removeClass('d-none')
        .prop('disabled', false)
        .removeClass('disabled')
        .removeAttr('title')
        .css({
          'opacity': '1',
          'cursor': 'pointer'
        });
    } else {
      // Ocultar el botón
      $botonNormal.addClass('d-none')
        .prop('disabled', true)
        .addClass('disabled')
        .attr('title', 'No se puede mitigar un riesgo que no aplica')
        .css({
          'opacity': '0.6',
          'cursor': 'not-allowed'
        });
    }
  }

  // Actualizar botón personalizado (riesgos personalizados)
  if ($botonPersonal.length) {
    if (aplica) {
      // Mostrar y habilitar el botón
      $botonPersonal.removeClass('d-none')
        .prop('disabled', false)
        .removeClass('disabled')
        .removeAttr('title')
        .css({
          'opacity': '1',
          'cursor': 'pointer'
        });
    } else {
      // Ocultar el botón
      $botonPersonal.addClass('d-none')
        .prop('disabled', true)
        .addClass('disabled')
        .attr('title', 'No se puede mitigar un riesgo que no aplica')
        .css({
          'opacity': '0.6',
          'cursor': 'not-allowed'
        });
    }
  }

  // Si no se encontró ningún botón, puede ser normal si el riesgo está inactivo
  if ($botonNormal.length === 0 && $botonPersonal.length === 0) {
  }
}

// ========== VALIDACIÓN DINÁMICA DE CONTROLES ==========
// Esta función verifica si un control cumple con la validación de fase

function validarControlEnTiempoReal(idDatControl) {
  const $fila = $(`.fila-control[data-id-control="${idDatControl}"]`);

  if ($fila.length === 0) return;

  // 🆕 VERIFICAR SI ESTE CONTROL DEBE SER VALIDADO EN LA FASE ACTUAL
  const debeValidarse = $fila.data('debe-validarse') === 1;

  if (!debeValidarse) {
    // Este control no debe ser validado todavía en esta fase
    quitarMarcaInvalida($fila, idDatControl);
    return;
  }

  // Obtener valores actuales
  const aplica = $fila.find('.aplica-select-control').val();
  const madurezId = $fila.find('.select-madurez').val();
  const madurezMinima = $fila.find('.select-madurez').data('madurez-minima');

  // Si no aplica, el control es válido (no necesita validación)
  if (aplica === "0") {
    quitarMarcaInvalida($fila, idDatControl);
    return;
  }

  // Si aplica pero no tiene madurez informada, es inválido
  if (!madurezId || madurezId === "") {
    marcarComoInvalido($fila, idDatControl, "Sin nivel de madurez informado");
    return;
  }

  // Si no hay madurez mínima definida, es válido
  if (!madurezMinima || madurezMinima === "0") {
    quitarMarcaInvalida($fila, idDatControl);
    return;
  }

  // Obtener el valor numérico de la madurez actual
  const $optionActual = $fila.find(`.select-madurez option[value="${madurezId}"]`);
  const madurezActualValor = parseInt($optionActual.data('valor')) || 0;
  const madurezMinimaValor = parseInt(madurezMinima) || 0;


  // Validar: madurez actual >= madurez mínima
  if (madurezActualValor >= madurezMinimaValor) {
    quitarMarcaInvalida($fila, idDatControl);
  } else {
    marcarComoInvalido($fila, idDatControl, "Nivel de madurez insuficiente para esta fase");
  }
}

// Función para marcar un control como inválido
function marcarComoInvalido($fila, idDatControl, mensaje) {
  // Agregar clase de fila inválida
  $fila.addClass('fila-control-invalida');

  // ✨ NO mostrar el icono de alerta si el control está inactivo (L_ACTIVA = 0)
  const lActiva = $fila.attr('data-l-activa');
  if (lActiva === '0') {
    // El control está inactivo, no mostrar el icono
    return;
  }

  // Agregar icono de advertencia si no existe
  const $primeraCelda = $fila.find('td:first-child');
  if ($primeraCelda.find('.icono-control-invalido').length === 0) {
    $primeraCelda.append(
      `<i class="bi bi-exclamation-triangle-fill icono-control-invalido"
          title="${mensaje}"></i>`
    );
  } else {
    // Actualizar el título del icono existente
    $primeraCelda.find('.icono-control-invalido').attr('title', mensaje);
  }
}

// Función para quitar la marca de inválido
function quitarMarcaInvalida($fila, idDatControl) {
  // Quitar clase de fila inválida
  $fila.removeClass('fila-control-invalida');

  // Quitar icono de advertencia
  $fila.find('.icono-control-invalido').remove();
}

// ========== ACTIVACIÓN DE RIESGOS INACTIVOS ==========
function confirmarActivacionRiesgo() {
  return new Promise((resolve) => {
    const modalEl = document.getElementById('modalConfirmarActivarRiesgo');
    const modal = new bootstrap.Modal(modalEl);

    const confirmarBtn = modalEl.querySelector('#btnConfirmarActivacion');
    const cancelarBtns = modalEl.querySelectorAll('[data-bs-dismiss="modal"]');

    const onConfirmar = () => {
      limpiar();
      resolve(true);
    };
    const onCancelar = () => {
      limpiar();
      resolve(false);
    };

    function limpiar() {
      confirmarBtn.removeEventListener('click', onConfirmar);
      cancelarBtns.forEach(btn => btn.removeEventListener('click', onCancelar));
      modal.hide();
    }

    confirmarBtn.addEventListener('click', onConfirmar);
    cancelarBtns.forEach(btn => btn.addEventListener('click', onCancelar));

    modal.show();
  });
}
/**
 * Activa un riesgo que estaba inactivo (L_ACTIVA=0) en la base de datos.
 * @param {number} idRiesgoOriginal - ID del riesgo original (RIE_ID_RIESGO)
 */
async function activarRiesgo(idRiesgoOriginal) {
  const confirmado = await confirmarActivacionRiesgo();
  if (!confirmado) return;


  fetch('/activar-riesgo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_riesgo: idRiesgoOriginal })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('ver_todos') === '1') {
          window.location.href = window.location.pathname + '?ver_todos=1';
        } else {
          (function(){ var u=new URL(window.location.href); u.searchParams.set("_t",Date.now()); window.location.href=u.toString(); })();
        }
      } else {
        alert('Error al activar el riesgo: ' + data.error);
      }
    })
    .catch(error => {
      alert('Error de red al activar el riesgo. Por favor, inténtelo de nuevo.');
    });
}

// ========== ACTIVACIÓN DE CONTROLES INACTIVOS ==========
function confirmarActivacionControl() {
  return new Promise((resolve) => {
    const modalEl = document.getElementById('modalConfirmarActivarControl');
    const modal = new bootstrap.Modal(modalEl);

    const confirmarBtn = modalEl.querySelector('#btnConfirmarActivacionControl');
    const cancelarBtns = modalEl.querySelectorAll('[data-bs-dismiss="modal"]');

    const onConfirmar = () => {
      limpiar();
      resolve(true);
    };
    const onCancelar = () => {
      limpiar();
      resolve(false);
    };

    function limpiar() {
      confirmarBtn.removeEventListener('click', onConfirmar);
      cancelarBtns.forEach(btn => btn.removeEventListener('click', onCancelar));
      modal.hide();
    }

    confirmarBtn.addEventListener('click', onConfirmar);
    cancelarBtns.forEach(btn => btn.addEventListener('click', onCancelar));

    modal.show();
  });
}
/**
 * Activa un control que estaba inactivo (L_ACTIVA=0) en la base de datos.
 * @param {number} idControlOriginal - ID del control original (CON_ID_CONTROL)
 */
async function activarControl(idControlOriginal) {
  const confirmado = await confirmarActivacionControl();
  if (!confirmado) return;


  fetch('/activar-control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_control: idControlOriginal })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const urlParams = new URLSearchParams(window.location.search);

        // 🆕 FIX: Mantener el filtro activo al recargar la página
        // 🔄 MODIFICADO: Ahora respeta la exclusividad de filtros
        if (urlParams.get('ver_todos') === '1') {
          // Construir la URL preservando ver_todos y el filtro activo
          let reloadUrl = window.location.pathname + '?ver_todos=1';

          // Verificar parámetros existentes
          const idSistema = urlParams.get('id_sistema');
          const idRiesgoFiltro = urlParams.get('id_riesgo_filtro');
          const idRequisitoFiltro = urlParams.get('id_requisito_filtro');

          // Añadir id_sistema si existe
          if (idSistema) {
            reloadUrl += '&id_sistema=' + encodeURIComponent(idSistema);
          }

          // 🔄 EXCLUSIVIDAD: Prioridad al filtro de requisito
          if (idRequisitoFiltro) {
            reloadUrl += '&id_requisito_filtro=' + encodeURIComponent(idRequisitoFiltro);
          } else if (idRiesgoFiltro) {
            // Solo añadir riesgo si NO hay requisito
            reloadUrl += '&id_riesgo_filtro=' + encodeURIComponent(idRiesgoFiltro);
          }

          window.location.href = reloadUrl;
        } else {
          (function(){ var u=new URL(window.location.href); u.searchParams.set("_t",Date.now()); window.location.href=u.toString(); })();
        }
      } else {
        alert('Error al activar el control: ' + data.error);
      }
    })
    .catch(error => {
      alert('Error de red al activar el control. Por favor, inténtelo de nuevo.');
    });
}

// ========== VALIDACIÓN DE INCOMPATIBILIDADES ADI ==========

/**
 * Obtiene todas las respuestas actualmente seleccionadas en el formulario
 * @returns {Array<number>} Array de IDs de respuestas seleccionadas
 */
function obtenerRespuestasSeleccionadas() {
  const respuestasSeleccionadas = [];

  // Selects (preguntas de respuesta única)
  $('select[name^="pregunta_"]').each(function () {
    const valor = $(this).val();
    if (valor) {
      // El valor es "C_OPCION,N_PTOSBASE", extraer el ID_RESPUESTA
      const preguntaId = parseInt($(this).attr('name').replace('pregunta_', ''));
      const cOpcion = valor.split(',')[0];

      // Buscar el ID_RESPUESTA correspondiente en el DOM
      const $option = $(this).find('option:selected');
      const idRespuesta = $option.data('id-respuesta');

      if (idRespuesta) {
        respuestasSeleccionadas.push(parseInt(idRespuesta));
      }
    }
  });

  // Checkboxes (preguntas de respuesta múltiple)
  $('input[type="checkbox"][name^="pregunta_"]:checked').each(function () {
    const idRespuesta = $(this).data('id-respuesta');
    if (idRespuesta) {
      respuestasSeleccionadas.push(parseInt(idRespuesta));
    }
  });

  return respuestasSeleccionadas;
}

/**
 * Valida si una respuesta es compatible con las ya seleccionadas
 * @param {number} idRespuesta - ID de la respuesta a validar
 * @param {Array<number>} respuestasActuales - IDs de respuestas ya seleccionadas
 * @returns {Promise<Object>} Resultado de la validación
 */
async function validarIncompatibilidadADI(idRespuesta, respuestasActuales) {
  try {
    const response = await fetch('/api/validar-incompatibilidad-adi', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        respuesta_seleccionada: idRespuesta,
        respuestas_actuales: respuestasActuales
      })
    });

    const data = await response.json();

    if (!response.ok) {
      return { tiene_incompatibilidad: false };
    }

    return data;
  } catch (error) {
    return { tiene_incompatibilidad: false };
  }
}

/**
 * Muestra el modal de prohibición
 * @param {Object} incompatibilidad - Datos de la incompatibilidad
 */
function mostrarModalProhibicion(incompatibilidad) {
  const incompat = incompatibilidad.incompatibilidades[0]; // Solo la primera

  const mensaje = `Es incompatible con la respuesta
        <strong>"${incompat.respuesta_codigo} - ${incompat.respuesta_texto}"</strong>
        a la pregunta
        <strong>"${incompat.pregunta_codigo}. ${incompat.pregunta_texto}"</strong>`;

  $('#mensajeProhibicion').html(mensaje);

  if (incompat.mensaje && incompat.mensaje.trim() !== '') {
    $('#mensajeAdicionalProhibicion').html(
      `<div class="alert alert-light border">
                <strong>Información adicional:</strong><br>
                ${incompat.mensaje}
            </div>`
    );
  } else {
    $('#mensajeAdicionalProhibicion').html('');
  }

  const modal = new bootstrap.Modal(document.getElementById('modalIncompatibilidadProhibida'));
  modal.show();
}

/**
 * Muestra el modal de aviso con tabla de incompatibilidades
 * @param {Object} incompatibilidad - Datos de las incompatibilidades
 */
function mostrarModalAviso(incompatibilidad) {
  const tbody = $('#tbodyIncompatibilidades');
  tbody.empty();

  incompatibilidad.incompatibilidades.forEach(incompat => {
    const fila = `
            <tr>
                <td class="fw-bold">${incompat.pregunta_codigo}</td>
                <td>${incompat.respuesta_codigo} - ${incompat.respuesta_texto}</td>
                <td class="text-muted">${incompat.mensaje || '<em>Sin observaciones adicionales</em>'}</td>
            </tr>
        `;
    tbody.append(fila);
  });

  const modal = new bootstrap.Modal(document.getElementById('modalIncompatibilidadAviso'));
  modal.show();
}

/**
 * Revertir selección de un select (respuesta única)
 * @param {jQuery} $select - Elemento select
 * @param {string} valorAnterior - Valor anterior a restaurar
 */
function revertirSelect($select, valorAnterior) {
  $select.val(valorAnterior);
}

/**
 * Revertir selección de un checkbox (respuesta múltiple)
 * @param {jQuery} $checkbox - Elemento checkbox
 */
function revertirCheckbox($checkbox) {
  $checkbox.prop('checked', false);
}

/**
 * Obtiene el ID_RESPUESTA desde el valor del select o atributo data
 */
function obtenerIdRespuestaDesdeSelect($select) {
  const $option = $select.find('option:selected');
  let idRespuesta = $option.data('id-respuesta');

  // Si no existe data-id-respuesta, intentar inferir del DOM
  if (!idRespuesta) {
    // Buscar en la estructura de respuestas del backend
    const preguntaId = parseInt($select.attr('name').replace('pregunta_', ''));
    const cOpcion = $select.val().split(',')[0];

    // Aquí podrías tener una estructura global con el mapeo
    // Por ahora, asumir que está en un atributo data
  }

  return idRespuesta ? parseInt(idRespuesta) : null;
}

/**
 * Obtiene el ID_RESPUESTA desde el checkbox
 */
function obtenerIdRespuestaDesdeCheckbox($checkbox) {
  const idRespuesta = $checkbox.data('id-respuesta');
  return idRespuesta ? parseInt(idRespuesta) : null;
}

// ========== EVENT LISTENERS ==========

$(document).ready(function () {

  // --- VALIDACIÓN PARA SELECTS (Respuesta única) ---
  $('select[name^="pregunta_"]').on('change', async function (e) {
    const $select = $(this);
    const valorNuevo = $select.val();
    const valorAnterior = $select.data('valor-anterior') || '';

    // Si no hay valor nuevo o es vacío, no validar
    if (!valorNuevo || valorNuevo === '') {
      $select.data('valor-anterior', '');
      return;
    }

    const idRespuesta = obtenerIdRespuestaDesdeSelect($select);

    if (!idRespuesta) {
      $select.data('valor-anterior', valorNuevo);
      return;
    }

    // Obtener respuestas actuales (excluyendo la que se está validando)
    let respuestasActuales = obtenerRespuestasSeleccionadas();
    respuestasActuales = respuestasActuales.filter(id => id !== idRespuesta);

    // Validar incompatibilidad
    const validacion = await validarIncompatibilidadADI(idRespuesta, respuestasActuales);

    if (validacion.tiene_incompatibilidad) {
      if (validacion.tipo === 'P') {
        // PROHIBICIÓN: Revertir y mostrar modal
        revertirSelect($select, valorAnterior);
        mostrarModalProhibicion(validacion);
      } else if (validacion.tipo === 'A') {
        // AVISO: Mostrar modal pero mantener selección
        mostrarModalAviso(validacion);
        $select.data('valor-anterior', valorNuevo);
      }
    } else {
      // No hay incompatibilidad, actualizar valor anterior
      $select.data('valor-anterior', valorNuevo);
    }
  });

  // Inicializar valores anteriores en selects
  $('select[name^="pregunta_"]').each(function () {
    $(this).data('valor-anterior', $(this).val() || '');
  });

  // --- VALIDACIÓN PARA CHECKBOXES (Respuesta múltiple) ---
  $('input[type="checkbox"][name^="pregunta_"]').on('change', async function (e) {
    const $checkbox = $(this);
    const estaChecked = $checkbox.is(':checked');

    // Solo validar si se está MARCANDO (no al desmarcar)
    if (!estaChecked) {
      return;
    }

    const idRespuesta = obtenerIdRespuestaDesdeCheckbox($checkbox);

    if (!idRespuesta) {
      return;
    }

    // Obtener respuestas actuales (excluyendo la que se está validando)
    let respuestasActuales = obtenerRespuestasSeleccionadas();
    respuestasActuales = respuestasActuales.filter(id => id !== idRespuesta);

    // Validar incompatibilidad
    const validacion = await validarIncompatibilidadADI(idRespuesta, respuestasActuales);

    if (validacion.tiene_incompatibilidad) {
      if (validacion.tipo === 'P') {
        // PROHIBICIÓN: Desmarcar y mostrar modal
        revertirCheckbox($checkbox);
        mostrarModalProhibicion(validacion);
      } else if (validacion.tipo === 'A') {
        // AVISO: Mostrar modal pero mantener marcado
        mostrarModalAviso(validacion);
      }
    }
  });

  // --- CERRAR MODAL DE AVISO Y CONFIRMAR SELECCIÓN ---
  $('#btnAceptarAviso').on('click', function () {
    const modal = bootstrap.Modal.getInstance(document.getElementById('modalIncompatibilidadAviso'));
    if (modal) {
      modal.hide();
    }
    // La selección ya está aplicada, solo cerrar el modal
  });

});
