"""
G5 — access control + labels for the per-company internal message thread.

One thread per company. A user may read/post iff they are: platform staff, a user of
that company, or an ACTIVE auditor with an ACCEPTED assignment to it. Anyone else gets a
safe 404 in the view (never reveals the thread's existence).
"""


def can_access_thread(user, company):
    """True iff `user` may view/post on `company`'s engagement thread."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff or user.is_superuser:
        return True
    if getattr(user, 'company_id', None) == company.id:
        return True
    # Assigned auditor: must be a fully-live (ACTIVE profile + ACTIVE user) auditor with an
    # accepted assignment — P0-03 routes this through the single de-provisioning policy so a
    # suspended/rejected auditor can no longer read or post in the company's private thread.
    from auditors.services import is_auditor_eligible_for_company
    return is_auditor_eligible_for_company(user, company)


def sender_role_label(user):
    """Arabic role label for a message sender (who is speaking in the thread)."""
    if user is None:
        return 'مستخدم'
    if user.is_staff or user.is_superuser:
        return 'الإدارة'
    if getattr(user, 'role', '') == 'auditor':
        return 'المدقّق'
    return 'الشركة'
