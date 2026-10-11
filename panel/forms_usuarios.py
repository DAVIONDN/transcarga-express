"""Formularios de gestión de usuarios (creación, edición y contraseña)."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm

from comun.forms import FormularioBootstrapMixin
from comun.permisos import (
    GRUPO_ADMINISTRADOR,
    asignar_rol,
    es_ultimo_administrador_activo,
    roles_disponibles,
)

Usuario = get_user_model()


class _FormularioConRolMixin:
    """Añade el campo `rol` y la política de roles exclusivos a un formulario de usuario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rol"] = forms.ChoiceField(
            label="Rol", choices=roles_disponibles()
        )
        if getattr(self, "instance", None) and self.instance.pk:
            grupo = self.instance.groups.filter(
                name__in=[nombre for nombre, _ in roles_disponibles()]
            ).first()
            if grupo:
                self.fields["rol"].initial = grupo.name
        self.fields["first_name"].required = False
        self.fields["last_name"].required = False
        self.fields["email"].required = False


class UsuarioCrearForm(FormularioBootstrapMixin, _FormularioConRolMixin, UserCreationForm):
    """Alta de usuario con contraseña inicial y rol."""

    class Meta(UserCreationForm.Meta):
        fields = ("username", "first_name", "last_name", "email")

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if commit:
            usuario.save()
            asignar_rol(usuario, self.cleaned_data["rol"])
        return usuario


class UsuarioEditarForm(FormularioBootstrapMixin, _FormularioConRolMixin, forms.ModelForm):
    """Edición de datos básicos, estado y rol (sin tocar la contraseña)."""

    class Meta:
        model = Usuario
        fields = ("username", "first_name", "last_name", "email", "is_active")
        error_messages = {
            "username": {"unique": "Ya existe un usuario con ese nombre."},
        }
        help_texts = {
            "is_active": (
                "Desmarcar desactiva la cuenta: el usuario no podrá iniciar sesión. "
                "No se elimina ningún dato histórico."
            ),
        }
        labels = {"is_active": "Cuenta activa"}

    def clean(self):
        datos = super().clean()
        usuario = self.instance
        # No se puede degradar ni desactivar al último administrador activo.
        if (
            usuario
            and usuario.pk
            and es_ultimo_administrador_activo(usuario)
            and (
                not datos.get("is_active")
                or datos.get("rol") != GRUPO_ADMINISTRADOR
            )
        ):
            self.add_error(
                "rol",
                "No se puede quitar el rol de Administrador ni desactivar al último "
                "administrador activo del sistema.",
            )
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if commit:
            usuario.save()
            asignar_rol(usuario, self.cleaned_data["rol"])
        return usuario


class RestablecerClaveForm(FormularioBootstrapMixin, SetPasswordForm):
    """Asigna una contraseña nueva a un usuario (sin mostrar ni recuperar la anterior)."""
