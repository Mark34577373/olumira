from services.database import get_connection, today_string

MAX_ROUTINES = 40

ROUTINE_TEMPLATES = {
	"Morning": ["Wake up", "Brush teeth", "Get dressed", "Eat breakfast", "Pack backpack"],
	"Meals": ["Wash hands", "Eat lunch", "Eat dinner", "Drink water"],
	"Bedtime": ["Bath or wash up", "Put on pajamas", "Brush teeth", "Read a book", "Lights out"],
}


def _clean(name, category):
	name = (name or "").strip()[:80]
	category = (category or "").strip()[:40] or "General"
	return name, category


def _count(connection, owner_id):
	return connection.execute(
		"SELECT COUNT(*) FROM routines WHERE owner_id = ?", (owner_id,)
	).fetchone()[0]


def get_routines(owner_id):
	connection = get_connection()

	try:
		return connection.execute("""
			SELECT r.id, r.name, r.category,
				CASE WHEN c.routine_id IS NULL THEN 0 ELSE 1 END AS completed
			FROM routines r
			LEFT JOIN routine_completions c
				ON c.routine_id = r.id AND c.completion_date = ?
			WHERE r.owner_id = ?
			ORDER BY r.id
		""", (today_string(), owner_id)).fetchall()
	finally:
		connection.close()


def group_by_category(routines):
	groups = {}
	for routine in routines:
		groups.setdefault(routine["category"], []).append(routine)
	return groups


def summarize_progress(routines):
	total = len(routines)
	completed = sum(routine["completed"] for routine in routines)
	percent = round((completed / total) * 100) if total else 0
	return completed, total, percent


def toggle_routine(owner_id, routine_id):
	connection = get_connection()
	today = today_string()

	try:
		owned = connection.execute("""
			SELECT 1 FROM routines WHERE id = ? AND owner_id = ?
		""", (routine_id, owner_id)).fetchone()
		if not owned:
			return False

		done = connection.execute("""
			SELECT 1 FROM routine_completions
			WHERE routine_id = ? AND completion_date = ?
		""", (routine_id, today)).fetchone()

		if done:
			connection.execute("""
				DELETE FROM routine_completions
				WHERE routine_id = ? AND completion_date = ?
			""", (routine_id, today))
		else:
			connection.execute("""
				INSERT INTO routine_completions (routine_id, completion_date)
				VALUES (?, ?)
			""", (routine_id, today))

		connection.commit()
		return True
	finally:
		connection.close()


def add_routine(owner_id, name, category):
	"""Returns "ok", "invalid", or "limit"."""
	name, category = _clean(name, category)
	if not name:
		return "invalid"

	connection = get_connection()

	try:
		if _count(connection, owner_id) >= MAX_ROUTINES:
			return "limit"

		connection.execute("""
			INSERT INTO routines (owner_id, name, category) VALUES (?, ?, ?)
		""", (owner_id, name, category))
		connection.commit()
		return "ok"
	finally:
		connection.close()


def update_routine(owner_id, routine_id, name, category):
	"""Returns "ok", "invalid", or "missing"."""
	name, category = _clean(name, category)
	if not name:
		return "invalid"

	connection = get_connection()

	try:
		result = connection.execute("""
			UPDATE routines SET name = ?, category = ?
			WHERE id = ? AND owner_id = ?
		""", (name, category, routine_id, owner_id))
		connection.commit()
		return "ok" if result.rowcount == 1 else "missing"
	finally:
		connection.close()


def delete_routine(owner_id, routine_id):
	connection = get_connection()

	try:
		result = connection.execute("""
			DELETE FROM routines WHERE id = ? AND owner_id = ?
		""", (routine_id, owner_id))
		connection.commit()
		return result.rowcount == 1
	finally:
		connection.close()


def add_template(owner_id, template_name):
	"""Returns "ok", "invalid", or "limit". Skips routines that already exist."""
	names = ROUTINE_TEMPLATES.get(template_name)
	if names is None:
		return "invalid"

	connection = get_connection()

	try:
		existing = {
			row["name"]
			for row in connection.execute("""
				SELECT name FROM routines WHERE owner_id = ? AND category = ?
			""", (owner_id, template_name))
		}
		new_names = [name for name in names if name not in existing]

		if _count(connection, owner_id) + len(new_names) > MAX_ROUTINES:
			return "limit"

		connection.executemany("""
			INSERT INTO routines (owner_id, name, category) VALUES (?, ?, ?)
		""", [(owner_id, name, template_name) for name in new_names])
		connection.commit()
		return "ok"
	finally:
		connection.close()