"""Serve the health probes before host validation and the HTTPS redirect.

Platform health checks (e.g. DigitalOcean App Platform) call the container directly over plain
HTTP with a Host header that isn't in ``ALLOWED_HOSTS``. Going through the normal stack would turn
them into 400 (``DisallowedHost`` in CommonMiddleware) or 301 (SSL redirect), so this middleware,
first in ``MIDDLEWARE``, answers ``/healthz/`` and ``/readyz/`` itself. The views never read the
Host header and return no user data.
"""

from common.views import healthz, readyz

_PROBES = {"/healthz/": healthz, "/readyz/": readyz}


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        view = _PROBES.get(request.path_info)
        if view is not None and request.method in ("GET", "HEAD"):
            return view(request)
        return self.get_response(request)
