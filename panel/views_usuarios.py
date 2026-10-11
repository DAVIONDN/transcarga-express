"""Vistas de gestión de usuarios (solo Administrador).

Todas exigen el permiso correspondiente de `auth` y protegen igual GET y POST.
No se confía en el identificador del navegador para decidir quién actúa: la
autorización sale siempre de `request.user`.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, FormView, ListView, UpdateView, View

from auditoria.models import TipoAccion, auditar
from comun.permisos import (
    PermisoRequeridoMixin,
    es_ultimo_administrador_activo,
    puede_gestionar_cuenta,
)

from .forms_usuarios import (
    RestablecerClaveForm,
    UsuarioCrearForm,
    UsuarioEditarForm,
)

Usuario = get_user_model()


class UsuarioMixin(PermisoRequeridoMixin):
    """Obtiene el usuario indicado en la URL y protege las cuentas privilegiadas."""

    def get_usuario(self):
        if not hasattr(self, "_usuario"):
            self._usuario = get_object_or_404(Usuario, pk=self.kwargs["pk"])
        return self._usuario

    def dispatch(self, request, *args, **kwargs):
        # Un Administrador no superusuario no puede gestionar cuentas de superusuario
        # (evita escalar privilegios restableciendo la contraseña de un superusuario).
        if request.user.is_authenticated and not puede_gestionar_cuenta(
            request.user, self.get_usuario()
        ):
            messages.error(
                request,
                "No puedes administrar una cuenta con privilegios de superusuario.",
            )
            return render(
                request,
                "403.html",
                {"titulo": "Acceso denegado", "permiso_requerido": None},
                status=403,
            )
        return super().dispatch(request, *args, **kwargs)


class ListaUsuariosView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "auth.view_user"
    model = Usuario
    template_name = "panel/usuarios/lista.html"
    context_object_name = "usuarios"
    paginate_by = 15

    def get_queryset(self):
        consulta = super().get_queryset().prefetch_related("groups").order_by("username")
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(username__icontains=texto)
                | Q(first_name__icontains=texto)
                | Q(last_name__icontains=texto)
                | Q(email__icontains=texto)
            )
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Usuarios"
        contexto["texto_busqueda"] = self.request.GET.get("q", "")
        return contexto


class CrearUsuarioView(PermisoRequeridoMixin, CreateView):
    permiso_requerido = "auth.add_user"
    model = Usuario
    form_class = UsuarioCrearForm
    template_name = "panel/usuarios/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nuevo usuario"
        contexto["texto_boton"] = "Crear usuario"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.USUARIO,
            entidad="usuario",
            entidad_id=self.object.pk,
            resumen=f"Alta de «{self.object.username}» con rol {form.cleaned_data['rol']}.",
        )
        messages.success(
            self.request,
            f"Usuario «{self.object.username}» creado con el rol {form.cleaned_data['rol']}.",
        )
        return respuesta

    def get_success_url(self):
        return reverse("panel:usuarios_lista")


class EditarUsuarioView(UsuarioMixin, UpdateView):
    permiso_requerido = "auth.change_user"
    model = Usuario
    form_class = UsuarioEditarForm
    template_name = "panel/usuarios/formulario.html"

    def get_object(self, queryset=None):
        return self.get_usuario()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar usuario: {self.object.username}"
        contexto["texto_boton"] = "Guardar cambios"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.USUARIO,
            entidad="usuario",
            entidad_id=self.object.pk,
            resumen=f"Edición de «{self.object.username}» (rol {form.cleaned_data['rol']}).",
        )
        messages.success(
            self.request,
            f"Cambios guardados para «{self.object.username}» (rol {form.cleaned_data['rol']}).",
        )
        return respuesta

    def get_success_url(self):
        return reverse("panel:usuarios_lista")


class CambiarEstadoUsuarioView(UsuarioMixin, View):
    """Activa o desactiva una cuenta con confirmación y protección del último administrador."""

    permiso_requerido = "auth.change_user"
    template_name = "panel/usuarios/confirmar_estado.html"

    def get(self, request, *args, **kwargs):
        usuario = self.get_usuario()
        accion = "desactivar" if usuario.is_active else "activar"
        return render(
            request,
            self.template_name,
            {"usuario": usuario, "accion": accion, "titulo": f"{accion.capitalize()} cuenta"},
        )

    def post(self, request, *args, **kwargs):
        usuario = self.get_usuario()
        if usuario.is_active:
            if es_ultimo_administrador_activo(usuario):
                messages.error(
                    request,
                    "No se puede desactivar al último administrador activo del sistema.",
                )
                return redirect("panel:usuarios_lista")
            usuario.is_active = False
            usuario.save(update_fields=["is_active"])
            auditar(
                usuario=request.user,
                accion=TipoAccion.USUARIO,
                entidad="usuario",
                entidad_id=usuario.pk,
                resumen=f"Cuenta «{usuario.username}» desactivada.",
            )
            messages.success(request, f"La cuenta «{usuario.username}» quedó desactivada.")
        else:
            usuario.is_active = True
            usuario.save(update_fields=["is_active"])
            auditar(
                usuario=request.user,
                accion=TipoAccion.USUARIO,
                entidad="usuario",
                entidad_id=usuario.pk,
                resumen=f"Cuenta «{usuario.username}» activada.",
            )
            messages.success(request, f"La cuenta «{usuario.username}» quedó activada.")
        return redirect("panel:usuarios_lista")


class RestablecerClaveUsuarioView(UsuarioMixin, FormView):
    """Asigna una contraseña nueva a un usuario (procedimiento administrativo seguro)."""

    permiso_requerido = "auth.change_user"
    form_class = RestablecerClaveForm
    template_name = "panel/usuarios/restablecer_clave.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.get_usuario()
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["usuario"] = self.get_usuario()
        contexto["titulo"] = f"Restablecer contraseña de {self.get_usuario().username}"
        return contexto

    def form_valid(self, form):
        form.save()  # guarda la contraseña ya encriptada (nunca en texto legible)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.USUARIO,
            entidad="usuario",
            entidad_id=self.get_usuario().pk,
            resumen=f"Contraseña restablecida para «{self.get_usuario().username}».",
        )
        messages.success(
            self.request,
            f"Contraseña actualizada para «{self.get_usuario().username}».",
        )
        return redirect("panel:usuarios_lista")
