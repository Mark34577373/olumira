from services.database import get_connection


def get_routines():
	connection = get_connection()
	routines = connection.execute("""
		SELECT *
		FROM routines
		ORDER BY id
	""").fetchall()
	connection.close()
	return routines


def get_progress():
	connection = get_connection()

	total = connection.execute("""
		SELECT COUNT(*) FROM routines
	""").fetchone()[0]

	completed = connection.execute("""
		SELECT COUNT(*) FROM routines
		WHERE completed = 1
	""").fetchone()[0]

	connection.close()

	if total == 0:
		return 0

	return round((completed / total) * 100)


def toggle_routine(routine_id):
	connection = get_connection()

	try:
		result = connection.execute("""
			UPDATE routines
			SET completed = CASE WHEN completed = 1 THEN 0 ELSE 1 END
			WHERE id = ?
		""", (routine_id,))
		connection.commit()
		return result.rowcount == 1
	finally:
		connection.close()
