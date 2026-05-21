"""
api_urls.py — URLs de la API REST.

Para incluirlo en el urls.py principal del proyecto agrega:
    path('api/v1/', include('biblioteca.api_urls')),

Endpoints resultantes:
  /api/v1/auth/token/          POST  → obtener token (login Flutter)
  /api/v1/auth/logout/         POST  → invalidar token

  /api/v1/dashboard/           GET   → KPIs del dashboard

  /api/v1/autores/             GET, POST
  /api/v1/autores/{id}/        GET, PUT, PATCH, DELETE

  /api/v1/generos/             GET, POST
  /api/v1/generos/{id}/        GET, PUT, PATCH, DELETE

  /api/v1/libros/              GET, POST
  /api/v1/libros/{id}/         GET, PUT, PATCH, DELETE
  /api/v1/libros/importar/     POST  → importar desde Open Library
  /api/v1/libros/disponibles/  GET   → solo con stock > 0

  /api/v1/usuarios/            GET, POST
  /api/v1/usuarios/{id}/       GET, PUT, PATCH, DELETE (soft)

  /api/v1/empleados/           GET, POST
  /api/v1/empleados/{id}/      GET, PUT, PATCH, DELETE (soft)

  /api/v1/prestamos/           GET, POST
  /api/v1/prestamos/{id}/      GET, PUT, PATCH, DELETE
  /api/v1/prestamos/{id}/devolver/ POST → devolver préstamo

  /api/v1/multas/              GET, POST
  /api/v1/multas/{id}/         GET, PUT, PATCH, DELETE
  /api/v1/multas/{id}/pagar/   POST  → registrar pago

  /api/v1/historial/           GET
  /api/v1/historial/{id}/      GET

  /api/v1/auditlog/            GET   (solo superadmin)
  /api/v1/auditlog/{id}/       GET   (solo superadmin)
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import (
    ObtenerTokenView, CerrarSesionAPIView, DashboardAPIView,
    RegistroUsuarioAPIView, PerfilAPIView, ConfiguracionPublicaAPIView,
    ClienteDashboardAPIView, ClientePrestamosAPIView, ClienteReservasAPIView,
    ClienteHistorialAPIView, ClienteDeudasAPIView, ClienteValoracionesAPIView,
    AutorViewSet, GeneroViewSet, LibroViewSet,
    UsuarioViewSet, EmpleadoViewSet,
    PrestamoViewSet, MultaViewSet,
    HistorialViewSet, AuditLogViewSet,
)

router = DefaultRouter()
router.register(r'autores',   AutorViewSet,   basename='api-autor')
router.register(r'generos',   GeneroViewSet,  basename='api-genero')
router.register(r'libros',    LibroViewSet,   basename='api-libro')
router.register(r'usuarios',  UsuarioViewSet, basename='api-usuario')
router.register(r'empleados', EmpleadoViewSet, basename='api-empleado')
router.register(r'prestamos', PrestamoViewSet, basename='api-prestamo')
router.register(r'multas',    MultaViewSet,   basename='api-multa')
router.register(r'historial', HistorialViewSet, basename='api-historial')
router.register(r'auditlog',  AuditLogViewSet, basename='api-auditlog')

urlpatterns = [
    # ── Autenticación ─────────────────────────────────────────────
    path('auth/token/',  ObtenerTokenView.as_view(),  name='api-token'),
    path('auth/registro/', RegistroUsuarioAPIView.as_view(), name='api-registro'),
    path('auth/logout/', CerrarSesionAPIView.as_view(), name='api-logout'),
    path('auth/me/', PerfilAPIView.as_view(), name='api-me'),
    path('configuracion-publica/', ConfiguracionPublicaAPIView.as_view(), name='api-config-publica'),

    # ── Dashboard ─────────────────────────────────────────────────
    path('dashboard/', DashboardAPIView.as_view(), name='api-dashboard'),
    path('cliente/dashboard/', ClienteDashboardAPIView.as_view(), name='api-cliente-dashboard'),
    path('cliente/prestamos/', ClientePrestamosAPIView.as_view(), name='api-cliente-prestamos'),
    path('cliente/reservas/', ClienteReservasAPIView.as_view(), name='api-cliente-reservas'),
    path('cliente/historial/', ClienteHistorialAPIView.as_view(), name='api-cliente-historial'),
    path('cliente/deudas/', ClienteDeudasAPIView.as_view(), name='api-cliente-deudas'),
    path('cliente/valoraciones/', ClienteValoracionesAPIView.as_view(), name='api-cliente-valoraciones'),

    # ── Recursos (generados por el router) ────────────────────────
    path('', include(router.urls)),
]
