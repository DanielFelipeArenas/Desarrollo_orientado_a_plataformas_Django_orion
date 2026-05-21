import uuid
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout as auth_logout
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.http import HttpResponse

from .models import (
    Libro, Prestamo, Multa, Usuario, Empleado,
    Historial, Autor, Genero, DetallePrestamo,
    AuditLog, Configuracion, ReservaLibro, ValoracionLibro,
)


# ─────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────

def _get_client_ip(request):
    """Extrae la IP real del cliente (considera proxies)."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def registrar_auditoria(request, tabla, objeto_id, accion,
                        repr_objeto='', datos_anteriores=None, datos_nuevos=None):
    """
    Crea un registro en AuditLog.
    Llamar desde cualquier vista antes/después de un CREATE / UPDATE / DELETE.
    """
    AuditLog.objects.create(
        tabla=tabla,
        objeto_id=objeto_id,
        objeto_repr=str(repr_objeto)[:255],
        accion=accion,
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
        usuario=request.user if request.user.is_authenticated else None,
        empleado_nombre=(
            request.user.get_full_name() or request.user.username
            if request.user.is_authenticated else ''
        ),
        ip_address=_get_client_ip(request) or None,
    )


def obtener_empleado_actual(request):
    """Devuelve el Empleado asociado al usuario autenticado, o None."""
    if not request.user.is_authenticated or request.user.is_superuser:
        return None
    if request.user.email:
        emp = Empleado.objects.filter(email__iexact=request.user.email).first()
        if emp:
            return emp
    emp = Empleado.objects.filter(email__iexact=request.user.username).first()
    if emp:
        return emp
    if request.user.first_name:
        return Empleado.objects.filter(nombre__iexact=request.user.first_name).first()
    return None


def obtener_usuario_actual(request):
    """Devuelve el perfil lector asociado al auth_user actual, o None."""
    if not request.user.is_authenticated:
        return None
    perfil = getattr(request.user, 'perfil_lector', None)
    if perfil and perfil.activo:
        return perfil
    if request.user.email:
        perfil = Usuario.objects.filter(email__iexact=request.user.email, activo=True).first()
        if perfil:
            if perfil.user_id is None:
                perfil.user = request.user
                perfil.save(update_fields=['user'])
            return perfil
    return Usuario.objects.filter(email__iexact=request.user.username, activo=True).first()


def es_usuario_comun(request):
    return (
        request.user.is_authenticated
        and not request.user.is_superuser
        and obtener_empleado_actual(request) is None
        and obtener_usuario_actual(request) is not None
    )


class EmpleadoRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_superuser or obtener_empleado_actual(request):
            return super().dispatch(request, *args, **kwargs)
        messages.error(request, 'Acceso restringido a empleados y administradores.')
        return redirect('dashboard')


class AdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        messages.error(request, 'Acceso restringido a administradores.')
        return redirect('dashboard')


def activar_siguiente_reserva(libro, request=None):
    """Aparta por un dia el primer lector en cola cuando vuelve una copia."""
    ahora = timezone.now()
    reserva = (
        ReservaLibro.objects
        .filter(libro=libro, estado='En cola')
        .select_related('usuario', 'libro')
        .first()
    )
    if not reserva:
        return None
    reserva.estado = 'Apartado'
    reserva.fecha_apartado = ahora
    reserva.fecha_expiracion = ahora + timedelta(days=1)
    reserva.save(update_fields=['estado', 'fecha_apartado', 'fecha_expiracion'])
    if request:
        registrar_auditoria(
            request, 'ReservaLibro', reserva.id, 'UPDATE', str(reserva),
            datos_nuevos={
                'estado': 'Apartado',
                'vence': str(reserva.fecha_expiracion),
                'libro': libro.titulo,
                'usuario': reserva.usuario.nombre,
            },
        )
    return reserva


def vencer_reservas_expiradas():
    ahora = timezone.now()
    vencidas = ReservaLibro.objects.filter(estado='Apartado', fecha_expiracion__lt=ahora)
    for reserva in vencidas.select_related('libro'):
        reserva.estado = 'Vencido'
        reserva.save(update_fields=['estado'])
        activar_siguiente_reserva(reserva.libro)


def sincronizar_reservas_disponibles(request=None):
    libros_con_reserva = (
        Libro.objects
        .filter(cantidad_disponible__gt=0, reservas__estado='En cola')
        .distinct()
    )
    for libro in libros_con_reserva:
        if not ReservaLibro.objects.filter(libro=libro, estado='Apartado').exists():
            activar_siguiente_reserva(libro, request)


def config_entero(clave, default, minimo=1, maximo=365):
    try:
        valor = int(Configuracion.get(clave, default))
    except (TypeError, ValueError):
        return default
    return max(minimo, min(valor, maximo))


def config_entero_desde_post(request, clave, default, minimo=1, maximo=365):
    try:
        valor = int(request.POST.get(clave, default))
    except (TypeError, ValueError):
        return default
    return max(minimo, min(valor, maximo))


def dias_prestamo_configurados():
    return config_entero('dias_prestamo_defecto', 7, minimo=1, maximo=60)


def max_libros_por_cliente():
    return config_entero('max_libros_cliente', 3, minimo=1, maximo=50)


def notificar_tiempo_real(evento='actualizacion'):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
    except Exception:
        return
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            'biblioteca_updates',
            {'type': 'biblioteca.update', 'evento': evento},
        )


def usuario_tiene_libro_activo(usuario, libro):
    return DetallePrestamo.objects.filter(
        prestamo__usuario=usuario,
        prestamo__estado__in=['Activo', 'Retraso'],
        libro=libro,
        devuelto=False,
    ).exists()


def prestamos_activos_usuario(usuario):
    return Prestamo.objects.filter(usuario=usuario, estado__in=['Activo', 'Retraso']).count()


def actualizar_estados_retraso():
    """
    Detecta préstamos vencidos, los pasa a 'Retraso' y genera multa/historial
    si aún no los tienen.  Se llama al cargar cualquier lista de préstamos.
    """
    hoy = timezone.now().date()
    for prestamo in Prestamo.objects.filter(estado='Activo', fecha_limite__lt=hoy):
        prestamo.estado = 'Retraso'
        prestamo.save(update_fields=['estado'])

        if not Multa.objects.filter(prestamo=prestamo, estado='Pendiente').exists():
            dias_retraso = (hoy - prestamo.fecha_limite).days
            Multa.objects.create(
                monto=dias_retraso * 1000,
                motivo='Retraso en devolución de libro',
                estado='Pendiente',
                prestamo=prestamo,
            )
            Historial.objects.create(
                tipo_accion='Moroso',
                descripcion=(
                    f'El préstamo #{prestamo.id} ("{prestamo.libros_resumen}") '
                    f'no fue devuelto a tiempo. '
                    f'Multa generada por {dias_retraso} día(s) de retraso.'
                ),
                prestamo=prestamo,
            )


def crear_superusuario_inicial(request):
    if User.objects.filter(is_superuser=True).exists():
        return HttpResponse(
            "Ya existe un superusuario. Por seguridad esta ruta está deshabilitada."
        )
    User.objects.create_superuser('adminProv', 'admin@admin.com', 'admin123')
    return HttpResponse(
        "Superusuario creado.<br><b>Usuario:</b> adminProv "
        "<br><b>Contraseña:</b> admin123 "
        "<br><br><a href='/login/'>Ir al Login</a>"
    )


# ─────────────────────────────────────────────
#  AUTENTICACIÓN  (FIX #7 – sesión caduca al cerrar navegador)
# ─────────────────────────────────────────────

class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, 'login.html', {'login_error': False})

    def post(self, request):
        identificador = request.POST.get('username', '').strip()
        password      = request.POST.get('password', '')

        user = authenticate(request, username=identificador, password=password)

        # Intento por e-mail en tabla auth_user
        if user is None:
            user_por_email = User.objects.filter(email__iexact=identificador).first()
            if user_por_email:
                user = authenticate(request, username=user_por_email.username, password=password)

        # Intento por perfil lector: permite iniciar sesión con nombre o e-mail del Usuario.
        if user is None:
            usuario = Usuario.objects.filter(
                Q(email__iexact=identificador) | Q(nombre__iexact=identificador),
                activo=True,
            ).select_related('user').first()
            if usuario:
                user_usuario = (
                    usuario.user
                    or User.objects.filter(username__iexact=usuario.email).first()
                    or User.objects.filter(email__iexact=usuario.email).first()
                )
                if user_usuario:
                    if usuario.user_id != user_usuario.id:
                        usuario.user = user_usuario
                        usuario.save(update_fields=['user'])
                    user = authenticate(request, username=user_usuario.username, password=password)

        # Intento por tabla Empleado (crea/sincroniza el auth_user si hace falta)
        if user is None:
            empleado = Empleado.objects.filter(
                Q(email__iexact=identificador) | Q(nombre__iexact=identificador)
            ).first()
            if empleado:
                user_emp = User.objects.filter(username__iexact=empleado.email).first()
                password_valido = check_password(password, empleado.password)

                if not user_emp and password_valido:
                    user_emp = User.objects.create_user(
                        username=empleado.email, email=empleado.email,
                        password=password, first_name=empleado.nombre,
                    )
                elif user_emp and password_valido and not user_emp.check_password(password):
                    user_emp.set_password(password)
                    user_emp.save()

                if user_emp and password_valido:
                    user = authenticate(request, username=user_emp.username, password=password)

        if user is not None:
            login(request, user)
            # ── FIX #7: la sesión expira al cerrar el navegador ──────────
            request.session.set_expiry(0)
            # ─────────────────────────────────────────────────────────────
            registrar_auditoria(request, 'auth', user.id, 'LOGIN', str(user))
            return redirect('dashboard')

        return render(request, 'login.html', {'login_error': True})


class RegistroUsuarioView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, 'registro.html')

    def post(self, request):
        nombre = request.POST.get('nombre', '').strip()
        email = request.POST.get('email', '').strip().lower()
        telefono = request.POST.get('telefono', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if not all([nombre, email, telefono, password, password2]):
            messages.error(request, 'Completa todos los campos obligatorios.')
            return redirect('registro_usuario')
        if password != password2:
            messages.error(request, 'Las contraseñas no coinciden.')
            return redirect('registro_usuario')
        if Empleado.objects.filter(email__iexact=email, activo=True).exists():
            messages.error(request, 'Este correo ya pertenece a una cuenta interna.')
            return redirect('registro_usuario')
        if User.objects.filter(username__iexact=email).exists() or Usuario.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Ya existe una cuenta registrada con ese correo.')
            return redirect('registro_usuario')

        user = User.objects.create_user(
            username=email, email=email, password=password, first_name=nombre
        )
        usuario = Usuario.objects.create(
            user=user, nombre=nombre, email=email, telefono=telefono
        )
        registrar_auditoria(
            request, 'Usuario', usuario.id, 'CREATE', str(usuario),
            datos_nuevos={'nombre': nombre, 'email': email, 'registro_publico': True},
        )
        login(request, user)
        request.session.set_expiry(0)
        messages.success(request, 'Registro completado. Bienvenido a Orion.')
        return redirect('dashboard')


class LogoutView(View):
    """Cierra la sesión de forma explícita y redirige al login."""
    def get(self, request):
        return self._logout(request)

    def post(self, request):
        return self._logout(request)

    def _logout(self, request):
        if request.user.is_authenticated:
            registrar_auditoria(request, 'auth', request.user.id, 'LOGOUT', str(request.user))
        auth_logout(request)
        return redirect('login')


# ─────────────────────────────────────────────
#  DASHBOARD & BÚSQUEDA
# ─────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        actualizar_estados_retraso()
        vencer_reservas_expiradas()
        sincronizar_reservas_disponibles(self.request)
        context = super().get_context_data(**kwargs)
        usuario_actual = obtener_usuario_actual(self.request)
        if es_usuario_comun(self.request):
            hoy = timezone.now().date()
            prestamos_usuario = Prestamo.objects.filter(usuario=usuario_actual)
            prestamos_activos_qs = prestamos_usuario.filter(estado__in=['Activo', 'Retraso'])
            multas_qs = Multa.objects.filter(prestamo__usuario=usuario_actual, estado='Pendiente')
            context.update({
                'es_usuario_comun': True,
                'usuario_actual': usuario_actual,
                'libros_leidos': (
                    DetallePrestamo.objects
                    .filter(prestamo__usuario=usuario_actual, devuelto=True)
                    .values('libro_id')
                    .distinct()
                    .count()
                ),
                'prestamos_activos': prestamos_activos_qs.count(),
                'total_multas': sum(m.monto for m in multas_qs),
                'prestamos_recientes': (
                    prestamos_usuario
                    .prefetch_related('libros')
                    .order_by('-id')[:5]
                ),
                'alertas_entrega': [
                    prestamo for prestamo in prestamos_activos_qs.prefetch_related('libros')
                    if 0 <= (prestamo.fecha_limite - hoy).days <= 2
                ],
                'reservas_usuario': ReservaLibro.objects.filter(
                    usuario=usuario_actual,
                    estado__in=['En cola', 'Apartado']
                ).select_related('libro'),
                'dias_prestamo_defecto': dias_prestamo_configurados(),
                'dias_gracia': 1,
            })
            return context

        multas_pendientes = Multa.objects.filter(estado='Pendiente')
        context.update({
            'es_usuario_comun': False,
            'total_libros':       Libro.objects.count(),
            'prestamos_activos':  Prestamo.objects.filter(estado='Activo').count(),
            'libros_mora':        Prestamo.objects.filter(estado='Retraso').count(),
            'total_multas':       sum(m.monto for m in multas_pendientes),
            'prestamos_recientes': (
                Prestamo.objects
                .select_related('usuario')
                .prefetch_related('libros')
                .order_by('-id')[:5]
            ),
        })
        return context


class BuscarView(LoginRequiredMixin, View):
    def get(self, request):
        query = request.GET.get('q', '').strip()
        contexto = {'query': query, 'libros': [], 'prestamos': [], 'usuarios': []}
        if query:
            contexto['libros'] = Libro.objects.filter(
                Q(titulo__icontains=query)
                | Q(autores__nombre__icontains=query)
                | Q(generos__nombre__icontains=query)
                | Q(isbn_13__icontains=query)
                | Q(isbn_10__icontains=query)
            ).distinct()
            if es_usuario_comun(request):
                return render(request, 'buscar.html', contexto)
            contexto['prestamos'] = (
                Prestamo.objects
                .filter(Q(usuario__nombre__icontains=query))
                .prefetch_related('libros')
                .distinct()
            )
            contexto['usuarios'] = Usuario.objects.filter(
                Q(nombre__icontains=query) | Q(email__icontains=query)
            )
        return render(request, 'buscar.html', contexto)


# ─────────────────────────────────────────────
#  LIBROS
# ─────────────────────────────────────────────

class LibroListView(LoginRequiredMixin, ListView):
    model               = Libro
    template_name       = 'libros.html'
    context_object_name = 'mis_libros'
    ordering            = ['-id']

    def get_queryset(self):
        actualizar_estados_retraso()
        vencer_reservas_expiradas()
        sincronizar_reservas_disponibles(self.request)
        return super().get_queryset().prefetch_related('autores', 'generos')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario_actual = obtener_usuario_actual(self.request)
        context['es_usuario_comun'] = es_usuario_comun(self.request)
        if usuario_actual:
            context['mis_valoraciones'] = {
                valoracion.libro_id: valoracion.puntaje
                for valoracion in ValoracionLibro.objects.filter(usuario=usuario_actual)
            }
            context['mis_reservas_activas'] = set(
                ReservaLibro.objects.filter(
                    usuario=usuario_actual,
                    estado__in=['En cola', 'Apartado']
                ).values_list('libro_id', flat=True)
            )
        return context


class UsuarioPedirLibroView(LoginRequiredMixin, View):
    def post(self, request, pk):
        usuario = obtener_usuario_actual(request)
        if not usuario or not es_usuario_comun(request):
            messages.error(request, 'Solo los usuarios lectores pueden pedir libros desde el catalogo.')
            return redirect('libros')

        libro = get_object_or_404(Libro, id=pk)
        if Multa.objects.filter(prestamo__usuario=usuario, estado='Pendiente').exists():
            messages.error(request, 'Tienes multas pendientes. Debes regularizarlas antes de pedir otro libro.')
            return redirect('libros')
        if usuario_tiene_libro_activo(usuario, libro):
            messages.error(request, 'Ya tienes un ejemplar activo de este libro. Devuelvelo antes de pedirlo otra vez.')
            return redirect('libros')
        if prestamos_activos_usuario(usuario) >= max_libros_por_cliente():
            messages.error(request, f'Alcanzaste el maximo de {max_libros_por_cliente()} libros prestados.')
            return redirect('libros')

        reserva_propia = ReservaLibro.objects.filter(
            usuario=usuario, libro=libro, estado='Apartado'
        ).first()
        reserva_ajena = ReservaLibro.objects.filter(
            libro=libro, estado='Apartado'
        ).exclude(usuario=usuario).first()
        if reserva_ajena:
            messages.warning(request, 'Este libro esta apartado temporalmente por otro usuario.')
            return redirect('libros')
        if libro.cantidad_disponible <= 0:
            messages.warning(request, 'No hay existencias disponibles. Puedes apartarlo para entrar a la cola.')
            return redirect('libros')

        with transaction.atomic():
            libro = Libro.objects.select_for_update().get(id=libro.id)
            if libro.cantidad_disponible <= 0:
                messages.warning(request, 'El libro dejo de estar disponible. Intenta apartarlo.')
                return redirect('libros')
            dias_base = dias_prestamo_configurados()
            fecha_limite = timezone.now().date() + timedelta(days=dias_base + 1)
            prestamo = Prestamo.objects.create(
                usuario=usuario,
                empleado=None,
                fecha_limite=fecha_limite,
                estado='Activo',
                observaciones=f'Prestamo solicitado por el usuario. Incluye {dias_base} dias de prestamo y 1 dia de gracia.',
            )
            DetallePrestamo.objects.create(prestamo=prestamo, libro=libro)
            libro.cantidad_disponible -= 1
            libro.save(update_fields=['cantidad_disponible'])
            if reserva_propia:
                reserva_propia.estado = 'Convertido'
                reserva_propia.save(update_fields=['estado'])

        Historial.objects.create(
            tipo_accion='Prestamo',
            descripcion=(
                f'{usuario.nombre} solicito "{libro.titulo}" desde el portal de usuarios. '
                f'Vence el {fecha_limite}; incluye un dia de gracia.'
            ),
            prestamo=prestamo,
        )
        registrar_auditoria(
            request, 'Prestamo', prestamo.id, 'CREATE', str(prestamo),
            datos_nuevos={
                'usuario': usuario.nombre,
                'libro': libro.titulo,
                'fecha_limite': str(fecha_limite),
                'dias_prestamo': dias_base,
                'dias_gracia': 1,
                'origen': 'portal_usuario',
            },
        )
        notificar_tiempo_real('prestamo_creado')
        messages.success(request, f'Prestamo registrado. Debes devolver "{libro.titulo}" antes del {fecha_limite}.')
        return redirect('dashboard')


class UsuarioReservarLibroView(LoginRequiredMixin, View):
    def post(self, request, pk):
        usuario = obtener_usuario_actual(request)
        if not usuario or not es_usuario_comun(request):
            messages.error(request, 'Solo los usuarios lectores pueden apartar libros.')
            return redirect('libros')
        libro = get_object_or_404(Libro, id=pk)
        if usuario_tiene_libro_activo(usuario, libro):
            messages.error(request, 'Ya tienes un ejemplar activo de este libro; no puedes apartar otro igual.')
            return redirect('libros')
        if libro.cantidad_disponible > 0:
            messages.info(request, 'El libro esta disponible; puedes pedirlo prestado directamente.')
            return redirect('libros')
        reserva = ReservaLibro.objects.filter(
            usuario=usuario,
            libro=libro,
            estado__in=['En cola', 'Apartado'],
        ).first()
        if reserva:
            messages.info(request, 'Ya estas en la cola de reserva para este libro.')
            return redirect('libros')
        reserva = ReservaLibro.objects.create(usuario=usuario, libro=libro, estado='En cola')
        registrar_auditoria(
            request, 'ReservaLibro', reserva.id, 'RESERVA', str(reserva),
            datos_nuevos={'usuario': usuario.nombre, 'libro': libro.titulo, 'estado': reserva.estado},
        )
        notificar_tiempo_real('reserva_creada')
        messages.success(request, f'Quedaste en la cola para "{libro.titulo}". Estate atento a tu dashboard para pedirlo cuando aparezca como apartado.')
        return redirect('libros')


class UsuarioValorarLibroView(LoginRequiredMixin, View):
    def post(self, request, pk):
        usuario = obtener_usuario_actual(request)
        if not usuario or not es_usuario_comun(request):
            messages.error(request, 'Solo los usuarios lectores pueden valorar libros.')
            return redirect('libros')
        libro = get_object_or_404(Libro, id=pk)
        try:
            puntaje = int(request.POST.get('puntaje', 0))
        except ValueError:
            puntaje = 0
        if puntaje < 1 or puntaje > 5:
            messages.error(request, 'La valoracion debe estar entre 1 y 5 estrellas.')
            return redirect('usuario_historial')
        if not DetallePrestamo.objects.filter(prestamo__usuario=usuario, libro=libro, devuelto=True).exists():
            messages.error(request, 'Solo puedes valorar libros que ya hayas devuelto.')
            return redirect('usuario_historial')
        valoracion, _ = ValoracionLibro.objects.update_or_create(
            usuario=usuario,
            libro=libro,
            defaults={'puntaje': puntaje},
        )
        registrar_auditoria(
            request, 'ValoracionLibro', valoracion.id, 'VALORACION', str(valoracion),
            datos_nuevos={'usuario': usuario.nombre, 'libro': libro.titulo, 'puntaje': puntaje},
        )
        notificar_tiempo_real('valoracion_creada')
        messages.success(request, f'Valoraste "{libro.titulo}" con {puntaje} estrella(s).')
        return redirect('usuario_historial')


class UsuarioHistorialLibrosView(LoginRequiredMixin, ListView):
    model = DetallePrestamo
    template_name = 'usuario_historial.html'
    context_object_name = 'detalles'

    def dispatch(self, request, *args, **kwargs):
        if not es_usuario_comun(request):
            messages.error(request, 'Acceso restringido a usuarios lectores.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            DetallePrestamo.objects
            .filter(prestamo__usuario=obtener_usuario_actual(self.request), devuelto=True)
            .select_related('libro', 'prestamo')
            .order_by('-prestamo__fecha_prestamo', '-id')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = obtener_usuario_actual(self.request)
        context['valoraciones_usuario'] = {
            valoracion.libro_id: valoracion.puntaje
            for valoracion in ValoracionLibro.objects.filter(usuario=usuario)
        }
        return context


class UsuarioDeudasView(LoginRequiredMixin, ListView):
    model = Multa
    template_name = 'usuario_deudas.html'
    context_object_name = 'multas'

    def dispatch(self, request, *args, **kwargs):
        if not es_usuario_comun(request):
            messages.error(request, 'Acceso restringido a usuarios lectores.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        actualizar_estados_retraso()
        return (
            Multa.objects
            .filter(prestamo__usuario=obtener_usuario_actual(self.request))
            .select_related('prestamo')
            .prefetch_related('prestamo__libros')
            .order_by('-fecha_generacion')
        )


class LibroCreateView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request):
        autor_str  = request.POST.get('autor', '')
        genero_str = request.POST.get('genero', '')
        cant_disp  = int(request.POST.get('cantidad_disponible', 0))
        cant_total = int(request.POST.get('cantidad_total', 0))
        isbn_nuevo = request.POST.get('isbn', '').strip()

        if isbn_nuevo and Libro.objects.filter(
            Q(isbn_13=isbn_nuevo) | Q(isbn_10=isbn_nuevo)
        ).exists():
            messages.error(request, f'El ISBN {isbn_nuevo} ya pertenece a otro libro.')
            return redirect('libros')

        if (cant_disp >= 0 and cant_total >= 0
                and cant_disp <= cant_total
                and not any(c.isdigit() for c in autor_str)):
            libro = Libro.objects.create(
                google_volume_id=f"LOCAL-{uuid.uuid4().hex[:10]}",
                titulo=request.POST.get('titulo'),
                isbn_13=isbn_nuevo,
                fecha_publicacion=request.POST.get('anio_publicacion', ''),
                cantidad_disponible=cant_disp,
                cantidad_total=cant_total,
            )
            for nombre in autor_str.split(','):
                nombre = nombre.strip()
                if nombre:
                    a, _ = Autor.objects.get_or_create(nombre=nombre)
                    libro.autores.add(a)
            for nombre in genero_str.split(','):
                nombre = nombre.strip()
                if nombre:
                    g, _ = Genero.objects.get_or_create(nombre=nombre)
                    libro.generos.add(g)

            registrar_auditoria(
                request, 'Libro', libro.id, 'CREATE', str(libro),
                datos_nuevos={'titulo': libro.titulo, 'isbn_13': libro.isbn_13},
            )
        return redirect('libros')


class LibroUpdateView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request, pk):
        libro      = get_object_or_404(Libro, id=pk)
        autor_str  = request.POST.get('autor', '')
        genero_str = request.POST.get('genero', '')
        cant_disp  = int(request.POST.get('cantidad_disponible', 0))
        cant_total = int(request.POST.get('cantidad_total', 0))
        isbn_nuevo = request.POST.get('isbn', '').strip()
        anio       = request.POST.get('anio_publicacion')

        if isbn_nuevo and Libro.objects.exclude(id=pk).filter(
            Q(isbn_13=isbn_nuevo) | Q(isbn_10=isbn_nuevo)
        ).exists():
            messages.error(request, f'El ISBN {isbn_nuevo} ya pertenece a otro libro.')
            return redirect('libros')

        if (cant_disp >= 0 and cant_total >= 0
                and cant_disp <= cant_total
                and not any(c.isdigit() for c in autor_str)):

            datos_anteriores = {
                'titulo': libro.titulo, 'isbn_13': libro.isbn_13,
                'cantidad_disponible': libro.cantidad_disponible,
            }

            libro.titulo             = request.POST.get('titulo')
            libro.isbn_13            = isbn_nuevo
            libro.fecha_publicacion  = anio if anio else ''
            libro.cantidad_disponible = cant_disp
            libro.cantidad_total     = cant_total
            libro.save()

            libro.autores.clear()
            for nombre in autor_str.split(','):
                nombre = nombre.strip()
                if nombre:
                    a, _ = Autor.objects.get_or_create(nombre=nombre)
                    libro.autores.add(a)

            libro.generos.clear()
            for nombre in genero_str.split(','):
                nombre = nombre.strip()
                if nombre:
                    g, _ = Genero.objects.get_or_create(nombre=nombre)
                    libro.generos.add(g)

            registrar_auditoria(
                request, 'Libro', libro.id, 'UPDATE', str(libro),
                datos_anteriores=datos_anteriores,
                datos_nuevos={'titulo': libro.titulo, 'isbn_13': libro.isbn_13,
                              'cantidad_disponible': libro.cantidad_disponible},
            )
        return redirect('libros')


class LibroDeleteView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    """
    FIX: antes no verificaba préstamos activos ni registraba auditoría.
    Ahora bloquea si hay DetallePrestamo sin devolver y registra la eliminación.
    """
    def post(self, request, pk):
        libro = get_object_or_404(Libro, id=pk)

        # Verificar que no haya préstamos activos
        if DetallePrestamo.objects.filter(libro=libro, devuelto=False).exists():
            messages.error(
                request,
                f'No se puede eliminar "{libro.titulo}": tiene préstamos activos sin devolver.'
            )
            return redirect('libros')

        repr_libro = str(libro)
        datos_ant  = {'titulo': libro.titulo, 'isbn_13': libro.isbn_13}

        registrar_auditoria(
            request, 'Libro', libro.id, 'DELETE', repr_libro,
            datos_anteriores=datos_ant,
        )
        libro.delete()
        messages.success(request, f'Libro "{repr_libro}" eliminado correctamente.')
        return redirect('libros')


class ImportarLibrosView(LoginRequiredMixin, View):
    """Importa libros hasta el límite de 100 desde Open Library."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Acceso restringido a administradores.')
            return redirect('libros')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        if Libro.objects.count() >= 100:
            messages.warning(request, "La biblioteca ya tiene el límite de 100 libros.")
            return redirect('libros')

        termino = request.POST.get('termino_busqueda') or 'variado'

        try:
            from .services import GoogleBooksService
            nuevos = GoogleBooksService.poblar_biblioteca(query=termino, limite_total=100)
            if nuevos > 0:
                messages.success(request, f"Se importaron {nuevos} libros exitosamente.")
            else:
                messages.info(request, "No se encontraron libros nuevos.")
        except Exception as e:
            messages.error(request, f"Error durante la importación: {str(e)}")

        return redirect('libros')


class SolicitarMasLibrosView(LoginRequiredMixin, View):
    """
    NUEVO (punto 4): Solicita exactamente 20 libros adicionales
    sin límite de tope, usando la nueva función del servicio.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Acceso restringido a administradores.')
            return redirect('libros')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        modo = request.POST.get('modo_busqueda', 'tema')
        titulo = request.POST.get('titulo_busqueda', '').strip()
        tema = request.POST.get('termino_busqueda', '').strip() or 'variado'
        try:
            cantidad = int(request.POST.get('cantidad_libros', 20))
        except (TypeError, ValueError):
            cantidad = 20
        cantidad = max(1, min(cantidad, 50))
        termino = titulo if modo == 'titulo' and titulo else tema
        try:
            from .services import GoogleBooksService
            nuevos = GoogleBooksService.solicitar_mas_libros(query=termino, cantidad=cantidad)
            if nuevos > 0:
                messages.success(request, f"Se añadieron {nuevos} libros nuevos a la biblioteca.")
            else:
                messages.info(request, "No se encontraron libros nuevos para ese término.")
        except Exception as e:
            messages.error(request, f"Error al solicitar libros: {str(e)}")
        return redirect('libros')


# ─────────────────────────────────────────────
#  PRÉSTAMOS  (FIX #3)
# ─────────────────────────────────────────────

class PrestamoListView(LoginRequiredMixin, EmpleadoRequiredMixin, ListView):
    model               = Prestamo
    template_name       = 'prestamos.html'
    context_object_name = 'mis_prestamos'
    ordering            = ['-id']

    def get_queryset(self):
        actualizar_estados_retraso()
        return (
            super().get_queryset()
            .select_related('usuario', 'empleado')
            .prefetch_related('libros')
        )


class PrestamoCreateView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request):
        usr = get_object_or_404(Usuario, id=request.POST.get('id_usuario'))

        if request.user.is_superuser:
            emp = get_object_or_404(Empleado, id=request.POST.get('id_empleado'))
        else:
            emp = obtener_empleado_actual(request)
            if not emp:
                messages.error(request, 'No se encontró el empleado asociado a tu cuenta.')
                return redirect('prestamos')

        fecha_limite = request.POST.get('fecha_limite')
        libros_ids   = request.POST.getlist('libros_ids')

        # Bloquear si el usuario tiene multas pendientes
        if Multa.objects.filter(prestamo__usuario=usr, estado='Pendiente').exists():
            messages.error(
                request,
                f'{usr.nombre} tiene multas pendientes y debe regularizarlas primero.'
            )
            return redirect('prestamos')

        if not libros_ids:
            messages.error(request, 'Debes seleccionar al menos un libro.')
            return redirect('prestamos')
        if len(libros_ids) != len(set(libros_ids)):
            messages.error(request, 'No puedes registrar dos ejemplares del mismo libro en un prestamo.')
            return redirect('prestamos')
        if Prestamo.objects.filter(usuario=usr, estado__in=['Activo', 'Retraso']).count() >= max_libros_por_cliente():
            messages.error(request, f'{usr.nombre} ya alcanzo el maximo de {max_libros_por_cliente()} prestamos activos.')
            return redirect('prestamos')

        prestamo = Prestamo.objects.create(
            usuario=usr, empleado=emp,
            fecha_limite=fecha_limite, estado='Activo',
        )

        libros_prestados = []
        for libro_id in libros_ids:
            libro = get_object_or_404(Libro, id=libro_id)
            if usuario_tiene_libro_activo(usr, libro):
                messages.error(request, f'{usr.nombre} ya tiene un ejemplar activo de "{libro.titulo}".')
                prestamo.delete()
                return redirect('prestamos')
            if libro.cantidad_disponible > 0:
                # FIX #3: usar DetallePrestamo.objects.create() en lugar de .add()
                # ya que libros tiene una tabla intermedia explícita (through=DetallePrestamo)
                DetallePrestamo.objects.create(prestamo=prestamo, libro=libro)
                libro.cantidad_disponible -= 1
                libro.save(update_fields=['cantidad_disponible'])
                libros_prestados.append(libro.titulo)

        Historial.objects.create(
            tipo_accion='Prestamo',
            descripcion=(
                f'Préstamo de "{prestamo.libros_resumen}" a {usr.nombre}. '
                f'Fecha límite: {fecha_limite}.'
            ),
            prestamo=prestamo,
        )
        registrar_auditoria(
            request, 'Prestamo', prestamo.id, 'CREATE', str(prestamo),
            datos_nuevos={
                'usuario': usr.nombre,
                'libros': libros_prestados,
                'fecha_limite': fecha_limite,
            },
        )
        notificar_tiempo_real('prestamo_creado')
        return redirect('prestamos')


class PrestamoDevolverView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request, pk):
        prestamo = get_object_or_404(Prestamo, id=pk)

        if prestamo.estado not in ('Activo', 'Retraso'):
            messages.warning(request, 'Este préstamo ya fue procesado.')
            return redirect('prestamos')

        hoy = timezone.now().date()
        prestamo.estado = 'Devuelto'
        prestamo.save(update_fields=['estado'])

        # Marcar cada detalle como devuelto
        DetallePrestamo.objects.filter(prestamo=prestamo, devuelto=False).update(
            fecha_devolucion_real=hoy,
            devuelto=True,
        )

        # Devolver stock solo de los libros no marcados aún
        for detalle in DetallePrestamo.objects.filter(prestamo=prestamo, devuelto=True,
                                                       fecha_devolucion_real=hoy):
            detalle.libro.cantidad_disponible += 1
            detalle.libro.save(update_fields=['cantidad_disponible'])
            activar_siguiente_reserva(detalle.libro, request)

        # Recalcular multa si ya existía
        multa = Multa.objects.filter(prestamo=prestamo, estado='Pendiente').first()
        if multa:
            multa.monto = (hoy - prestamo.fecha_limite).days * 1000
            multa.save(update_fields=['monto'])

        usuario_nombre = prestamo.usuario.nombre if prestamo.usuario else "Usuario Eliminado"
        Historial.objects.create(
            tipo_accion='Devolucion',
            descripcion=f'{usuario_nombre} devolvió "{prestamo.libros_resumen}" el {hoy}.',
            prestamo=prestamo,
        )
        registrar_auditoria(
            request, 'Prestamo', prestamo.id, 'UPDATE', str(prestamo),
            datos_anteriores={'estado': 'Activo/Retraso'},
            datos_nuevos={'estado': 'Devuelto', 'fecha_devolucion': str(hoy)},
        )
        notificar_tiempo_real('prestamo_devuelto')
        return redirect('prestamos')


class PrestamoDeleteView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    """
    FIX #6: ya no elimina entradas del Historial (se conservan para auditoría).
    Registra la eliminación en AuditLog antes de borrar.
    Solo permite eliminar préstamos ya devueltos.
    """
    def post(self, request, pk):
        prestamo = get_object_or_404(Prestamo, id=pk)

        if prestamo.estado != 'Devuelto':
            messages.error(
                request,
                'Solo se pueden eliminar préstamos con estado "Devuelto". '
                'Si el libro no fue devuelto, procese primero la devolución.'
            )
            return redirect('prestamos')

        registrar_auditoria(
            request, 'Prestamo', prestamo.id, 'DELETE', str(prestamo),
            datos_anteriores={
                'usuario': prestamo.usuario.nombre if prestamo.usuario else None,
                'estado': prestamo.estado,
                'libros': prestamo.libros_resumen,
            },
        )
        # El FK de Historial es SET_NULL, así que los registros históricos
        # sobreviven con prestamo=None — el historial NO se borra.
        prestamo.delete()
        return redirect('prestamos')


# ─────────────────────────────────────────────
#  MULTAS
# ─────────────────────────────────────────────

class MultaListView(LoginRequiredMixin, EmpleadoRequiredMixin, ListView):
    model               = Multa
    template_name       = 'multas.html'
    context_object_name = 'mis_multas'
    ordering            = ['-id']

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related('prestamo__usuario')
            .prefetch_related('prestamo__libros')
        )

    def get_context_data(self, **kwargs):
        actualizar_estados_retraso()
        context = super().get_context_data(**kwargs)
        context['empleados_lista'] = Empleado.objects.all()
        context['prestamos_lista'] = (
            Prestamo.objects
            .prefetch_related('libros')
            .select_related('usuario')
            .exclude(estado='Devuelto')
        )
        return context


class MultaCreateView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request):
        prestamo = get_object_or_404(Prestamo, id=request.POST.get('id_prestamo'))
        monto    = request.POST.get('monto')
        motivo   = (
            request.POST.get('motivo', '').strip()
            or f'Multa manual — préstamo #{prestamo.id} ({prestamo.libros_resumen}).'
        )

        multa = Multa.objects.create(
            monto=monto, motivo=motivo, estado='Pendiente', prestamo=prestamo,
        )
        usuario_nombre = prestamo.usuario.nombre if prestamo.usuario else "Usuario Eliminado"
        Historial.objects.create(
            tipo_accion='Multa',
            descripcion=f'Multa manual de ${monto} a {usuario_nombre}: {motivo}',
            prestamo=prestamo,
        )
        registrar_auditoria(
            request, 'Multa', multa.id, 'CREATE', str(multa),
            datos_nuevos={'monto': str(monto), 'motivo': motivo, 'usuario': usuario_nombre},
        )
        return redirect('multas')


class MultaPagarView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request, pk):
        multa = get_object_or_404(Multa, id=pk)
        hoy   = timezone.now().date()

        datos_ant = {'estado': multa.estado, 'fecha_pago': None}
        multa.estado    = 'Pagada'
        multa.fecha_pago = hoy
        multa.save(update_fields=['estado', 'fecha_pago'])

        usuario_nombre = (
            multa.prestamo.usuario.nombre
            if (multa.prestamo and multa.prestamo.usuario) else "Usuario Eliminado"
        )
        Historial.objects.create(
            tipo_accion='Multa',
            descripcion=f'Multa de ${multa.monto} de {usuario_nombre} pagada el {hoy}.',
            prestamo=multa.prestamo,
        )
        registrar_auditoria(
            request, 'Multa', multa.id, 'UPDATE', str(multa),
            datos_anteriores=datos_ant,
            datos_nuevos={'estado': 'Pagada', 'fecha_pago': str(hoy)},
        )
        return redirect('multas')


class MultaDeleteView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request, pk):
        multa = get_object_or_404(Multa, id=pk)
        registrar_auditoria(
            request, 'Multa', multa.id, 'DELETE', str(multa),
            datos_anteriores={'monto': str(multa.monto), 'estado': multa.estado},
        )
        multa.delete()
        return redirect('multas')


# ─────────────────────────────────────────────
#  HISTORIAL
# ─────────────────────────────────────────────

class HistorialListView(LoginRequiredMixin, EmpleadoRequiredMixin, ListView):
    model               = Historial
    template_name       = 'historial.html'
    context_object_name = 'historial'
    ordering            = ['-fecha_accion', '-id']

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related('prestamo__usuario')
            .prefetch_related('prestamo__libros')
        )


# ─────────────────────────────────────────────
#  AUDITORÍA  (NUEVO)
# ─────────────────────────────────────────────

class AuditLogListView(LoginRequiredMixin, ListView):
    """
    Solo accesible para superusuarios. Muestra todos los registros de auditoría
    con filtros por tabla y acción.
    """
    model               = AuditLog
    template_name       = 'auditlog.html'
    context_object_name = 'registros'
    paginate_by         = 50

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Acceso restringido a administradores.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs     = super().get_queryset().select_related('usuario')
        tabla  = self.request.GET.get('tabla', '')
        accion = self.request.GET.get('accion', '')
        if tabla:
            qs = qs.filter(tabla__icontains=tabla)
        if accion:
            qs = qs.filter(accion=accion)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tablas_disponibles']  = (
            AuditLog.objects.values_list('tabla', flat=True).distinct()
        )
        context['acciones_disponibles'] = AuditLog.ACCION_CHOICES
        return context


# ─────────────────────────────────────────────
#  USUARIOS
# ─────────────────────────────────────────────

class UsuarioListView(LoginRequiredMixin, EmpleadoRequiredMixin, ListView):
    model               = Usuario
    template_name       = 'usuarios.html'
    context_object_name = 'mis_usuarios'
    ordering            = ['-id']

    def get_queryset(self):
        return super().get_queryset().filter(activo=True)


class UsuarioCreateView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request):
        nombre   = request.POST.get('nombre', '').strip()
        email    = request.POST.get('email', '').strip().lower()
        telefono = request.POST.get('telefono', '').strip()
        password = request.POST.get('password', '')

        if not all([nombre, email, password]):
            messages.error(request, 'Completa nombre, email y contraseña.')
            return redirect('usuarios')

        if Empleado.objects.filter(email__iexact=email, activo=True).exists():
            messages.error(request, 'Este correo ya pertenece a una cuenta interna.')
            return redirect('usuarios')

        if User.objects.filter(username__iexact=email).exists() or Usuario.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Ya existe una cuenta registrada con ese correo.')
            return redirect('usuarios')

        user = User.objects.create_user(
            username=email, email=email, password=password, first_name=nombre
        )
        usuario = Usuario.objects.create(
            user=user, nombre=nombre, email=email, telefono=telefono
        )
        registrar_auditoria(
            request, 'Usuario', usuario.id, 'CREATE', str(usuario),
            datos_nuevos={'nombre': nombre, 'email': email},
        )
        messages.success(request, f'Usuario "{nombre}" creado correctamente.')
        return redirect('usuarios')


class UsuarioUpdateView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    def post(self, request, pk):
        usuario        = get_object_or_404(Usuario, id=pk)
        email_anterior = usuario.email
        nombre         = request.POST.get('nombre', '').strip()
        email          = request.POST.get('email', '').strip().lower()
        telefono       = request.POST.get('telefono', '').strip()
        password       = request.POST.get('password', '')

        if not all([nombre, email]):
            messages.error(request, 'Completa nombre y email.')
            return redirect('usuarios')

        if Usuario.objects.exclude(id=usuario.id).filter(email__iexact=email).exists():
            messages.error(request, 'Ya existe otro usuario con ese correo.')
            return redirect('usuarios')

        if Empleado.objects.filter(email__iexact=email, activo=True).exists():
            messages.error(request, 'Este correo ya pertenece a una cuenta interna.')
            return redirect('usuarios')

        user_usuario = (
            usuario.user
            or User.objects.filter(username__iexact=email_anterior, is_superuser=False).first()
            or User.objects.filter(email__iexact=email_anterior, is_superuser=False).first()
        )
        user_conflict = User.objects.filter(username__iexact=email).exclude(
            id=getattr(user_usuario, 'id', None)
        ).exists()
        if user_conflict:
            messages.error(request, 'Ya existe una cuenta de acceso con ese correo.')
            return redirect('usuarios')

        datos_ant = {
            'nombre': usuario.nombre,
            'email': email_anterior,
            'telefono': usuario.telefono,
        }

        usuario.nombre = nombre
        usuario.email = email
        usuario.telefono = telefono
        usuario.save(update_fields=['nombre', 'email', 'telefono'])

        if user_usuario:
            user_usuario.username = email
            user_usuario.email = email
            user_usuario.first_name = nombre
            if password:
                user_usuario.set_password(password)
            user_usuario.save()
            if usuario.user_id != user_usuario.id:
                usuario.user = user_usuario
                usuario.save(update_fields=['user'])
        elif password:
            usuario.user = User.objects.create_user(
                username=email, email=email, password=password, first_name=nombre
            )
            usuario.save(update_fields=['user'])

        registrar_auditoria(
            request, 'Usuario', usuario.id, 'UPDATE', str(usuario),
            datos_anteriores=datos_ant,
            datos_nuevos={'nombre': nombre, 'email': email, 'telefono': telefono},
        )
        messages.success(request, f'Usuario "{nombre}" actualizado correctamente.')
        return redirect('usuarios')


class UsuarioDeleteView(LoginRequiredMixin, EmpleadoRequiredMixin, View):
    """
    FIX #6: implementa soft-delete (marca activo=False) y registra en AuditLog.
    Los préstamos históricos permanecen intactos.
    """
    def post(self, request, pk):
        usuario = get_object_or_404(Usuario, id=pk)

        if Prestamo.objects.filter(usuario=usuario, estado__in=['Activo', 'Retraso']).exists():
            messages.error(
                request,
                f'{usuario.nombre} tiene préstamos activos. '
                'Procese las devoluciones antes de eliminar el usuario.'
            )
            return redirect('usuarios')

        registrar_auditoria(
            request, 'Usuario', usuario.id, 'DELETE', str(usuario),
            datos_anteriores={'nombre': usuario.nombre, 'email': usuario.email},
        )
        # Soft-delete: el historial y préstamos pasados permanecen consultables
        usuario.activo = False
        usuario.save(update_fields=['activo'])
        messages.success(request, f'Usuario "{usuario.nombre}" desactivado correctamente.')
        return redirect('usuarios')


# ─────────────────────────────────────────────
#  EMPLEADOS
# ─────────────────────────────────────────────

class EmpleadoListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model               = Empleado
    template_name       = 'empleados.html'
    context_object_name = 'mis_empleados'
    ordering            = ['-id']

    def get_queryset(self):
        return super().get_queryset().filter(activo=True)


class EmpleadoCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request):
        nombre   = request.POST.get('nombre', '').strip()
        email    = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()

        if (nombre and email and password
                and not Empleado.objects.filter(email=email).exists()
                and not User.objects.filter(username__iexact=email).exists()):

            emp = Empleado.objects.create(nombre=nombre, email=email, password=password)
            User.objects.create_user(username=email, email=email, password=password, first_name=nombre)

            registrar_auditoria(
                request, 'Empleado', emp.id, 'CREATE', str(emp),
                datos_nuevos={'nombre': nombre, 'email': email},
            )
        else:
            messages.error(request, 'Datos inválidos o el email ya está en uso.')
        return redirect('empleados')


class EmpleadoUpdateView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, pk):
        empleado       = get_object_or_404(Empleado, id=pk)
        email_anterior = empleado.email
        nombre         = request.POST.get('nombre', '').strip()
        email          = request.POST.get('email', '').strip()
        password       = request.POST.get('password', '').strip()

        if nombre and email and not Empleado.objects.exclude(id=empleado.id).filter(email=email).exists():
            if email.lower() == email_anterior.lower() or not User.objects.filter(username__iexact=email).exists():
                datos_ant = {'nombre': empleado.nombre, 'email': email_anterior}

                empleado.nombre = nombre
                empleado.email  = email
                if password:
                    empleado.password = password
                empleado.save()

                user_emp = (
                    User.objects.filter(username__iexact=email_anterior, is_superuser=False).first()
                    or User.objects.filter(email__iexact=email_anterior, is_superuser=False).first()
                )
                if user_emp:
                    user_emp.username   = email
                    user_emp.email      = email
                    user_emp.first_name = nombre
                    if password:
                        user_emp.set_password(password)
                    user_emp.save()

                registrar_auditoria(
                    request, 'Empleado', empleado.id, 'UPDATE', str(empleado),
                    datos_anteriores=datos_ant,
                    datos_nuevos={'nombre': nombre, 'email': email},
                )
        return redirect('empleados')


class EmpleadoDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    FIX: antes bloqueaba si existía CUALQUIER préstamo (incluyendo devueltos).
    Ahora solo bloquea si hay préstamos activos o en retraso.
    FIX #6: registra en AuditLog y hace soft-delete.
    """
    def post(self, request, pk):
        empleado = get_object_or_404(Empleado, id=pk)

        if Prestamo.objects.filter(empleado=empleado, estado__in=['Activo', 'Retraso']).exists():
            messages.error(
                request,
                f'{empleado.nombre} tiene préstamos activos asignados. '
                'Reasigna o finaliza esos préstamos antes de eliminar el empleado.'
            )
            return redirect('empleados')

        registrar_auditoria(
            request, 'Empleado', empleado.id, 'DELETE', str(empleado),
            datos_anteriores={'nombre': empleado.nombre, 'email': empleado.email},
        )

        # Desactivar el auth_user correspondiente
        user_emp = (
            User.objects.filter(username__iexact=empleado.email, is_superuser=False).first()
            or User.objects.filter(email__iexact=empleado.email, is_superuser=False).first()
        )
        if user_emp:
            user_emp.is_active = False
            user_emp.save(update_fields=['is_active'])

        # Soft-delete
        empleado.activo = False
        empleado.save(update_fields=['activo'])
        messages.success(request, f'Empleado "{empleado.nombre}" desactivado correctamente.')
        return redirect('empleados')


# ─────────────────────────────────────────────
#  CONFIGURACIÓN  (NUEVO – punto 5)
# ─────────────────────────────────────────────

PALETAS = [
    {'id': 'azul',    'nombre': 'Azul Clásico',      'color': '#1d4ed8'},
    {'id': 'verde',   'nombre': 'Verde Esmeralda',   'color': '#059669'},
    {'id': 'morado',  'nombre': 'Morado Elegante',   'color': '#7c3aed'},
    {'id': 'rojo',    'nombre': 'Rojo Corporativo',  'color': '#dc2626'},
    {'id': 'naranja', 'nombre': 'Naranja Vibrante',  'color': '#ea580c'},
    {'id': 'oscuro',  'nombre': 'Modo Oscuro',       'color': '#1f2937'},
    {'id': 'personalizada', 'nombre': 'Personalizada', 'color': '#D97706'},
]

PALETAS_VALIDAS = {p['id'] for p in PALETAS}
COLOR_CONFIG_KEYS = {
    'color_fondo': '#1A1614',
    'color_sidebar': '#3D322A',
    'color_acento': '#D97706',
    'color_texto': '#F5EEDB',
    'color_tarjetas': '#D5CFC4',
}

SISTEMA_CONFIG_DEFAULTS = {
    'nombre_biblioteca': "Orion's Library",
    'max_libros_cliente': '3',
    'dias_prestamo_defecto': '7',
}


class ConfiguracionView(LoginRequiredMixin, View):
    """
    GET  → muestra la página de configuración con paleta actual.
    POST → guarda la paleta seleccionada y otras opciones futuras.
    Las variables de color se inyectan a todos los templates
    a través de context_processors.py (ver ese archivo).
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Acceso restringido a administradores.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        paleta_actual = Configuracion.get('paleta_colores', 'azul')
        return render(request, 'configuracion.html', {
            'paleta_actual':      paleta_actual,
            'paletas_disponibles': PALETAS,
            'colores_personalizados': {
                clave: Configuracion.get(clave, default)
                for clave, default in COLOR_CONFIG_KEYS.items()
            },
            'config_sistema': {
                clave: Configuracion.get(clave, default)
                for clave, default in SISTEMA_CONFIG_DEFAULTS.items()
            },
        })

    def post(self, request):
        paleta = request.POST.get('paleta_colores', 'azul')
        if paleta not in PALETAS_VALIDAS:
            paleta = 'azul'

        paleta_anterior = Configuracion.get('paleta_colores', 'azul')
        colores_anteriores = {
            clave: Configuracion.get(clave, default)
            for clave, default in COLOR_CONFIG_KEYS.items()
        }

        if paleta == 'personalizada':
            for clave, default in COLOR_CONFIG_KEYS.items():
                valor = request.POST.get(clave, default).strip()
                if not valor.startswith('#') or len(valor) != 7:
                    valor = default
                Configuracion.set(clave, valor, descripcion='Color personalizado de la interfaz')

        Configuracion.set(
            'paleta_colores', paleta,
            descripcion='Paleta de colores de la interfaz'
        )
        nombre_biblioteca = request.POST.get('nombre_biblioteca', SISTEMA_CONFIG_DEFAULTS['nombre_biblioteca']).strip()
        if not nombre_biblioteca:
            nombre_biblioteca = SISTEMA_CONFIG_DEFAULTS['nombre_biblioteca']
        Configuracion.set('nombre_biblioteca', nombre_biblioteca, descripcion='Nombre visible de la biblioteca')
        Configuracion.set(
            'max_libros_cliente',
            str(config_entero_desde_post(request, 'max_libros_cliente', 3, 1, 50)),
            descripcion='Cantidad maxima de libros prestados por cliente',
        )
        Configuracion.set(
            'dias_prestamo_defecto',
            str(config_entero_desde_post(request, 'dias_prestamo_defecto', 7, 1, 60)),
            descripcion='Dias base de prestamo; el sistema suma siempre 1 dia de gracia',
        )
        registrar_auditoria(
            request, 'Configuracion', None, 'UPDATE',
            f'Paleta cambiada: {paleta_anterior} → {paleta}',
            datos_anteriores={'paleta_colores': paleta_anterior, **colores_anteriores},
            datos_nuevos={
                'paleta_colores': paleta,
                **{
                    clave: Configuracion.get(clave, default)
                    for clave, default in COLOR_CONFIG_KEYS.items()
                },
            },
        )
        messages.success(request, f'Paleta de colores actualizada correctamente.')
        return redirect('configuracion')
