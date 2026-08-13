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


@shared_task(
    bind=True,
    name='monitoring.tasks.analyze_evidence_async',
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={'max_retries': 3},
)
def analyze_evidence_async(self, evidence_id):
    """Process evidence outside the request and retry transient pipeline failures."""
    from compliance.services import process_evidence_pipeline

    result = process_evidence_pipeline(evidence_id)
    if result.get('error'):
        # The pipeline persists a user-visible failed status before Celery retries.
        raise RuntimeError(result['error'])
    return result
