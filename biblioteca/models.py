from django.contrib.auth.hashers import identify_hasher, make_password
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Avg
from django.core import validators


# ─────────────────────────────────────────────
#  MODELOS DE CATÁLOGO
# ─────────────────────────────────────────────

class Autor(models.Model):
    nombre = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name_plural = "Autores"

    def __str__(self):
        return self.nombre


class Genero(models.Model):
    nombre = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name_plural = "Géneros"

    def __str__(self):
        return self.nombre


# ─────────────────────────────────────────────
#  PERSONAS
# ─────────────────────────────────────────────

class Empleado(models.Model):
    nombre   = models.CharField(max_length=100)
    email    = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    activo   = models.BooleanField(default=True)          # Soft-delete

    class Meta:
        db_table = 'biblioteca_empleado'

    def save(self, *args, **kwargs):
        if self.password:
            try:
                identify_hasher(self.password)
            except ValueError:
                self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Usuario(models.Model):
    user            = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='perfil_lector'
    )
    nombre          = models.CharField(max_length=150)
    email           = models.EmailField(unique=True)
    telefono        = models.CharField(max_length=20)
    fecha_registro  = models.DateField(auto_now_add=True)
    activo          = models.BooleanField(default=True)    # Soft-delete

    def __str__(self):
        return self.nombre


# ─────────────────────────────────────────────
#  INVENTARIO
# ─────────────────────────────────────────────

class Libro(models.Model):
    google_volume_id  = models.CharField(max_length=50, unique=True)
    titulo            = models.CharField(max_length=255)
    subtitulo         = models.TextField(null=True, blank=True)
    editorial         = models.CharField(max_length=255, null=True, blank=True)
    fecha_publicacion = models.CharField(max_length=10, null=True, blank=True)
    descripcion       = models.TextField(null=True, blank=True)
    cantidad_paginas  = models.IntegerField(null=True, blank=True)
    idioma            = models.CharField(max_length=10, null=True, blank=True)

    autores = models.ManyToManyField('Autor')
    generos = models.ManyToManyField('Genero')

    isbn_10     = models.CharField(max_length=20, null=True, blank=True)
    isbn_13     = models.CharField(max_length=20, null=True, blank=True)
    portada_url = models.TextField(null=True, blank=True)
    preview_url = models.TextField(null=True, blank=True)

    tipo_impresion = models.CharField(max_length=20, default='BOOK')
    text_snippet   = models.TextField(null=True, blank=True)

    cantidad_disponible = models.IntegerField(
        validators=[validators.MinValueValidator(0)]
    )
    cantidad_total = models.IntegerField(
        validators=[validators.MinValueValidator(0)]
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    @property
    def autor(self):
        return ", ".join([a.nombre for a in self.autores.all()])

    @property
    def genero(self):
        return ", ".join([g.nombre for g in self.generos.all()])

    @property
    def promedio_valoracion(self):
        promedio = self.valoraciones.aggregate(promedio=Avg('puntaje'))['promedio']
        return round(promedio or 0, 1)

    @property
    def total_valoraciones(self):
        return self.valoraciones.count()

    def __str__(self):
        return self.titulo


# ─────────────────────────────────────────────
#  PRÉSTAMOS
# ─────────────────────────────────────────────

class Prestamo(models.Model):
    ESTADO_CHOICES = [
        ('Activo',    'Activo'),
        ('Devuelto',  'Devuelto'),
        ('Retraso',   'Retraso'),
    ]

    fecha_prestamo = models.DateField(auto_now_add=True)
    fecha_limite   = models.DateField()
    estado         = models.CharField(max_length=50, default='Activo', choices=ESTADO_CHOICES)
    observaciones  = models.TextField(null=True, blank=True)

    usuario  = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, related_name='prestamos'
    )
    empleado = models.ForeignKey(
        Empleado, on_delete=models.SET_NULL, null=True, related_name='prestamos_gestionados'
    )

    # La tabla intermedia explícita permite gestionar devoluciones por libro
    libros = models.ManyToManyField('Libro', through='DetallePrestamo')

    @property
    def libros_resumen(self):
        cantidad = self.libros.count()
        if cantidad == 0:
            return "Ningún libro"
        primer_libro = self.libros.first().titulo
        if cantidad == 1:
            return primer_libro
        return f"{primer_libro} (+{cantidad - 1} más)"

    def __str__(self):
        usr_nombre = self.usuario.nombre if self.usuario else "Eliminado"
        return f"Préstamo #{self.id} — {self.libros_resumen} a {usr_nombre}"


class DetallePrestamo(models.Model):
    """Tabla intermedia que permite controlar la devolución individual por libro."""
    prestamo              = models.ForeignKey(Prestamo, on_delete=models.CASCADE)
    libro                 = models.ForeignKey('Libro', on_delete=models.PROTECT)
    fecha_devolucion_real = models.DateField(null=True, blank=True)
    condicion_libro       = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Ej: Buen estado, Rayado, Dañado"
    )
    devuelto = models.BooleanField(default=False)

    def __str__(self):
        return f"Libro: {self.libro.titulo} en Préstamo #{self.prestamo.id}"


# ─────────────────────────────────────────────
#  MULTAS
# ─────────────────────────────────────────────

class ReservaLibro(models.Model):
    ESTADO_CHOICES = [
        ('En cola', 'En cola'),
        ('Apartado', 'Apartado'),
        ('Convertido', 'Convertido a prestamo'),
        ('Cancelado', 'Cancelado'),
        ('Vencido', 'Vencido'),
    ]

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='reservas')
    libro = models.ForeignKey(Libro, on_delete=models.CASCADE, related_name='reservas')
    fecha_reserva = models.DateTimeField(auto_now_add=True)
    fecha_apartado = models.DateTimeField(null=True, blank=True)
    fecha_expiracion = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='En cola')

    class Meta:
        ordering = ['fecha_reserva']

    def __str__(self):
        return f"{self.usuario.nombre} - {self.libro.titulo} ({self.estado})"


class ValoracionLibro(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='valoraciones')
    libro = models.ForeignKey(Libro, on_delete=models.CASCADE, related_name='valoraciones')
    puntaje = models.PositiveSmallIntegerField(
        validators=[validators.MinValueValidator(1), validators.MaxValueValidator(5)]
    )
    comentario = models.TextField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('usuario', 'libro')
        verbose_name = 'Valoracion de libro'
        verbose_name_plural = 'Valoraciones de libros'

    def __str__(self):
        return f"{self.libro.titulo}: {self.puntaje}/5 por {self.usuario.nombre}"


class Multa(models.Model):
    ESTADO_MULTA = [
        ('Pendiente', 'Pendiente'),
        ('Pagada',    'Pagada'),
    ]
    monto            = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[validators.MinValueValidator(0.01)]
    )
    motivo           = models.CharField(max_length=200)
    estado           = models.CharField(max_length=50, choices=ESTADO_MULTA, default='Pendiente')
    fecha_generacion = models.DateField(auto_now_add=True)
    fecha_pago       = models.DateField(null=True, blank=True)

    prestamo = models.ForeignKey(
        Prestamo, on_delete=models.SET_NULL, null=True, related_name='multas'
    )

    def __str__(self):
        return f"Multa de {self.monto} - Estado: {self.estado}"


# ─────────────────────────────────────────────
#  HISTORIAL DE OPERACIONES (existente)
# ─────────────────────────────────────────────

class Historial(models.Model):
    ACCION_CHOICES = [
        ('Prestamo',   'Préstamo'),
        ('Devolucion', 'Devolución'),
        ('Multa',      'Multa'),
        ('Moroso',     'Moroso'),
    ]
    fecha_accion = models.DateTimeField(auto_now_add=True)
    tipo_accion  = models.CharField(max_length=100, choices=ACCION_CHOICES)
    descripcion  = models.TextField(null=True, blank=True)

    prestamo = models.ForeignKey(
        Prestamo, on_delete=models.SET_NULL, null=True, related_name='historiales'
    )

    class Meta:
        verbose_name_plural = "Historiales"

    def __str__(self):
        return f"{self.tipo_accion} registrado el {self.fecha_accion.strftime('%d/%m/%Y %H:%M')}"


# ─────────────────────────────────────────────
#  AUDITORÍA (NUEVO)
# ─────────────────────────────────────────────

class AuditLog(models.Model):
    """
    Registra cada operación CRUD relevante sobre cualquier modelo.
    Se usa en todas las vistas de eliminación, edición y creación.
    """
    ACCION_CHOICES = [
        ('CREATE', 'Creación'),
        ('UPDATE', 'Actualización'),
        ('DELETE', 'Eliminación'),
        ('LOGIN',  'Inicio de sesión'),
        ('LOGOUT', 'Cierre de sesión'),
    ]

    tabla        = models.CharField(max_length=100)
    objeto_id    = models.IntegerField(null=True, blank=True)
    objeto_repr  = models.CharField(max_length=255, null=True, blank=True)
    accion       = models.CharField(max_length=20, choices=ACCION_CHOICES)

    # JSONField requiere Django ≥ 3.1. Si usas SQLite < 3.9 o MySQL < 5.7.8,
    # reemplaza por TextField y serializa/deserializa manualmente con json.
    datos_anteriores = models.JSONField(null=True, blank=True)
    datos_nuevos     = models.JSONField(null=True, blank=True)

    usuario         = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='auditlogs'
    )
    empleado_nombre = models.CharField(max_length=150, null=True, blank=True)
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    fecha           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name        = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'

    def __str__(self):
        return (
            f"[{self.accion}] {self.tabla} #{self.objeto_id} — "
            f"{self.fecha.strftime('%d/%m/%Y %H:%M')}"
        )


# ─────────────────────────────────────────────
#  CONFIGURACIÓN DEL SISTEMA (NUEVO)
# ─────────────────────────────────────────────

class Configuracion(models.Model):
    """
    Almacén clave-valor para ajustes globales de la aplicación.
    La paleta de colores y otras preferencias de UI se guardan aquí.
    """
    PALETAS_DISPONIBLES = [
        ('azul',    'Azul Clásico'),
        ('verde',   'Verde Esmeralda'),
        ('morado',  'Morado Elegante'),
        ('rojo',    'Rojo Corporativo'),
        ('naranja', 'Naranja Vibrante'),
        ('oscuro',  'Modo Oscuro'),
    ]

    clave       = models.CharField(max_length=100, unique=True)
    valor       = models.CharField(max_length=255)
    descripcion = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name        = 'Configuración'
        verbose_name_plural = 'Configuraciones'

    def __str__(self):
        return f"{self.clave}: {self.valor}"

    # ── Métodos de clase para acceso rápido ──────────────────────────
    @classmethod
    def get(cls, clave, default=None):
        """Obtiene el valor de una clave. Retorna `default` si no existe."""
        try:
            return cls.objects.get(clave=clave).valor
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, clave, valor, descripcion=None):
        """Crea o actualiza una clave de configuración."""
        kwargs = {'valor': valor}
        if descripcion:
            kwargs['descripcion'] = descripcion
        obj, _ = cls.objects.update_or_create(clave=clave, defaults=kwargs)
        return obj
