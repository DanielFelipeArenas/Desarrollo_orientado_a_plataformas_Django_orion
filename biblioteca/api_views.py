"""
api_views.py — Vistas de la API REST (Django REST Framework).
Punto 8: preparar el proyecto para ser consumido desde Flutter u otros clientes.

Rutas base:  /api/v1/
Autenticación: Token (para Flutter) + Session (para pruebas en navegador)
"""
from datetime import timedelta

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from .views import registrar_auditoria

from .models import (
    Autor, Genero, Libro, Empleado, Usuario,
    Prestamo, Multa, Historial, AuditLog,
    DetallePrestamo, ReservaLibro, ValoracionLibro, Configuracion,
)
from .serializers import (
    AutorSerializer, GeneroSerializer,
    LibroSerializer, LibroWriteSerializer,
    EmpleadoSerializer, UsuarioSerializer,
    PrestamoSerializer, PrestamoCreateSerializer, DetallePrestamoSerializer,
    MultaSerializer, HistorialSerializer, AuditLogSerializer,
    RegistroUsuarioAPISerializer, ReservaLibroSerializer,
    ValoracionLibroSerializer, ConfiguracionPublicaSerializer,
)

# ─────────────────────────────────────────────
#  UTILIDADES DE AUDITORÍA (importadas desde views)
# ─────────────────────────────────────────────

def _registrar_auditoria_api(request, tabla, objeto_id, accion,
                              repr_objeto='', datos_anteriores=None, datos_nuevos=None):
    """Wrapper que reutiliza la lógica de views.py sin importar el módulo completo."""
    try:
        from .views import registrar_auditoria
        registrar_auditoria(request, tabla, objeto_id, accion,
                            repr_objeto, datos_anteriores, datos_nuevos)
    except Exception:
        pass

# ─────────────────────────────────────────────
#  AUTENTICACIÓN  (Token para Flutter)
# ─────────────────────────────────────────────

class ObtenerTokenView(APIView):
    """
    POST /api/v1/auth/token/
    Body: { "username": "...", "password": "..." }
    Respuesta: { "token": "...", "user_id": ..., "email": "..." }

    Úsalo en Flutter para autenticar y guardar el token en secure storage.
    Luego envía el header: Authorization: Token <token>
    """
    permission_classes = []   # Pública — no requiere autenticación previa

    def post(self, request):
        username = request.data.get('username', '')
        password = request.data.get('password', '')

        user = authenticate(username=username, password=password)

        # Intento por email
        if user is None:
            from django.contrib.auth.models import User as DjangoUser
            user_by_email = DjangoUser.objects.filter(email__iexact=username).first()
            if user_by_email:
                user = authenticate(username=user_by_email.username, password=password)

        # Intento por first_name
        if user is None:
            from django.contrib.auth.models import User as DjangoUser
            user_by_name = DjangoUser.objects.filter(first_name__iexact=username).first()
            if user_by_name:
                user = authenticate(username=user_by_name.username, password=password)

        if user is None or not user.is_active:
            return Response(
                {'error': 'Credenciales inválidas.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token':    token.key,
            'user_id':  user.id,
            'username': user.username,
            'email':    user.email,
            'nombre':   user.get_full_name() or user.username,
            'is_admin': user.is_superuser,
        })

class ObtenerTokenPorTipoView(APIView):
    permission_classes = []

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        tipo = request.data.get('tipo', 'usuario').strip().lower()

        if tipo in ('admin', 'administrador'):
            user = self._auth_admin(username, password)
        elif tipo == 'empleado':
            user = self._auth_empleado(username, password)
        elif tipo == 'usuario':
            user = self._auth_usuario(username, password)
        else:
            user = None

        if user is None or not user.is_active:
            return Response(
                {'error': 'Credenciales inválidas.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'nombre': user.get_full_name() or user.first_name or user.username,
            'tipo': tipo,
            'is_admin': user.is_superuser,
        })

    def _auth_admin(self, username, password):
        user = self._auth_user(username, password)
        if user and user.is_superuser:
            return user
        return None

    def _auth_user(self, username, password):
        user = authenticate(username=username, password=password)
        if user:
            return user
        user_by_email = User.objects.filter(email__iexact=username).first()
        if user_by_email:
            return authenticate(username=user_by_email.username, password=password)
        return None

    def _auth_usuario(self, username, password):
        usuario = Usuario.objects.filter(
            Q(email__iexact=username) | Q(nombre__iexact=username),
            activo=True,
        ).select_related('user').first()
        if not usuario:
            return None
        user = (
            usuario.user
            or User.objects.filter(username__iexact=usuario.email).first()
            or User.objects.filter(email__iexact=usuario.email).first()
        )
        if not user:
            return None
        if usuario.user_id != user.id:
            usuario.user = user
            usuario.save(update_fields=['user'])
        return authenticate(username=user.username, password=password)

    def _auth_empleado(self, username, password):
        empleado = Empleado.objects.filter(
            Q(email__iexact=username) | Q(nombre__iexact=username),
            activo=True,
        ).first()
        if not empleado or not check_password(password, empleado.password):
            return None
        user = (
            User.objects.filter(username__iexact=empleado.email).first()
            or User.objects.filter(email__iexact=empleado.email).first()
        )
        if not user:
            user = User.objects.create_user(
                username=empleado.email,
                email=empleado.email,
                password=password,
                first_name=empleado.nombre,
            )
        else:
            changed = False
            if user.username != empleado.email:
                user.username = empleado.email
                changed = True
            if user.email != empleado.email:
                user.email = empleado.email
                changed = True
            if user.first_name != empleado.nombre:
                user.first_name = empleado.nombre
                changed = True
            if not user.check_password(password):
                user.set_password(password)
                changed = True
            if changed:
                user.save()
        return authenticate(username=user.username, password=password)


class CerrarSesionAPIView(APIView):
    """
    POST /api/v1/auth/logout/
    Invalida el token actual del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        return Response({'detail': 'Sesión cerrada correctamente.'})


# ─────────────────────────────────────────────
#  CATÁLOGO
# ─────────────────────────────────────────────

def _usuario_actual_api(request):
    perfil = getattr(request.user, 'perfil_lector', None)
    if perfil and perfil.activo:
        return perfil
    if request.user.email:
        perfil = Usuario.objects.filter(email__iexact=request.user.email, activo=True).first()
        if perfil and perfil.user_id is None:
            perfil.user = request.user
            perfil.save(update_fields=['user'])
        return perfil
    return Usuario.objects.filter(email__iexact=request.user.username, activo=True).first()


def _config_int(clave, default, minimo=1, maximo=365):
    try:
        valor = int(Configuracion.get(clave, default))
    except (TypeError, ValueError):
        return default
    return max(minimo, min(valor, maximo))


def _notificar(evento):
    try:
        from .views import notificar_tiempo_real
        notificar_tiempo_real(evento)
    except Exception:
        pass


def _activar_reservas(request=None):
    try:
        from .views import vencer_reservas_expiradas, sincronizar_reservas_disponibles
        vencer_reservas_expiradas()
        sincronizar_reservas_disponibles(request)
    except Exception:
        pass


class RegistroUsuarioAPIView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = RegistroUsuarioAPISerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.create_user(
            username=data['email'],
            email=data['email'],
            password=data['password'],
            first_name=data['nombre'],
        )
        usuario = Usuario.objects.create(
            user=user,
            nombre=data['nombre'],
            email=data['email'],
            telefono=data['telefono'],
        )
        token, _ = Token.objects.get_or_create(user=user)
        # Auditoría: request es anónimo en este endpoint público,
        # pero registrar_auditoria lo maneja dejando usuario=None.
        _registrar_auditoria_api(
            request, 'Usuario', usuario.id, 'CREATE', str(usuario),
            datos_nuevos={'nombre': usuario.nombre, 'email': usuario.email},
        )
        return Response({
            'token': token.key,
            'user_id': user.id,
            'usuario': UsuarioSerializer(usuario).data,
        }, status=status.HTTP_201_CREATED)


class PerfilAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usuario = _usuario_actual_api(request)
        empleado = Empleado.objects.filter(email__iexact=request.user.email, activo=True).first()
        rol = 'admin' if request.user.is_superuser else ('empleado' if empleado else 'usuario')
        return Response({
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'nombre': request.user.get_full_name() or request.user.first_name or request.user.username,
                'rol': rol,
            },
            'usuario': UsuarioSerializer(usuario).data if usuario else None,
            'empleado': EmpleadoSerializer(empleado).data if empleado else None,
        })


class ConfiguracionPublicaAPIView(APIView):
    permission_classes = []

    def get(self, request):
        data = {
            'nombre_biblioteca': Configuracion.get('nombre_biblioteca', "Orion's Library"),
            'max_libros_cliente': _config_int('max_libros_cliente', 3, 1, 50),
            'dias_prestamo_defecto': _config_int('dias_prestamo_defecto', 7, 1, 60),
            'dias_gracia': 1,
        }
        return Response(ConfiguracionPublicaSerializer(data).data)


# ─────────────────────────────────────────────
#  CATÁLOGO: AUTORES Y GÉNEROS
# ─────────────────────────────────────────────

class AutorViewSet(viewsets.ModelViewSet):
    queryset           = Autor.objects.all()
    serializer_class   = AutorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['nombre']

    def perform_create(self, serializer):
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Autor', obj.id, 'CREATE', str(obj),
            datos_nuevos={'nombre': obj.nombre},
        )

    def perform_update(self, serializer):
        ant = {'nombre': serializer.instance.nombre}
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Autor', obj.id, 'UPDATE', str(obj),
            datos_anteriores=ant,
            datos_nuevos={'nombre': obj.nombre},
        )

    def perform_destroy(self, instance):
        _registrar_auditoria_api(
            self.request, 'Autor', instance.id, 'DELETE', str(instance),
            datos_anteriores={'nombre': instance.nombre},
        )
        instance.delete()


class GeneroViewSet(viewsets.ModelViewSet):
    queryset           = Genero.objects.all()
    serializer_class   = GeneroSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['nombre']

    def perform_create(self, serializer):
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Genero', obj.id, 'CREATE', str(obj),
            datos_nuevos={'nombre': obj.nombre},
        )

    def perform_update(self, serializer):
        ant = {'nombre': serializer.instance.nombre}
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Genero', obj.id, 'UPDATE', str(obj),
            datos_anteriores=ant,
            datos_nuevos={'nombre': obj.nombre},
        )

    def perform_destroy(self, instance):
        _registrar_auditoria_api(
            self.request, 'Genero', instance.id, 'DELETE', str(instance),
            datos_anteriores={'nombre': instance.nombre},
        )
        instance.delete()


# ─────────────────────────────────────────────
#  LIBROS
# ─────────────────────────────────────────────

class LibroViewSet(viewsets.ModelViewSet):
    """
    GET  /api/v1/libros/            → listar (con ?search=<q>)
    POST /api/v1/libros/            → crear
    GET  /api/v1/libros/{id}/       → detalle
    PUT  /api/v1/libros/{id}/       → actualizar
    DEL  /api/v1/libros/{id}/       → eliminar

    Acciones extra:
    POST /api/v1/libros/importar/   → importar 20 libros de Open Library
    """
    queryset           = Libro.objects.prefetch_related('autores', 'generos').all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['titulo', 'autores__nombre', 'generos__nombre', 'isbn_13', 'isbn_10']
    ordering_fields    = ['titulo', 'creado_en', 'cantidad_disponible']
    ordering           = ['-creado_en']

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return LibroWriteSerializer
        return LibroSerializer

    @action(detail=False, methods=['post'])
    def importar(self, request):
        from .services import GoogleBooksService
        query    = request.data.get('query', 'ingenieria de sistemas')
        cantidad = int(request.data.get('cantidad', 20))
        nuevos   = GoogleBooksService.solicitar_mas_libros(query=query, cantidad=cantidad)
        return Response({
            'libros_importados': nuevos,
            'mensaje': f'Se importaron {nuevos} libro(s) nuevo(s) con el término "{query}".',
        })

    @action(detail=False, methods=['get'])
    def disponibles(self, request):
        qs = self.get_queryset().filter(cantidad_disponible__gt=0)
        serializer = LibroSerializer(qs, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        libro = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Libro', libro.id, 'CREATE', str(libro),
            datos_nuevos={'titulo': libro.titulo},
        )

    def perform_update(self, serializer):
        ant = {'titulo': serializer.instance.titulo}
        libro = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Libro', libro.id, 'UPDATE', str(libro),
            datos_anteriores=ant,
            datos_nuevos={'titulo': libro.titulo},
        )

    def perform_destroy(self, instance):
        _registrar_auditoria_api(
            self.request, 'Libro', instance.id, 'DELETE', str(instance),
            datos_anteriores={'titulo': instance.titulo},
        )
        instance.delete()


# ─────────────────────────────────────────────
#  PERSONAS
# ─────────────────────────────────────────────

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset           = Usuario.objects.filter(activo=True)
    serializer_class   = UsuarioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['nombre', 'email']

    def perform_create(self, serializer):
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Usuario', obj.id, 'CREATE', str(obj),
            datos_nuevos={'nombre': obj.nombre, 'email': obj.email},
        )

    def perform_update(self, serializer):
        ant = {'nombre': serializer.instance.nombre, 'email': serializer.instance.email}
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Usuario', obj.id, 'UPDATE', str(obj),
            datos_anteriores=ant,
            datos_nuevos={'nombre': obj.nombre, 'email': obj.email},
        )

    def destroy(self, request, *args, **kwargs):
        usuario = self.get_object()
        if Prestamo.objects.filter(usuario=usuario, estado__in=['Activo', 'Retraso']).exists():
            return Response({'error': 'El usuario tiene préstamos activos.'}, status=400)
        _registrar_auditoria_api(
            request, 'Usuario', usuario.id, 'DELETE', str(usuario),
            datos_anteriores={'nombre': usuario.nombre, 'email': usuario.email},
        )
        usuario.activo = False
        usuario.save(update_fields=['activo'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmpleadoViewSet(viewsets.ModelViewSet):
    queryset           = Empleado.objects.filter(activo=True)
    serializer_class   = EmpleadoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['nombre', 'email']

    def perform_create(self, serializer):
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Empleado', obj.id, 'CREATE', str(obj),
            datos_nuevos={'nombre': obj.nombre, 'email': obj.email},
        )

    def perform_update(self, serializer):
        ant = {'nombre': serializer.instance.nombre, 'email': serializer.instance.email}
        obj = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Empleado', obj.id, 'UPDATE', str(obj),
            datos_anteriores=ant,
            datos_nuevos={'nombre': obj.nombre, 'email': obj.email},
        )

    def destroy(self, request, *args, **kwargs):
        empleado = self.get_object()
        if Prestamo.objects.filter(empleado=empleado, estado__in=['Activo', 'Retraso']).exists():
            return Response(
                {'error': 'El empleado tiene préstamos activos asignados.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        _registrar_auditoria_api(
            request, 'Empleado', empleado.id, 'DELETE', str(empleado),
            datos_anteriores={'nombre': empleado.nombre, 'email': empleado.email},
        )
        empleado.activo = False
        empleado.save(update_fields=['activo'])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
#  PRÉSTAMOS
# ─────────────────────────────────────────────

class PrestamoViewSet(viewsets.ModelViewSet):
    """
    Acciones extra:
    POST /api/v1/prestamos/{id}/devolver/  → marcar como devuelto
    """
    queryset           = (
        Prestamo.objects
        .select_related('usuario', 'empleado')
        .prefetch_related('libros', 'detalleprestamo_set')
        .order_by('-id')
    )
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['usuario__nombre', 'estado']
    ordering_fields    = ['fecha_prestamo', 'fecha_limite', 'estado']

    def get_serializer_class(self):
        if self.action == 'create':
            return PrestamoCreateSerializer
        return PrestamoSerializer

    def perform_create(self, serializer):
        prestamo = serializer.save()
        usuario_nombre = prestamo.usuario.nombre if prestamo.usuario else 'Desconocido'
        _registrar_auditoria_api(
            self.request, 'Prestamo', prestamo.id, 'CREATE', str(prestamo),
            datos_nuevos={
                'usuario': usuario_nombre,
                'fecha_limite': str(prestamo.fecha_limite),
                'estado': prestamo.estado,
            },
        )

    def perform_update(self, serializer):
        ant = {'estado': serializer.instance.estado}
        prestamo = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Prestamo', prestamo.id, 'UPDATE', str(prestamo),
            datos_anteriores=ant,
            datos_nuevos={'estado': prestamo.estado},
        )

    def destroy(self, request, *args, **kwargs):
        prestamo = self.get_object()
        if prestamo.estado != 'Devuelto':
            return Response(
                {'error': 'Solo se pueden eliminar préstamos con estado "Devuelto".'},
                status=status.HTTP_400_BAD_REQUEST
            )
        _registrar_auditoria_api(
            request, 'Prestamo', prestamo.id, 'DELETE', str(prestamo),
            datos_anteriores={'estado': prestamo.estado},
        )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def devolver(self, request, pk=None):
        """POST /api/v1/prestamos/{id}/devolver/"""
        from .models import DetallePrestamo, Multa, Historial
        prestamo = self.get_object()

        if prestamo.estado not in ('Activo', 'Retraso'):
            return Response(
                {'error': 'Este préstamo ya fue procesado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        hoy = timezone.now().date()
        prestamo.estado = 'Devuelto'
        prestamo.save(update_fields=['estado'])

        DetallePrestamo.objects.filter(prestamo=prestamo, devuelto=False).update(
            fecha_devolucion_real=hoy, devuelto=True
        )
        for detalle in DetallePrestamo.objects.filter(prestamo=prestamo,
                                                       fecha_devolucion_real=hoy):
            detalle.libro.cantidad_disponible += 1
            detalle.libro.save(update_fields=['cantidad_disponible'])
            try:
                from .views import activar_siguiente_reserva
                activar_siguiente_reserva(detalle.libro, request)
            except Exception:
                pass

        multa = Multa.objects.filter(prestamo=prestamo, estado='Pendiente').first()
        if multa:
            multa.monto = (hoy - prestamo.fecha_limite).days * 1000
            multa.save(update_fields=['monto'])

        usuario_nombre = prestamo.usuario.nombre if prestamo.usuario else 'Eliminado'
        Historial.objects.create(
            tipo_accion='Devolucion',
            descripcion=f'{usuario_nombre} devolvió "{prestamo.libros_resumen}" el {hoy}.',
            prestamo=prestamo,
        )
        _registrar_auditoria_api(
            request, 'Prestamo', prestamo.id, 'UPDATE', str(prestamo),
            datos_nuevos={'estado': 'Devuelto', 'fecha': str(hoy)},
        )
        return Response({'detail': 'Préstamo devuelto correctamente.',
                         'multa_pendiente': multa is not None})


# ─────────────────────────────────────────────
#  MULTAS
# ─────────────────────────────────────────────

class MultaViewSet(viewsets.ModelViewSet):
    queryset           = Multa.objects.select_related('prestamo__usuario').order_by('-id')
    serializer_class   = MultaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['estado', 'prestamo__usuario__nombre']

    def perform_create(self, serializer):
        multa = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Multa', multa.id, 'CREATE', str(multa),
            datos_nuevos={
                'monto': float(multa.monto),
                'estado': multa.estado,
                'motivo': multa.motivo if hasattr(multa, 'motivo') else '',
            },
        )

    def perform_update(self, serializer):
        ant = {'estado': serializer.instance.estado, 'monto': float(serializer.instance.monto)}
        multa = serializer.save()
        _registrar_auditoria_api(
            self.request, 'Multa', multa.id, 'UPDATE', str(multa),
            datos_anteriores=ant,
            datos_nuevos={'estado': multa.estado, 'monto': float(multa.monto)},
        )

    def destroy(self, request, *args, **kwargs):
        multa = self.get_object()
        _registrar_auditoria_api(
            request, 'Multa', multa.id, 'DELETE', str(multa),
            datos_anteriores={'estado': multa.estado, 'monto': float(multa.monto)},
        )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def pagar(self, request, pk=None):
        """POST /api/v1/multas/{id}/pagar/"""
        from .models import Historial
        multa = self.get_object()
        hoy   = timezone.now().date()

        if multa.estado == 'Pagada':
            return Response({'error': 'Esta multa ya fue pagada.'}, status=400)

        multa.estado     = 'Pagada'
        multa.fecha_pago = hoy
        multa.save(update_fields=['estado', 'fecha_pago'])

        Historial.objects.create(
            tipo_accion='Multa',
            descripcion=f'Multa #{multa.id} de ${multa.monto} pagada el {hoy} vía API.',
            prestamo=multa.prestamo,
        )
        _registrar_auditoria_api(
            request, 'Multa', multa.id, 'UPDATE', str(multa),
            datos_nuevos={'estado': 'Pagada', 'monto': float(multa.monto), 'fecha_pago': str(hoy)},
        )
        return Response({'detail': 'Multa pagada correctamente.'})


# ─────────────────────────────────────────────
#  HISTORIAL  (solo lectura)
# ─────────────────────────────────────────────

class HistorialViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Historial.objects.select_related('prestamo__usuario').order_by('-fecha_accion')
    serializer_class   = HistorialSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['tipo_accion', 'descripcion']


# ─────────────────────────────────────────────
#  AUDITORÍA  (solo superadmin, solo lectura)
# ─────────────────────────────────────────────

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Solo accesible para administradores."""
    queryset           = AuditLog.objects.select_related('usuario').order_by('-fecha')
    serializer_class   = AuditLogSerializer
    permission_classes = [IsAdminUser]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['tabla', 'accion', 'objeto_repr', 'empleado_nombre']


# ─────────────────────────────────────────────
#  DASHBOARD RESUMEN  (útil para Flutter)
# ─────────────────────────────────────────────

class DashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import Prestamo, Multa, Libro
        from .views import actualizar_estados_retraso
        actualizar_estados_retraso()

        multas_pendientes = Multa.objects.filter(estado='Pendiente')
        total_multas = sum(m.monto for m in multas_pendientes)

        return Response({
            'total_libros':      Libro.objects.count(),
            'libros_disponibles': Libro.objects.filter(cantidad_disponible__gt=0).count(),
            'prestamos_activos': Prestamo.objects.filter(estado='Activo').count(),
            'prestamos_retraso': Prestamo.objects.filter(estado='Retraso').count(),
            'multas_pendientes': multas_pendientes.count(),
            'total_multas':      float(total_multas),
        })


class ClienteDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .views import actualizar_estados_retraso
        actualizar_estados_retraso()
        _activar_reservas(request)
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)

        prestamos = Prestamo.objects.filter(usuario=usuario).prefetch_related('libros').order_by('-id')
        activos = prestamos.filter(estado__in=['Activo', 'Retraso'])
        multas = Multa.objects.filter(prestamo__usuario=usuario, estado='Pendiente')
        leidos = DetallePrestamo.objects.filter(
            prestamo__usuario=usuario, devuelto=True
        ).values('libro_id').distinct().count()
        hoy = timezone.now().date()
        alertas = [
            PrestamoSerializer(p).data for p in activos
            if 0 <= (p.fecha_limite - hoy).days <= 2
        ]

        return Response({
            'usuario': UsuarioSerializer(usuario).data,
            'estadisticas': {
                'libros_leidos': leidos,
                'prestamos_activos': activos.count(),
                'multas_sin_pagar': float(sum(m.monto for m in multas)),
            },
            'prestamos': PrestamoSerializer(prestamos[:10], many=True).data,
            'reservas': ReservaLibroSerializer(
                ReservaLibro.objects.filter(
                    usuario=usuario, estado__in=['En cola', 'Apartado']
                ).select_related('libro'),
                many=True,
            ).data,
            'multas': MultaSerializer(multas, many=True).data,
            'alertas_entrega': alertas,
        })


class ClientePrestamosAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        prestamos = Prestamo.objects.filter(usuario=usuario).prefetch_related('libros').order_by('-id')
        return Response(PrestamoSerializer(prestamos, many=True).data)

    def post(self, request):
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        libro_id = request.data.get('libro_id')
        libro = Libro.objects.filter(id=libro_id).first()
        if not libro:
            return Response({'error': 'Libro no encontrado.'}, status=404)
        if Multa.objects.filter(prestamo__usuario=usuario, estado='Pendiente').exists():
            return Response({'error': 'Tienes multas pendientes.'}, status=400)
        if DetallePrestamo.objects.filter(
            prestamo__usuario=usuario,
            prestamo__estado__in=['Activo', 'Retraso'],
            libro=libro,
            devuelto=False,
        ).exists():
            return Response({'error': 'Ya tienes un ejemplar activo de este libro.'}, status=400)
        max_libros = _config_int('max_libros_cliente', 3, 1, 50)
        if Prestamo.objects.filter(usuario=usuario, estado__in=['Activo', 'Retraso']).count() >= max_libros:
            return Response({'error': f'Alcanzaste el maximo de {max_libros} libros prestados.'}, status=400)
        reserva_ajena = ReservaLibro.objects.filter(libro=libro, estado='Apartado').exclude(usuario=usuario).first()
        if reserva_ajena:
            return Response({'error': 'Este libro esta apartado temporalmente por otro usuario.'}, status=400)

        with transaction.atomic():
            libro = Libro.objects.select_for_update().get(id=libro.id)
            if libro.cantidad_disponible <= 0:
                return Response({'error': 'No hay existencias disponibles.'}, status=400)
            dias_base = _config_int('dias_prestamo_defecto', 7, 1, 60)
            fecha_limite = timezone.now().date() + timedelta(days=dias_base + 1)
            prestamo = Prestamo.objects.create(
                usuario=usuario,
                empleado=None,
                fecha_limite=fecha_limite,
                estado='Activo',
                observaciones=f'Prestamo solicitado por API. Incluye {dias_base} dias y 1 dia de gracia.',
            )
            DetallePrestamo.objects.create(prestamo=prestamo, libro=libro)
            libro.cantidad_disponible -= 1
            libro.save(update_fields=['cantidad_disponible'])
            ReservaLibro.objects.filter(
                usuario=usuario, libro=libro, estado='Apartado'
            ).update(estado='Convertido')

        Historial.objects.create(
            tipo_accion='Prestamo',
            descripcion=f'{usuario.nombre} solicito "{libro.titulo}" via API. Vence el {fecha_limite}.',
            prestamo=prestamo,
        )
        _registrar_auditoria_api(
            request, 'Prestamo', prestamo.id, 'CREATE', f'Préstamo API: {libro.titulo}',
            datos_nuevos={
                'usuario': usuario.nombre,
                'libro': libro.titulo,
                'fecha_limite': str(fecha_limite),
            },
        )
        _notificar('prestamo_creado')
        return Response({
            'detail': f'Debes devolver "{libro.titulo}" antes del {fecha_limite}.',
            'prestamo': PrestamoSerializer(prestamo).data,
        }, status=201)


class ClienteReservasAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _activar_reservas(request)
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        reservas = ReservaLibro.objects.filter(usuario=usuario).select_related('libro').order_by('-fecha_reserva')
        return Response(ReservaLibroSerializer(reservas, many=True).data)

    def post(self, request):
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        libro = Libro.objects.filter(id=request.data.get('libro_id')).first()
        if not libro:
            return Response({'error': 'Libro no encontrado.'}, status=404)
        if libro.cantidad_disponible > 0:
            return Response({'error': 'El libro esta disponible; puedes pedirlo directamente.'}, status=400)
        if DetallePrestamo.objects.filter(
            prestamo__usuario=usuario,
            prestamo__estado__in=['Activo', 'Retraso'],
            libro=libro,
            devuelto=False,
        ).exists():
            return Response({'error': 'Ya tienes un ejemplar activo de este libro.'}, status=400)
        reserva = ReservaLibro.objects.filter(
            usuario=usuario,
            libro=libro,
            estado__in=['En cola', 'Apartado'],
        ).first()
        if reserva:
            return Response({'detail': 'Ya estas en la cola para este libro.', 'reserva': ReservaLibroSerializer(reserva).data})
        reserva = ReservaLibro.objects.create(usuario=usuario, libro=libro, estado='En cola')
        _registrar_auditoria_api(
            request, 'ReservaLibro', reserva.id, 'CREATE', str(reserva),
            datos_nuevos={'usuario': usuario.nombre, 'libro': libro.titulo, 'estado': 'En cola'},
        )
        _notificar('reserva_creada')
        return Response({
            'detail': 'Reserva creada. Estate atento a tu dashboard para pedirlo cuando este apartado.',
            'reserva': ReservaLibroSerializer(reserva).data,
        }, status=201)


class ClienteHistorialAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        detalles = DetallePrestamo.objects.filter(
            prestamo__usuario=usuario, devuelto=True
        ).select_related('libro', 'prestamo').order_by('-prestamo__fecha_prestamo')
        return Response(DetallePrestamoSerializer(detalles, many=True).data)


class ClienteDeudasAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        multas = Multa.objects.filter(prestamo__usuario=usuario).order_by('-fecha_generacion')
        return Response(MultaSerializer(multas, many=True).data)


class ClienteValoracionesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        valoraciones = ValoracionLibro.objects.filter(usuario=usuario).select_related('libro')
        return Response(ValoracionLibroSerializer(valoraciones, many=True).data)

    def post(self, request):
        usuario = _usuario_actual_api(request)
        if not usuario:
            return Response({'error': 'No hay perfil de usuario lector asociado.'}, status=403)
        libro = Libro.objects.filter(id=request.data.get('libro_id')).first()
        if not libro:
            return Response({'error': 'Libro no encontrado.'}, status=404)
        if not DetallePrestamo.objects.filter(prestamo__usuario=usuario, libro=libro, devuelto=True).exists():
            return Response({'error': 'Solo puedes valorar libros leidos/devueltos.'}, status=400)
        try:
            puntaje = int(request.data.get('puntaje', 0))
        except (TypeError, ValueError):
            puntaje = 0
        if puntaje < 1 or puntaje > 5:
            return Response({'error': 'La valoracion debe estar entre 1 y 5.'}, status=400)
        valoracion, _ = ValoracionLibro.objects.update_or_create(
            usuario=usuario,
            libro=libro,
            defaults={
                'puntaje': puntaje,
                'comentario': request.data.get('comentario', ''),
            },
        )
        _registrar_auditoria_api(
            request, 'ValoracionLibro', valoracion.id, 'CREATE', str(valoracion),
            datos_nuevos={'usuario': usuario.nombre, 'libro': libro.titulo, 'puntaje': puntaje},
        )
        _notificar('valoracion_creada')
        return Response(ValoracionLibroSerializer(valoracion).data, status=201)