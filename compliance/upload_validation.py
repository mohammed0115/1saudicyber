"""P0-6 — real content-type validation for evidence uploads (magic bytes).

Extension checks alone are spoofable (a .exe renamed .pdf passes). This sniffs the leading
bytes with `filetype` and enforces:

* declared extension must be in the allowed list; AND
* if `filetype` recognises a concrete type, it must match the declared extension; OR
* if `filetype` returns None (genuine text files carry no magic bytes), accept only when the
  declared extension is in the explicit text allowlist — never reject solely because the
  sniffer returned None.

Pure and side-effect-light: reads the file head and rewinds it. No storage, no network.
"""
import filetype

# Formats with no magic signature that are legitimately text.
TEXT_EXTS = {'txt', 'csv', 'md'}

# Sniffer/extension synonyms so a real JPEG declared ".jpeg" (sniffed "jpg") still matches.
_SYNONYMS = {'jpeg': 'jpg', 'tif': 'tiff'}

_SNIFF_BYTES = 262  # enough for every signature filetype knows


def _canon(ext):
    ext = (ext or '').lower().lstrip('.')
    return _SYNONYMS.get(ext, ext)


def declared_extension(filename):
    name = (filename or '').lower()
    return name.rsplit('.', 1)[1] if '.' in name else ''


def validate_evidence_file(uploaded_file, allowed_exts):
    """Return (ok: bool, ext: str, error: str). `error` is a safe, path-free message."""
    ext = declared_extension(getattr(uploaded_file, 'name', ''))
    allowed = {e.lower() for e in (allowed_exts or [])}
    if not ext or ext not in allowed:
        return False, ext, f'Unsupported file type ".{ext}".'

    try:
        head = uploaded_file.read(_SNIFF_BYTES)
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    kind = filetype.guess(head)
    if kind is None:
        # No signature — only genuine text formats are allowed to reach storage.
        if ext in TEXT_EXTS:
            return True, ext, ''
        return False, ext, 'File content does not match its extension.'

    if _canon(kind.extension) != _canon(ext):
        return False, ext, 'File content does not match its extension.'
    return True, ext, ''
