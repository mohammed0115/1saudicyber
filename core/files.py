"""P0-01 — authorized serving of private files.

The CALLER must authorize the request (tenant/role) BEFORE calling these helpers; they only
turn an already-authorized FieldFile into a response. Two modes:

* Default: stream the bytes through Django (``FileResponse``) — works everywhere (local disk,
  S3) and is what dev/test use.
* Production with nginx: if ``PRIVATE_MEDIA_XACCEL_PREFIX`` is set, hand off via
  ``X-Accel-Redirect`` so nginx serves the file from an internal (non-public) location and the
  bytes never pass through Django. The prefix location must be marked ``internal;`` in nginx.

Filenames are always sent RFC 5987-encoded, so special characters can never break the
``Content-Disposition`` header or smuggle a path.
"""
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, HttpResponse


def _content_disposition(download_name, as_attachment):
    disp = 'attachment' if as_attachment else 'inline'
    safe = quote((download_name or 'file').replace('\r', '').replace('\n', ''))
    return f"{disp}; filename*=UTF-8''{safe}"


def serve_authorized_file(fieldfile, *, download_name, as_attachment=True,
                          content_type=None, extra_headers=None):
    """Return an HttpResponse streaming (or X-Accel-delegating) an authorized private file."""
    prefix = getattr(settings, 'PRIVATE_MEDIA_XACCEL_PREFIX', '') or ''
    if prefix:
        resp = HttpResponse()
        # fieldfile.name is the storage key (e.g. evidence_v2/2026/07/x.pdf); nginx joins it
        # to the internal root behind the configured prefix.
        resp['X-Accel-Redirect'] = f"{prefix.rstrip('/')}/{fieldfile.name}"
        resp['Content-Disposition'] = _content_disposition(download_name, as_attachment)
        # Let nginx set the length; Django must not send a body.
        resp['Content-Type'] = content_type or 'application/octet-stream'
    else:
        resp = FileResponse(fieldfile.open('rb'), as_attachment=as_attachment,
                            filename=download_name or 'file')
        if content_type:
            resp['Content-Type'] = content_type
    for key, value in (extra_headers or {}).items():
        resp[key] = value
    return resp
