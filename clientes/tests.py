"""Pruebas de empresas clientes."""

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from comun.pruebas import PruebaAutenticada, crear_empresa_cliente, crear_oferta
from clientes.forms import EmpresaClienteForm


class EmpresaClienteTests(PruebaAutenticada):
    def datos(self, **cambios):
        datos = {
            "ruc": "20987654321",
            "razon_social": "Agroindustrias del Sur S.A.C.",
            "direccion": "Carretera Panamericana Sur km 45",
            "actividad_economica": "Agroindustria",
        }
        datos.update(cambios)
        return datos

    def test_alta_correcta(self):
        respuesta = self.client.post(reverse("clientes:crear"), self.datos())

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(self.client.session is not None)

    def test_ruc_debe_tener_11_digitos(self):
        # T-26
        respuesta = self.client.post(reverse("clientes:crear"), self.datos(ruc="2098765432"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "RUC debe tener 11 dígitos")

    def test_ruc_debe_contener_solo_digitos(self):
        respuesta = self.client.post(reverse("clientes:crear"), self.datos(ruc="2098765432A"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "solo dígitos")

    def test_ruc_es_unico(self):
        crear_empresa_cliente(ruc="20111111111")
        respuesta = self.client.post(reverse("clientes:crear"), self.datos(ruc="20111111111"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya existe una empresa cliente")

    def test_una_empresa_puede_tener_varias_ofertas_y_distintos_transportistas(self):
        empresa = crear_empresa_cliente()
        primera = crear_oferta(empresa=empresa, destino="Trujillo")
        segunda = crear_oferta(empresa=empresa, destino="Cusco", nivel_requerido=2)

        respuesta = self.client.get(reverse("clientes:detalle", args=[empresa.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["ofertas"]), 2)
        self.assertIn(segunda, [oferta for oferta in respuesta.context["ofertas"]])

    def test_los_campos_obligatorios_se_exigen_en_el_servidor(self):
        formulario = EmpresaClienteForm(data={"ruc": "", "razon_social": ""})

        self.assertFalse(formulario.is_valid())
        self.assertIn("ruc", formulario.errors)
        self.assertIn("razon_social", formulario.errors)

    def test_no_se_borra_una_empresa_con_ofertas(self):
        empresa = crear_empresa_cliente()
        crear_oferta(empresa=empresa)

        with self.assertRaises(ProtectedError):
            empresa.delete()


class ModuloClientesTests(PruebaAutenticada):
    """Ciclo del módulo: edición, búsqueda por RUC y razón social y filtros."""

    def datos(self, **cambios):
        datos = {
            "ruc": "20987654321",
            "razon_social": "Agroindustrias del Sur S.A.C.",
            "direccion": "Carretera Panamericana Sur km 45",
            "actividad_economica": "Agroindustria",
        }
        datos.update(cambios)
        return datos

    def test_edicion_de_una_empresa_cliente(self):
        empresa = crear_empresa_cliente()

        respuesta = self.client.post(
            reverse("clientes:editar", args=[empresa.pk]),
            self.datos(ruc=empresa.ruc, razon_social="Razón Social Actualizada S.A.C."),
        )

        self.assertEqual(respuesta.status_code, 302)
        empresa.refresh_from_db()
        self.assertEqual(empresa.razon_social, "Razón Social Actualizada S.A.C.")

    def test_busqueda_por_ruc_y_por_razon_social(self):
        buscada = crear_empresa_cliente(ruc="20999888777", razon_social="Buscada S.A.C.")
        crear_empresa_cliente(razon_social="Otra Empresa S.A.C.")

        por_ruc = self.client.get(reverse("clientes:lista"), {"q": "20999888777"})
        self.assertEqual(list(por_ruc.context["empresas"]), [buscada])

        por_nombre = self.client.get(reverse("clientes:lista"), {"q": "Buscada"})
        self.assertEqual(list(por_nombre.context["empresas"]), [buscada])

    def test_el_listado_muestra_el_numero_de_ofertas(self):
        empresa = crear_empresa_cliente(razon_social="Con Dos Ofertas S.A.C.")
        crear_oferta(empresa=empresa, destino="Trujillo")
        crear_oferta(empresa=empresa, destino="Cusco")

        respuesta = self.client.get(reverse("clientes:lista"))

        self.assertEqual(respuesta.context["empresas"][0].total_ofertas, 2)

    def test_filtro_por_empresas_con_y_sin_ofertas(self):
        con_ofertas = crear_empresa_cliente(razon_social="Con Ofertas S.A.C.")
        sin_ofertas = crear_empresa_cliente(razon_social="Sin Ofertas S.A.C.")
        crear_oferta(empresa=con_ofertas)

        con_filtro = self.client.get(reverse("clientes:lista"), {"ofertas": "con"})
        self.assertEqual(list(con_filtro.context["empresas"]), [con_ofertas])

        sin_filtro = self.client.get(reverse("clientes:lista"), {"ofertas": "sin"})
        self.assertEqual(list(sin_filtro.context["empresas"]), [sin_ofertas])

    def test_la_ficha_muestra_las_ofertas_de_la_empresa(self):
        empresa = crear_empresa_cliente()
        oferta = crear_oferta(empresa=empresa, destino="Trujillo")

        respuesta = self.client.get(reverse("clientes:detalle", args=[empresa.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, oferta.codigo)
        self.assertContains(respuesta, "Trujillo")
        self.assertContains(respuesta, empresa.ruc)
