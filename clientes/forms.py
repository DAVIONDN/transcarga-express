"""Formularios de empresas clientes (validación del lado del servidor)."""

from django import forms

from comun.forms import FormularioBootstrapMixin

from .models import EmpresaCliente


class EmpresaClienteForm(FormularioBootstrapMixin, forms.ModelForm):
    class Meta:
        model = EmpresaCliente
        fields = ("ruc", "razon_social", "direccion", "actividad_economica")
        help_texts = {
            "ruc": "11 dígitos, sin guiones ni espacios.",
            "actividad_economica": "Por ejemplo: comercio al por mayor, manufactura, minería.",
        }
        error_messages = {
            "ruc": {"unique": "Ya existe una empresa cliente registrada con este RUC."},
        }

    def clean_ruc(self):
        ruc = (self.cleaned_data.get("ruc") or "").strip()
        if not ruc:
            return ruc
        if not ruc.isdigit():
            raise forms.ValidationError("El RUC debe contener solo dígitos.")
        if len(ruc) != 11:
            raise forms.ValidationError("El RUC debe tener 11 dígitos.")
        return ruc
