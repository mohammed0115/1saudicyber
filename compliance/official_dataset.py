"""
Phase 2F — read-only loader for official control datasets (YAML).

Loads compliance/data/official_controls/<file>.yaml for a given FrameworkVersion
code and returns (metadata, controls). It NEVER writes to the database.

Kept as a standalone module (not a `services/` package) so it does not collide
with the existing compliance/services.py.
"""
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parent / 'data' / 'official_controls'

# FrameworkVersion.code -> dataset filename.
DATASET_FILES = {
    'ARAMCO-SACS-002': 'aramco_sacs_002.yaml',
    'SABIC-CYBERTRUST-1-0': 'sabic_cybertrust_v1_0.yaml',
    'NCA-ECC-2-2024': 'nca_ecc_2_2024.yaml',
    'NCA-CSCC-1-2019': 'nca_cscc_1_2019.yaml',
    'NCA-OSMACC-1-2021': 'nca_osmacc_1_2021.yaml',
    'NCA-TCC-1-2021': 'nca_tcc_1_2021.yaml',
    'NCA-CCC-2-2024': 'nca_ccc_2_2024.yaml',
}

# Expected control-id pattern per framework version (for validation).
# All NCA control frameworks share the x-x-x main-control numbering.
ID_PATTERNS = {
    'ARAMCO-SACS-002': r'^TPC-\d+$',
    'SABIC-CYBERTRUST-1-0': r'^CT-\d+$',
    'NCA-ECC-2-2024': r'^\d+-\d+-\d+$',
    'NCA-CSCC-1-2019': r'^\d+-\d+-\d+$',
    'NCA-OSMACC-1-2021': r'^\d+-\d+-\d+$',
    'NCA-TCC-1-2021': r'^\d+-\d+-\d+$',
    # CCC uses a party-specific scheme: d-d-P-d (provider) / d-d-T-d (tenant).
    'NCA-CCC-2-2024': r'^\d+-\d+-[PT]-\d+$',
}

# Phase 2I strategy (planning only) for the remaining NCA frameworks. NONE of
# these are imported/applied yet — this is documentation consumed by the
# strategy tests and the next phases. `declared` / `raw_ids` come from a
# read-only inspection of each official PDF (declared count vs pdftotext -raw
# x-x-x matches). `batch` is the recommended import order.
REMAINING_NCA_FRAMEWORKS = {
    'NCA-CSCC-1-2019':   dict(source='Critical-Systems-Cybersecurity-Controls.pdf',
                              declared=32, raw_ids=32, confidence='high', batch=1, manual_curation=False),
    'NCA-OSMACC-1-2021': dict(source='osmacc-en.pdf',
                              declared=15, raw_ids=15, confidence='high', batch=1, manual_curation=False),
    'NCA-TCC-1-2021':    dict(source='telework_cybersecurity_controls-en.pdf',
                              declared=21, raw_ids=21, confidence='high', batch=1, manual_curation=False),
    'NCA-CCC-2-2024':    dict(source='CCC-2-2024-EN-.pdf',
                              declared=37, raw_ids=0, confidence='medium', batch=2, manual_curation=True),
    'NCA-OTCC-1-2022':   dict(source='otcc_en.pdf',
                              declared=47, raw_ids=51, confidence='medium', batch=2, manual_curation=True),
    'NCA-DCC-1-2022':    dict(source='Data-Cybersecurity-Controls-.pdf',
                              declared=None, raw_ids=0, confidence='low', batch=3, manual_curation=True),
}


class DatasetError(Exception):
    """Raised when a dataset file is missing or malformed."""


def dataset_path(framework_version_code):
    fname = DATASET_FILES.get(framework_version_code)
    if not fname:
        raise DatasetError(f"No official dataset registered for '{framework_version_code}'.")
    return DATA_DIR / fname


def load_official_dataset(framework_version_code):
    """Return (metadata: dict, controls: list[dict]). Read-only; never touches the DB."""
    path = dataset_path(framework_version_code)
    if not path.exists():
        raise DatasetError(f"Dataset file not found: {path}")
    try:
        with open(path, encoding='utf-8') as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise DatasetError(f"Invalid YAML in {path}: {exc}")
    if not isinstance(doc, dict):
        raise DatasetError(f"Dataset {path} must be a mapping at the top level.")
    controls = doc.get('controls') or []
    metadata = {k: v for k, v in doc.items() if k != 'controls'}
    metadata['_path'] = str(path)
    return metadata, controls
