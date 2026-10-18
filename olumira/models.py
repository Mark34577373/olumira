"""Account, workspace and routine models preserve nullable legacy ownership."""
from .extensions import db


class Owner(db.Model):
    __tablename__ = 'owners'
    id = db.Column(db.Text, primary_key=True)
    created_at = db.Column(db.Text, nullable=False)


class Routine(db.Model):
    __tablename__ = 'routines'
    __table_args__ = (db.Index('idx_routines_owner', 'owner_id'), {'sqlite_autoincrement': True})
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), index=True)
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'))
    owner_id = db.Column(db.Text, nullable=True)
    name = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False, default='', server_default='')
    icon = db.Column(db.String(24), nullable=False, default='sun', server_default='sun')
    color = db.Column(db.String(16), nullable=False, default='sage', server_default='sage')
    archived_at = db.Column(db.DateTime(timezone=True))
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    is_checklist = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_by = db.Column(db.String(32), db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: utcnow())
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: utcnow(), onupdate=lambda: utcnow())



class Observation(db.Model):
    __tablename__ = 'observations'
    __table_args__ = (db.Index('idx_observations_owner', 'owner_id'), db.Index('ix_observations_scope_time','workspace_id','profile_id','observed_at','id'), db.Index('ix_observations_scope_category','workspace_id','profile_id','category'), {'sqlite_autoincrement': True})
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), index=True)
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'))
    owner_id = db.Column(db.Text, nullable=True)
    activity = db.Column(db.Text, nullable=False)
    date = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    mood = db.Column(db.Text)
    tags = db.Column(db.Text)
    category = db.Column(db.String(60), nullable=False, default='General notes', server_default='General notes')
    author_id = db.Column(db.String(32), db.ForeignKey('users.id'))
    observed_at = db.Column(db.DateTime(timezone=True))
    timezone = db.Column(db.String(64))
    created_at = db.Column(db.DateTime(timezone=True))
    updated_at = db.Column(db.DateTime(timezone=True))
    archived_at = db.Column(db.DateTime(timezone=True))
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    session_id = db.Column(db.String(32), db.ForeignKey('routine_sessions.id'))
    task_id = db.Column(db.String(32), db.ForeignKey('caregiver_tasks.id'))


class RoutineCompletion(db.Model):
    __tablename__ = 'routine_completions'
    routine_id = db.Column(db.Integer, db.ForeignKey('routines.id', ondelete='CASCADE'), primary_key=True)
    completion_date = db.Column(db.Text, primary_key=True)


from datetime import datetime, timezone
from flask_login import UserMixin


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    closed_at = db.Column(db.DateTime(timezone=True))
    __tablename__ = 'users'
    __table_args__ = (
        db.UniqueConstraint('email', name='uq_users_email'),
        db.UniqueConstraint('owner_id', name='uq_users_owner'),
        db.CheckConstraint('email = lower(email)', name='ck_users_email_normalized'),
    )
    id = db.Column(db.String(32), primary_key=True)
    email = db.Column(db.String(254), nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    pending_email = db.Column(db.String(254))
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    # Only explicitly linked account owners are accessible; legacy owners stay unlinked.
    owner_id = db.Column(db.Text, db.ForeignKey('owners.id'), nullable=False)


class AuthSession(db.Model):
    __tablename__ = 'auth_sessions'
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    last_seen_at = db.Column(db.BigInteger, nullable=False)
    revoked_at = db.Column(db.BigInteger)
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')


class AccountToken(db.Model):
    __tablename__ = 'account_tokens'
    __table_args__ = (db.CheckConstraint("purpose IN ('verify_email', 'reset_password', 'change_email')", name='ck_account_tokens_purpose'),)
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    purpose = db.Column(db.String(24), nullable=False)
    target_email = db.Column(db.String(254), nullable=False)
    auth_version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    used_at = db.Column(db.BigInteger)


class EmailOutbox(db.Model):
    __tablename__ = 'email_outbox'
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash = db.Column(db.String(64), db.ForeignKey('account_tokens.token_hash', ondelete='CASCADE'))
    invitation_id = db.Column(db.String(32), db.ForeignKey('workspace_invitations.id'))
    kind = db.Column(db.String(24), nullable=False)
    encrypted_payload = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    available_at = db.Column(db.BigInteger, nullable=False, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    delivered_at = db.Column(db.BigInteger)
    cancelled_at = db.Column(db.BigInteger)
    last_error = db.Column(db.String(32))


class FamilyWorkspace(db.Model):
    closed_at = db.Column(db.DateTime(timezone=True))
    __tablename__ = 'family_workspaces'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    created_by = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class WorkspaceMembership(db.Model):
    __tablename__ = 'workspace_memberships'
    __table_args__ = (db.UniqueConstraint('workspace_id', 'user_id', name='uq_workspace_member'),
        db.CheckConstraint("role IN ('owner','caregiver','viewer')", name='ck_membership_role'),
        db.CheckConstraint("status IN ('active','revoked')", name='ck_membership_status'))
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False, index=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False, default='active')
    joined_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class CareProfile(db.Model):
    __tablename__ = 'care_profiles'
    __table_args__ = (db.UniqueConstraint('id', 'workspace_id', name='uq_profile_workspace'),)
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    avatar = db.Column(db.String(16), nullable=False, default='leaf')
    communication = db.Column(db.String(500), nullable=False, default='')
    routine_preferences = db.Column(db.String(500), nullable=False, default='')
    interests = db.Column(db.String(500), nullable=False, default='')
    support_notes = db.Column(db.String(1000), nullable=False, default='')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class WorkspaceInvitation(db.Model):
    __tablename__ = 'workspace_invitations'
    __table_args__ = (db.CheckConstraint("role IN ('caregiver','viewer')", name='ck_invitation_role'),)
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False, index=True)
    email = db.Column(db.String(254), nullable=False)
    role = db.Column(db.String(16), nullable=False)
    invited_by = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    accepted_at = db.Column(db.BigInteger)
    revoked_at = db.Column(db.BigInteger)


class AuditEvent(db.Model):
    __tablename__ = 'audit_events'
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False, index=True)
    actor_id = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False)
    event_type = db.Column(db.String(48), nullable=False)
    target_id = db.Column(db.String(64))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class RoutineStep(db.Model):
    timer_seconds = db.Column(db.Integer,nullable=False,default=0,server_default='0')
    __tablename__ = 'routine_steps'
    __table_args__ = (db.UniqueConstraint('routine_id','position',name='uq_routine_step_position'),
                     db.CheckConstraint('position >= 0',name='ck_routine_step_position'))
    id = db.Column(db.String(32), primary_key=True)
    routine_id = db.Column(db.Integer, db.ForeignKey('routines.id',ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(500), nullable=False, default='')
    icon = db.Column(db.String(24), nullable=False, default='sun')
    position = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class RoutineCompletionSnapshot(db.Model):
    __tablename__ = 'routine_completion_snapshots'
    __table_args__ = (db.ForeignKeyConstraint(['routine_id','completion_date'],
        ['routine_completions.routine_id','routine_completions.completion_date'],ondelete='CASCADE'),)
    routine_id = db.Column(db.Integer, primary_key=True)
    completion_date = db.Column(db.Text, primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'))
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'))
    name = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(16), nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class RoutineSchedule(db.Model):
    __tablename__ = "routine_schedules"
    __table_args__ = (
        db.CheckConstraint(
            "state IN ('active','paused','ended')", name="ck_schedule_state"
        ),
    )
    id = db.Column(db.String(32), primary_key=True)
    routine_id = db.Column(
        db.Integer, db.ForeignKey("routines.id"), nullable=False, index=True
    )
    workspace_id = db.Column(
        db.String(32), db.ForeignKey("family_workspaces.id"), nullable=False, index=True
    )
    profile_id = db.Column(db.String(32), db.ForeignKey("care_profiles.id"))
    state = db.Column(db.String(12), nullable=False, default="active")
    version = db.Column(db.Integer, nullable=False, default=1)
    revision = db.Column(db.Integer, nullable=False, default=1)
    created_by = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class RoutineScheduleRevision(db.Model):
    __tablename__ = "routine_schedule_revisions"
    __table_args__ = (
        db.UniqueConstraint("schedule_id", "number", name="uq_schedule_revision"),
        db.CheckConstraint(
            "frequency IN ('once','daily','weekdays','weekly')",
            name="ck_schedule_frequency",
        ),
    )
    id = db.Column(db.String(32), primary_key=True)
    schedule_id = db.Column(
        db.String(32), db.ForeignKey("routine_schedules.id"), nullable=False, index=True
    )
    number = db.Column(db.Integer, nullable=False)
    timezone = db.Column(db.String(64), nullable=False)
    local_time = db.Column(db.String(5), nullable=False)
    frequency = db.Column(db.String(12), nullable=False)
    weekdays = db.Column(db.String(13), nullable=False)
    start_date = db.Column(db.String(10), nullable=False)
    end_date = db.Column(db.String(10))
    valid_from = db.Column(db.DateTime(timezone=True), nullable=False)
    valid_until = db.Column(db.DateTime(timezone=True))


class RoutineOccurrence(db.Model):
    __tablename__ = "routine_occurrences"
    __table_args__ = (
        db.UniqueConstraint("revision_id", "local_date", name="uq_occurrence_day"),
    )
    id = db.Column(db.String(64), primary_key=True)
    revision_id = db.Column(
        db.String(32), db.ForeignKey("routine_schedule_revisions.id"), nullable=False
    )
    routine_id = db.Column(db.Integer, db.ForeignKey("routines.id"), nullable=False)
    workspace_id = db.Column(
        db.String(32), db.ForeignKey("family_workspaces.id"), nullable=False, index=True
    )
    profile_id = db.Column(db.String(32), db.ForeignKey("care_profiles.id"))
    scheduled_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    local_date = db.Column(db.String(10), nullable=False)
    local_time = db.Column(db.String(5), nullable=False)
    timezone = db.Column(db.String(64), nullable=False)


class RoutineSession(db.Model):
    __tablename__ = "routine_sessions"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active','paused','completed')", name="ck_session_status"
        ),
        db.Index(
            "ix_sessions_scope_started", "workspace_id", "profile_id", "started_at"
        ),
        db.Index("ix_sessions_scope_completed","workspace_id","profile_id","completed_at"),
    )
    id = db.Column(db.String(32), primary_key=True)
    routine_id = db.Column(
        db.Integer, db.ForeignKey("routines.id"), nullable=False, index=True
    )
    workspace_id = db.Column(
        db.String(32), db.ForeignKey("family_workspaces.id"), nullable=False
    )
    profile_id = db.Column(db.String(32), db.ForeignKey("care_profiles.id"))
    occurrence_id = db.Column(
        db.String(64), db.ForeignKey("routine_occurrences.id"), unique=True
    )
    # Only ad-hoc runs use this slot; NULL permits multiple finished runs.
    active_key = db.Column(db.String(64), unique=True)
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(24), nullable=False)
    color = db.Column(db.String(16), nullable=False)
    profile_name = db.Column(db.String(80), nullable=False)
    routine_version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(12), nullable=False, default="active")
    version = db.Column(db.Integer, nullable=False, default=1)
    started_by = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    paused_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))


class RoutineSessionStep(db.Model):
    timer_seconds = db.Column(db.Integer,nullable=False,default=0,server_default='0')
    __tablename__ = "routine_session_steps"
    __table_args__ = (
        db.UniqueConstraint("session_id", "position", name="uq_session_step_position"),
        db.CheckConstraint("position >= 0", name="ck_session_step_position"),
    )
    id = db.Column(db.String(32), primary_key=True)
    session_id = db.Column(
        db.String(32), db.ForeignKey("routine_sessions.id"), nullable=False, index=True
    )
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(24), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    completed_by = db.Column(db.String(32), db.ForeignKey("users.id"))
    completed_at = db.Column(db.DateTime(timezone=True))


class RoutineSessionEvent(db.Model):
    __tablename__ = "routine_session_events"
    id = db.Column(db.String(32), primary_key=True)
    session_id = db.Column(
        db.String(32), db.ForeignKey("routine_sessions.id"), nullable=False, index=True
    )
    step_id = db.Column(db.String(32), db.ForeignKey("routine_session_steps.id"))
    actor_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(24), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class RoutineLaunchRequest(db.Model):
    __tablename__ = "routine_launch_requests"
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(
        db.String(32), db.ForeignKey("family_workspaces.id"), nullable=False
    )
    actor_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False)
    routine_id = db.Column(db.Integer, db.ForeignKey("routines.id"), nullable=False)
    session_id = db.Column(
        db.String(32), db.ForeignKey("routine_sessions.id"), nullable=False
    )


class CommunicationBoard(db.Model):
    __tablename__ = 'communication_boards'
    __table_args__ = (db.CheckConstraint("layout IN ('2','3','4','adaptive')", name='ck_board_layout'),
        db.Index('ix_boards_scope_updated','workspace_id','profile_id','updated_at'))
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False)
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'))
    title = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(500), nullable=False, default='')
    category = db.Column(db.String(40), nullable=False)
    layout = db.Column(db.String(12), nullable=False, default='adaptive')
    version = db.Column(db.Integer, nullable=False, default=1)
    archived_at = db.Column(db.DateTime(timezone=True))
    created_by = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    cards = db.relationship('CommunicationCard', back_populates='board', lazy='raise', order_by='CommunicationCard.position', cascade='all, delete-orphan')


class CommunicationCard(db.Model):
    __tablename__ = 'communication_cards'
    __table_args__ = (db.UniqueConstraint('board_id','position',name='uq_communication_card_position'),
        db.CheckConstraint('position >= 0',name='ck_communication_card_position'))
    id = db.Column(db.String(32), primary_key=True)
    board_id = db.Column(db.String(32), db.ForeignKey('communication_boards.id', ondelete='CASCADE'), nullable=False, index=True)
    label = db.Column(db.String(60), nullable=False)
    spoken_text = db.Column(db.String(200), nullable=False)
    symbol = db.Column(db.String(32), nullable=False)
    color = db.Column(db.String(16), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    board = db.relationship('CommunicationBoard', back_populates='cards', lazy='raise')


class SavedCommunicationPhrase(db.Model):
    __tablename__ = 'saved_communication_phrases'
    __table_args__ = (db.CheckConstraint('position >= 0',name='ck_saved_phrase_position'),
        db.Index('ix_saved_phrases_scope_order','workspace_id','profile_id','position'))
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False)
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'))
    label = db.Column(db.String(60), nullable=False)
    text = db.Column(db.String(1000), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    archived_at = db.Column(db.DateTime(timezone=True))
    created_by = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CommunicationPreference(db.Model):
    __tablename__ = 'communication_preferences'
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False, index=True)
    card_size = db.Column(db.String(12), nullable=False, default='medium')
    layout = db.Column(db.String(12), nullable=False, default='board')
    text_position = db.Column(db.String(12), nullable=False, default='below')
    show_text = db.Column(db.Boolean, nullable=False, default=True)
    show_symbols = db.Column(db.Boolean, nullable=False, default=True)
    speech_enabled = db.Column(db.Boolean, nullable=False, default=True)
    speech_rate = db.Column(db.String(5), nullable=False, default='1')
    voice_id = db.Column(db.String(300), nullable=False, default='')
    simplified = db.Column(db.Boolean, nullable=False, default=False)
    high_contrast = db.Column(db.Boolean, nullable=False, default=False)
    reduced_motion = db.Column(db.Boolean, nullable=False, default=False)
    default_board_id = db.Column(db.String(32), db.ForeignKey('communication_boards.id',ondelete='SET NULL'))
    version = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow,onupdate=utcnow)


class FavoriteCommunicationCard(db.Model):
    __tablename__ = 'favorite_communication_cards'
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'), primary_key=True)
    card_id = db.Column(db.String(32), db.ForeignKey('communication_cards.id',ondelete='CASCADE'), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False)


class FavoriteCommunicationPhrase(db.Model):
    __tablename__ = 'favorite_communication_phrases'
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'), primary_key=True)
    phrase_id = db.Column(db.String(32), db.ForeignKey('saved_communication_phrases.id',ondelete='CASCADE'), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False)


class CaregiverTask(db.Model):
    __tablename__ = 'caregiver_tasks'
    __table_args__ = (db.CheckConstraint("status IN ('todo','in_progress','completed','canceled')", name='ck_care_task_status'),db.CheckConstraint("priority IN ('low','normal','high')",name='ck_care_task_priority'),db.Index('ix_tasks_scope_due','workspace_id','profile_id','due_at'),db.Index('ix_tasks_scope_completed','workspace_id','profile_id','completed_at'))
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False)
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'))
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(2000), nullable=False,default='')
    assigned_to = db.Column(db.String(32),db.ForeignKey('users.id'))
    routine_id = db.Column(db.Integer,db.ForeignKey('routines.id'))
    due_at = db.Column(db.DateTime(timezone=True))
    timezone = db.Column(db.String(64),nullable=False)
    priority = db.Column(db.String(8),nullable=False,default='normal')
    status = db.Column(db.String(16),nullable=False,default='todo')
    version = db.Column(db.Integer,nullable=False,default=1)
    created_by = db.Column(db.String(32),db.ForeignKey('users.id'),nullable=False)
    completed_by = db.Column(db.String(32),db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow,onupdate=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True))


class CaregiverHandoff(db.Model):
    __tablename__ = 'caregiver_handoffs'
    __table_args__ = (db.Index('ix_handoffs_scope_created','workspace_id','profile_id','created_at'),)
    id = db.Column(db.String(32),primary_key=True)
    workspace_id = db.Column(db.String(32),db.ForeignKey('family_workspaces.id'),nullable=False)
    profile_id = db.Column(db.String(32),db.ForeignKey('care_profiles.id'))
    summary = db.Column(db.String(2000),nullable=False)
    recipient_kind = db.Column(db.String(8),nullable=False)
    routine_id = db.Column(db.Integer,db.ForeignKey('routines.id'))
    observation_id = db.Column(db.Integer,db.ForeignKey('observations.id'))
    created_by = db.Column(db.String(32),db.ForeignKey('users.id'),nullable=False)
    created_at = db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)


class HandoffRecipient(db.Model):
    __tablename__ = 'handoff_recipients'
    handoff_id = db.Column(db.String(32),db.ForeignKey('caregiver_handoffs.id'),primary_key=True)
    user_id = db.Column(db.String(32),db.ForeignKey('users.id'),primary_key=True)
    acknowledged_at = db.Column(db.DateTime(timezone=True))


class HandoffTask(db.Model):
    __tablename__ = 'handoff_tasks'
    handoff_id = db.Column(db.String(32),db.ForeignKey('caregiver_handoffs.id'),primary_key=True)
    task_id = db.Column(db.String(32),db.ForeignKey('caregiver_tasks.id'),primary_key=True)


class CalendarEvent(db.Model):
    __tablename__='calendar_events'
    __table_args__=(db.Index('ix_calendar_scope_start','workspace_id','profile_id','start_date'),)
    id=db.Column(db.String(32),primary_key=True)
    workspace_id=db.Column(db.String(32),db.ForeignKey('family_workspaces.id'),nullable=False)
    profile_id=db.Column(db.String(32),db.ForeignKey('care_profiles.id'))
    title=db.Column(db.String(120),nullable=False)
    description=db.Column(db.String(2000),nullable=False,default='')
    start_date=db.Column(db.String(10),nullable=False)
    local_time=db.Column(db.String(5),nullable=False)
    end_date=db.Column(db.String(10),nullable=False)
    end_time=db.Column(db.String(5),nullable=False)
    timezone=db.Column(db.String(64),nullable=False)
    all_day=db.Column(db.Boolean,nullable=False,default=False)
    frequency=db.Column(db.String(12),nullable=False,default='once')
    weekdays=db.Column(db.String(20),nullable=False,default='')
    repeat_until=db.Column(db.String(10))
    assigned_to=db.Column(db.String(32),db.ForeignKey('users.id'))
    status=db.Column(db.String(12),nullable=False,default='active')
    version=db.Column(db.Integer,nullable=False,default=1)
    created_by=db.Column(db.String(32),db.ForeignKey('users.id'),nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    updated_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)


class ReminderPreference(db.Model):
    __tablename__='reminder_preferences'
    user_id=db.Column(db.String(32),db.ForeignKey('users.id'),primary_key=True)
    workspace_id=db.Column(db.String(32),db.ForeignKey('family_workspaces.id'),primary_key=True)
    context_key=db.Column(db.String(32),primary_key=True)
    profile_id=db.Column(db.String(32),db.ForeignKey('care_profiles.id'))
    enabled=db.Column(db.Boolean,nullable=False,default=True)
    lead_minutes=db.Column(db.Integer,nullable=False,default=60)
    categories=db.Column(db.String(60),nullable=False,default='routine,task,event')
    version=db.Column(db.Integer,nullable=False,default=1)


class Resource(db.Model):
    __tablename__='resources'
    id=db.Column(db.String(40),primary_key=True)
    title=db.Column(db.String(120),nullable=False)
    summary=db.Column(db.String(500),nullable=False)
    content=db.Column(db.Text,nullable=False)
    category=db.Column(db.String(60),nullable=False,index=True)
    tags=db.Column(db.String(200),nullable=False,default='')
    publisher=db.Column(db.String(120),nullable=False)
    external_url=db.Column(db.String(1000))
    publication_date=db.Column(db.String(10))
    reviewed_at=db.Column(db.String(10))
    published=db.Column(db.Boolean,nullable=False,default=True)
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    updated_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)


class ResourceBookmark(db.Model):
    __tablename__='resource_bookmarks'
    user_id=db.Column(db.String(32),db.ForeignKey('users.id'),primary_key=True)
    resource_id=db.Column(db.String(40),db.ForeignKey('resources.id'),primary_key=True)
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)


class DashboardPreference(db.Model):
    __tablename__='dashboard_preferences'
    user_id=db.Column(db.String(32),db.ForeignKey('users.id'),primary_key=True)
    workspace_id=db.Column(db.String(32),db.ForeignKey('family_workspaces.id'),primary_key=True)
    preferred_profile_id=db.Column(db.String(32),db.ForeignKey('care_profiles.id'))
    sections=db.Column(db.String(120),nullable=False,default='upcoming,runs,communication,observations,collaboration,insights')
    timezone=db.Column(db.String(64),nullable=False,default='America/Chicago')
    version=db.Column(db.Integer,nullable=False,default=1)


class OnboardingState(db.Model):
    """DAY 36 — PREMIUM EXPERIENCE PHASE 1: GUIDED ONBOARDING."""
    __tablename__='onboarding_states'
    user_id=db.Column(db.String(32),db.ForeignKey('users.id'),primary_key=True)
    workspace_id=db.Column(db.String(32),db.ForeignKey('family_workspaces.id'),primary_key=True)
    step=db.Column(db.Integer,nullable=False,default=0)
    version=db.Column(db.Integer,nullable=False,default=1)
    profile_id=db.Column(db.String(32),db.ForeignKey('care_profiles.id'))
    routine_id=db.Column(db.Integer,db.ForeignKey('routines.id'))
    board_id=db.Column(db.String(32),db.ForeignKey('communication_boards.id'))
    skipped_steps=db.Column(db.String(40),nullable=False,default='')
    started_at=db.Column(db.DateTime(timezone=True))
    completed_at=db.Column(db.DateTime(timezone=True))
    skipped_at=db.Column(db.DateTime(timezone=True))
    legacy_exempt=db.Column(db.Boolean,nullable=False,default=False)


class UserPreference(db.Model):
    __tablename__ = "user_preferences"
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), primary_key=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    larger_text = db.Column(db.Boolean, nullable=False, default=False)
    reduced_motion = db.Column(db.Boolean, nullable=False, default=False)
    enhanced_contrast = db.Column(db.Boolean, nullable=False, default=False)
    simplified = db.Column(db.Boolean, nullable=False, default=False)
    reduced_effects = db.Column(db.Boolean, nullable=False, default=False)
    calendar_view = db.Column(db.String(10), nullable=False, default="month")
    week_start = db.Column(db.String(6), nullable=False, default="monday")
    time_format = db.Column(db.String(2), nullable=False, default="24")


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(
        db.String(32), db.ForeignKey("users.id"), nullable=False, index=True
    )
    workspace_id = db.Column(
        db.String(32), db.ForeignKey("family_workspaces.id"), nullable=False, index=True
    )
    profile_id = db.Column(db.String(32), db.ForeignKey("care_profiles.id"))
    category = db.Column(db.String(16), nullable=False)
    entity_type = db.Column(db.String(16), nullable=False)
    entity_id = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    dedup_key = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime(timezone=True))
    dismissed_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.Index(
            "ix_notification_inbox",
            "user_id",
            "workspace_id",
            "dismissed_at",
            "read_at",
            "created_at",
        ),
        db.ForeignKeyConstraint(
            ["profile_id", "workspace_id"],
            ["care_profiles.id", "care_profiles.workspace_id"],
        ),
        db.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspace_memberships.workspace_id", "workspace_memberships.user_id"],
        ),
        db.CheckConstraint("category IN ('task','handoff','routine','event')"),
    )


class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), primary_key=True)
    workspace_id = db.Column(
        db.String(32), db.ForeignKey("family_workspaces.id"), primary_key=True
    )
    categories = db.Column(
        db.String(100), nullable=False, default="task,handoff,routine,event"
    )
    retention_days = db.Column(db.Integer, nullable=False, default=90)
    version = db.Column(db.Integer, nullable=False, default=1)


class DataExport(db.Model):
    __tablename__ = "data_exports"
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(
        db.String(32), db.ForeignKey("users.id"), nullable=False, index=True
    )
    workspace_id = db.Column(db.String(32), db.ForeignKey("family_workspaces.id"))
    scope = db.Column(db.String(12), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.BigInteger, nullable=False, index=True)
    consumed_at = db.Column(db.BigInteger)


class DeletionRequest(db.Model):
    __tablename__ = "deletion_requests"
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey("users.id"), nullable=False)
    workspace_id = db.Column(db.String(32), db.ForeignKey("family_workspaces.id"))
    scope = db.Column(db.String(12), nullable=False)
    status = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class CarePlan(db.Model):
    __tablename__ = 'care_plans'
    __table_args__ = (db.Index('ix_care_plans_scope', 'workspace_id', 'profile_id'), db.CheckConstraint("status IN ('draft','active','archived')", name='ck_care_plan_status'))
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('family_workspaces.id'), nullable=False)
    profile_id = db.Column(db.String(32), db.ForeignKey('care_profiles.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(2000), nullable=False, default='')
    priorities = db.Column(db.String(2000), nullable=False, default='')
    status = db.Column(db.String(12), nullable=False, default='active')
    version = db.Column(db.Integer, nullable=False, default=1)
    created_by = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False)
    updated_by = db.Column(db.String(32), db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CareGoal(db.Model):
    __tablename__ = 'care_goals'
    __table_args__ = (db.CheckConstraint("status IN ('planned','in_progress','completed','paused')", name='ck_care_goal_status'),)
    id = db.Column(db.String(32), primary_key=True)
    plan_id = db.Column(db.String(32), db.ForeignKey('care_plans.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(1000), nullable=False, default='')
    category = db.Column(db.String(40), nullable=False, default='Daily support')
    status = db.Column(db.String(16), nullable=False, default='planned')
    target_date = db.Column(db.String(10))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CarePlanRoutine(db.Model):
    __tablename__ = 'care_plan_routines'
    plan_id = db.Column(db.String(32), db.ForeignKey('care_plans.id', ondelete='CASCADE'), primary_key=True)
    routine_id = db.Column(db.Integer, db.ForeignKey('routines.id'), primary_key=True)


class CarePlanBoard(db.Model):
    __tablename__ = 'care_plan_boards'
    plan_id = db.Column(db.String(32), db.ForeignKey('care_plans.id', ondelete='CASCADE'), primary_key=True)
    board_id = db.Column(db.String(32), db.ForeignKey('communication_boards.id'), primary_key=True)


class CarePlanTask(db.Model):
    __tablename__ = 'care_plan_tasks'
    plan_id = db.Column(db.String(32), db.ForeignKey('care_plans.id', ondelete='CASCADE'), primary_key=True)
    task_id = db.Column(db.String(32), db.ForeignKey('caregiver_tasks.id'), primary_key=True)


class HandoffDraft(db.Model):
    __tablename__ = 'handoff_drafts'
    __table_args__ = (db.Index('ix_handoff_drafts_scope','workspace_id','profile_id','created_by'),db.CheckConstraint("status IN ('draft','ready','shared')",name='ck_handoff_draft_status'))
    id = db.Column(db.String(32),primary_key=True)
    workspace_id = db.Column(db.String(32),db.ForeignKey('family_workspaces.id'),nullable=False)
    profile_id = db.Column(db.String(32),db.ForeignKey('care_profiles.id'))
    created_by = db.Column(db.String(32),db.ForeignKey('users.id'),nullable=False)
    recipient_id = db.Column(db.String(32),db.ForeignKey('users.id'),nullable=False)
    summary = db.Column(db.String(2000),nullable=False)
    status = db.Column(db.String(12),nullable=False,default='draft')
    version = db.Column(db.Integer,nullable=False,default=1)
    period_start = db.Column(db.DateTime(timezone=True),nullable=False)
    period_end = db.Column(db.DateTime(timezone=True),nullable=False)
    shared_id = db.Column(db.String(32),db.ForeignKey('caregiver_handoffs.id'))
    created_at = db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow,onupdate=utcnow)
