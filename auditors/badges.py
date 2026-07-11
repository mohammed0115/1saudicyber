"""Display-only framework capability badges for an auditor.

Inferred CONSERVATIVELY from existing free-text profile fields (specialization,
bio, organization) — no DB fields, no migration. These are INTERNAL hints for the
platform UI only. They describe what the auditor reviews as a *readiness reviewer*
and DO NOT represent official authorization, accreditation, or certification from
NCA, Aramco, or SABIC. Wording deliberately uses "مراجع جاهزية" (readiness reviewer),
never "معتمد رسميًا".
"""

# (key, short code shown on the badge, full Arabic label, lowercase text signals)
_FRAMEWORK_SIGNALS = [
    ('nca_ecc', 'NCA ECC', 'مراجع جاهزية NCA ECC',
     ('nca', 'ecc', 'الهيئة الوطنية', 'الأمن السيبراني', 'السيبراني')),
    ('aramco', 'Aramco CCC / SACS', 'مراجع جاهزية Aramco CCC / SACS',
     ('aramco', 'ccc', 'sacs', 'أرامكو')),
    ('sabic', 'SABIC CyberTrust', 'مراجع جاهزية SABIC CyberTrust',
     ('sabic', 'cybertrust', 'cyber trust', 'سابك')),
]


def auditor_framework_badges(profile):
    """Return a conservative list of inferred capability badges for an auditor profile.

    Each badge: {'key', 'code', 'label'}. Falls back to a neutral general-reviewer
    badge when nothing specific is detected. Never asserts official accreditation.
    """
    if profile is None:
        return []
    text = ' '.join([
        getattr(profile, 'specialization', '') or '',
        getattr(profile, 'bio', '') or '',
        getattr(profile, 'organization_name', '') or '',
    ]).lower()
    badges = []
    for key, code, label, signals in _FRAMEWORK_SIGNALS:
        if any(s in text for s in signals):
            badges.append({'key': key, 'code': code, 'label': label})
    if len(badges) >= 2:
        badges.append({'key': 'multi', 'code': 'متعدد الأطر', 'label': 'مدقق متعدد الأطر'})
    if not badges:
        badges.append({'key': 'general', 'code': 'مراجعة عامة', 'label': 'مراجع امتثال عام'})
    return badges
