"""Content validation for evidence uploads with bounded memory and OOXML safety checks."""
from __future__ import annotations

import zipfile

import filetype

TEXT_EXTS = {'txt', 'csv', 'md'}
_SYNONYMS = {'jpeg': 'jpg', 'tif': 'tiff'}
_SNIFF_BYTES = 8192
_MAX_ARCHIVE_MEMBERS = 2000
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
_MAX_ARCHIVE_RATIO = 100
_OOXML_REQUIRED_PREFIX = {'docx': 'word/', 'xlsx': 'xl/'}


def _canon(ext):
    ext = (ext or '').lower().lstrip('.')
    return _SYNONYMS.get(ext, ext)


def declared_extension(filename):
    name = (filename or '').lower()
    return name.rsplit('.', 1)[1] if '.' in name else ''


def _safe_ooxml(uploaded_file, ext):
    """Verify OOXML structure without extracting the archive or reading it into RAM."""
    try:
        with zipfile.ZipFile(uploaded_file) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > _MAX_ARCHIVE_MEMBERS:
                return False
            total_uncompressed = sum(entry.file_size for entry in entries)
            if total_uncompressed > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                return False
            for entry in entries:
                if entry.file_size and entry.compress_size and entry.file_size / entry.compress_size > _MAX_ARCHIVE_RATIO:
                    return False
            names = {entry.filename for entry in entries}
            required_prefix = _OOXML_REQUIRED_PREFIX[ext]
            return '[Content_Types].xml' in names and any(name.startswith(required_prefix) for name in names)
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False
    finally:
        try:
            uploaded_file.seek(0)
        except (OSError, ValueError):
            pass


def validate_evidence_file(uploaded_file, allowed_exts):
    """Return ``(ok, extension, error)`` without loading the complete upload into memory."""
    ext = declared_extension(getattr(uploaded_file, 'name', ''))
    allowed = {value.lower().lstrip('.') for value in (allowed_exts or [])}
    if not ext or ext not in allowed:
        return False, ext, f'Unsupported file type ".{ext}".'

    try:
        head = uploaded_file.read(_SNIFF_BYTES)
    except (OSError, ValueError):
        return False, ext, 'Could not inspect uploaded file.'
    finally:
        try:
            uploaded_file.seek(0)
        except (OSError, ValueError):
            pass

    if ext in _OOXML_REQUIRED_PREFIX:
        if not _safe_ooxml(uploaded_file, ext):
            return False, ext, 'Office document structure is invalid or unsafe.'
        return True, ext, ''

    kind = filetype.guess(head)
    if kind is None:
        if ext in TEXT_EXTS:
            return True, ext, ''
        return False, ext, 'File content does not match its extension.'
    if _canon(kind.extension) != _canon(ext):
        return False, ext, 'File content does not match its extension.'
    return True, ext, ''
