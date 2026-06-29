"""Phase 8D-2-FIX-C — read-only auditor guided journey (10 steps).

Deterministic and read-only. Computes each auditor step's status from EXISTING
data only (auditor profile status, assignments, recorded final verdicts). It
never writes, never activates an auditor, and never issues a compliance
decision. The auditor verdict it reflects is an INTERNAL human review only —
never an official certification or accreditation.
"""

# Canonical auditor statuses used by the guided stepper / status badge.
COMPLETED = 'completed'
CURRENT = 'current'
BLOCKED = 'blocked'
NOT_STARTED = 'not_started'

# (key, title, short explanation) — the 10-step auditor journey.
_STEP_DEFS = [
    ('registration', 'تسجيل المدقق', 'إنشاء حساب المدقق على المنصة.'),
    ('pending_activation', 'تفعيل المنصة للحساب', 'مراجعة إدارة المنصة لحساب المدقق قبل التفعيل.'),
    ('dashboard', 'لوحة المدقق', 'الوصول إلى لوحة المدقق بعد التفعيل.'),
    ('assigned_files', 'ملفات الشركات المسندة', 'ظهور ملفات الشركات المسندة للمراجعة.'),
    ('evidence_review', 'مراجعة الأدلة', 'استعراض الأدلة المرفوعة لكل ضابط.'),
    ('ai_review', 'مراجعة التحليل الاستشاري', 'الاطلاع على التحليل الاستشاري للذكاء الاصطناعي (لا يُعد قرارًا نهائيًا).'),
    ('rule_review', 'مراجعة الحالة المقترحة', 'الاطلاع على الحالة المقترحة من محرك القواعد (مقترحة فقط).'),
    ('final_verdict', 'الحكم النهائي الداخلي', 'تسجيل حكم المدقق الداخلي على الأدلة (مراجعة بشرية داخلية).'),
    ('auditor_notes', 'ملاحظات المدقق', 'إضافة ملاحظات المراجعة الداخلية.'),
    ('reviewed_report', 'التقرير الداخلي بعد المراجعة', 'التقرير الداخلي بعد مراجعة المدقق وإصدار الحكم.'),
]


def _signals(user):
    """Read-only signals describing the auditor's progress."""
    from .services import get_auditor_profile
    from .models import AuditorAssignment
    from compliance.models import AuditorFinalVerdict

    profile = get_auditor_profile(user)
    is_active = bool(profile and profile.is_active_auditor())
    assignments = (AuditorAssignment.objects.filter(auditor=profile)
                   if profile else AuditorAssignment.objects.none())
    accepted = assignments.filter(status='accepted')
    has_verdict = (AuditorFinalVerdict.objects.filter(reviewer=user).exists()
                   if getattr(user, 'is_authenticated', False) else False)
    return {
        'profile': profile,
        'has_profile': profile is not None,
        'is_active': is_active,
        'is_pending': bool(profile and profile.status == 'pending_review'),
        'has_assignments': assignments.exists(),
        'has_accepted': accepted.exists(),
        'has_verdict': has_verdict,
    }


def build_auditor_journey(user):
    """Return the read-only auditor journey model. Never writes.

    Keys: steps, next_action, current_step, is_pending, has_assignments,
    completed_count, total, pending_message, no_assignment_message.
    """
    f = _signals(user)

    def status_for(key):
        if key == 'registration':
            return COMPLETED if f['has_profile'] else CURRENT
        if key == 'pending_activation':
            if f['is_active']:
                return COMPLETED
            return CURRENT if f['has_profile'] else NOT_STARTED
        if key == 'dashboard':
            if not f['is_active']:
                return BLOCKED
            return COMPLETED
        if key == 'assigned_files':
            if not f['is_active']:
                return BLOCKED
            return COMPLETED if f['has_assignments'] else CURRENT
        if key in ('evidence_review', 'ai_review', 'rule_review'):
            if not f['is_active']:
                return BLOCKED
            if not f['has_accepted']:
                return BLOCKED
            return CURRENT if not f['has_verdict'] else COMPLETED
        if key == 'final_verdict':
            if not f['is_active'] or not f['has_accepted']:
                return BLOCKED
            return COMPLETED if f['has_verdict'] else CURRENT
        if key == 'auditor_notes':
            if not f['is_active'] or not f['has_accepted']:
                return BLOCKED
            return COMPLETED if f['has_verdict'] else NOT_STARTED
        if key == 'reviewed_report':
            if not f['is_active'] or not f['has_accepted']:
                return BLOCKED
            return COMPLETED if f['has_verdict'] else CURRENT
        return NOT_STARTED

    steps = []
    for i, (key, title, desc) in enumerate(_STEP_DEFS, start=1):
        steps.append({'order': i, 'key': key, 'title': title,
                      'description': desc, 'status': status_for(key)})

    current = next((s for s in steps if s['status'] == CURRENT), None)
    completed_count = sum(1 for s in steps if s['status'] == COMPLETED)

    # Next action depends on the auditor's state (read-only, safe).
    if not f['has_profile']:
        next_action = {'title': 'أكمل تسجيل المدقق', 'url_name': 'auditors:register',
                       'action_label': 'التسجيل كمدقق'}
    elif f['is_pending'] or not f['is_active']:
        next_action = {'title': 'بانتظار تفعيل المنصة لحسابك',
                       'url_name': 'auditors:onboarding', 'action_label': 'عرض حالة الحساب'}
    elif not f['has_assignments']:
        next_action = {'title': 'بانتظار إسناد ملف شركة للمراجعة',
                       'url_name': 'auditors:dashboard', 'action_label': 'فتح لوحة المدقق'}
    else:
        next_action = {'title': 'تابع مراجعة الملفات المسندة وإصدار الحكم الداخلي',
                       'url_name': 'auditors:dashboard', 'action_label': 'فتح لوحة المدقق'}

    return {
        'steps': steps,
        'current_step': current,
        'next_action': next_action,
        'is_pending': f['is_pending'],
        'is_active': f['is_active'],
        'has_profile': f['has_profile'],
        'has_assignments': f['has_assignments'],
        'completed_count': completed_count,
        'total': len(steps),
        'pending_message': ('حسابك قيد مراجعة إدارة منصة 1SaudiCyber لدى شركة احصل الحل. '
                            'بعد التفعيل ستظهر لك ملفات الشركات المسندة.'),
        'rejected_message': ('تعذر تفعيل حسابك كمدقق في الوقت الحالي. '
                             'يمكنك التواصل مع إدارة منصة احصل الحل لمزيد من التفاصيل.'),
        'suspended_message': ('تم إيقاف صلاحية حساب المدقق مؤقتًا من إدارة المنصة. '
                              'يرجى التواصل مع إدارة منصة احصل الحل.'),
        'no_assignment_message': ('لا توجد ملفات شركات مسندة إليك حاليًا. '
                                  'تواصل مع إدارة منصة احصل الحل لإسناد ملف مراجعة.'),
    }
