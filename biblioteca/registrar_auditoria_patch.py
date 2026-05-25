# ─────────────────────────────────────────────────────────────────────────────
#  PATCH para views.py — función registrar_auditoria
#
#  PROBLEMA (Bug 1):
#    RegistroUsuarioAPIView tiene permission_classes = [], por lo que durante
#    el registro request.user es AnonymousUser.  Al llamar registrar_auditoria
#    sin más, el AuditLog queda sin usuario (o lanza IntegrityError si el campo
#    usuario tiene null=False), y la acción de "Registro de nuevo usuario" nunca
#    se graba correctamente en auditoría.
#
#  SOLUCIÓN:
#    Añadir el parámetro opcional `usuario_override` a registrar_auditoria.
#    Cuando se pasa, se usa ese User en lugar de request.user.
#    La llamada en api_views.py ya fue actualizada para pasar `usuario_override=user`.
#
#  CÓMO APLICAR:
#    Busca la función registrar_auditoria en tu views.py y reemplázala
#    con la versión de abajo (o agrega solo el parámetro y la línea marcada).
# ─────────────────────────────────────────────────────────────────────────────

def registrar_auditoria(
    request,
    tabla,
    objeto_id,
    accion,
    objeto_repr='',
    datos_anteriores=None,
    datos_nuevos=None,
    usuario_override=None,          # <── NUEVO PARÁMETRO
):
    """
    Registra una entrada en AuditLog.

    Parámetros:
        request          – HttpRequest actual (puede ser anónimo en endpoints públicos).
        tabla            – Nombre del modelo afectado (str).
        objeto_id        – PK del objeto afectado (int).
        accion           – 'CREATE' | 'UPDATE' | 'DELETE'.
        objeto_repr      – str() del objeto (opcional, mejora legibilidad).
        datos_anteriores – dict con los valores antes del cambio (solo UPDATE/DELETE).
        datos_nuevos     – dict con los valores después del cambio (solo CREATE/UPDATE).
        usuario_override – User de Django a usar en lugar de request.user.
                           Útil cuando request.user es AnonymousUser (endpoints públicos).
    """
    import json
    from .models import AuditLog

    # ── Determinar el usuario responsable ────────────────────────────────────
    # Prioridad: override explícito > usuario autenticado en request > None
    if usuario_override is not None:
        usuario = usuario_override
    elif request is not None and hasattr(request, 'user') and request.user.is_authenticated:
        usuario = request.user
    else:
        usuario = None                  # AuditLog.usuario debe aceptar null=True

    # ── Determinar nombre visible del responsable ─────────────────────────────
    if usuario is not None:
        empleado_nombre = (
            usuario.get_full_name()
            or usuario.first_name
            or usuario.username
        )
    else:
        empleado_nombre = 'Sistema / Anónimo'

    try:
        AuditLog.objects.create(
            tabla=tabla,
            objeto_id=objeto_id,
            accion=accion,
            objeto_repr=str(objeto_repr)[:255],
            datos_anteriores=json.dumps(datos_anteriores or {}, ensure_ascii=False, default=str),
            datos_nuevos=json.dumps(datos_nuevos or {}, ensure_ascii=False, default=str),
            usuario=usuario,
            empleado_nombre=empleado_nombre,
        )
    except Exception as exc:            # nunca debe romper el flujo principal
        import logging
        logging.getLogger(__name__).warning(
            'registrar_auditoria falló silenciosamente: %s', exc
        )
