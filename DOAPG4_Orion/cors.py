from django.http import HttpResponse


class ApiCorsMiddleware:
    """Permite consumir la API local desde Flutter Web durante desarrollo."""

    allowed_origin_prefixes = (
        'http://localhost:',
        'http://127.0.0.1:',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin', '')
        if self._is_cors_path(request.path) and self._is_allowed_origin(origin):
            request.META['HTTP_ORIGIN'] = f'{request.scheme}://{request.get_host()}'

        if self._is_cors_path(request.path) and request.method == 'OPTIONS':
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        origin = origin or request.headers.get('Origin', '')
        if self._is_cors_path(request.path) and self._is_allowed_origin(origin):
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = (
                'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            )
            response['Access-Control-Allow-Headers'] = (
                'Authorization, Content-Type, Accept, X-CSRFToken'
            )
            response['Access-Control-Max-Age'] = '86400'
            response['Vary'] = self._append_vary(response.get('Vary'), 'Origin')

        return response

    def _is_allowed_origin(self, origin):
        return origin.startswith(self.allowed_origin_prefixes)

    def _is_cors_path(self, path):
        return path.startswith('/api/') or path == '/login/' or path == '/logout/'

    def _append_vary(self, current, value):
        if not current:
            return value
        parts = [part.strip() for part in current.split(',')]
        if value in parts:
            return current
        return f'{current}, {value}'
