from django.contrib import admin
from django.urls import include, path
from biblioteca import views
from django.views.decorators.cache import never_cache
from biblioteca.views import ImportarLibrosView, SolicitarMasLibrosView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Setup para el jurado
    path('setup-admin/', views.crear_superusuario_inicial, name='setup_admin'),

    # Login / Logout
    path('login/', never_cache(views.LoginView.as_view()), name='login'),
    path('registro/', never_cache(views.RegistroUsuarioView.as_view()), name='registro_usuario'),
    path('logout/', never_cache(views.LogoutView.as_view()), name='logout'),

    # Vistas principales
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('administradores/', views.EmpleadoListView.as_view(), name='administradores'),
    path('libros/', views.LibroListView.as_view(), name='libros'),
    path('prestamos/', views.PrestamoListView.as_view(), name='prestamos'),
    path('multas/', views.MultaListView.as_view(), name='multas'),
    path('historial/', views.HistorialListView.as_view(), name='historial'),
    path('auditoria/', views.AuditLogListView.as_view(), name='auditlog'),
    path('usuarios/', views.UsuarioListView.as_view(), name='usuarios'),
    path('empleados/', views.EmpleadoListView.as_view(), name='empleados'),
    path('configuracion/', views.ConfiguracionView.as_view(), name='configuracion'),

    # Libros
    path('libros/crear/', views.LibroCreateView.as_view(), name='crear_libro'),
    path('libros/editar/<int:pk>/', views.LibroUpdateView.as_view(), name='editar_libro'),
    path('libros/eliminar/<int:pk>/', views.LibroDeleteView.as_view(), name='eliminar_libro'),
    path('libros/<int:pk>/pedir/', views.UsuarioPedirLibroView.as_view(), name='usuario_pedir_libro'),
    path('libros/<int:pk>/reservar/', views.UsuarioReservarLibroView.as_view(), name='usuario_reservar_libro'),
    path('libros/<int:pk>/valorar/', views.UsuarioValorarLibroView.as_view(), name='usuario_valorar_libro'),

    # Préstamos
    path('prestamos/crear/', views.PrestamoCreateView.as_view(), name='crear_prestamo'),
    path('prestamos/devolver/<int:pk>/', views.PrestamoDevolverView.as_view(), name='devolver_prestamo'),
    path('prestamos/eliminar/<int:pk>/', views.PrestamoDeleteView.as_view(), name='eliminar_prestamo'),

    # Multas
    path('multas/crear/', views.MultaCreateView.as_view(), name='crear_multa_manual'),
    path('multas/pagar/<int:pk>/', views.MultaPagarView.as_view(), name='pagar_multa'),
    path('multas/eliminar/<int:pk>/', views.MultaDeleteView.as_view(), name='eliminar_multa'),

    # Usuarios
    path('usuarios/crear/', views.UsuarioCreateView.as_view(), name='crear_usuario'),
    path('usuarios/editar/<int:pk>/', views.UsuarioUpdateView.as_view(), name='editar_usuario'),
    path('usuarios/eliminar/<int:pk>/', views.UsuarioDeleteView.as_view(), name='eliminar_usuario'),
    path('mi-historial/', views.UsuarioHistorialLibrosView.as_view(), name='usuario_historial'),
    path('mis-deudas/', views.UsuarioDeudasView.as_view(), name='usuario_deudas'),

    # Empleados
    path('empleados/crear/', views.EmpleadoCreateView.as_view(), name='crear_empleado'),
    path('empleados/editar/<int:pk>/', views.EmpleadoUpdateView.as_view(), name='editar_empleado'),
    path('empleados/eliminar/<int:pk>/', views.EmpleadoDeleteView.as_view(), name='eliminar_empleado'),

    # Búsqueda
    path('buscar/', views.BuscarView.as_view(), name='buscar'),

    # Importar libros desde Google Books API
    path('libros/importar/', ImportarLibrosView.as_view(), name='importar_libros'),
    path('libros/solicitar-mas/', SolicitarMasLibrosView.as_view(), name='solicitar_mas_libros'),

    # API REST para clientes moviles como Flutter
    path('api/v1/', include('biblioteca.api_urls')),
]
