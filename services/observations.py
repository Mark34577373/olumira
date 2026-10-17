from services.database import get_connection

MAX_OBSERVATIONS = 300


def add_observation(owner_id, activity, date, notes, mood, tags):
	"""Returns the new id, or None if the entry was invalid or the limit was reached."""
	activity = (activity or "").strip()[:120]
	date = (date or "").strip()[:10]
	notes = (notes or "").strip()[:2000]
	mood = (mood or "").strip()[:20]
	tags = (tags or "").strip()[:120]

	if not activity or not date:
		return None

	connection = get_connection()

	try:
		count = connection.execute("""
			SELECT COUNT(*) FROM observations WHERE owner_id = ?
		""", (owner_id,)).fetchone()[0]
		if count >= MAX_OBSERVATIONS:
			return None

		cursor = connection.execute("""
			INSERT INTO observations (owner_id, activity, date, notes, mood, tags)
			VALUES (?, ?, ?, ?, ?, ?)
		""", (owner_id, activity, date, notes, mood, tags))
		connection.commit()
		return cursor.lastrowid
	finally:
		connection.close()


def get_observations(owner_id, limit=None):
	connection = get_connection()

	try:
		query = """
			SELECT *
			FROM observations
			WHERE owner_id = ?
			ORDER BY date DESC, id DESC
		"""
		params = [owner_id]

		if limit:
			query += " LIMIT ?"
			params.append(limit)

		return connection.execute(query, params).fetchall()
	finally:
		connection.close()