"""Separate caregiver configuration and communication use; shared authorization."""

import uuid
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
    jsonify,
)
from olumira.content import COMMUNICATION_OPTIONS
from services import communication as boards
from services.workspaces import require

bp = Blueprint("communication", __name__)


@bp.get("/communication")
def communication():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        abort(400)
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    state = request.args.get("status", "active")
    entries, cards, total, categories = boards.library(query, category, state, page)
    return render_template(
        "communication.html",
        boards=entries,
        cards=cards,
        total=total,
        categories=categories,
        query=query,
        category=category,
        state=state,
        page=page,
        templates=boards.TEMPLATES,
        new_key=uuid.uuid4,
    )


@bp.get("/communication/quick")
def quick_choices():
    return render_template(
        "communication/quick.html",
        communication_categories=("Needs", "Activities"),
        communication_options=COMMUNICATION_OPTIONS,
    )


def editor(values, board=None, error=None, status=200):
    return (
        render_template(
            "communication/editor.html",
            values=values,
            board=board,
            error=error,
            symbols=boards.SYMBOLS,
            colors=boards.COLORS,
        ),
        status,
    )


def draft_action(values):
    action = request.form.get("editor_action")
    if not action:
        return False
    cards = values["cards"]
    if action == "add":
        if len(cards) >= 48:
            raise boards.InvalidCommunication("A board can have up to 48 cards.")
        cards.append(
            dict(id="", label="", spoken_text="", symbol="water", color="sage")
        )
    elif action == "preview":
        return "preview"
    else:
        try:
            direction, index = action.split(":")
            index = int(index)
        except (ValueError, TypeError):
            abort(400)
        if direction not in {"up", "down", "remove", "copy"} or not 0 <= index < len(
            cards
        ):
            abort(400)
        if direction == "remove":
            cards.pop(index)
        elif direction == "copy":
            if len(cards) >= 48:
                raise boards.InvalidCommunication("A board can have up to 48 cards.")
            cards.insert(index + 1, dict(cards[index], id=""))
        else:
            target = index + (-1 if direction == "up" else 1)
            if 0 <= target < len(cards):
                cards[index], cards[target] = cards[target], cards[index]
    return True


@bp.route("/communication/new", methods=["GET", "POST"])
@bp.route("/communication/<board_id>/edit", methods=["GET", "POST"])
def board_editor(board_id=None):
    require("communication.manage")
    board = boards.find(board_id, "communication.manage") if board_id else None
    if board and board.archived_at:
        abort(409, description="Restore the board before editing it.")
    values = boards.draft(board)
    if not board and request.args.get("template"):
        values = boards.template_draft(request.args["template"])
    if request.method == "POST":
        if request.form.get("scope_workspace") != g.workspace_id:
            abort(
                409,
                description="Your workspace changed. Reopen the editor before saving.",
            )
        try:
            values = boards.from_form(request.form)
            action = draft_action(values)
            if action:
                return editor(values, board)
            identity, profile_id = boards.save(values, board_id)
        except boards.InvalidCommunication as error:
            return editor(
                values,
                board,
                str(error),
                409 if isinstance(error, boards.CommunicationConflict) else 422,
            )
        session["profile_id"] = profile_id
        flash("Board saved. Your communication view is ready.", "success")
        return redirect(url_for("communication.board_view", board_id=identity))
    return editor(values, board)


@bp.get("/communication/<board_id>")
def board_view(board_id):
    board = boards.find(board_id)
    return render_template(
        "communication/board.html",
        board=board,
        cards=boards.cards_for(board.id),
        phrases=boards.phrases(),
        creation_key=uuid.uuid4().hex,
    )


@bp.get("/communication/<board_id>/state")
def board_state(board_id):
    from flask import jsonify

    board = boards.find(board_id)
    if board.archived_at:
        abort(409)
    return jsonify(version=board.version)


@bp.post("/communication/<board_id>/manage/<action>")
def board_action(board_id, action):
    try:
        if action == "duplicate":
            identity, profile_id = boards.duplicate(board_id, request.form)
            session["profile_id"] = profile_id
            flash("Board copied with fresh cards.", "success")
            return redirect(url_for("communication.board_editor", board_id=identity))
        if action not in {"archive", "restore"}:
            abort(400)
        boards.archive(board_id, request.form.get("version"), action == "restore")
    except boards.InvalidCommunication as error:
        return (
            render_template(
                "error.html", code=409, heading="Review this board", message=str(error)
            ),
            409,
        )
    flash("Board updated. Its cards are preserved.", "success")
    return redirect(url_for("communication.communication"))


@bp.route("/communication/phrases", methods=["GET", "POST"])
@bp.route("/communication/phrases/<phrase_id>/edit", methods=["GET", "POST"])
def phrase_editor(phrase_id=None):
    require("communication.manage")
    item = boards.find_phrase(phrase_id) if phrase_id else None
    values = dict(
        label=item.label if item else "",
        text=item.text if item else "",
        version=item.version if item else "",
        creation_key=uuid.uuid4().hex,
    )
    error = None
    status = 200
    if request.method == "POST":
        if request.form.get("scope_workspace") != g.workspace_id or request.form.get(
            "scope_profile", ""
        ) != (g.profile_id or ""):
            if request.accept_mimetypes.best == "application/json":
                return (
                    jsonify(
                        error="Your workspace or profile changed. Reopen the board before saving."
                    ),
                    409,
                )
            abort(
                409,
                description="Your workspace or profile changed. Reopen the phrase editor before saving.",
            )
        values = {key: request.form.get(key, "") for key in values}
        try:
            identity = boards.save_phrase(values, phrase_id)
        except boards.InvalidCommunication as exc:
            error, status = str(exc), (
                409 if isinstance(exc, boards.CommunicationConflict) else 422
            )
        else:
            if request.accept_mimetypes.best == "application/json":
                saved = boards.find_phrase(identity)
                return jsonify(id=saved.id, label=saved.label, text=saved.text), 201
            flash("Phrase saved. It is available on this profile’s boards.", "success")
            return redirect(url_for("communication.phrase_editor"))
    if error and request.accept_mimetypes.best == "application/json":
        return jsonify(error=error), status
    return (
        render_template(
            "communication/phrases.html",
            item=item,
            values=values,
            error=error,
            phrases=boards.phrases(),
            archived=boards.phrases(True),
        ),
        status,
    )


@bp.post("/communication/phrases/<phrase_id>/<action>")
def phrase_action(phrase_id, action):
    try:
        boards.phrase_action(phrase_id, action, request.form.get("version"))
    except boards.InvalidCommunication as error:
        return (
            render_template(
                "error.html", code=409, heading="Review this phrase", message=str(error)
            ),
            409,
        )
    return redirect(url_for("communication.phrase_editor"))
