"""
G5 — email notifications for audit-engagement events, on the existing mail infra.

Best-effort but never silent: a mail error must NEVER block the underlying action (recording
a finding, an RFI, or a message), yet it must still reach the log — see core.mail. In dev the
console EmailBackend prints; in production SMTP is configured via env (EMAIL_HOST /
DEFAULT_FROM_EMAIL). All copy is Arabic and internal — these are readiness-review notices,
not official certification correspondence.
"""
from core.mail import send_mail_logged


def _send(to_emails, subject, body):
    """Send one notice to a de-duplicated recipient list; returns count sent (0 if none)."""
    return send_mail_logged(subject, body, to_emails)


def _company_emails(company):
    return list(company.users.values_list('email', flat=True))


def _inapp(recipients, title, *, body='', url_name='', url_args=None, kind='system'):
    """Best-effort in-app notifications alongside email. Never raises."""
    try:
        from core.notify_services import notify_many
        url = ''
        if url_name:
            from django.urls import reverse
            url = reverse(url_name, args=url_args or [])
        notify_many(list(recipients), title, body=body, url=url, kind=kind)
    except Exception:
        pass


def _company_users(company):
    return list(company.users.all())


def _auditor_user(item):
    au = getattr(item, 'auditor', None)
    if au is not None:
        return au
    assessment = getattr(item, 'assessment', None)
    return getattr(assessment, 'assigned_auditor', None)


def notify_new_finding(finding):
    """Email the company's users that an auditor recorded a finding on their control."""
    company = finding.company_control.company
    cid = getattr(finding.company_control.control, 'control_id', '')
    _inapp(_company_users(company), 'ملاحظة تدقيق جديدة على الضابط %s' % cid,
           body=finding.title, url_name='auditor_portal:company_findings', kind='finding')
    return _send(
        _company_emails(company),
        'ملاحظة تدقيق جديدة على أحد ضوابطك',
        'سجّل المدقّق ملاحظة (%s) على الضابط %s:\n\n%s\n\n'
        'يرجى الدخول إلى المنصة لإضافة خطة معالجة. هذه مراجعة داخلية للجاهزية وليست شهادة رسمية.'
        % (finding.severity_ar, cid, finding.title))


def notify_new_rfi(rfi):
    """Email the company's users that the auditor requested additional information (RFI)."""
    company = rfi.company_control.company
    cid = getattr(rfi.company_control.control, 'control_id', '')
    _inapp(_company_users(company), 'طلب معلومات إضافية من المدقّق (RFI) — الضابط %s' % cid,
           body=(rfi.title or ''), url_name='auditor_portal:company_rfi_list', kind='rfi')
    return _send(
        _company_emails(company),
        'طلب معلومات إضافية من المدقّق (RFI)',
        'طلب المدقّق معلومات/أدلة إضافية على الضابط %s:\n\n%s\n\n'
        'يرجى الدخول إلى المنصة للرد على الطلب.' % (cid, rfi.description or rfi.title or ''))


def notify_new_message(message):
    """Email the OTHER thread participants that a new message was posted."""
    company = message.company
    recipients = set(_company_emails(company))
    # Include the assigned auditor(s) so the message reaches them too.
    try:
        from auditors.models import AuditorAssignment
        recipients.update(
            AuditorAssignment.objects.filter(company=company, status='accepted')
            .values_list('auditor__user__email', flat=True))
    except Exception:
        pass
    sender_email = getattr(message.sender, 'email', None)
    recipients.discard(sender_email)   # don't notify the author of their own message
    # In-app: company users + assigned auditor(s) + platform admins (staff) — all
    # thread participants — minus the sender.
    try:
        sender_id = getattr(message.sender, 'id', None)
        in_app_users = list(company.users.exclude(id=sender_id))
        from auditors.models import AuditorAssignment
        for u in AuditorAssignment.objects.filter(company=company, status='accepted').select_related('auditor__user'):
            au = getattr(u.auditor, 'user', None)
            if au and au.id != sender_id:
                in_app_users.append(au)
        # Platform admins participate in every company's internal thread.
        from core.models import User as _U
        for admin in _U.objects.filter(is_staff=True).exclude(id=sender_id):
            in_app_users.append(admin)
        _inapp(in_app_users, 'رسالة جديدة في قناة المراسلة',
               body='بخصوص ملف «%s»' % company.name,
               url_name='auditor_portal:message_thread', url_args=[company.id], kind='message')
    except Exception:
        pass
    return _send(recipients, 'رسالة جديدة في قناة المراسلة',
                 'وصلت رسالة جديدة بخصوص ملف «%s». ادخل إلى المنصة للاطلاع والرد.' % company.name)


def _auditor_email(finding_or_rfi):
    """Email of the auditor who owns the item (raiser, else the assessment's assigned auditor)."""
    au = getattr(finding_or_rfi, 'auditor', None)
    email = getattr(au, 'email', None)
    if email:
        return email
    assessment = getattr(finding_or_rfi, 'assessment', None)
    return getattr(getattr(assessment, 'assigned_auditor', None), 'email', None)


def notify_rfi_response(rfi):
    """Email the auditor that the company responded to their RFI."""
    cid = getattr(rfi.company_control.control, 'control_id', '')
    _inapp([_auditor_user(rfi)], 'ردّت الشركة على طلب المعلومات (RFI) — الضابط %s' % cid,
           url_name='auditor_portal:review_assessment',
           url_args=[rfi.assessment_id] if getattr(rfi, 'assessment_id', None) else None, kind='rfi')
    return _send([_auditor_email(rfi)], 'ردّت الشركة على طلب المعلومات (RFI)',
                 'ردّت الشركة على طلبك بخصوص الضابط %s. ادخل إلى المنصة لمراجعة الرد.' % cid)


def notify_company_capa(finding):
    """Email the auditor that the company proposed a corrective action (CAPA)."""
    cid = getattr(finding.company_control.control, 'control_id', '')
    return _send([_auditor_email(finding)], 'خطة معالجة جديدة من الشركة',
                 'أضافت الشركة خطة معالجة للملاحظة على الضابط %s. ادخل لمراجعتها والتحقّق.' % cid)


def notify_finding_status(finding):
    """Email the company when the auditor changes a finding's status (e.g. closed/reopened)."""
    company = finding.company_control.company
    cid = getattr(finding.company_control.control, 'control_id', '')
    return _send(_company_emails(company), 'تحديث حالة ملاحظة تدقيق',
                 'أصبحت حالة الملاحظة على الضابط %s: %s.' % (cid, finding.status_ar))


def notify_capa_verified(action):
    """Email the company that the auditor verified their corrective action."""
    company = action.finding.company_control.company
    cid = getattr(action.finding.company_control.control, 'control_id', '')
    return _send(_company_emails(company), 'تم التحقّق من خطة المعالجة',
                 'تحقّق المدقّق من خطة المعالجة الخاصة بالضابط %s.' % cid)
