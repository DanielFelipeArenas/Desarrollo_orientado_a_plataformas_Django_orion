"""
settings_snippet.py
═══════════════════
Este archivo NO es un settings.py completo.
Contiene ÚNICAMENTE los bloques que debes AÑADIR o MODIFICAR
en tu settings.py existente para que todas las mejoras funcionen.

Busca cada sección por su título y aplica los cambios indicados.
"""

# ═══════════════════════════════════════════════════════════════════
# 1. INSTALLED_APPS  — añade estas apps al final de tu lista
# ═══════════════════════════════════════════════════════════════════
INSTALLED_APPS_ADDITIONS = [
    # Django REST Framework (punto 8)
    'rest_framework',
    'rest_framework.authtoken',

    # CORS — necesario para que Flutter pueda llamar a la API
    # Instala con: pip install django-cors-headers
    'corsheaders',
]
# Ejemplo de cómo quedaría tu INSTALLED_APPS:
# INSTALLED_APPS = [
#     'django.contrib.admin',
#     ...
#     'biblioteca',
#     'rest_framework',
#     'rest_framework.authtoken',
#     'corsheaders',
# ]


# ═══════════════════════════════════════════════════════════════════
# 2. MIDDLEWARE  — añade CorsMiddleware ANTES de CommonMiddleware
# ═══════════════════════════════════════════════════════════════════
# MIDDLEWARE = [
#     'corsheaders.middleware.CorsMiddleware',   ← AÑADIR PRIMERO
#     'django.middleware.common.CommonMiddleware',
#     ...
# ]


# ═══════════════════════════════════════════════════════════════════
# 3. SESIONES  — FIX punto 7: sesión caduca al cerrar el navegador
# ═══════════════════════════════════════════════════════════════════

# La sesión muere cuando el navegador se cierra
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Tiempo máximo de sesión aunque el navegador siga abierto (8 horas)
SESSION_COOKIE_AGE = 60 * 60 * 8   # segundos

# Refresca el tiempo de expiración en cada petición
SESSION_SAVE_EVERY_REQUEST = True

# Seguridad adicional (activa en producción con HTTPS)
# SESSION_COOKIE_SECURE   = True   # Solo HTTPS
# SESSION_COOKIE_HTTPONLY = True   # No accesible desde JS (ya es True por defecto)
# SESSION_COOKIE_SAMESITE = 'Lax'  # Protección CSRF


# ═══════════════════════════════════════════════════════════════════
# 4. DJANGO REST FRAMEWORK  — punto 8
# ═══════════════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    # Flutter usará Token; el navegador puede usar Session para pruebas
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],

    # Todo endpoint requiere autenticación por defecto
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],

    # Paginación automática
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,

    # Formato de fecha/hora ISO 8601 (compatible con Dart/Flutter)
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%SZ',
    'DATE_FORMAT':     '%Y-%m-%d',

    # Throttling básico (evita abuso de la API)
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/hour',
        'user': '1000/hour',
    },
}


# ═══════════════════════════════════════════════════════════════════
# 5. CORS  — permite que Flutter llame a la API desde otro origen
# ═══════════════════════════════════════════════════════════════════

# Durante desarrollo: permitir todos los orígenes
CORS_ALLOW_ALL_ORIGINS = True   # ← Cambiar a False en producción

# En producción, reemplazar por:
# CORS_ALLOWED_ORIGINS = [
#     'http://localhost:8080',       # Flutter Web en desarrollo
#     'https://tu-app.ejemplo.com',  # Flutter Web en producción
# ]
# Para Flutter móvil (iOS/Android) no se necesitan orígenes CORS,
# ya que no tienen "origen" de navegador.


# ═══════════════════════════════════════════════════════════════════
# 6. CONTEXT PROCESSORS  — añade global_context a tu TEMPLATES
# ═══════════════════════════════════════════════════════════════════
# En la sección TEMPLATES > OPTIONS > context_processors añade:
#   'biblioteca.context_processors.global_context',
#
# Ejemplo:
# TEMPLATES = [{
#     ...
#     'OPTIONS': {
#         'context_processors': [
#             'django.template.context_processors.debug',
#             'django.template.context_processors.request',
#             'django.contrib.auth.context_processors.auth',
#             'django.contrib.messages.context_processors.messages',
#             'biblioteca.context_processors.global_context',   ← AÑADIR
#         ],
#     },
# }]


# ═══════════════════════════════════════════════════════════════════
# 7. URLS PRINCIPALES (urls.py del proyecto)
# ═══════════════════════════════════════════════════════════════════
# Añade en tu urls.py principal:
#
# from django.urls import path, include
#
# urlpatterns = [
#     ...
#     # API REST
#     path('api/v1/', include('biblioteca.api_urls')),
#
#     # Rutas web existentes — añade logout y las nuevas vistas
#     path('logout/', LogoutView.as_view(), name='logout'),
#     path('configuracion/', ConfiguracionView.as_view(), name='configuracion'),
#     path('libros/solicitar-mas/', SolicitarMasLibrosView.as_view(), name='solicitar_mas_libros'),
#     path('auditlog/', AuditLogListView.as_view(), name='auditlog'),
# ]


# ═══════════════════════════════════════════════════════════════════
# 8. MIGRACIONES NECESARIAS
# ═══════════════════════════════════════════════════════════════════
# Después de aplicar los cambios en models.py ejecuta:
#
#   python manage.py makemigrations biblioteca
#   python manage.py migrate
#
# Para crear los tokens de la API REST:
#   python manage.py migrate  (ya crea la tabla authtoken_token)
#
# Para generar tokens para usuarios existentes:
#   python manage.py shell
#   >>> from rest_framework.authtoken.models import Token
#   >>> from django.contrib.auth.models import User
#   >>> for u in User.objects.all(): Token.objects.get_or_create(user=u)


# ═══════════════════════════════════════════════════════════════════
# 9. INSTALACIÓN DE DEPENDENCIAS
# ═══════════════════════════════════════════════════════════════════
# Ejecuta en tu entorno virtual:
#
#   pip install djangorestframework
#   pip install django-cors-headers
#
# Y añade al requirements.txt:
#   djangorestframework>=3.14
#   django-cors-headers>=4.0


# ═══════════════════════════════════════════════════════════════════
# 10. EJEMPLO DE LLAMADA DESDE FLUTTER (referencia)
# ═══════════════════════════════════════════════════════════════════
# // 1. Login → obtener token
# final resp = await http.post(
#   Uri.parse('https://tu-servidor.com/api/v1/auth/token/'),
#   body: {'username': 'empleado@lib.com', 'password': '1234'},
# );
# final token = jsonDecode(resp.body)['token'];
#
# // 2. Usar el token en llamadas posteriores
# final libros = await http.get(
#   Uri.parse('https://tu-servidor.com/api/v1/libros/'),
#   headers: {'Authorization': 'Token $token'},
# );
