"""Models mirror the legacy schema, including nullable legacy ownership."""
from .extensions import db


class Owner(db.Model):
    __tablename__ = 'owners'
    id = db.Column(db.Text, primary_key=True)
    created_at = db.Column(db.Text, nullable=False)


class Routine(db.Model):
    __tablename__ = 'routines'
    __table_args__ = (db.Index('idx_routines_owner', 'owner_id'), {'sqlite_autoincrement': True})
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Text, nullable=True)
    name = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False)


class Observation(db.Model):
    __tablename__ = 'observations'
    __table_args__ = (db.Index('idx_observations_owner', 'owner_id'), {'sqlite_autoincrement': True})
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Text, nullable=True)
    activity = db.Column(db.Text, nullable=False)
    date = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    mood = db.Column(db.Text)
    tags = db.Column(db.Text)


class RoutineCompletion(db.Model):
    __tablename__ = 'routine_completions'
    routine_id = db.Column(db.Integer, db.ForeignKey('routines.id', ondelete='CASCADE'), primary_key=True)
    completion_date = db.Column(db.Text, primary_key=True)
