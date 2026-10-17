"""Private shared boards and explicit saved phrases; no utterance logging."""

import re
import uuid
from flask import abort, g
from flask_login import current_user
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    CommunicationBoard as Board,
    CommunicationCard as Card,
    SavedCommunicationPhrase as Phrase,
    CareProfile,
    utcnow,
)
from services.workspaces import require, scope, care_audit
from services.database import transaction

COLORS = {
    "sage": "Sage green",
    "peach": "Warm peach",
    "lavender": "Soft lavender",
    "sky": "Sky blue",
}
SYMBOLS = {
    "water": ("Water", "Basic needs"),
    "food": ("Food", "Food & drinks"),
    "bathroom": ("Bathroom", "Basic needs"),
    "help": ("Help", "Requests"),
    "break": ("Break", "Requests"),
    "rest": ("Rest", "Daily routines"),
    "happy": ("Happy", "Feelings"),
    "sad": ("Sad", "Feelings"),
    "tired": ("Tired", "Feelings"),
    "excited": ("Excited", "Feelings"),
    "frustrated": ("Frustrated", "Feelings"),
    "calm": ("Calm", "Feelings"),
    "read": ("Read", "Activities"),
    "play": ("Play", "Activities"),
    "walk": ("Walk", "Activities"),
    "music": ("Music", "Activities"),
    "draw": ("Draw", "Activities"),
    "eat": ("Eat", "Food & drinks"),
    "person": ("I / person", "People"),
    "want": ("Want", "Requests"),
    "yes": ("Yes", "Yes & no"),
    "no": ("No", "Yes & no"),
    "home": ("Home", "Places"),
    "school": ("School", "Places"),
    "family": ("Family", "People"),
    "outside": ("Outside", "Places"),
    "thanks": ("Thank you", "Requests"),
    "bag": ("Bag", "Daily routines"),
}
TEMPLATES = {
    "needs": dict(
        title="Basic Needs",
        category="Basic needs",
        symbols=["water", "food", "bathroom", "help", "break", "rest"],
    ),
    "feelings": dict(
        title="Feelings",
        category="Feelings",
        symbols=["happy", "sad", "tired", "excited", "frustrated", "calm"],
    ),
    "activities": dict(
        title="Daily Activities",
        category="Activities",
        symbols=["read", "play", "walk", "music", "draw", "eat"],
    ),
    "words": dict(
        title="My words",
        category="Everyday words",
        symbols=["person", "want", "water", "help", "yes", "no"],
    ),
}
SPOKEN = {
    "person": ("I", "I"),
    "want": ("want", "want"),
    "water": ("water", "water"),
    "help": ("Help", "I need help."),
    "break": ("Break", "I want a break."),
    "rest": ("Rest", "I want to rest."),
    "thanks": ("Thank you", "Thank you."),
}


class InvalidCommunication(ValueError):
    pass


class CommunicationConflict(InvalidCommunication):
    pass


def key(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{32}", value):
        abort(400, description="Reload the form before trying again.")
    return value


def profile(value):
    result = value or None
    if result and not db.session.scalar(
        select(CareProfile.id).where(
            CareProfile.id == result, CareProfile.workspace_id == g.workspace_id
        )
    ):
        abort(404)
    return result


def find(board_id, permission="communication.view"):
    require(permission)
    board = db.session.scalar(
        select(Board)
        .where(Board.id == board_id, scope(Board, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not board:
        abort(404)
    return board


def cards_for(board_id):
    return list(
        db.session.scalars(
            select(Card)
            .where(Card.board_id == board_id)
            .order_by(Card.position)
            .execution_options(populate_existing=True)
        )
    )


def draft(board=None):
    return dict(
        title=board.title if board else "",
        description=board.description if board else "",
        category=board.category if board else "Basic needs",
        layout=board.layout if board else "adaptive",
        profile_id=(board.profile_id if board else g.profile_id) or "",
        version=board.version if board else "",
        creation_key=uuid.uuid4().hex,
        cards=(
            [
                dict(
                    id=c.id,
                    label=c.label,
                    spoken_text=c.spoken_text,
                    symbol=c.symbol,
                    color=c.color,
                )
                for c in cards_for(board.id)
            ]
            if board
            else []
        ),
    )


def template_draft(name):
    choice = TEMPLATES.get(name)
    if not choice:
        abort(404)
    values = draft()
    values.update(title=choice["title"], category=choice["category"])
    values["cards"] = [
        dict(
            id="",
            label=SPOKEN.get(symbol, (SYMBOLS[symbol][0],) * 2)[0],
            spoken_text=SPOKEN.get(symbol, (SYMBOLS[symbol][0],) * 2)[1],
            symbol=symbol,
            color=list(COLORS)[i % 4],
        )
        for i, symbol in enumerate(choice["symbols"])
    ]
    return values


def from_form(form):
    values = {
        k: form.get(k, "").strip()
        for k in [
            "title",
            "description",
            "category",
            "layout",
            "profile_id",
            "version",
            "creation_key",
        ]
    }
    fields = ["id", "label", "spoken_text", "symbol", "color"]
    arrays = {k: form.getlist("card_" + k) for k in fields}
    if len({len(a) for a in arrays.values()}) != 1 or len(arrays["id"]) > 48:
        raise InvalidCommunication(
            "Keep up to 48 cards with complete card information."
        )
    values["cards"] = [
        {k: arrays[k][i].strip() for k in fields} for i in range(len(arrays["id"]))
    ]
    return values


def validate(values):
    clean = {
        k: str(values.get(k, "")).strip()
        for k in ["title", "description", "category", "layout"]
    }
    if (
        not 1 <= len(clean["title"]) <= 80
        or len(clean["description"]) > 500
        or not 1 <= len(clean["category"]) <= 40
    ):
        raise InvalidCommunication(
            "Use a board name of 1–80 characters, a category up to 40, and a description up to 500."
        )
    if clean["layout"] not in {"2", "3", "4", "adaptive"}:
        raise InvalidCommunication("Choose one of the available layouts.")
    clean["profile_id"] = profile(values.get("profile_id"))
    cards = values.get("cards", [])
    if not isinstance(cards, list) or len(cards) > 48:
        raise InvalidCommunication("A board can have up to 48 cards.")
    seen = set()
    for card in cards:
        if (
            not isinstance(card, dict)
            or not 1 <= len(card.get("label", "")) <= 60
            or not 1 <= len(card.get("spoken_text", "")) <= 200
            or card.get("symbol") not in SYMBOLS
            or card.get("color") not in COLORS
        ):
            raise InvalidCommunication(
                "Each card needs a label up to 60 characters, spoken text up to 200, and an available symbol and color."
            )
        if card.get("id"):
            if card["id"] in seen:
                raise InvalidCommunication(
                    "A card was included twice. Duplicate it using the card control instead."
                )
            seen.add(card["id"])
    return clean, cards


def version(obj, value):
    if str(value) != str(obj.version):
        raise CommunicationConflict(
            "Another caregiver changed this record. Your draft is retained. Open the latest saved version and review both before saving again."
        )


def capacity(profile_id, exclude=None):
    count = db.session.scalar(
        select(func.count())
        .select_from(Board)
        .where(
            Board.workspace_id == g.workspace_id,
            Board.profile_id == profile_id,
            Board.archived_at.is_(None),
            Board.id != exclude if exclude else True,
        )
    )
    if count >= 40:
        raise InvalidCommunication(
            "This profile has 40 active boards. Archive a board before adding another."
        )


def save(values, board_id=None):
    with transaction():
        require("communication.manage", lock=True)
        clean, items = validate(values)
        board = find(board_id, "communication.manage") if board_id else None
        if board:
            version(board, values.get("version"))
            if board.archived_at:
                raise InvalidCommunication("Restore this board before editing it.")
            existing = {c.id: c for c in cards_for(board.id)}
        else:
            identity = key(values.get("creation_key"))
            previous = db.session.get(Board, identity)
            if previous:
                if (
                    previous.workspace_id,
                    previous.profile_id,
                    previous.created_by,
                ) != (g.workspace_id, clean["profile_id"], current_user.id):
                    abort(404)
                return previous.id, previous.profile_id
            existing = {}
            capacity(clean["profile_id"])
            board = Board(
                id=identity,
                workspace_id=g.workspace_id,
                created_by=current_user.id,
                version=1,
                **clean
            )
            db.session.add(board)
            db.session.flush()
        if any(c.get("id") and c["id"] not in existing for c in items):
            abort(404)
        if board.profile_id != clean["profile_id"]:
            capacity(clean["profile_id"], board.id)
        for k, v in clean.items():
            setattr(board, k, v)
        if board_id:
            board.version += 1
        # Move out of the unique position range before deletes/reordering.
        for i, c in enumerate(existing.values()):
            c.position = 1000 + i
        db.session.flush()
        kept = {c["id"] for c in items if c.get("id")}
        for cid, c in existing.items():
            if cid not in kept:
                db.session.delete(c)
        db.session.flush()
        for position, item in enumerate(items):
            c = existing.get(item.get("id"))
            if c is None:
                c = Card(id=uuid.uuid4().hex, board_id=board.id)
                db.session.add(c)
            for k in ["label", "spoken_text", "symbol", "color"]:
                setattr(c, k, item[k])
            c.position = position
        care_audit("communication.board_saved", board.id)
        result = board.id, board.profile_id
    return result


def duplicate(board_id, values):
    # Acquire the same workspace lock before reading the source; save commits it.
    require("communication.manage", lock=True)
    source = find(board_id, "communication.manage")
    version(source, values.get("version"))
    data = draft(source)
    data.update(
        title=source.title[:73] + " (copy)",
        profile_id=values.get("profile_id", ""),
        creation_key=values.get("creation_key"),
    )
    for card in data["cards"]:
        card["id"] = ""
    return save(data)


def archive(board_id, expected, restore=False):
    with transaction():
        require("communication.manage", lock=True)
        board = find(board_id, "communication.manage")
        version(board, expected)
        if restore and board.archived_at:
            capacity(board.profile_id, board.id)
        board.archived_at = None if restore else utcnow()
        board.version += 1
        care_audit(
            (
                "communication.board_restored"
                if restore
                else "communication.board_archived"
            ),
            board.id,
        )


def library(query="", category="", state="active", page=1):
    require("communication.view")
    if (
        len(query) > 100
        or len(category) > 40
        or state not in {"active", "archived", "all"}
        or not 1 <= page <= 10000
    ):
        abort(400)
    base = select(Board).where(scope(Board, g.workspace_id))
    if state != "all":
        base = base.where(
            Board.archived_at.is_not(None)
            if state == "archived"
            else Board.archived_at.is_(None)
        )
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base = base.where(Board.title.ilike("%" + escaped + "%", escape="\\"))
    if category:
        base = base.where(Board.category == category)
    total = db.session.scalar(select(func.count()).select_from(base.subquery()))
    boards = list(
        db.session.scalars(
            base.order_by(Board.updated_at.desc(), Board.id)
            .offset((page - 1) * 18)
            .limit(18)
        )
    )
    ids = [b.id for b in boards]
    cards = {bid: [] for bid in ids}
    if ids:
        for card in db.session.scalars(
            select(Card).where(Card.board_id.in_(ids)).order_by(Card.position)
        ):
            cards[card.board_id].append(card)
    categories = list(
        db.session.scalars(
            select(Board.category)
            .where(scope(Board, g.workspace_id))
            .distinct()
            .order_by(Board.category)
            .limit(100)
        )
    )
    return boards, cards, total, categories


def phrases(archived=False):
    require("communication.view")
    return list(
        db.session.scalars(
            select(Phrase)
            .where(
                scope(Phrase, g.workspace_id),
                (
                    Phrase.archived_at.is_not(None)
                    if archived
                    else Phrase.archived_at.is_(None)
                ),
            )
            .order_by(
                Phrase.updated_at.desc() if archived else Phrase.position, Phrase.id
            )
            .limit(50)
        )
    )


def find_phrase(identity, permission="communication.manage"):
    require(permission)
    item = db.session.scalar(
        select(Phrase)
        .where(Phrase.id == identity, scope(Phrase, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not item:
        abort(404)
    return item


def phrase_capacity():
    if (
        db.session.scalar(
            select(func.count())
            .select_from(Phrase)
            .where(scope(Phrase, g.workspace_id), Phrase.archived_at.is_(None))
        )
        >= 50
    ):
        raise InvalidCommunication(
            "This profile has 50 active phrases. Archive one before adding another."
        )


def save_phrase(values, identity=None):
    label = (values.get("label") or "").strip()
    text = (values.get("text") or "").strip()
    if not 1 <= len(label) <= 60 or not 1 <= len(text) <= 1000:
        raise InvalidCommunication(
            "Use a phrase label of 1–60 characters and text of 1–1,000 characters."
        )
    with transaction():
        require("communication.manage", lock=True)
        if identity:
            item = find_phrase(identity)
            version(item, values.get("version"))
            if item.archived_at:
                raise InvalidCommunication("Restore this phrase before editing it.")
            item.label, item.text = label, text
            item.version += 1
        else:
            identity = key(values.get("creation_key"))
            existing = db.session.get(Phrase, identity)
            if existing:
                if (
                    existing.workspace_id,
                    existing.profile_id,
                    existing.created_by,
                ) != (g.workspace_id, g.profile_id, current_user.id):
                    abort(404)
                return existing.id
            phrase_capacity()
            last = db.session.scalar(
                select(func.max(Phrase.position)).where(scope(Phrase, g.workspace_id))
            )
            item = Phrase(
                id=identity,
                workspace_id=g.workspace_id,
                profile_id=g.profile_id,
                label=label,
                text=text,
                position=(last + 1 if last is not None else 0),
                version=1,
                created_by=current_user.id,
            )
            db.session.add(item)
        care_audit("communication.phrase_saved", identity)
    return identity


def phrase_action(identity, action, expected):
    if action not in {"up", "down", "archive", "restore"}:
        abort(400)
    with transaction():
        require("communication.manage", lock=True)
        item = find_phrase(identity)
        version(item, expected)
        if action in {"archive", "restore"}:
            if action == "restore" and item.archived_at:
                phrase_capacity()
            item.archived_at = None if action == "restore" else utcnow()
        else:
            if item.archived_at:
                raise InvalidCommunication("Restore this phrase before moving it.")
            ordered = phrases()
            index = next(i for i, p in enumerate(ordered) if p.id == identity)
            target = index + (-1 if action == "up" else 1)
            if not 0 <= target < len(ordered):
                return
            # Normalize order in the same transaction; touch affected versions.
            ordered[index], ordered[target] = ordered[target], ordered[index]
            for i, p in enumerate(ordered):
                if p.position != i:
                    p.position = i
                    p.version += 1
        item.version += 1
        care_audit("communication.phrase_" + action, identity)
