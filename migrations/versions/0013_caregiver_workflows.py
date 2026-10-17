"""Additive profile personalization/caregiver workflows; no legacy rewrites."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TABLE caregiver_tasks (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\ttitle VARCHAR(120) NOT NULL, \n\tdescription VARCHAR(2000) NOT NULL, \n\tassigned_to VARCHAR(32), \n\troutine_id INTEGER, \n\tdue_at DATETIME, \n\ttimezone VARCHAR(64) NOT NULL, \n\tpriority VARCHAR(8) NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcompleted_by VARCHAR(32), \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tcompleted_at DATETIME, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_care_task_status CHECK (status IN ('todo','in_progress','completed','canceled')), \n\tCONSTRAINT ck_care_task_priority CHECK (priority IN ('low','normal','high')), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(assigned_to) REFERENCES users (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(completed_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_tasks_scope_due ON caregiver_tasks (workspace_id, profile_id, due_at)"
        )
        op.execute(
            "CREATE TABLE caregiver_handoffs (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tsummary VARCHAR(2000) NOT NULL, \n\trecipient_kind VARCHAR(8) NOT NULL, \n\troutine_id INTEGER, \n\tobservation_id INTEGER, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(observation_id) REFERENCES observations (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_handoffs_scope_created ON caregiver_handoffs (workspace_id, profile_id, created_at)"
        )
        op.execute(
            "CREATE TABLE handoff_recipients (\n\thandoff_id VARCHAR(32) NOT NULL, \n\tuser_id VARCHAR(32) NOT NULL, \n\tacknowledged_at DATETIME, \n\tPRIMARY KEY (handoff_id, user_id), \n\tFOREIGN KEY(handoff_id) REFERENCES caregiver_handoffs (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE TABLE handoff_tasks (\n\thandoff_id VARCHAR(32) NOT NULL, \n\ttask_id VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (handoff_id, task_id), \n\tFOREIGN KEY(handoff_id) REFERENCES caregiver_handoffs (id), \n\tFOREIGN KEY(task_id) REFERENCES caregiver_tasks (id)\n)"
        )
        op.execute(
            "CREATE TRIGGER caregiver_tasks_profile_insert BEFORE INSERT ON caregiver_tasks WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER caregiver_tasks_profile_update BEFORE UPDATE ON caregiver_tasks WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER caregiver_handoffs_profile_insert BEFORE INSERT ON caregiver_handoffs WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER caregiver_handoffs_profile_update BEFORE UPDATE ON caregiver_handoffs WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE TABLE caregiver_tasks (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\ttitle VARCHAR(120) NOT NULL, \n\tdescription VARCHAR(2000) NOT NULL, \n\tassigned_to VARCHAR(32), \n\troutine_id INTEGER, \n\tdue_at TIMESTAMP WITH TIME ZONE, \n\ttimezone VARCHAR(64) NOT NULL, \n\tpriority VARCHAR(8) NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcompleted_by VARCHAR(32), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_care_task_status CHECK (status IN ('todo','in_progress','completed','canceled')), \n\tCONSTRAINT ck_care_task_priority CHECK (priority IN ('low','normal','high')), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(assigned_to) REFERENCES users (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(completed_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_tasks_scope_due ON caregiver_tasks (workspace_id, profile_id, due_at)"
        )
        op.execute(
            "CREATE TABLE caregiver_handoffs (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tsummary VARCHAR(2000) NOT NULL, \n\trecipient_kind VARCHAR(8) NOT NULL, \n\troutine_id INTEGER, \n\tobservation_id INTEGER, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(observation_id) REFERENCES observations (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_handoffs_scope_created ON caregiver_handoffs (workspace_id, profile_id, created_at)"
        )
        op.execute(
            "CREATE TABLE handoff_recipients (\n\thandoff_id VARCHAR(32) NOT NULL, \n\tuser_id VARCHAR(32) NOT NULL, \n\tacknowledged_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (handoff_id, user_id), \n\tFOREIGN KEY(handoff_id) REFERENCES caregiver_handoffs (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE TABLE handoff_tasks (\n\thandoff_id VARCHAR(32) NOT NULL, \n\ttask_id VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (handoff_id, task_id), \n\tFOREIGN KEY(handoff_id) REFERENCES caregiver_handoffs (id), \n\tFOREIGN KEY(task_id) REFERENCES caregiver_tasks (id)\n)"
        )
        op.execute(
            "CREATE TRIGGER caregiver_tasks_profile_scope BEFORE INSERT OR UPDATE ON caregiver_tasks FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
        )
        op.execute(
            "CREATE TRIGGER caregiver_handoffs_profile_scope BEFORE INSERT OR UPDATE ON caregiver_handoffs FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER task_routine_insert BEFORE INSERT ON caregiver_tasks WHEN NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND (r.profile_id=NEW.profile_id OR (r.profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER task_routine_update BEFORE UPDATE ON caregiver_tasks WHEN NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND (r.profile_id=NEW.profile_id OR (r.profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION task_routine_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND (r.profile_id=NEW.profile_id OR (r.profile_id IS NULL AND NEW.profile_id IS NULL))) THEN RAISE EXCEPTION 'Care reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER task_routine BEFORE INSERT OR UPDATE ON caregiver_tasks FOR EACH ROW EXECUTE FUNCTION task_routine_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER handoff_links_insert BEFORE INSERT ON caregiver_handoffs WHEN (NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND (r.profile_id=NEW.profile_id OR (r.profile_id IS NULL AND NEW.profile_id IS NULL)))) OR (NEW.observation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.id=NEW.observation_id AND o.workspace_id=NEW.workspace_id AND (o.profile_id=NEW.profile_id OR (o.profile_id IS NULL AND NEW.profile_id IS NULL)))) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER handoff_links_update BEFORE UPDATE ON caregiver_handoffs WHEN (NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND (r.profile_id=NEW.profile_id OR (r.profile_id IS NULL AND NEW.profile_id IS NULL)))) OR (NEW.observation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.id=NEW.observation_id AND o.workspace_id=NEW.workspace_id AND (o.profile_id=NEW.profile_id OR (o.profile_id IS NULL AND NEW.profile_id IS NULL)))) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION handoff_links_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND (r.profile_id=NEW.profile_id OR (r.profile_id IS NULL AND NEW.profile_id IS NULL)))) OR (NEW.observation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.id=NEW.observation_id AND o.workspace_id=NEW.workspace_id AND (o.profile_id=NEW.profile_id OR (o.profile_id IS NULL AND NEW.profile_id IS NULL)))) THEN RAISE EXCEPTION 'Care reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER handoff_links BEFORE INSERT OR UPDATE ON caregiver_handoffs FOR EACH ROW EXECUTE FUNCTION handoff_links_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER handoff_task_scope_insert BEFORE INSERT ON handoff_tasks WHEN NOT EXISTS (SELECT 1 FROM caregiver_handoffs h JOIN caregiver_tasks t ON t.workspace_id=h.workspace_id AND (t.profile_id=h.profile_id OR (t.profile_id IS NULL AND h.profile_id IS NULL)) WHERE h.id=NEW.handoff_id AND t.id=NEW.task_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER handoff_task_scope_update BEFORE UPDATE ON handoff_tasks WHEN NOT EXISTS (SELECT 1 FROM caregiver_handoffs h JOIN caregiver_tasks t ON t.workspace_id=h.workspace_id AND (t.profile_id=h.profile_id OR (t.profile_id IS NULL AND h.profile_id IS NULL)) WHERE h.id=NEW.handoff_id AND t.id=NEW.task_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION handoff_task_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM caregiver_handoffs h JOIN caregiver_tasks t ON t.workspace_id=h.workspace_id AND (t.profile_id=h.profile_id OR (t.profile_id IS NULL AND h.profile_id IS NULL)) WHERE h.id=NEW.handoff_id AND t.id=NEW.task_id) THEN RAISE EXCEPTION 'Care reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER handoff_task_scope BEFORE INSERT OR UPDATE ON handoff_tasks FOR EACH ROW EXECUTE FUNCTION handoff_task_scope_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER recipient_membership_insert BEFORE INSERT ON handoff_recipients WHEN NOT EXISTS (SELECT 1 FROM caregiver_handoffs h JOIN workspace_memberships m ON m.workspace_id=h.workspace_id WHERE h.id=NEW.handoff_id AND m.user_id=NEW.user_id AND m.status='active' AND m.role IN ('owner','caregiver')) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER recipient_membership_update BEFORE UPDATE ON handoff_recipients WHEN NOT EXISTS (SELECT 1 FROM caregiver_handoffs h JOIN workspace_memberships m ON m.workspace_id=h.workspace_id WHERE h.id=NEW.handoff_id AND m.user_id=NEW.user_id AND m.status='active' AND m.role IN ('owner','caregiver')) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION recipient_membership_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM caregiver_handoffs h JOIN workspace_memberships m ON m.workspace_id=h.workspace_id WHERE h.id=NEW.handoff_id AND m.user_id=NEW.user_id AND m.status='active' AND m.role IN ('owner','caregiver')) THEN RAISE EXCEPTION 'Care reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER recipient_membership BEFORE INSERT OR UPDATE ON handoff_recipients FOR EACH ROW EXECUTE FUNCTION recipient_membership_guard()"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER handoff_immutable BEFORE UPDATE ON caregiver_handoffs WHEN 1=1 BEGIN SELECT RAISE(ABORT, 'Care history is immutable'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION handoff_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TRUE THEN RAISE EXCEPTION 'Care history is immutable'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER handoff_immutable BEFORE UPDATE ON caregiver_handoffs FOR EACH ROW EXECUTE FUNCTION handoff_immutable_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER ack_immutable BEFORE UPDATE ON handoff_recipients WHEN OLD.acknowledged_at IS NOT NULL OR NEW.handoff_id IS NOT OLD.handoff_id OR NEW.user_id IS NOT OLD.user_id BEGIN SELECT RAISE(ABORT, 'Care history is immutable'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION ack_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.acknowledged_at IS NOT NULL OR NEW.handoff_id IS DISTINCT FROM OLD.handoff_id OR NEW.user_id IS DISTINCT FROM OLD.user_id THEN RAISE EXCEPTION 'Care history is immutable'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER ack_immutable BEFORE UPDATE ON handoff_recipients FOR EACH ROW EXECUTE FUNCTION ack_immutable_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER task_scope_immutable BEFORE UPDATE ON caregiver_tasks WHEN NEW.workspace_id IS NOT OLD.workspace_id OR NEW.profile_id IS NOT OLD.profile_id BEGIN SELECT RAISE(ABORT, 'Care history is immutable'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION task_scope_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.profile_id IS DISTINCT FROM OLD.profile_id THEN RAISE EXCEPTION 'Care history is immutable'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER task_scope_immutable BEFORE UPDATE ON caregiver_tasks FOR EACH ROW EXECUTE FUNCTION task_scope_immutable_guard()"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER task_assignee_insert BEFORE INSERT ON caregiver_tasks WHEN NEW.assigned_to IS NOT NULL AND NOT EXISTS (SELECT 1 FROM workspace_memberships m WHERE m.user_id=NEW.assigned_to AND m.workspace_id=NEW.workspace_id AND m.status='active' AND m.role IN ('owner','caregiver')) BEGIN SELECT RAISE(ABORT, 'Assignee must be an active caregiver'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER task_assignee_update BEFORE UPDATE ON caregiver_tasks WHEN NEW.assigned_to IS NOT OLD.assigned_to AND NEW.assigned_to IS NOT NULL AND NOT EXISTS (SELECT 1 FROM workspace_memberships m WHERE m.user_id=NEW.assigned_to AND m.workspace_id=NEW.workspace_id AND m.status='active' AND m.role IN ('owner','caregiver')) BEGIN SELECT RAISE(ABORT, 'Assignee must be an active caregiver'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION task_assignee_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.assigned_to IS NOT NULL AND (TG_OP='INSERT' OR NEW.assigned_to IS DISTINCT FROM OLD.assigned_to) AND NOT EXISTS (SELECT 1 FROM workspace_memberships m WHERE m.user_id=NEW.assigned_to AND m.workspace_id=NEW.workspace_id AND m.status='active' AND m.role IN ('owner','caregiver')) THEN RAISE EXCEPTION 'Assignee must be an active caregiver'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER task_assignee BEFORE INSERT OR UPDATE ON caregiver_tasks FOR EACH ROW EXECUTE FUNCTION task_assignee_guard()"
        )


def downgrade():
    raise RuntimeError(
        "Restore a reviewed backup; care history/preferences are not automatically deleted."
    )
