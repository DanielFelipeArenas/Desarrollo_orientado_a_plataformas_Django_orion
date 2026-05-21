from .models import Libro, Usuario, Empleado, Configuracion


# Mapa de paletas → variables CSS que se inyectan en los templates.
# El template base debe tener un bloque <style> que use estas variables:
#   :root { --color-primary: {{ paleta_css.primary }}; ... }
PALETAS_CSS = {
    'azul': {
        'primary':       '#1d4ed8',
        'primary_dark':  '#1e3a8a',
        'primary_light': '#dbeafe',
        'accent':        '#3b82f6',
        'nombre':        'Azul Clásico',
    },
    'verde': {
        'primary':       '#059669',
        'primary_dark':  '#064e3b',
        'primary_light': '#d1fae5',
        'accent':        '#10b981',
        'nombre':        'Verde Esmeralda',
    },
    'morado': {
        'primary':       '#7c3aed',
        'primary_dark':  '#4c1d95',
        'primary_light': '#ede9fe',
        'accent':        '#8b5cf6',
        'nombre':        'Morado Elegante',
    },
    'rojo': {
        'primary':       '#dc2626',
        'primary_dark':  '#7f1d1d',
        'primary_light': '#fee2e2',
        'accent':        '#ef4444',
        'nombre':        'Rojo Corporativo',
    },
    'naranja': {
        'primary':       '#ea580c',
        'primary_dark':  '#7c2d12',
        'primary_light': '#ffedd5',
        'accent':        '#f97316',
        'nombre':        'Naranja Vibrante',
    },
    'oscuro': {
        'primary':       '#374151',
        'primary_dark':  '#111827',
        'primary_light': '#f3f4f6',
        'accent':        '#6b7280',
        'nombre':        'Modo Oscuro',
    },
}

COLOR_KEYS = {
    'primary_dark': 'color_sidebar',
    'accent': 'color_acento',
    'primary_light': 'color_tarjetas',
    'fondo': 'color_fondo',
    'texto': 'color_texto',
}


def _paleta_personalizada():
    base = PALETAS_CSS['azul'].copy()
    base.update({
        'primary_dark': Configuracion.get('color_sidebar', '#3D322A'),
        'accent': Configuracion.get('color_acento', '#D97706'),
        'primary_light': Configuracion.get('color_tarjetas', '#D5CFC4'),
        'fondo': Configuracion.get('color_fondo', '#1A1614'),
        'texto': Configuracion.get('color_texto', '#F5EEDB'),
        'nombre': 'Personalizada',
    })
    return base


def global_context(request):
    """
    Inyecta en todos los templates:
      - empleado_actual / empleado_actual_id
      - libros_disponibles, usuarios_lista, empleados_lista
      - paleta_actual (id string) y paleta_css (dict con colores)
    """
    if not request.user.is_authenticated:
        return {
            'empleado_actual':    None,
            'empleado_actual_id': None,
            'paleta_actual':      'azul',
            'paleta_css':         PALETAS_CSS['azul'],
            'nombre_biblioteca':  Configuracion.get('nombre_biblioteca', "Orion's Library"),
        }

    # ── Empleado asociado al usuario ────────────────────────────────
    empleado_actual = None
    usuario_actual = None
    if not request.user.is_superuser:
        if request.user.email:
            empleado_actual = Empleado.objects.filter(
                email__iexact=request.user.email
            ).first()
            usuario_actual = Usuario.objects.filter(
                email__iexact=request.user.email, activo=True
            ).first()
        if not empleado_actual:
            empleado_actual = Empleado.objects.filter(
                email__iexact=request.user.username
            ).first()
        if not usuario_actual:
            usuario_actual = Usuario.objects.filter(
                email__iexact=request.user.username, activo=True
            ).first()
        if not empleado_actual and request.user.first_name:
            empleado_actual = Empleado.objects.filter(
                nombre__iexact=request.user.first_name
            ).first()

    # ── Paleta de colores ───────────────────────────────────────────
    paleta_actual = Configuracion.get('paleta_colores', 'azul')
    if paleta_actual == 'personalizada':
        paleta_css = _paleta_personalizada()
    else:
        paleta_css = PALETAS_CSS.get(paleta_actual, PALETAS_CSS['azul']).copy()
        paleta_css.setdefault('fondo', '#1A1614')
        paleta_css.setdefault('texto', '#F5EEDB')

    return {
        'libros_disponibles': Libro.objects.filter(cantidad_disponible__gt=0),
        'usuarios_lista':     Usuario.objects.filter(activo=True),
        'empleados_lista':    Empleado.objects.filter(activo=True),
        'empleado_actual':    empleado_actual,
        'empleado_actual_id': empleado_actual.id if empleado_actual else None,
        'usuario_actual':     usuario_actual,
        'es_usuario_comun':   bool(usuario_actual and not empleado_actual and not request.user.is_superuser),
        'paleta_actual':      paleta_actual,
        'paleta_css':         paleta_css,
        'nombre_biblioteca':  Configuracion.get('nombre_biblioteca', "Orion's Library"),
    }
