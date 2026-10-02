from services.database import get_connection


def add_observation(activity, date, notes, mood, tags):
	connection = get_connection()

	try:
		cursor = connection.execute("""
			INSERT INTO observations (activity, date, notes, mood, tags)
			VALUES (?, ?, ?, ?, ?)
		""", (activity, date, notes, mood, tags))
		connection.commit()
		return cursor.lastrowid
	finally:
		connection.close()


def get_observations():
	connection = get_connection()

	try:
		return connection.execute("""
			SELECT *
			FROM observations
			ORDER BY date DESC, id DESC
		""").fetchall()
	finally:
		connection.close()
