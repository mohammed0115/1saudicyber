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
        # Phase 7B: reports complete only when an active subscription AND a recorded
        # auditor final verdict exist (the internal auditor-reviewed report is available).
        'reports': f['subscription'] and f['auditor_verdict_exists'],
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


# ============================================================
# Phase 8D-2-FIX-C — per-page guided "Where am I / What now / Next" card.
# Read-only. Reuses _signals() so page guidance never diverges from the journey.
# ============================================================

# The canonical 13-step company journey (numbers shown to the user). The page
# guide maps each guided page to one of these steps and answers the three
# questions: where am I, what do I do now, what is the next step.
GUIDE_TOTAL = 13

# page_key -> dict(n, title, what, next_title, done(f), prereq_ok(f), blocked_msg, cta)
# cta is (url_name, label) for the primary action ON this page (advisory/onward).
_PAGE_GUIDE = {
    'classification': dict(
        n=3, title='التصنيف الذكي',
        what='أجب على أسئلة التصنيف لتحديد الأطر المحتملة لمنشأتك.',
        next_title='تحليل الأطر القابلة للتطبيق',
        done=lambda f: f['applicability'] or f['intake_profile'],
        prereq_ok=lambda f: True,
        blocked_msg='',
        cta=('compliance:intake', 'إكمال بيانات التصنيف'),
        # UAT-UI-5: once the intake is complete, the CTA must not say "إكمال" (contradicts the
        # "مكتمل" badge) — offer review/edit instead.
        cta_done_label='مراجعة بيانات التصنيف'),
    'applicability': dict(
        n=4, title='تحليل الأطر القابلة للتطبيق',
        what='راجع الأطر المقترحة بناءً على إجابات التصنيف ثم اعتمد النطاق.',
        next_title='خطة الضوابط وقائمة الأدلة',
        done=lambda f: f['control_plan'] or f['approved_scope'],
        prereq_ok=lambda f: f['intake_profile'] or f['applicability'],
        blocked_msg='لم تظهر نتائج بعد لأن خطوة التصنيف لم تكتمل. ابدأ بالتصنيف الذكي لتحديد الأطر المحتملة.',
        cta=('compliance:classification', 'فتح التصنيف الذكي')),
    'controls': dict(
        n=5, title='خطة الضوابط وقائمة الأدلة',
        what='استعرض الضوابط المنطبقة وولّد خطة الضوابط وقائمة الأدلة لمنشأتك.',
        next_title='رفع الأدلة',
        done=lambda f: f['checklist'],
        prereq_ok=lambda f: f['approved_scope'] or f['control_plan'],
        blocked_msg='ستظهر خطة الضوابط الخاصة بمنشأتك بعد اعتماد الأطر القابلة للتطبيق. أكمل خطوة تحليل الأطر أولًا.',
        cta=('compliance:applicability_review', 'مراجعة واعتماد الأطر')),
    'evidence': dict(
        n=6, title='رفع الأدلة',
        what='ارفع الأدلة المطلوبة لكل ضابط في خطة الضوابط لبدء التحليل الاستشاري.',
        next_title='التحليل الاستشاري ثم الحالة المقترحة',
        done=lambda f: f['submissions'],
        prereq_ok=lambda f: f['checklist'] or f['control_plan'],
        blocked_msg='لا توجد قائمة أدلة بعد لأن خطة الضوابط لم تُنشأ. أكمل اعتماد الأطر وتوليد خطة الضوابط أولًا.',
        cta=('compliance:control_plan', 'عرض خطة الضوابط')),
    'auditor_report': dict(
        n=12, title='التقرير الداخلي بعد مراجعة المدقق',
        what='يعرض هذا التقرير نتيجة مراجعة المدقق الداخلية بعد إصدار الحكم على الأدلة.',
        next_title='سجل المخاطر وخطة المعالجة',
        done=lambda f: f['auditor_verdict_exists'],
        prereq_ok=lambda f: True,
        blocked_msg='',
        cta=('compliance:reports_index', 'عرض التقارير')),
    'risks': dict(
        n=13, title='سجل المخاطر وخطة المعالجة',
        what='سجّل المخاطر والفجوات وأدرها عبر مهام المعالجة. هذه خطوة استشارية مساعدة.',
        next_title='المراقبة المستمرة',
        done=lambda f: f['risks'],
        prereq_ok=lambda f: True,
        blocked_msg='',
        cta=('risk:list', 'إدارة المخاطر والمعالجة')),
    # Continuous/ongoing area after auditor review — not one of the 13 discrete steps.
    'monitoring': dict(
        n=None, title='المراقبة المستمرة بعد المراجعة',
        what='تابع فحوص المراقبة الدورية لصحّة الضوابط بعد مراجعة المدقق. خطوة مستمرة ومساعدة، والأساس متاح عند ربط مصادر البيانات المناسبة.',
        next_title='',
        done=lambda f: f['monitoring_checks'],
        prereq_ok=lambda f: True,
        blocked_msg='',
        cta=('monitoring:overview', 'فتح المراقبة المستمرة')),
}


def build_page_guide(company, page_key):
    """Return a read-only {where/what/next} guide for one guided page, or None.

    status: completed | current | blocked | not_started. Never writes; derived
    purely from existing data signals so it cannot diverge from the journey.
    """
    cfg = _PAGE_GUIDE.get(page_key)
    if cfg is None:
        return None
    f = _signals(company)
    done = cfg['done'](f)
    prereq_ok = cfg['prereq_ok'](f)
    if done:
        status = 'completed'
    elif not prereq_ok:
        status = 'blocked'
    else:
        status = 'current'
    url_name, label = cfg['cta']
    if status == 'completed' and cfg.get('cta_done_label'):
        label = cfg['cta_done_label']
    return {
        'step_number': cfg['n'],
        'total': GUIDE_TOTAL,
        'title': cfg['title'],
        'status': status,
        'what_now': cfg['what'],
        'next_title': cfg['next_title'],
        'blocked_reason': cfg['blocked_msg'] if status == 'blocked' else '',
        'cta_url_name': url_name,
        'cta_label': label,
    }


# ============================================================
# UAT-COMPANY-JOURNEY-NEXT-BACK-STEPPER-FIX-A
# State-driven Next/Back navigation for every company journey page. The "next" button is
# enabled only when THIS step's requirement is satisfied; otherwise it is a disabled button
# with a short Arabic locked reason. "back" always points to the previous logical step (not
# browser history). Derived purely from existing data signals — never writes, tenant-scoped
# via `company`.
# page_key -> dict(back=(url_name, label)|None, next_url, next_label, ready(f)->bool, locked)
_JOURNEY_NAV = {
    'intake': dict(
        back=('dashboard:main', 'العودة للوحة الامتثال'),
        next_url='compliance:classification', next_label='الخطوة التالية: التصنيف الذكي',
        ready=lambda f: f['intake_profile'], locked='أكمل بيانات التصنيف أولًا'),
    'classification': dict(
        back=('compliance:intake', 'العودة: بيانات التصنيف'),
        next_url='compliance:applicability_review', next_label='مراجعة بيانات التصنيف',
        ready=lambda f: f['intake_profile'] or f['applicability'],
        locked='أكمل بيانات التصنيف أولًا'),
    # NB: 'applicability' (review) is handled specially in build_journey_nav — step 4 is where the
    # scope is APPROVED, so its forward action is the approve CTA on the page (a POST form), not a
    # circular locked "next". Here we only need the Back target.
    'applicability': dict(
        back=('compliance:classification', 'العودة: التصنيف الذكي'),
        next_url=None, next_label='', ready=lambda f: False, locked=''),
    'controls': dict(
        back=('compliance:applicability_review', 'العودة: مراجعة واعتماد الأطر'),
        next_url='compliance:evidence_checklist', next_label='الخطوة التالية: قائمة الأدلة ورفعها',
        ready=lambda f: f['control_plan'], locked='أنشئ خطة الضوابط أولًا'),
    'evidence': dict(
        back=('compliance:control_plan', 'العودة: خطة الضوابط'),
        next_url='compliance:reports_index', next_label='الخطوة التالية: التقارير',
        ready=lambda f: f['submissions'], locked='ارفع الأدلة المطلوبة أولًا'),
    'reports': dict(
        back=('compliance:evidence_checklist', 'العودة: قائمة الأدلة'),
        next_url=None, next_label='', ready=lambda f: False, locked=''),
}


def build_journey_nav(company, page_key):
    """Return {back, next} navigation for a company journey page, or None.

    next_enabled reflects the REAL company state; when disabled, next_locked_reason explains
    why in Arabic. Read-only; safe to call on any company-scoped page.
    """
    cfg = _JOURNEY_NAV.get(page_key)
    if cfg is None:
        return None
    f = _signals(company)
    # Review page (step 4): the approve CTA on the page is the forward action. Only once the scope
    # is approved does the nav offer an enabled "next -> control plan"; it is never a circular lock.
    if page_key == 'applicability':
        approved = bool(f['approved_scope'])
        return {
            'back_url_name': cfg['back'][0], 'back_label': cfg['back'][1],
            'next_url_name': 'compliance:control_plan' if approved else None,
            'next_label': 'الخطوة التالية: خطة الضوابط' if approved else '',
            'next_enabled': approved,
            'next_locked_reason': '',
        }
    ready = bool(cfg['ready'](f))
    has_next = bool(cfg['next_url'])
    return {
        'back_url_name': cfg['back'][0] if cfg['back'] else None,
        'back_label': cfg['back'][1] if cfg['back'] else 'العودة للخلف',
        'next_url_name': cfg['next_url'],
        'next_label': cfg['next_label'],
        'next_enabled': has_next and ready,
        'next_locked_reason': '' if (ready or not has_next) else cfg['locked'],
    }
