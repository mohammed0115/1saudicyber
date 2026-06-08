"""
Monitoring services — the logic behind continuous compliance (FR-010).
Pure functions so they can run from Celery tasks, a management command, or tests.
"""
from datetime import date, timedelta

from django.utils import timezone

from compliance.models import CompanyControl, Framework
from monitoring.models import ComplianceScore, Alert, MonthlyReport, CertificateTracker

_COMPLIANT = 'compliant'
_FW_FIELD = {'NCA_ECC': 'nca', 'ARAMCO_SACS002': 'aramco', 'SABIC_CT': 'sabic'}


def compute_scores(company):
    """Return overall + per-framework compliance percentages for a company."""
    qs = CompanyControl.objects.filter(company=company)
    total = qs.count()
    compliant = qs.filter(status=_COMPLIANT).count()
    overall = round(compliant / total * 100, 1) if total else 0.0

    per_fw = {}
    for code, short in _FW_FIELD.items():
        fwq = qs.filter(control__framework__code=code)
        t = fwq.count()
        c = fwq.filter(status=_COMPLIANT).count()
        per_fw[short] = round(c / t * 100, 1) if t else 0.0
    return {'overall': overall, 'total': total, 'compliant': compliant, **per_fw}


def recalculate_score(company, snapshot_date=None):
    """FR-010.1: write today's ComplianceScore snapshot and update the Company row."""
    snapshot_date = snapshot_date or timezone.localdate()
    s = compute_scores(company)
    score, _ = ComplianceScore.objects.update_or_create(
        company=company, date=snapshot_date,
        defaults={
            'overall_score': s['overall'], 'nca_score': s['nca'],
            'aramco_score': s['aramco'], 'sabic_score': s['sabic'],
            'controls_compliant': s['compliant'], 'controls_total': s['total'],
        },
    )
    company.overall_compliance_score = s['overall']
    company.nca_score = s['nca']
    company.aramco_score = s['aramco']
    company.sabic_score = s['sabic']
    company.save(update_fields=['overall_compliance_score', 'nca_score', 'aramco_score', 'sabic_score', 'updated_at'])
    return score


def detect_score_drop(company, threshold=5.0):
    """FR-010.4: raise an alert if the latest score dropped vs the previous snapshot."""
    last_two = list(ComplianceScore.objects.filter(company=company).order_by('-date')[:2])
    if len(last_two) < 2:
        return None
    latest, previous = last_two[0], last_two[1]
    drop = previous.overall_score - latest.overall_score
    if drop >= threshold:
        return Alert.objects.create(
            company=company, alert_type='score_drop', severity='high',
            title=f'Compliance score dropped by {drop:.1f}%',
            title_ar=f'انخفضت درجة الامتثال بمقدار {drop:.1f}%',
            description=f'Overall score fell from {previous.overall_score}% to {latest.overall_score}%.',
            description_ar=f'انخفضت الدرجة الكلية من {previous.overall_score}% إلى {latest.overall_score}%.',
        )
    return None


def check_certificate_expiry(company, warn_within_days=60):
    """FR-010.3/.4: alert when a certificate is close to expiry; refresh days_remaining."""
    today = timezone.localdate()
    created = []
    for cert in CertificateTracker.objects.filter(company=company, is_active=True, expiry_date__isnull=False):
        cert.days_remaining = (cert.expiry_date - today).days
        cert.save(update_fields=['days_remaining'])
        if 0 <= cert.days_remaining <= warn_within_days:
            alert = Alert.objects.create(
                company=company, alert_type='certificate_expiry', severity='medium',
                title=f'Certificate {cert.framework_code} expires in {cert.days_remaining} days',
                title_ar=f'تنتهي شهادة {cert.framework_code} خلال {cert.days_remaining} يومًا',
                description='Plan renewal to avoid a compliance lapse.',
                description_ar='خطّط للتجديد لتجنّب انقطاع الامتثال.',
                affected_control=cert.framework_code,
            )
            created.append(alert)
    return created


def generate_monthly_report(company, month=None):
    """FR-010.2: build/refresh the auto monthly report for a company."""
    month = month or timezone.localdate().replace(day=1)
    s = compute_scores(company)
    data = {
        'overall_score': s['overall'],
        'frameworks': {'nca': s['nca'], 'aramco': s['aramco'], 'sabic': s['sabic']},
        'controls_total': s['total'], 'controls_compliant': s['compliant'],
        'open_alerts': Alert.objects.filter(company=company, is_resolved=False).count(),
    }
    report, _ = MonthlyReport.objects.update_or_create(
        company=company, month=month,
        defaults={
            'report_data': data,
            'summary_en': (f"As of {month:%B %Y}, overall compliance is {s['overall']}% "
                           f"({s['compliant']}/{s['total']} controls compliant)."),
            'summary_ar': (f"حتى {month:%Y-%m}، بلغت نسبة الامتثال الكلية {s['overall']}% "
                           f"({s['compliant']}/{s['total']} ضابطًا مطابقًا)."),
        },
    )
    return report


def run_company_checks(company):
    """Run the full daily check pipeline for one company; returns a summary dict."""
    recalculate_score(company)
    drop = detect_score_drop(company)
    expiries = check_certificate_expiry(company)
    return {'company': company.id, 'score_drop_alert': bool(drop), 'expiry_alerts': len(expiries)}
