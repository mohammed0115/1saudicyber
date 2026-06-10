"""
Phase 3A — deterministic, explainable framework applicability.

Evaluates a company (via its CompanyIntakeProfile, falling back to the legacy
target_* checkboxes) and produces a FrameworkApplicabilityResult per AVAILABLE
official FrameworkVersion. "Available" = the framework version has official
(non-legacy) controls imported. OTCC/DCC therefore stay unavailable until they
are imported.

Pure rules — no AI, no hidden defaults. Every decision carries a reason and a
source. It never creates CompanyControl or Evidence and never touches uploads.

Kept as a standalone module (not a `services/` package) so it doesn't collide
with the existing compliance/services.py.
"""
from compliance.models import Control, FrameworkVersion, FrameworkApplicabilityResult

# Framework version code -> rule callable(profile, company) -> (decision, reason, source).
# profile may be None (then we fall back to legacy checkboxes).
DECISION_APPLICABLE = 'applicable'
DECISION_NOT = 'not_applicable'
DECISION_REVIEW = 'needs_review'


def _legacy(company, attr):
    return bool(getattr(company, attr, False))


def _rule_nca_ecc(p, company):
    # Broad cybersecurity scope OR legacy target_nca -> applicable; else needs_review (never silent false).
    if p:
        signals = any([p.is_government_entity, p.is_critical_system_operator, p.uses_cloud_services,
                       p.provides_cloud_services, p.has_ot_environment, p.handles_sensitive_data,
                       p.handles_personal_data, p.has_remote_work])
        if signals:
            return DECISION_APPLICABLE, 'Company has a cybersecurity scope per intake signals.', 'rule'
    if _legacy(company, 'target_nca'):
        return DECISION_APPLICABLE, 'Legacy target_nca checkbox is set.', 'legacy_checkbox'
    return DECISION_REVIEW, 'No clear NCA scope from intake or legacy flags; needs manual review.', 'rule'


def _rule_cscc(p, company):
    if p and p.is_critical_system_operator:
        return DECISION_APPLICABLE, 'Company operates critical systems (is_critical_system_operator).', 'rule'
    return DECISION_NOT, 'Company does not operate critical systems.', 'rule'


def _rule_ccc(p, company):
    if p and (p.uses_cloud_services or p.provides_cloud_services):
        return DECISION_APPLICABLE, 'Company uses or provides cloud services.', 'rule'
    return DECISION_NOT, 'No cloud usage/provision indicated.', 'rule'


def _rule_tcc(p, company):
    if p and p.has_remote_work:
        return DECISION_APPLICABLE, 'Company has remote work (telework).', 'rule'
    return DECISION_NOT, 'No remote work indicated.', 'rule'


def _rule_osmacc(p, company):
    if p and p.manages_official_social_media_accounts:
        return DECISION_APPLICABLE, 'Company manages official social media accounts.', 'rule'
    return DECISION_NOT, 'No official social media account management indicated.', 'rule'


def _rule_aramco(p, company):
    if p and p.works_with_aramco:
        return DECISION_APPLICABLE, 'Company works with Saudi Aramco (intake).', 'rule'
    if _legacy(company, 'target_aramco'):
        return DECISION_APPLICABLE, 'Legacy target_aramco checkbox is set.', 'legacy_checkbox'
    return DECISION_NOT, 'No Aramco relationship indicated.', 'rule'


def _rule_sabic(p, company):
    if p and p.works_with_sabic:
        return DECISION_APPLICABLE, 'Company works with SABIC (intake).', 'rule'
    if _legacy(company, 'target_sabic'):
        return DECISION_APPLICABLE, 'Legacy target_sabic checkbox is set.', 'legacy_checkbox'
    return DECISION_NOT, 'No SABIC relationship indicated.', 'rule'


RULES = {
    'NCA-ECC-2-2024': _rule_nca_ecc,
    'NCA-CSCC-1-2019': _rule_cscc,
    'NCA-CCC-2-2024': _rule_ccc,
    'NCA-TCC-1-2021': _rule_tcc,
    'NCA-OSMACC-1-2021': _rule_osmacc,
    'ARAMCO-SACS-002': _rule_aramco,
    'SABIC-CYBERTRUST-1-0': _rule_sabic,
}


def _is_available(fv):
    """A framework version is available iff it has official (non-legacy) controls imported."""
    return Control.objects.filter(framework_version=fv, is_legacy_import=False).exists()


def evaluate_company(company, *, apply=False, user=None):
    """Return a list of decision dicts; optionally persist FrameworkApplicabilityResult rows.

    Never creates CompanyControl/Evidence. Idempotent (update_or_create per fv).
    `skipped` entries (e.g. OTCC/DCC, or a manual override we must not clobber) are reported
    but not written as rule decisions.
    """
    profile = getattr(company, 'intake_profile', None)
    results = []
    for code, rule in RULES.items():
        fv = FrameworkVersion.objects.filter(code=code).first()
        if fv is None:
            results.append({'framework': code, 'status': 'skipped',
                            'reason': 'FrameworkVersion not seeded.'})
            continue
        if not _is_available(fv):
            results.append({'framework': code, 'status': 'unavailable',
                            'reason': 'No official controls imported for this framework yet.'})
            continue
        decision, reason, source = rule(profile, company)
        entry = {'framework': code, 'status': decision, 'reason': reason, 'source': source}
        results.append(entry)
        if apply:
            existing = FrameworkApplicabilityResult.objects.filter(
                company=company, framework_version=fv).first()
            # Do not clobber a manual override.
            if existing and existing.decision == 'manually_overridden':
                entry['status'] = 'manually_overridden'
                entry['reason'] = 'Preserved existing manual override.'
                continue
            FrameworkApplicabilityResult.objects.update_or_create(
                company=company, framework_version=fv,
                defaults={'decision': decision, 'reason': reason, 'source': source, 'confidence': 1.0})
    return results
