"""One post-login decision; all destinations still enforce their own permissions."""
from flask import g, url_for
from flask_login import current_user


def after_login(destination=None):
    if not current_user.email_verified:
        return url_for('auth.verification')
    # Invitation codes stay in email fragments / explicit forms, never sessions.
    if destination == '/workspaces/accept':
        return destination
    from services.workspaces import resolve_context
    resolve_context()
    if not g.workspace_id:
        return url_for('workspaces.index')
    if destination:
        return destination
    from services.onboarding import get
    state = get()
    if not (state.completed_at or state.skipped_at or state.legacy_exempt):
        return url_for('onboarding.setup')
    return url_for('dashboard.dashboard')
