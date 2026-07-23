"""P0-01 — private storage for sensitive uploads (evidence, RFI attachments).

These files must NEVER be reachable via a public/guessable URL:

* When an object store (S3) is the default backend, evidence already uses signed, expiring,
  non-listable URLs (AWS_QUERYSTRING_AUTH), so we keep using the default storage.
* Otherwise (local disk) we pin the files to PRIVATE_MEDIA_ROOT, which is OUTSIDE MEDIA_ROOT,
  so neither the dev ``static()`` handler nor any reverse proxy serving ``/media/`` can reach
  them. ``base_url=None`` makes ``.url`` raise (fail-loud) — no code path can mint a public
  link; downloads go only through an authenticated, tenant-scoped view.

Passed to FileField as a callable so migrations serialize the reference (no baked-in path) and
the S3-vs-local decision is made from the environment at model load.
"""
from django.core.files.storage import FileSystemStorage, default_storage
from django.conf import settings


class PrivateFileSystemStorage(FileSystemStorage):
    """Local storage for sensitive files with NO public URL.

    NOTE: FileSystemStorage(base_url=None) does NOT disable .url — it silently falls back to
    settings.MEDIA_URL. So we override .url to raise (fail-loud): no code path can ever mint a
    public link; files are reachable only through an authorized download view.
    """
    def url(self, name):
        raise ValueError('Private file — no public URL; use the authorized download view.')


def private_media_storage():
    if getattr(settings, 'AWS_STORAGE_BUCKET_NAME', ''):
        # S3 default already yields signed, expiring, private URLs.
        return default_storage
    return PrivateFileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
