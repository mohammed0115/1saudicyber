"""
Phase 4D — read-only company workflow stepper (13 stages, grouped).

Deterministic, tenant-scoped, READ-ONLY. Computes each stage's status from
EXISTING data only — it never writes, never creates CompanyControl, never changes
subscription/assessment state, and never lets AI decide compliance. Report /
download / assign-auditor stages are shown LOCKED when the subscription is
inactive (matching Phase 4B/4C); earlier workflow stages are never locked.
"""
from billing.subscription_access import company_has_active_subscription

# Status keys + Arabic labels.
COMPLETED = 'completed'
CURRENT = 'current'
NEEDS_ACTION = 'needs_action'
LOCKED = 'locked'
NOT_STARTED = 'not_started'
UNAVAILABLE = 'unavailable'

STATUS_LABELS = {
    COMPLETED: 'مكتمل',
    CURRENT: 'الخطوة الحالية',
    NEEDS_ACTION: 'يتطلب إجراء',
    LOCKED: 'مقفل',
    NOT_STARTED: 'لم يبدأ',
    UNAVAILABLE: 'غير متاح حاليًا',
}

# Group labels (to avoid overcrowding 13 steps).
GROUPS = [('start', 'البداية'), ('frameworks', 'الأطر'),
          ('evidence', 'الأدلة'), ('review', 'المراجعة'), ('reports', 'التقارير')]


def _flags(company):
    from .models import (CompanyIntakeProfile, FrameworkApplicabilityResult,
                         CompanyFrameworkScope, ControlApplicabilityResult,
                         EvidenceChecklistItem, EvidenceSubmission, EvidenceAnalysisResult,
                         ControlAssessment)
    from auditors.models import AuditorAssignment
    from risk.services import has_open_high_critical
    q = lambda m, **kw: m.objects.filter(company=company, **kw).exists()
    return {
        'risk_open_high_critical': has_open_high_critical(company),
        'registration': True,  # a company user always has a company
        'onboarding': bool(getattr(company, 'onboarding_completed', False)),
        'intake': q(CompanyIntakeProfile),
        'applicability': q(FrameworkApplicabilityResult),
        'approval': q(CompanyFrameworkScope, status='approved'),
        'control_plan': q(ControlApplicabilityResult, decision='applicable',
                          control__framework_version__isnull=False, control__is_legacy_import=False),
        'checklist': q(EvidenceChecklistItem),
        'upload': q(EvidenceSubmission),
        'analysis': q(EvidenceAnalysisResult),
        'auditor_review': ControlAssessment.objects.filter(company=company)
                          .exclude(status='not_reviewed').exists(),
        'assignment': AuditorAssignment.objects.filter(
            company=company, status__in=['requested', 'accepted', 'completed']).exists(),
        'auditor_selection_pending': AuditorAssignment.objects.filter(
            company=company, status='requested').exists(),
        'auditor_selection_accepted': AuditorAssignment.objects.filter(
            company=company, status__in=['accepted', 'completed']).exists(),
    }


# (key, title, group, action_url_name, action_label)
_STAGE_DEFS = [
    ('registration', 'تسجيل الشركة', 'start', 'core:onboarding', 'تسجيل الشركة'),
    ('onboarding', 'التهيئة', 'start', 'core:onboarding', 'أكمل التهيئة'),
    ('intake', 'بيانات الامتثال', 'start', 'compliance:intake', 'أكمل بيانات الامتثال'),
    ('applicability', 'مراجعة الأطر المقترحة', 'frameworks', 'compliance:applicability_review', 'راجع الأطر المقترحة'),
    ('approval', 'اعتماد الأطر', 'frameworks', 'compliance:applicability_review', 'اعتمد الأطر'),
    ('control_plan', 'خطة الضوابط', 'frameworks', 'compliance:control_plan', 'ولّد خطة الضوابط'),
    ('checklist', 'قائمة الأدلة', 'evidence', 'compliance:evidence_checklist', 'ولّد قائمة الأدلة'),
    ('upload', 'رفع الأدلة', 'evidence', 'compliance:evidence_checklist', 'ارفع الأدلة'),
    ('analysis', 'التحليل الاستشاري', 'evidence', 'compliance:evidence_checklist', 'التحليل الاستشاري'),
    ('auditor_selection', 'اختيار المدقق', 'review', 'auditors:list', 'اختر مدققاً'),
    ('auditor_review', 'مراجعة المدقق', 'review', 'compliance:auditor_review_queue', 'مراجعة المدقق'),
    ('risk_register', 'سجل المخاطر والمعالجة', 'review', 'risk:list', 'إدارة المخاطر والمعالجة'),
    ('subscription', 'تفعيل الاشتراك', 'review', 'compliance:reports_index', 'فعّل الاشتراك لتنزيل التقارير'),
    ('reports', 'التقارير', 'reports', 'compliance:reports_index', 'عرض التقارير'),
    ('download_assign', 'تنزيل التقرير أو إسناده لمدقق', 'reports', 'compliance:reports_index', 'تنزيل التقرير أو إسناد الملف'),
]
# Stages locked when there is no active subscription.
_SUBSCRIPTION_LOCKED = {'reports', 'download_assign'}


def build_company_workflow_stepper(company, user=None):
    """Return the read-only stepper model for a company. Never writes."""
    sub_active = company_has_active_subscription(company)
    f = _flags(company)
    f['subscription'] = sub_active
    f['reports'] = sub_active and f['auditor_review']
    f['download_assign'] = f['assignment']

    stages = []
    current_assigned = False
    for i, (key, title, group, url_name, label) in enumerate(_STAGE_DEFS, start=1):
        completed = bool(f.get(key, False))
        locked = (key in _SUBSCRIPTION_LOCKED) and not sub_active

        if key == 'risk_register':
            # Read-only & advisory: needs attention only when open high/critical risks exist.
            status = NEEDS_ACTION if f['risk_open_high_critical'] else COMPLETED
        elif key == 'subscription':
            status = COMPLETED if sub_active else NEEDS_ACTION
        elif key == 'auditor_selection':
            # Company-driven: accepted -> completed; a pending request is an active waiting state
            # ("بانتظار موافقة المدقق") regardless of position; otherwise choose an auditor.
            if f['auditor_selection_accepted']:
                status = COMPLETED
            elif f['auditor_selection_pending']:
                status = CURRENT
                label = 'بانتظار موافقة المدقق'
            elif not current_assigned:
                status = CURRENT
                current_assigned = True
            else:
                status = NOT_STARTED
        elif completed:
            status = COMPLETED
        elif locked:
            status = LOCKED
        elif not current_assigned:
            status = CURRENT
            current_assigned = True
        else:
            status = NOT_STARTED

        stages.append({
            'order': i, 'key': key, 'title': title, 'group': group,
            'status': status, 'status_label': STATUS_LABELS[status],
            'action_url_name': url_name, 'action_label': label,
        })

    # Next recommended action: the current step, else subscription, else download/assign.
    nxt = next((s for s in stages if s['status'] == CURRENT), None)
    if nxt is None and not sub_active:
        nxt = next(s for s in stages if s['key'] == 'subscription')
    if nxt is None:
        nxt = next(s for s in stages if s['key'] == 'download_assign')

    groups = [{'key': gk, 'title': gt,
               'stages': [s for s in stages if s['group'] == gk]} for gk, gt in GROUPS]
    completed_count = sum(1 for s in stages if s['status'] == COMPLETED)
    return {
        'stages': stages,
        'groups': groups,
        'subscription_active': sub_active,
        'completed_count': completed_count,
        'total': len(stages),
        'next_action': {'title': nxt['title'], 'action_label': nxt['action_label'],
                        'action_url_name': nxt['action_url_name']},
    }
