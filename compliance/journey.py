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
    ('ocr_extraction', 'استخراج النص من الأدلة', 'evidence', 'extraction', 'compliance:evidence_checklist',
     'استخراج النص', 'استخراج النص القابل للقراءة من المستندات (OCR للصور مُخطّط لاحقًا).'),
    ('ai_analysis', 'التحليل الاستشاري للذكاء الاصطناعي', 'evidence', 'ai_analysis', 'compliance:evidence_checklist',
     'إدارة الأدلة', 'تحليل استشاري مساعد للأدلة — لا يُعد قرارًا نهائيًا.'),
    ('rule_engine', 'محرك القواعد', 'evidence', 'rule_engine', 'compliance:evidence_checklist',
     'تشغيل التقييم النظامي', 'حالة نظامية مقترحة بناءً على القواعد والأدلة — بانتظار مراجعة المدقق.'),

    ('gap_risk', 'تحليل الفجوات والمخاطر', 'gaps', 'optional', 'risk:list',
     'فتح سجل المخاطر', 'تسجيل المخاطر والفجوات وتقييمها.'),
    ('remediation', 'خطة المعالجة', 'gaps', 'optional', 'risk:list',
     'إدارة المعالجة', 'مهام معالجة المخاطر والفجوات.'),

    ('auditor_review', 'مراجعة المدقق', 'review', 'auditor_review', 'compliance:auditor_review_queue',
     'قائمة المراجعة', 'مراجعة المدقّق للأدلة وتسجيل القرار النهائي (مراجعة بشرية).'),
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
                         EvidenceTextExtraction, EvidenceAIAnalysis, EvidenceRuleEvaluation,
                         AuditorFinalVerdict, ControlAssessment)
    from risk.models import RiskItem, RemediationTask
    from auditors.models import AuditorAssignment
    from monitoring.models import MonitoringCheck
    q = lambda m, **kw: m.objects.filter(company=company, **kw).exists()
    assessments = ControlAssessment.objects.filter(company=company)
    return {
        'intake': q(CompanyIntakeProfile) or bool(getattr(company, 'onboarding_completed', False)),
        'intake_profile': q(CompanyIntakeProfile),
        'applicability': q(FrameworkApplicabilityResult),
        'approved_scope': q(CompanyFrameworkScope, status='approved'),
        'control_plan': q(ControlApplicabilityResult, decision='applicable',
                          control__framework_version__isnull=False, control__is_legacy_import=False),
        'assessments': assessments.exists(),
        'reviewed': assessments.exclude(status='not_reviewed').exists(),
        'all_reviewed': assessments.exists() and not assessments.filter(status='not_reviewed').exists(),
        'submissions': q(EvidenceSubmission),
        # Phase 6C-FIX-A: truthful — only a PERSISTED successful extraction counts.
        'text_extracted': EvidenceTextExtraction.objects.filter(
            submission__company=company, status='extracted', char_count__gt=0).exists(),
        'analysis': q(EvidenceAnalysisResult),
        # Phase 6D: advisory AI analyzer step — only a completed advisory result counts.
        'ai_analysis_completed': EvidenceAIAnalysis.objects.filter(
            submission__company=company, status='completed').exists(),
        # Phase 6E: rule-engine step — only a completed suggestion counts.
        'rule_eval_completed': EvidenceRuleEvaluation.objects.filter(
            submission__company=company, status='completed').exists(),
        # Phase 6F: a recorded human auditor final verdict on any submission.
        'auditor_verdict_exists': AuditorFinalVerdict.objects.filter(
            submission__company=company).exists(),
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
        # Phase 6A: Smart Classification is computable once an intake profile exists
        # (advisory). Still completed when deterministic applicability has been run.
        'smart_classification': f['applicability'] or f['intake_profile'],
        'control_library': True,
        # Phase 6B: an advisory applicability preview is computable once an intake
        # profile exists; still completed when the persisted control plan is generated.
        'applicability': f['control_plan'] or f['intake_profile'],
        'assessment_creation': f['assessments'],
        'evidence_upload': f['submissions'],
        # Phase 6C-FIX-A: text-extraction step completes ONLY when an actual
        # successful extraction (status=extracted, char_count>0) is persisted —
        # never from a file-type heuristic. OCR (scanned images) stays planned.
        'ocr_extraction': f['text_extracted'],
        # Phase 6D: completed only when a persisted advisory AI analysis is completed.
        'ai_analysis': f['ai_analysis_completed'],
        # Phase 6E: completed only when a persisted suggested status is computed.
        'rule_engine': f['rule_eval_completed'],
        'gap_risk': f['risks'],
        'remediation': f['remediation'],
        # Phase 6F: auditor-review/final-verdict steps reflect a recorded human verdict.
        'auditor_review': f['auditor_verdict_exists'],
        'final_verdict': f['auditor_verdict_exists'],
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
        elif kind == 'extraction':
            # Phase 6C: text extraction is available. Completed when an
            # extractable-type evidence file exists; needs_action when evidence
            # exists but none is text-extractable; planned before any upload.
            if completed:
                status = 'completed'
            elif f['submissions']:
                status = 'needs_action'
            else:
                status = 'planned'
        elif kind == 'ai_analysis':
            # Phase 6D: advisory analysis requires extracted text first.
            # completed = a completed advisory analysis exists; needs_action =
            # extracted text exists but no completed analysis; planned otherwise.
            if completed:
                status = 'completed'
            elif f['text_extracted']:
                status = 'needs_action'
            else:
                status = 'planned'
        elif kind == 'rule_engine':
            # Phase 6E: suggested status requires a completed advisory analysis first.
            # completed = a completed rule evaluation exists; needs_action = AI
            # advisory done but no rule run; planned otherwise.
            if completed:
                status = 'completed'
            elif f['ai_analysis_completed']:
                status = 'needs_action'
            else:
                status = 'planned'
        elif kind == 'auditor_review':
            # Phase 6F: human verdict. completed = a recorded auditor verdict exists;
            # needs_action = a rule suggestion exists but no verdict; planned otherwise.
            if completed:
                status = 'completed'
            elif f['rule_eval_completed']:
                status = 'needs_action'
            else:
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
