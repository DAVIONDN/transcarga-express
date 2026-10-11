/* TransCarga Express — interacciones reales mínimas.
   Sin validaciones ni lógica de negocio: solo navegación compacta,
   mostrar/ocultar contraseña y cierre del panel móvil al navegar. */
(function () {
  "use strict";

  /* Barra lateral compacta en escritorio (se recuerda por navegador). */
  var alternar = document.getElementById("alternarNav");
  var CLAVE = "tc-nav-compacta";

  function sincronizar() {
    if (!alternar) {
      return;
    }
    var compacta = document.body.classList.contains("nav-compacta");
    alternar.setAttribute("aria-expanded", String(!compacta));
  }

  try {
    if (window.localStorage && localStorage.getItem(CLAVE) === "1") {
      document.body.classList.add("nav-compacta");
    }
  } catch (error) {
    /* Sin almacenamiento: la navegación sigue funcionando expandida. */
  }

  if (alternar) {
    sincronizar();
    alternar.addEventListener("click", function () {
      document.body.classList.toggle("nav-compacta");
      try {
        localStorage.setItem(
          CLAVE,
          document.body.classList.contains("nav-compacta") ? "1" : "0"
        );
      } catch (error) {
        /* Sin almacenamiento: solo se aplica en esta visita. */
      }
      sincronizar();
    });
  }

  /* Mostrar u ocultar la contraseña del acceso (accesible). */
  document.querySelectorAll("[data-mostrar-clave]").forEach(function (boton) {
    var objetivo = document.getElementById(boton.getAttribute("aria-controls"));
    if (!objetivo) {
      return;
    }
    boton.addEventListener("click", function () {
      var visible = objetivo.getAttribute("type") === "text";
      objetivo.setAttribute("type", visible ? "password" : "text");
      boton.setAttribute("aria-pressed", String(!visible));
      boton.textContent = visible ? "Mostrar" : "Ocultar";
    });
  });

  /* En móvil, cerrar el panel lateral al elegir una opción. */
  var barra = document.getElementById("barraLateral");
  if (barra && window.bootstrap && window.innerWidth < 992) {
    barra.querySelectorAll("a.nav-link").forEach(function (enlace) {
      enlace.addEventListener("click", function () {
        var panel = window.bootstrap.Offcanvas.getInstance(barra);
        if (panel) {
          panel.hide();
        }
      });
    });
  }
})();
