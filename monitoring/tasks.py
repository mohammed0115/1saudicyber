"""Celery tasks for continuous monitoring (FR-010) and async AI processing (FR-006)."""
from celery import shared_task


@shared_task(name='monitoring.tasks.recalculate_all_scores')
def recalculate_all_scores():
    from core.models import Company
    from monitoring.services import recalculate_score
    n = 0
    for company in Company.objects.all():
        recalculate_score(company)
        n += 1
    return f'recalculated {n} companies'


@shared_task(name='monitoring.tasks.generate_monthly_reports')
def generate_monthly_reports():
    from core.models import Company
    from monitoring.services import generate_monthly_report
    n = 0
    for company in Company.objects.all():
        generate_monthly_report(company)
        n += 1
    return f'generated {n} monthly reports'


@shared_task(name='monitoring.tasks.run_compliance_checks')
def run_compliance_checks():
    from core.models import Company
    from monitoring.services import run_company_checks
    results = [run_company_checks(c) for c in Company.objects.all()]
    return {'companies_checked': len(results)}


@shared_task(bind=True, name='ai_engine.tasks.analyze_evidence_async',
             max_retries=3, default_retry_delay=60,
             soft_time_limit=120, time_limit=180)
def analyze_evidence_async(self, evidence_id):
    """Async wrapper so evidence OCR + AI analysis runs off the request thread (FR-006).

    The pipeline itself always lands the row on a terminal status, so a worker crash can
    never leave it 'processing'. On a soft timeout or unexpected error we still force the
    row to a terminal error state before retrying/giving up, so the UI never hangs.
    """
    from celery.exceptions import SoftTimeLimitExceeded
    from compliance.services import process_evidence_pipeline, _mark_evidence_error
    from compliance.models import Evidence
    try:
        return process_evidence_pipeline(evidence_id)
    except SoftTimeLimitExceeded:
        ev = Evidence.objects.filter(id=evidence_id).first()
        if ev is not None:
            _mark_evidence_error(ev, 'analysis timed out')
        return {'error': 'timeout'}
    except Exception as exc:  # pragma: no cover - pipeline already guards internally
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            ev = Evidence.objects.filter(id=evidence_id).first()
            if ev is not None:
                _mark_evidence_error(ev, exc)
            return {'error': str(exc)}
