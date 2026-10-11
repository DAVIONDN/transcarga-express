"""Mezclas reutilizables para los formularios del proyecto (Bootstrap 5)."""

from django import forms


class FormularioBootstrapMixin:
    """Aplica las clases de Bootstrap 5 a todos los campos de un formulario.

    No sustituye a la validación del servidor: solo mejora la presentación.
    """

    clase_por_defecto = "form-control"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.HiddenInput):
                continue
            widget.attrs["class"] = self._clase_para(widget, widget.attrs.get("class", ""))
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"

    def _clase_para(self, widget, clases_existentes):
        if isinstance(widget, forms.CheckboxInput):
            clase = "form-check-input"
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            clase = "form-select"
        elif isinstance(widget, (forms.ClearableFileInput, forms.FileInput)):
            clase = "form-control"
        else:
            clase = self.clase_por_defecto
        return f"{clases_existentes} {clase}".strip()
