"""
serializers.py — Serializadores para la API REST (Django REST Framework).
Cada modelo principal tiene su serializador de lectura (anidado) y
de escritura (por IDs), siguiendo la convención estándar de DRF.
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Autor, Genero, Libro, Empleado, Usuario,
    Prestamo, DetallePrestamo, Multa, Historial, AuditLog,
    ReservaLibro, ValoracionLibro,
)


# ─────────────────────────────────────────────
#  CATÁLOGO
# ─────────────────────────────────────────────

class AutorSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Autor
        fields = ['id', 'nombre']


class GeneroSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Genero
        fields = ['id', 'nombre']


# ─────────────────────────────────────────────
#  LIBRO
# ─────────────────────────────────────────────

class LibroSerializer(serializers.ModelSerializer):
    """Serializador completo para lectura (incluye autores y géneros anidados)."""
    autores = AutorSerializer(many=True, read_only=True)
    generos = GeneroSerializer(many=True, read_only=True)
    promedio_valoracion = serializers.FloatField(read_only=True)
    total_valoraciones = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Libro
        fields = [
            'id', 'google_volume_id', 'titulo', 'subtitulo', 'editorial',
            'fecha_publicacion', 'descripcion', 'cantidad_paginas', 'idioma',
            'autores', 'generos', 'isbn_10', 'isbn_13',
            'portada_url', 'preview_url',
            'cantidad_disponible', 'cantidad_total', 'creado_en',
            'promedio_valoracion', 'total_valoraciones',
        ]
        read_only_fields = ['id', 'creado_en']


class LibroWriteSerializer(serializers.ModelSerializer):
    """Serializador para escritura (acepta IDs de autores y géneros)."""
    autores_ids = serializers.PrimaryKeyRelatedField(
        queryset=Autor.objects.all(), many=True, source='autores', write_only=True
    )
    generos_ids = serializers.PrimaryKeyRelatedField(
        queryset=Genero.objects.all(), many=True, source='generos', write_only=True
    )

    class Meta:
        model  = Libro
        fields = [
            'google_volume_id', 'titulo', 'subtitulo', 'editorial',
            'fecha_publicacion', 'descripcion', 'cantidad_paginas', 'idioma',
            'autores_ids', 'generos_ids', 'isbn_10', 'isbn_13',
            'portada_url', 'preview_url',
            'cantidad_disponible', 'cantidad_total',
        ]


# ─────────────────────────────────────────────
#  PERSONAS
# ─────────────────────────────────────────────

class UsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model  = Usuario
        fields = ['id', 'user', 'nombre', 'email', 'telefono', 'password', 'fecha_registro', 'activo']
        read_only_fields = ['id', 'fecha_registro']

    def validate(self, data):
        if self.instance is None and not data.get('password'):
            raise serializers.ValidationError({'password': 'La contraseña es obligatoria.'})
        email = data.get('email')
        if email and Empleado.objects.filter(email__iexact=email, activo=True).exists():
            raise serializers.ValidationError({'email': 'Este correo ya pertenece a una cuenta interna.'})
        if email:
            user_id = getattr(getattr(self.instance, 'user', None), 'id', None)
            if User.objects.filter(username__iexact=email).exclude(id=user_id).exists():
                raise serializers.ValidationError({'email': 'Ya existe una cuenta de acceso con ese correo.'})
        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        email = validated_data.get('email', '').lower()
        nombre = validated_data.get('nombre', '')
        user = User.objects.create_user(
            username=email, email=email, password=password, first_name=nombre
        )
        validated_data['user'] = user
        validated_data['email'] = email
        return super().create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', '')
        usuario = super().update(instance, validated_data)
        user = usuario.user
        if user:
            user.username = usuario.email
            user.email = usuario.email
            user.first_name = usuario.nombre
            if password:
                user.set_password(password)
            user.save()
        elif password:
            usuario.user = User.objects.create_user(
                username=usuario.email,
                email=usuario.email,
                password=password,
                first_name=usuario.nombre,
            )
            usuario.save(update_fields=['user'])
        return usuario


class RegistroUsuarioAPISerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    telefono = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        from django.contrib.auth.models import User
        if User.objects.filter(username__iexact=value).exists() or Usuario.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Ya existe una cuenta con ese correo.')
        if Empleado.objects.filter(email__iexact=value, activo=True).exists():
            raise serializers.ValidationError('Este correo ya pertenece a una cuenta interna.')
        return value.lower()


class EmpleadoSerializer(serializers.ModelSerializer):
    """El campo password es write_only por seguridad."""
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model  = Empleado
        fields = ['id', 'nombre', 'email', 'password', 'activo']
        read_only_fields = ['id']

    def validate(self, data):
        if self.instance is None and not data.get('password'):
            raise serializers.ValidationError({'password': 'La contraseña es obligatoria.'})
        email = data.get('email')
        if email:
            user_emp = None
            if self.instance is not None:
                user_emp = (
                    User.objects.filter(username__iexact=self.instance.email, is_superuser=False).first()
                    or User.objects.filter(email__iexact=self.instance.email, is_superuser=False).first()
                )
            if User.objects.filter(username__iexact=email).exclude(id=getattr(user_emp, 'id', None)).exists():
                raise serializers.ValidationError({'email': 'Ya existe una cuenta de acceso con ese correo.'})
            if Usuario.objects.filter(email__iexact=email, activo=True).exists():
                raise serializers.ValidationError({'email': 'Este correo ya pertenece a un usuario lector.'})
        return data

    def create(self, validated_data):
        empleado = super().create(validated_data)
        User.objects.create_user(
            username=empleado.email,
            email=empleado.email,
            password=validated_data['password'],
            first_name=empleado.nombre,
        )
        return empleado

    def update(self, instance, validated_data):
        password = validated_data.get('password', '')
        email_anterior = instance.email
        empleado = super().update(instance, validated_data)
        user_emp = (
            User.objects.filter(username__iexact=email_anterior, is_superuser=False).first()
            or User.objects.filter(email__iexact=email_anterior, is_superuser=False).first()
        )
        if user_emp:
            user_emp.username = empleado.email
            user_emp.email = empleado.email
            user_emp.first_name = empleado.nombre
            if password:
                user_emp.set_password(password)
            user_emp.save()
        elif password:
            User.objects.create_user(
                username=empleado.email,
                email=empleado.email,
                password=password,
                first_name=empleado.nombre,
            )
        return empleado


# ─────────────────────────────────────────────
#  PRÉSTAMOS
# ─────────────────────────────────────────────

class DetallePrestamoSerializer(serializers.ModelSerializer):
    libro_titulo = serializers.CharField(source='libro.titulo', read_only=True)

    class Meta:
        model  = DetallePrestamo
        fields = [
            'id', 'libro', 'libro_titulo',
            'fecha_devolucion_real', 'condicion_libro', 'devuelto',
        ]


class PrestamoSerializer(serializers.ModelSerializer):
    """Serializa el préstamo completo con datos del usuario, empleado y libros."""
    usuario_nombre  = serializers.CharField(source='usuario.nombre',  read_only=True)
    empleado_nombre = serializers.CharField(source='empleado.nombre', read_only=True)
    detalles        = DetallePrestamoSerializer(
        source='detalleprestamo_set', many=True, read_only=True
    )
    libros_resumen  = serializers.CharField(read_only=True)

    class Meta:
        model  = Prestamo
        fields = [
            'id', 'fecha_prestamo', 'fecha_limite', 'estado', 'observaciones',
            'usuario', 'usuario_nombre',
            'empleado', 'empleado_nombre',
            'libros_resumen', 'detalles',
        ]
        read_only_fields = ['id', 'fecha_prestamo', 'libros_resumen']


class PrestamoCreateSerializer(serializers.ModelSerializer):
    """
    Serializer para la creación de préstamos vía API.
    Acepta una lista de IDs de libros (libros_ids).
    """
    libros_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True
    )

    class Meta:
        model  = Prestamo
        fields = ['usuario', 'empleado', 'fecha_limite', 'observaciones', 'libros_ids']

    def validate(self, data):
        usuario = data.get('usuario')
        from .models import Multa
        if Multa.objects.filter(prestamo__usuario=usuario, estado='Pendiente').exists():
            raise serializers.ValidationError(
                f'{usuario.nombre} tiene multas pendientes que debe regularizar primero.'
            )
        return data

    def create(self, validated_data):
        from .models import Libro, DetallePrestamo
        libros_ids = validated_data.pop('libros_ids')
        prestamo   = Prestamo.objects.create(**validated_data)

        for libro_id in libros_ids:
            try:
                libro = Libro.objects.get(id=libro_id)
                if libro.cantidad_disponible > 0:
                    DetallePrestamo.objects.create(prestamo=prestamo, libro=libro)
                    libro.cantidad_disponible -= 1
                    libro.save(update_fields=['cantidad_disponible'])
            except Libro.DoesNotExist:
                pass

        from .models import Historial
        Historial.objects.create(
            tipo_accion='Prestamo',
            descripcion=f'Préstamo #{prestamo.id} creado vía API REST.',
            prestamo=prestamo,
        )
        return prestamo


class ReservaLibroSerializer(serializers.ModelSerializer):
    libro = LibroSerializer(read_only=True)
    libro_id = serializers.PrimaryKeyRelatedField(
        queryset=Libro.objects.all(), source='libro', write_only=True
    )
    usuario_nombre = serializers.CharField(source='usuario.nombre', read_only=True)

    class Meta:
        model = ReservaLibro
        fields = [
            'id', 'usuario', 'usuario_nombre', 'libro', 'libro_id',
            'fecha_reserva', 'fecha_apartado', 'fecha_expiracion', 'estado',
        ]
        read_only_fields = [
            'id', 'usuario', 'fecha_reserva', 'fecha_apartado',
            'fecha_expiracion', 'estado',
        ]


class ValoracionLibroSerializer(serializers.ModelSerializer):
    libro = LibroSerializer(read_only=True)
    libro_id = serializers.PrimaryKeyRelatedField(
        queryset=Libro.objects.all(), source='libro', write_only=True
    )

    class Meta:
        model = ValoracionLibro
        fields = ['id', 'usuario', 'libro', 'libro_id', 'puntaje', 'comentario', 'fecha']
        read_only_fields = ['id', 'usuario', 'fecha']


class ConfiguracionPublicaSerializer(serializers.Serializer):
    nombre_biblioteca = serializers.CharField()
    max_libros_cliente = serializers.IntegerField()
    dias_prestamo_defecto = serializers.IntegerField()
    dias_gracia = serializers.IntegerField()


# ─────────────────────────────────────────────
#  MULTAS
# ─────────────────────────────────────────────

class MultaSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model  = Multa
        fields = [
            'id', 'monto', 'motivo', 'estado',
            'fecha_generacion', 'fecha_pago',
            'prestamo', 'usuario_nombre',
        ]
        read_only_fields = ['id', 'fecha_generacion']

    def get_usuario_nombre(self, obj):
        if obj.prestamo and obj.prestamo.usuario:
            return obj.prestamo.usuario.nombre
        return "Usuario eliminado"


# ─────────────────────────────────────────────
#  HISTORIAL
# ─────────────────────────────────────────────

class HistorialSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Historial
        fields = ['id', 'fecha_accion', 'tipo_accion', 'descripcion', 'prestamo']
        read_only_fields = ['id', 'fecha_accion']


# ─────────────────────────────────────────────
#  AUDITORÍA
# ─────────────────────────────────────────────

class AuditLogSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source='usuario.username', read_only=True)

    class Meta:
        model  = AuditLog
        fields = [
            'id', 'tabla', 'objeto_id', 'objeto_repr', 'accion',
            'datos_anteriores', 'datos_nuevos',
            'usuario', 'usuario_username', 'empleado_nombre',
            'ip_address', 'fecha',
        ]
        read_only_fields = fields  # Solo lectura — no se crea auditoría desde la API
