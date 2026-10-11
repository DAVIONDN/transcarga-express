"""Cursos de capacitación e historial de participaciones de transportistas.

Un curso no otorga acreditaciones externas ni modifica la clasificación por
niveles: solo registra formación interna. Completar exige la acción explícita
de confirmación por un usuario autorizado.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from comun import fechas
from comun.choices import (
    EstadoCurso,
    EstadoParticipacion,
    ResultadoParticipacion,
)

PESO_MAXIMO_CONSTANCIA = 5 * 1024 * 1024  # 5 MB
EXTENSIONES_CONSTANCIA = (".pdf", ".jpg", ".jpeg", ".png")


def normalizar_codigo(valor):
    """Código en mayúsculas y sin espacios: «cur 01» → «CUR01»."""
    if not valor:
        return valor
    return str(valor).strip().upper().replace(" ", "").replace("-", "")


def validar_constancia(archivo):
    """Comprueba peso y formato de la constancia digital (en el servidor)."""
    if archivo.size > PESO_MAXIMO_CONSTANCIA:
        raise ValidationError("La constancia no debe pesar más de 5 MB.")
    if not archivo.name.lower().endswith(EXTENSIONES_CONSTANCIA):
        raise ValidationError("La constancia debe estar en formato PDF, JPG o PNG.")


class Curso(models.Model):
    """Curso ofrecido por la empresa (formación interna, sin acreditación externa)."""

    codigo = models.CharField(
        "Código",
        max_length=20,
        unique=True,
        help_text="Identificador único, en mayúsculas y sin espacios.",
    )
    titulo = models.CharField("Título", max_length=150)
    tema = models.CharField("Tema o materia", max_length=150)
    duracion_horas = models.PositiveIntegerField(
        "Duración (horas)",
        validators=[MinValueValidator(1, message="La duración debe ser mayor que cero.")],
    )
    estado = models.CharField(
        "Estado",
        max_length=10,
        choices=EstadoCurso.choices,
        default=EstadoCurso.ACTIVO,
    )
    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Curso"
        verbose_name_plural = "Cursos"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.titulo}"

    def clean(self):
        super().clean()
        self.codigo = normalizar_codigo(self.codigo)
        if self.duracion_horas is not None and self.duracion_horas <= 0:
            raise ValidationError(
                {"duracion_horas": "La duración debe ser mayor que cero."}
            )

    def save(self, *args, **kwargs):
        self.codigo = normalizar_codigo(self.codigo)
        super().save(*args, **kwargs)

    @property
    def esta_activo(self):
        return self.estado == EstadoCurso.ACTIVO


class Participacion(models.Model):
    """Participación de un transportista en una convocatoria de un curso.

    La convocatoria distingue ediciones (p. ej. «2026-03») sin duplicar datos
    del curso: el triple transportista–curso–convocatoria es único (ni
    duplicadas ni dos pendientes del mismo triple). Cada repetición conserva
    su fecha, estado, resultado y constancia propios.
    """

    transportista = models.ForeignKey(
        "transportistas.Transportista",
        on_delete=models.PROTECT,
        related_name="participaciones",
        verbose_name="Transportista",
    )
    curso = models.ForeignKey(
        Curso,
        on_delete=models.PROTECT,
        related_name="participaciones",
        verbose_name="Curso",
    )
    convocatoria = models.CharField(
        "Convocatoria",
        max_length=20,
        help_text="Edición del curso, por ejemplo «2026-03».",
    )
    fecha = models.DateField("Fecha de inscripción o participación", default=fechas.hoy)
    estado = models.CharField(
        "Estado",
        max_length=12,
        choices=EstadoParticipacion.choices,
        default=EstadoParticipacion.INSCRITO,
    )
    fecha_finalizacion = models.DateField(
        "Fecha de finalización", null=True, blank=True
    )
    resultado = models.CharField(
        "Resultado",
        max_length=12,
        choices=ResultadoParticipacion.choices,
        null=True,
        blank=True,
    )
    observaciones = models.TextField("Observaciones", blank=True, default="")
    constancia = models.FileField(
        "Constancia digital",
        upload_to="constancias/%Y/%m/",
        null=True,
        blank=True,
        validators=[validar_constancia],
        help_text="Opcional, preferentemente en PDF y de hasta 5 MB.",
    )
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="participaciones_confirmadas",
        verbose_name="Confirmado por",
    )
    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Participación"
        verbose_name_plural = "Participaciones"
        ordering = ["-fecha", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["transportista", "curso", "convocatoria"],
                name="una_participacion_por_convocatoria",
            )
        ]
        permissions = [
            (
                "finalizar_participacion",
                "Puede confirmar la finalización de una participación.",
            ),
        ]

    def __str__(self):
        return (
            f"{self.transportista.nombre} — {self.curso.codigo} "
            f"({self.convocatoria}, {self.get_estado_display()})"
        )

    def clean(self):
        super().clean()
        errores = {}
        self.convocatoria = (self.convocatoria or "").strip().upper()

        if self.curso_id and not self.curso.esta_activo:
            errores["curso"] = (
                "El curso está inactivo y no admite nuevas inscripciones."
            )
        if self.estado == EstadoParticipacion.COMPLETADO:
            if not self.fecha_finalizacion:
                errores["fecha_finalizacion"] = (
                    "La participación completada exige fecha de finalización."
                )
            if not self.resultado:
                errores["resultado"] = (
                    "La participación completada exige un resultado verificado."
                )
            if (
                self.fecha_finalizacion
                and self.fecha
                and self.fecha_finalizacion < self.fecha
            ):
                errores["fecha_finalizacion"] = (
                    "La finalización no puede ser anterior a la inscripción."
                )
        else:
            if self.resultado or self.fecha_finalizacion:
                errores["resultado"] = (
                    "El resultado y la finalización solo corresponden a una "
                    "participación completada y confirmada."
                )
        if errores:
            raise ValidationError(errores)

    @property
    def esta_completada(self):
        return self.estado == EstadoParticipacion.COMPLETADO

    @property
    def constancia_pendiente(self):
        """Aprobada sin archivo: falta cargar la constancia (solo informativo)."""
        return (
            self.esta_completada
            and self.resultado == ResultadoParticipacion.APROBADO
            and not self.constancia
        )

    def confirmar(self, *, fecha_finalizacion, resultado, observaciones="", constancia=None, usuario=None):
        """Confirma la finalización (acción explícita y autorizada).

        No modifica la clasificación del transportista. Devuelve la instancia.
        """
        if self.esta_completada:
            raise ValidationError("La participación ya está completada.")
        self.estado = EstadoParticipacion.COMPLETADO
        self.fecha_finalizacion = fecha_finalizacion
        self.resultado = resultado
        self.observaciones = (observaciones or "").strip()
        if constancia is not None:
            self.constancia = constancia
        if usuario is not None and usuario.is_authenticated:
            self.confirmado_por = usuario
        self.full_clean()
        self.save()
        return self
