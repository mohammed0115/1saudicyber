"""Defense-in-depth validation for untrusted evidence uploads."""
from __future__ import annotations

import os
import shlex
import subprocess
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


SIGNATURES = {
    'pdf': (b'%PDF-',),
    'png': (b'\x89PNG\r\n\x1a\n',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'tiff': (b'II*\x00', b'MM\x00*'),
    'bmp': (b'BM',),
}
ZIP_EXTENSIONS = {'docx', 'xlsx', 'xlsm'}
TEXT_EXTENSIONS = {'txt', 'csv', 'md'}


def _extension(uploaded_file):
    return Path(uploaded_file.name).suffix.lower().lstrip('.')


def _read_head(uploaded_file, size=8192):
    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        return uploaded_file.read(size)
    finally:
        uploaded_file.seek(position)


def _validate_zip_container(uploaded_file, extension):
    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        if not zipfile.is_zipfile(uploaded_file):
            raise ValidationError('The uploaded file is not a valid Office document container.')
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            names = set(archive.namelist())
            if '[Content_Types].xml' not in names:
                raise ValidationError('The Office document is missing its content manifest.')
            required_prefix = 'word/' if extension == 'docx' else 'xl/'
            if not any(name.startswith(required_prefix) for name in names):
                raise ValidationError('The Office document content does not match its declared type.')
    except zipfile.BadZipFile as exc:
        raise ValidationError('The uploaded Office document is invalid.') from exc
    finally:
        uploaded_file.seek(position)


def _validate_optional_antivirus(file_path):
    command = getattr(settings, 'EVIDENCE_ANTIVIRUS_COMMAND', '').strip()
    if not command:
        return
    args = shlex.split(command) + [str(file_path)]
    result = subprocess.run(args, capture_output=True, timeout=30, check=False)
    if result.returncode != 0:
        raise ValidationError('The evidence file did not pass malware scanning.')


def validate_evidence_upload(uploaded_file):
    """Validate file identity before it is persisted and return a normalized extension."""
    extension = _extension(uploaded_file)
    allowed = set(getattr(settings, 'ALLOWED_EVIDENCE_EXTENSIONS', ()))
    if extension not in allowed:
        raise ValidationError(f'Unsupported file type ".{extension}".')

    max_size = getattr(settings, 'MAX_EVIDENCE_FILE_SIZE', 50 * 1024 * 1024)
    if uploaded_file.size > max_size:
        raise ValidationError(f'File exceeds the {max_size // (1024 * 1024)} MB limit.')
    if uploaded_file.size == 0:
        raise ValidationError('Empty files cannot be used as evidence.')

    head = _read_head(uploaded_file)
    if extension in SIGNATURES and not any(head.startswith(sig) for sig in SIGNATURES[extension]):
        raise ValidationError('The file signature does not match its declared extension.')
    if extension in ZIP_EXTENSIONS:
        _validate_zip_container(uploaded_file, extension)
    if extension in TEXT_EXTENSIONS and b'\x00' in head:
        raise ValidationError('The declared text file contains binary data.')
    return extension


def validate_stored_evidence(file_path):
    """Run optional post-storage malware scanning in the async processing boundary."""
    _validate_optional_antivirus(os.fspath(file_path))
