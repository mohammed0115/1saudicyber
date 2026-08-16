"""Celery tasks for continuous monitoring (FR-010) and async AI processing (FR-006).

Hardening (DD P1 — monitoring.tasks): the periodic company-sweep tasks run bounded
(soft/hard time limits) and isolate failures PER company — one company raising must
not abort the whole sweep. acks_late requeues a task killed mid-run (at-least-once);
the per-company work is naturally idempotent (recompute/regenerate in place).
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Bounds for the whole-fleet sweeps. Generous, but finite, so a wedged run cannot hang a
# worker slot forever; the hard limit is the backstop if soft handling is ignored.
_SWEEP_SOFT = 600   # 10 min
_SWEEP_HARD = 660


def _sweep(per_company):
    """Run per_company(company) over every company, isolating individual failures.

    Returns (ok_count, failed_count). A single company's exception is logged and skipped
    so the sweep still processes the rest of the fleet."""
    from core.models import Company
    ok = failed = 0
    for company in Company.objects.all().iterator():
        try:
            per_company(company)
            ok += 1
        except Exception:
            failed += 1
            logger.exception('monitoring sweep failed for company id=%s', company.id)
    return ok, failed


@shared_task(name='monitoring.tasks.recalculate_all_scores', acks_late=True,
             soft_time_limit=_SWEEP_SOFT, time_limit=_SWEEP_HARD)
def recalculate_all_scores():
    from monitoring.services import recalculate_score
    from monitoring.task_locks import task_lease
    with task_lease('recalculate_all_scores', timeout=_SWEEP_HARD + 60) as acquired:
        if not acquired:
            return 'skipped: another score sweep is running'
        ok, failed = _sweep(recalculate_score)
        return f'recalculated {ok} companies ({failed} failed)'


@shared_task(name='monitoring.tasks.generate_monthly_reports', acks_late=True,
             soft_time_limit=_SWEEP_SOFT, time_limit=_SWEEP_HARD)
def generate_monthly_reports():
    from monitoring.services import generate_monthly_report
    from monitoring.task_locks import task_lease
    with task_lease('generate_monthly_reports', timeout=_SWEEP_HARD + 60) as acquired:
        if not acquired:
            return 'skipped: another monthly-report sweep is running'
        ok, failed = _sweep(generate_monthly_report)
        return f'generated {ok} monthly reports ({failed} failed)'


@shared_task(name='monitoring.tasks.run_compliance_checks', acks_late=True,
             soft_time_limit=_SWEEP_SOFT, time_limit=_SWEEP_HARD)
def run_compliance_checks():
    from monitoring.services import run_company_checks
    from monitoring.task_locks import task_lease
    with task_lease('run_compliance_checks', timeout=_SWEEP_HARD + 60) as acquired:
        if not acquired:
            return {'companies_checked': 0, 'companies_failed': 0, 'skipped': True}
        ok, failed = _sweep(run_company_checks)
        return {'companies_checked': ok, 'companies_failed': failed, 'skipped': False}


@shared_task(bind=True, name='ai_engine.tasks.analyze_evidence_async',
             max_retries=3, default_retry_delay=60,
             soft_time_limit=120, time_limit=180)
def analyze_evidence_async(self, evidence_id, expected_company_id=None):
    """Async wrapper so evidence OCR + AI analysis runs off the request thread (FR-006).

    The pipeline itself always lands the row on a terminal status, so a worker crash can
    never leave it 'processing'. On a soft timeout or unexpected error we still force the
    row to a terminal error state before retrying/giving up, so the UI never hangs.

    P0-01: ``expected_company_id`` is forwarded to the pipeline as a defense-in-depth
    tripwire (see process_evidence_pipeline). Optional for backward compatibility.
    """
    from celery.exceptions import SoftTimeLimitExceeded
    from compliance.services import process_evidence_pipeline, _mark_evidence_error
    from compliance.models import Evidence
    try:
        return process_evidence_pipeline(evidence_id, expected_company_id=expected_company_id)
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
