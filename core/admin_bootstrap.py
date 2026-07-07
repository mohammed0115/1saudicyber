"""Env-driven initial superuser creation (no hardcoded credentials).

Pure and testable: the caller passes the env mapping and the User model.
"""


class AdminCredentialsMissing(ValueError):
    """Raised when ADMIN_EMAIL / ADMIN_PASSWORD are not both provided."""


def create_superuser_from_env(env, user_model):
    """Create a superuser from ADMIN_EMAIL / ADMIN_PASSWORD.

    Returns (created: bool, email: str). Raises AdminCredentialsMissing when either
    variable is empty — there is NO default admin password.
    """
    email = (env.get('ADMIN_EMAIL') or '').strip()
    password = env.get('ADMIN_PASSWORD') or ''
    if not email or not password:
        raise AdminCredentialsMissing(
            'ADMIN_EMAIL and ADMIN_PASSWORD environment variables are required '
            '(no default admin credentials are shipped).')
    if user_model.objects.filter(email=email).exists():
        return False, email
    user_model.objects.create_superuser(
        email=email, password=password,
        first_name=env.get('ADMIN_FIRST_NAME', 'Admin'),
        last_name=env.get('ADMIN_LAST_NAME', 'CyberTrust'),
    )
    return True, email
