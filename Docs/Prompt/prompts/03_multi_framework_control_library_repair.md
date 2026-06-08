# Prompt 03 — Multi-Framework Control Library Repair

Implement or repair the multi-framework Control Library.

The platform must support:
1. NCA ECC controls.
2. Saudi Aramco SACS-002 controls.
3. SABIC CyberTrust controls.
4. Cross-framework mappings.

The SRS states the platform manages 334 controls across NCA, Aramco, and SABIC.
The Third Party Cybersecurity Compliance Report Template contains Aramco/SACS-002 controls using references like TPC-1, TPC-2, etc.

Do not hardcode controls in templates.
Store controls in the database.

Required models or equivalent:
- Framework
- FrameworkVersion
- Domain
- Control
- ControlClause
- EvidenceRequirement
- ControlMapping
- ControlApplicabilityRule

Each Control must support:
- framework
- code/reference
- title_en
- title_ar
- description_en
- description_ar
- domain
- priority
- mandatory flag
- evidence types
- evidence guidance en/ar
- applicable sectors
- applicable company sizes
- applicable third-party classifications
- active/version fields

Add management commands:
- import_controls_from_excel
- export_controls_to_excel
- seed_minimum_frameworks

Acceptance criteria:
- NCA, Aramco, SABIC frameworks exist.
- Controls can be filtered by framework/domain/priority.
- Aramco TPC controls support Compliance/Noncompliance output.
- NCA controls support C/PC/NC/N/A output.
- Tests verify framework creation, control import, and filtering.
