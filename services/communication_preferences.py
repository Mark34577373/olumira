"""Server-persisted profile choices; favorites reference existing content, never copy it."""

from types import SimpleNamespace
from flask import abort, g
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    CommunicationPreference as Preference,
    FavoriteCommunicationCard as FavoriteCard,
    FavoriteCommunicationPhrase as FavoritePhrase,
    CommunicationBoard as Board,
    CommunicationCard as Card,
    SavedCommunicationPhrase as Phrase,
)
from services.workspaces import require, scope, care_audit
from services.database import transaction
from services.communication import (
    InvalidCommunication,
    CommunicationConflict,
    version,
    find as find_board,
)

DEFAULTS = dict(
    card_size="medium",
    layout="board",
    text_position="below",
    show_text=True,
    show_symbols=True,
    speech_enabled=True,
    speech_rate="1",
    voice_id="",
    simplified=False,
    high_contrast=False,
    reduced_motion=False,
    default_board_id=None,
)
CHOICES = dict(
    card_size={"large", "medium", "compact"},
    layout={"board", "adaptive", "2", "3", "4"},
    text_position={"above", "below"},
    speech_rate={"0.8", "1", "1.15"},
)
BOOLS = [
    "show_text",
    "show_symbols",
    "speech_enabled",
    "simplified",
    "high_contrast",
    "reduced_motion",
]


def profile_required():
    if not g.profile_id:
        raise InvalidCommunication(
            "Select a care profile to personalize communication."
        )


def get():
    require("communication.view")
    row = (
        db.session.scalar(
            select(Preference)
            .where(scope(Preference, g.workspace_id))
            .execution_options(populate_existing=True)
        )
        if g.profile_id
        else None
    )
    return row or SimpleNamespace(**DEFAULTS, version=0)


def as_dict(pref=None):
    pref = pref or get()
    return {key: getattr(pref, key) for key in DEFAULTS} | dict(version=pref.version)


def locked():
    require("communication.manage", lock=True)
    profile_required()
    pref = db.session.scalar(
        select(Preference)
        .where(scope(Preference, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not pref:
        pref = Preference(
            profile_id=g.profile_id, workspace_id=g.workspace_id, version=0, **DEFAULTS
        )
        db.session.add(pref)
    return pref


def save(values):
    with transaction():
        pref = locked()
        version(pref, values.get("version"))
        clean = {key: values.get(key, "") for key in CHOICES}
        if any(clean[key] not in options for key, options in CHOICES.items()):
            raise InvalidCommunication(
                "Choose one of the available display and speech options."
            )
        clean.update(
            {key: values.get(key) in {"on", "true", "1", True} for key in BOOLS}
        )
        if not clean["show_text"] and not clean["show_symbols"]:
            raise InvalidCommunication("Keep either picture labels or symbols visible.")
        voice = (values.get("voice_id") or "").strip()
        if len(voice) > 300:
            raise InvalidCommunication(
                "Choose a voice identifier up to 300 characters."
            )
        board_id = values.get("default_board_id") or None
        if board_id:
            board = find_board(board_id)
            if board.archived_at:
                raise InvalidCommunication("Choose an active board as the default.")
        clean.update(voice_id=voice, default_board_id=board_id)
        for key, value in clean.items():
            setattr(pref, key, value)
        pref.version += 1
        care_audit("communication.preferences_saved", g.profile_id)


def board_choices():
    return list(
        db.session.scalars(
            select(Board)
            .where(scope(Board, g.workspace_id), Board.archived_at.is_(None))
            .order_by(Board.title)
            .limit(40)
        )
    )


def favorites(include_archived=False):
    require("communication.view")
    if not g.profile_id:
        return [], []
    card_query = (
        select(FavoriteCard, Card, Board)
        .join(Card, Card.id == FavoriteCard.card_id)
        .join(Board, Board.id == Card.board_id)
        .where(scope(FavoriteCard, g.workspace_id), scope(Board, g.workspace_id))
    )
    phrase_query = (
        select(FavoritePhrase, Phrase)
        .join(Phrase, Phrase.id == FavoritePhrase.phrase_id)
        .where(scope(FavoritePhrase, g.workspace_id), scope(Phrase, g.workspace_id))
    )
    if not include_archived:
        card_query = card_query.where(Board.archived_at.is_(None))
        phrase_query = phrase_query.where(Phrase.archived_at.is_(None))
    return (
        db.session.execute(
            card_query.order_by(FavoriteCard.position, FavoriteCard.card_id).limit(50)
        ).all(),
        db.session.execute(
            phrase_query.order_by(
                FavoritePhrase.position, FavoritePhrase.phrase_id
            ).limit(50)
        ).all(),
    )


def change_favorite(kind, target, action, expected):
    if kind not in {"card", "phrase"} or action not in {"add", "remove", "up", "down"}:
        abort(400)
    model, field = (
        (FavoriteCard, "card_id") if kind == "card" else (FavoritePhrase, "phrase_id")
    )
    with transaction():
        pref = locked()
        if kind == "card":
            item = db.session.scalar(
                select(Card)
                .join(Board, Board.id == Card.board_id)
                .where(Card.id == target, scope(Board, g.workspace_id))
            )
        else:
            item = db.session.scalar(
                select(Phrase).where(Phrase.id == target, scope(Phrase, g.workspace_id))
            )
        if not item:
            abort(404)
        existing = db.session.get(model, (g.profile_id, target))
        # Desired add/remove retries do not toggle or introduce duplicate favorites.
        if action == "add" and existing or action == "remove" and not existing:
            return
        version(pref, expected)
        ordered = list(
            db.session.scalars(
                select(model)
                .where(scope(model, g.workspace_id))
                .order_by(model.position, getattr(model, field))
            )
        )
        if action == "add":
            if len(ordered) >= 50:
                raise InvalidCommunication(
                    "Keep up to 50 favorites of each kind. Remove one before adding another."
                )
            if (
                kind == "card"
                and db.session.get(Board, item.board_id).archived_at
                or kind == "phrase"
                and item.archived_at
            ):
                raise InvalidCommunication("Restore the item before favoriting it.")
            db.session.add(
                model(
                    profile_id=g.profile_id,
                    workspace_id=g.workspace_id,
                    position=(max([f.position for f in ordered], default=-1) + 1),
                    **{field: target},
                )
            )
        elif action == "remove":
            db.session.delete(existing)
        else:
            if not existing:
                abort(404)
            index = ordered.index(existing)
            to = index + (-1 if action == "up" else 1)
            if not 0 <= to < len(ordered):
                return
            ordered[index], ordered[to] = ordered[to], ordered[index]
            for index, row in enumerate(ordered):
                row.position = index
        pref.version += 1
        care_audit("communication.favorite_" + action, target)


def default_board():
    pref = get()
    return (
        db.session.scalar(
            select(Board).where(
                scope(Board, g.workspace_id),
                Board.id == pref.default_board_id,
                Board.archived_at.is_(None),
            )
        )
        if pref.default_board_id
        else None
    )


def favorites_version():
    import hashlib

    cards, phrases = favorites(True)
    parts = (
        [str(get().version)]
        + [
            f"{f.card_id}:{f.position}:{b.version}:{bool(b.archived_at)}"
            for f, c, b in cards
        ]
        + [
            f"{f.phrase_id}:{f.position}:{p.version}:{bool(p.archived_at)}"
            for f, p in phrases
        ]
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
