import os
import sqlite3

DATABASE = "database/olumira.db"

os.makedirs("database", exist_ok=True)


def get_connection():
	connection = sqlite3.connect(DATABASE)
	connection.row_factory = sqlite3.Row
	return connection


def initialize_database():
	connection = get_connection()

	connection.execute("""
		CREATE TABLE IF NOT EXISTS routines (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			category TEXT NOT NULL,
			completed INTEGER DEFAULT 0
		)
	""")

	connection.execute("""
		CREATE TABLE IF NOT EXISTS observations (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			activity TEXT NOT NULL,
			date TEXT NOT NULL,
			notes TEXT,
			mood TEXT,
			tags TEXT
		)
	""")

	connection.commit()
	connection.close()


def add_starter_routines():
	connection = get_connection()
	existing = connection.execute(
		"SELECT COUNT(*) FROM routines"
	).fetchone()[0]

	if existing == 0:
		starter_routines = [
			("Wake up", "Morning"),
			("Brush teeth", "Morning"),
			("Get dressed", "Morning"),
			("Eat breakfast", "Morning"),
			("Pack backpack", "Morning"),
		]

		connection.executemany("""
			INSERT INTO routines (name, category)
			VALUES (?, ?)
		""", starter_routines)
		connection.commit()

	connection.close()
