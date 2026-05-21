from django.contrib import admin
from .models import (
    Autor, Genero,
    Empleado, Usuario,
    Libro, Prestamo, DetallePrestamo,
    Multa, Historial,
    AuditLog, Configuracion, ReservaLibro, ValoracionLibro,
)


# ── Inline para ver detalles de préstamo dentro del admin de Prestamo ──
class DetallePrestamoInline(admin.TabularInline):
    model  = DetallePrestamo
    extra  = 0
    fields = ['libro', 'devuelto', 'fecha_devolucion_real', 'condicion_libro']
    readonly_fields = ['libro']


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display  = ['id', 'usuario', 'empleado', 'estado', 'fecha_prestamo', 'fecha_limite']
    list_filter   = ['estado']
    search_fields = ['usuario__nombre', 'empleado__nombre']
    inlines       = [DetallePrestamoInline]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display   = ['fecha', 'accion', 'tabla', 'objeto_id', 'objeto_repr', 'empleado_nombre', 'ip_address']
    list_filter    = ['accion', 'tabla']
    search_fields  = ['tabla', 'objeto_repr', 'empleado_nombre']
    readonly_fields = [f.name for f in AuditLog._meta.get_fields() if hasattr(f, 'name')]

    def has_add_permission(self, request):
        return False   # El log de auditoría no se crea manualmente

    def has_change_permission(self, request, obj=None):
        return False   # Tampoco se edita

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser   # Solo superadmin puede purgar


@admin.register(Configuracion)
class ConfiguracionAdmin(admin.ModelAdmin):
    list_display = ['clave', 'valor', 'descripcion']


# Registro simple para los demás modelos
admin.site.register(Autor)
admin.site.register(Genero)
admin.site.register(Empleado)
admin.site.register(Usuario)
admin.site.register(Libro)
admin.site.register(DetallePrestamo)
admin.site.register(Multa)
admin.site.register(Historial)
admin.site.register(ReservaLibro)
admin.site.register(ValoracionLibro)
