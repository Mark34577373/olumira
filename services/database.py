import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DATABASE = "database/olumira.db"
TIMEZONE = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Chicago"))

STARTER_ROUTINES = [
	("Wake up", "Morning"),
	("Brush teeth", "Morning"),
	("Get dressed", "Morning"),
	("Eat breakfast", "Morning"),
	("Pack backpack", "Morning"),
]

os.makedirs("database", exist_ok=True)


def now():
	return datetime.now(TIMEZONE)


def today_string():
	return now().date().isoformat()


def time_greeting():
	hour = now().hour
	if hour < 12:
		return "Good morning"
	if hour < 17:
		return "Good afternoon"
	return "Good evening"


def get_connection():
	connection = sqlite3.connect(DATABASE)
	connection.row_factory = sqlite3.Row
	connection.execute("PRAGMA foreign_keys = ON")
	return connection


def _add_column_if_missing(connection, table, column, definition):
	columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
	if column not in columns:
		connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database():
	connection = get_connection()

	try:
		connection.execute("""
			CREATE TABLE IF NOT EXISTS owners (
				id TEXT PRIMARY KEY,
				created_at TEXT NOT NULL
			)
		""")

		connection.execute("""
			CREATE TABLE IF NOT EXISTS routines (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				owner_id TEXT,
				name TEXT NOT NULL,
				category TEXT NOT NULL
			)
		""")

		connection.execute("""
			CREATE TABLE IF NOT EXISTS observations (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				owner_id TEXT,
				activity TEXT NOT NULL,
				date TEXT NOT NULL,
				notes TEXT,
				mood TEXT,
				tags TEXT
			)
		""")

		connection.execute("""
			CREATE TABLE IF NOT EXISTS routine_completions (
				routine_id INTEGER NOT NULL,
				completion_date TEXT NOT NULL,
				PRIMARY KEY (routine_id, completion_date),
				FOREIGN KEY (routine_id) REFERENCES routines(id) ON DELETE CASCADE
			)
		""")

		# Older databases were created without owner_id
		_add_column_if_missing(connection, "routines", "owner_id", "TEXT")
		_add_column_if_missing(connection, "observations", "owner_id", "TEXT")

		connection.execute(
			"CREATE INDEX IF NOT EXISTS idx_routines_owner ON routines(owner_id)"
		)
		connection.execute(
			"CREATE INDEX IF NOT EXISTS idx_observations_owner ON observations(owner_id)"
		)

		connection.commit()
	finally:
		connection.close()


def ensure_workspace(owner_id):
	"""Create a private workspace with starter routines the first time an owner is seen."""
	connection = get_connection()

	try:
		created = connection.execute("""
			INSERT OR IGNORE INTO owners (id, created_at) VALUES (?, ?)
		""", (owner_id, today_string())).rowcount == 1

		if created:
			connection.executemany("""
				INSERT INTO routines (owner_id, name, category) VALUES (?, ?, ?)
			""", [(owner_id, name, category) for name, category in STARTER_ROUTINES])

		connection.commit()
	finally:
		connection.close()


def purge_old_workspaces(days=30):
	"""Delete workspaces older than `days` so the demo database stays small."""
	cutoff = (now().date() - timedelta(days=days)).isoformat()
	connection = get_connection()

	try:
		old_owners = "SELECT id FROM owners WHERE created_at < ?"
		connection.execute(
			f"DELETE FROM observations WHERE owner_id IN ({old_owners})", (cutoff,)
		)
		connection.execute(
			f"DELETE FROM routines WHERE owner_id IN ({old_owners})", (cutoff,)
		)
		connection.execute("DELETE FROM owners WHERE created_at < ?", (cutoff,))
		connection.commit()
	finally:
		connection.close()