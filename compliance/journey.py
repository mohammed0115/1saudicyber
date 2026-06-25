"""
Phase UX-WIZARD-A — target compliance journey builder (read-only, deterministic).

Builds a two-level wizard: 5 main stages over 16 target substeps. Computes each
substep's status from EXISTING company data only — it never writes, never changes
ControlAssessment, never implements OCR / AI analyzer / rule engine. Unfinished
target features are shown truthfully as 'planned' / 'not_available'.
"""
from billing.subscription_access import company_has_active_subscription

# Allowed substep statuses (Arabic labels live in the template/status_badge).
STATUSES = ('completed', 'current', 'needs_action', 'locked',
            'planned', 'not_available', 'optional')

# Stage 1..5 (level 1).
STAGES = [
    ('start', 'البدء والتصنيف'),
    ('frameworks', 'الأطر والضوابط'),
    ('evidence', 'الأدلة والتحليل'),
    ('gaps', 'الفجوات والمعالجة'),
    ('review', 'المراجعة والتقارير والمراقبة'),
]

# (key, title, stage, kind, url_name, action_label, description)
# kind: required | optional | planned | platform | partial | gated
_STEP_DEFS = [
    ('company_registration', 'تسجيل الشركة', 'start', 'required', 'core:onboarding',
     'استعراض الحساب', 'تم إنشاء حساب الشركة وربطه بالمستخدم.'),
    ('company_profile', 'بيانات الشركة', 'start', 'required', 'compliance:intake',
     'إكمال بيانات الشركة', 'أكمل ملف التصنيف لتحديد الأطر المنطبقة.'),
    ('smart_classification', 'التصنيف الذكي', 'start', 'required', 'compliance:applicability_review',
     'مراجعة التصنيف', 'تحديد الأطر المنطبقة بناءً على بيانات التصنيف.'),

    ('control_library', 'مكتبة الضوابط', 'frameworks', 'platform', 'compliance:controls_list',
     'استعراض المكتبة', 'مكتبة الضوابط الرسمية (417 ضابطًا عبر أطر NCA وAramco وSABIC).'),
    ('applicability', 'قابلية التطبيق', 'frameworks', 'required', 'compliance:control_plan',
     'عرض خطة الضوابط', 'الضوابط الرسمية المنطبقة تحت الأطر المعتمدة.'),
    ('assessment_creation', 'إنشاء التقييم', 'frameworks', 'required', 'compliance:auditor_review_queue',
     'إدارة التقييمات', 'إنشاء تقييمات الضوابط الرسمية المنطبقة.'),

    ('evidence_upload', 'رفع الأدلة', 'evidence', 'required', 'compliance:evidence_checklist',
     'رفع الأدلة', 'رفع الأدلة المرتبطة بعناصر قائمة الأدلة.'),
    ('ocr_extraction', 'استخراج النص / OCR', 'evidence', 'planned', None,
     '', 'استخراج النص من المستندات — قيد التجهيز (غير مفعّل بعد).'),
    ('ai_analysis', 'التحليل الاستشاري للذكاء الاصطناعي', 'evidence', 'optional', 'compliance:evidence_checklist',
     'إدارة الأدلة', 'تحليل استشاري مساعد للأدلة — لا يُعد قرارًا نهائيًا.'),
    ('rule_engine', 'محرك القواعد', 'evidence', 'planned', None,
     '', 'محرك قواعد تقييم الأدلة — قيد التجهيز (متاح في مرحلة لاحقة).'),

    ('gap_risk', 'تحليل الفجوات والمخاطر', 'gaps', 'optional', 'risk:list',
     'فتح سجل المخاطر', 'تسجيل المخاطر والفجوات وتقييمها.'),
    ('remediation', 'خطة المعالجة', 'gaps', 'optional', 'risk:list',
     'إدارة المعالجة', 'مهام معالجة المخاطر والفجوات.'),

    ('auditor_review', 'مراجعة المدقق', 'review', 'required', 'compliance:auditor_review_queue',
     'قائمة المراجعة', 'مراجعة المدقّق للضوابط واتخاذ القرار.'),
    ('final_verdict', 'النتيجة النهائية بعد المراجعة', 'review', 'partial', 'compliance:auditor_review_queue',
     'عرض التقييمات', 'القرار النهائي للمدقّق على كل الضوابط المنطبقة.'),
    ('reports', 'التقارير', 'review', 'gated', 'compliance:reports_index',
     'عرض التقارير', 'تقارير الامتثال وتحليل الفجوات (تتطلب اشتراكًا فعّالًا).'),
    ('monitoring', 'المراقبة المستمرة', 'review', 'optional', 'monitoring:overview',
     'فتح المراقبة', 'فحوص المراقبة الدورية لصحّة الضوابط (الأساس متاح).'),
]


def _signals(company):
    from .models import (CompanyIntakeProfile, FrameworkApplicabilityResult,
                         CompanyFrameworkScope, ControlApplicabilityResult,
                         EvidenceChecklistItem, EvidenceSubmission, EvidenceAnalysisResult,
                         ControlAssessment)
    from risk.models import RiskItem, RemediationTask
    from auditors.models import AuditorAssignment
    from monitoring.models import MonitoringCheck
    q = lambda m, **kw: m.objects.filter(company=company, **kw).exists()
    assessments = ControlAssessment.objects.filter(company=company)
    return {
        'intake': q(CompanyIntakeProfile) or bool(getattr(company, 'onboarding_completed', False)),
        'applicability': q(FrameworkApplicabilityResult),
        'approved_scope': q(CompanyFrameworkScope, status='approved'),
        'control_plan': q(ControlApplicabilityResult, decision='applicable',
                          control__framework_version__isnull=False, control__is_legacy_import=False),
        'assessments': assessments.exists(),
        'reviewed': assessments.exclude(status='not_reviewed').exists(),
        'all_reviewed': assessments.exists() and not assessments.filter(status='not_reviewed').exists(),
        'submissions': q(EvidenceSubmission),
        'analysis': q(EvidenceAnalysisResult),
        'risks': q(RiskItem),
        'remediation': q(RemediationTask),
        'assignment_accepted': AuditorAssignment.objects.filter(
            company=company, status='accepted').exists(),
        'subscription': company_has_active_subscription(company),
        'monitoring_checks': q(MonitoringCheck),
        'checklist': q(EvidenceChecklistItem),
    }


def _completed(key, f):
    return {
        'company_registration': True,
        'company_profile': f['intake'],
        'smart_classification': f['applicability'],
        'control_library': True,
        'applicability': f['control_plan'],
        'assessment_creation': f['assessments'],
        'evidence_upload': f['submissions'],
        'ai_analysis': f['analysis'],
        'gap_risk': f['risks'],
        'remediation': f['remediation'],
        'auditor_review': f['reviewed'] or f['assignment_accepted'],
        'final_verdict': f['all_reviewed'],
        'reports': f['subscription'] and f['reviewed'],
        'monitoring': f['monitoring_checks'],
    }.get(key, False)


def build_company_compliance_journey(company, user=None):
    """Return the wizard model: {stages, next_action, overall_progress, current_stage_title}."""
    f = _signals(company)
    steps = []
    current_assigned = False
    for key, title, stage, kind, url_name, action_label, desc in _STEP_DEFS:
        completed = _completed(key, f)
        if kind == 'platform':
            status = 'completed'
        elif kind == 'planned':
            status = 'planned'
        elif kind == 'gated' and not f['subscription']:
            status = 'locked'
        elif kind == 'partial' and not completed:
            status = 'planned'   # a distinct final-verdict sign-off object is not implemented yet
        elif completed:
            status = 'completed'
        elif kind == 'optional':
            status = 'optional'
        else:  # required + incomplete + available
            if not current_assigned:
                status, current_assigned = 'current', True
            else:
                status = 'needs_action'
        steps.append({
            'key': key, 'title': title, 'stage': stage, 'kind': kind,
            'status': status, 'url_name': url_name, 'action_label': action_label,
            'description': desc, 'is_advisory': key == 'ai_analysis',
            'is_available': status not in ('planned', 'not_available', 'locked'),
        })

    # Next recommended action.
    def _first(*statuses):
        return next((s for s in steps if s['status'] in statuses), None)
    nxt = _first('current') or _first('needs_action') or _first('locked') or _first('optional') or steps[-1]

    # Roll up into 5 stages.
    stages = []
    completed_total = sum(1 for s in steps if s['status'] == 'completed')
    for skey, stitle in STAGES:
        sub = [s for s in steps if s['stage'] == skey]
        avail = [s for s in sub if s['is_available']]
        if any(s['status'] == 'current' for s in sub):
            sstatus = 'current'
        elif avail and all(s['status'] == 'completed' for s in avail):
            sstatus = 'completed'
        elif any(s['status'] == 'needs_action' for s in sub):
            sstatus = 'needs_action'
        elif any(s['status'] == 'locked' for s in sub):
            sstatus = 'locked'
        else:
            sstatus = 'planned'
        done = sum(1 for s in sub if s['status'] == 'completed')
        stages.append({
            'key': skey, 'title': stitle, 'status': sstatus,
            'progress_percent': round(done / len(sub) * 100) if sub else 0,
            'steps': sub,
        })

    current_stage = next((st for st in stages if st['status'] == 'current'), None)
    return {
        'stages': stages,
        'steps': steps,
        'next_action': {'title': nxt['title'], 'action_label': nxt['action_label'],
                        'url_name': nxt['url_name'], 'status': nxt['status']},
        'overall_progress': round(completed_total / len(steps) * 100),
        'completed_count': completed_total,
        'total_steps': len(steps),
        'current_stage_title': current_stage['title'] if current_stage else (
            stages[-1]['title'] if stages else ''),
    }
