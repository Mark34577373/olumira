import os
import uuid
from datetime import timedelta

from flask import Flask, abort, g, redirect, render_template, request, session, url_for

from services.database import (
    initialize_database,
    ensure_workspace,
    purge_old_workspaces,
    today_string,
    time_greeting,
)
from services.routines import (
    ROUTINE_TEMPLATES,
    add_routine,
    add_template,
    delete_routine,
    get_routines,
    group_by_category,
    summarize_progress,
    toggle_routine,
    update_routine,
)
from services.observations import add_observation, get_observations

DEV_SECRET_KEY = "dev-only-secret-change-me"

COMMUNICATION_OPTIONS = [
    {"id": "thirsty", "name": "Thirsty", "icon": "💧", "category": "Needs", "message": "I want water."},
    {"id": "hungry", "name": "Hungry", "icon": "🍎", "category": "Needs", "message": "I want something to eat."},
    {"id": "bathroom", "name": "Bathroom", "icon": "🚽", "category": "Needs", "message": "I need to use the bathroom."},
    {"id": "tired", "name": "Tired", "icon": "😴", "category": "Needs", "message": "I feel tired."},
    {"id": "unwell", "name": "Not feeling well", "icon": "🤕", "category": "Needs", "message": "I don't feel well."},
    {"id": "play", "name": "Play", "icon": "🎮", "category": "Activities", "message": "I want to play."},
    {"id": "outside", "name": "Outside", "icon": "🌳", "category": "Activities", "message": "I want to go outside."},
    {"id": "school", "name": "School", "icon": "📚", "category": "Activities", "message": "I want to go to school."},
    {"id": "music", "name": "Music", "icon": "🎵", "category": "Activities", "message": "I want to listen to music."},
    {"id": "quiet-time", "name": "Quiet time", "icon": "🧸", "category": "Activities", "message": "I want quiet time."},
]

RESOURCE_TYPES = [
    "All",
    "Communication",
    "Daily routines",
    "Activities",
    "Learning",
    "Safety",
    "Caregiver support",
]

RESOURCES = [
    {
        "title": "Visual Communication",
        "category": "Communication",
        "summary": "Tools and ideas for supporting communication.",
        "details": "Using pictures, symbols, and simple visual choices can help make communication easier.",
        "action": "Learn more",
    },
    {
        "title": "Choice Boards",
        "category": "Communication",
        "summary": "Quick ways to offer choices during the day.",
        "details": "Put a few high-frequency choices on a board so the person can point or choose without needing long explanations.",
        "action": "Open ideas",
    },
    {
        "title": "Building Routines",
        "category": "Daily routines",
        "summary": "Ideas for creating predictable routines.",
        "details": "Keep steps consistent and visible, and pair each routine with a clear visual cue to reduce stress and confusion.",
        "action": "View tips",
    },
    {
        "title": "Transition Helpers",
        "category": "Daily routines",
        "summary": "Gentle supports for the move between activities.",
        "details": "Use a 5-minute warning, a countdown card, or a first-then visual to make transitions calmer and clearer.",
        "action": "See examples",
    },
    {
        "title": "Short Activity Ideas",
        "category": "Activities",
        "summary": "Simple activities for movement and engagement.",
        "details": "Rotate between sensory play, music, outdoor exploration, and calm-down activities to keep the day balanced.",
        "action": "Explore",
    },
    {
        "title": "Movement Breaks",
        "category": "Activities",
        "summary": "Small movement activities for a reset.",
        "details": "Short movement, music, or sensory breaks can help reset energy without turning the day into a long activity block.",
        "action": "Try it",
    },
    {
        "title": "Learning at Home",
        "category": "Learning",
        "summary": "Gentle, visual learning supports.",
        "details": "Break tasks into small steps, celebrate progress, and use visuals to reinforce routines and skills at home.",
        "action": "Read guide",
    },
    {
        "title": "Skill Building",
        "category": "Learning",
        "summary": "Simple progress-focused practice ideas.",
        "details": "Practice one skill at a time with visual supports and repeated short opportunities for success.",
        "action": "Review steps",
    },
    {
        "title": "Safety Check",
        "category": "Safety",
        "summary": "Basic safety routines to review regularly.",
        "details": "Reinforce handwashing, bathroom routines, supervision expectations, and clear household safety steps.",
        "action": "Review",
    },
    {
        "title": "Emergency Steps",
        "category": "Safety",
        "summary": "Key reminders for calm and clear routines.",
        "details": "Keep a calm, simple safety flow on paper so responses stay clear even when the day feels busy.",
        "action": "See reminders",
    },
    {
        "title": "Caregiver Support",
        "category": "Caregiver support",
        "summary": "Helpful reminders and support ideas.",
        "details": "Keep your plan realistic, build in breaks, and rely on visual supports to help everyone stay consistent.",
        "action": "Open support",
    },
    {
        "title": "Self Care",
        "category": "Caregiver support",
        "summary": "Simple ways to recharge during busy days.",
        "details": "Short breaks, routines for rest, and shared check-ins can help sustain energy and reduce overwhelm.",
        "action": "Take a minute",
    },
]

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

if os.environ.get("RENDER") and app.secret_key == DEV_SECRET_KEY:
    print("WARNING: SECRET_KEY is not set. Add it in Render's Environment settings.")

initialize_database()
purge_old_workspaces()


@app.before_request
def load_workspace():
    # Every visitor gets a private workspace tied to a signed cookie.
    if request.endpoint in (None, "static"):
        return

    owner_id = session.get("owner_id") or uuid.uuid4().hex
    ensure_workspace(owner_id)
    session["owner_id"] = owner_id
    session.permanent = True
    g.owner_id = owner_id


@app.route("/")
def dashboard():
    routine_list = get_routines(g.owner_id)
    completed_routines, routine_count, progress = summarize_progress(routine_list)

    saved_observations = get_observations(g.owner_id)

    return render_template(
        "dashboard.html",
        greeting=time_greeting(),
        routine_groups=group_by_category(routine_list),
        completed_routines=completed_routines,
        routine_count=routine_count,
        progress=progress,
        recent_observations=saved_observations[:2],
        observation_count=len(saved_observations),
        active_routine_count=len(group_by_category(routine_list)),
    )


@app.route("/routines/<int:routine_id>/toggle", methods=["POST"])
def toggle_routine_completion(routine_id):
    if not toggle_routine(g.owner_id, routine_id):
        abort(404)
    endpoint = {
        "dashboard": "dashboard",
        "routines": "routines",
    }.get(request.form.get("return_to"), "dashboard")
    return redirect(url_for(endpoint))


@app.route("/routines")
def routines():
    routine_list = get_routines(g.owner_id)
    groups = group_by_category(routine_list)
    completed_routines, routine_count, progress = summarize_progress(routine_list)

    return render_template(
        "routines.html",
        routine_groups=groups,
        category_options=sorted(set(groups) | set(ROUTINE_TEMPLATES)),
        template_names=list(ROUTINE_TEMPLATES),
        completed_routines=completed_routines,
        routine_count=routine_count,
        progress=progress,
        error=request.args.get("error"),
    )


@app.route("/routines/add", methods=["POST"])
def add_routine_route():
    status = add_routine(
        g.owner_id, request.form.get("name"), request.form.get("category")
    )
    return redirect(url_for("routines", error=None if status == "ok" else status))


@app.route("/routines/<int:routine_id>/edit", methods=["POST"])
def edit_routine_route(routine_id):
    status = update_routine(
        g.owner_id, routine_id, request.form.get("name"), request.form.get("category")
    )
    if status == "missing":
        abort(404)
    return redirect(url_for("routines", error=None if status == "ok" else status))


@app.route("/routines/<int:routine_id>/delete", methods=["POST"])
def delete_routine_route(routine_id):
    if not delete_routine(g.owner_id, routine_id):
        abort(404)
    return redirect(url_for("routines"))


@app.route("/routines/add-template", methods=["POST"])
def add_template_route():
    status = add_template(g.owner_id, request.form.get("template"))
    if status == "invalid":
        abort(400)
    return redirect(url_for("routines", error=None if status == "ok" else status))


@app.route("/communication")
def communication():
    return render_template(
        "communication.html",
        communication_categories=("Needs", "Activities"),
        communication_options=COMMUNICATION_OPTIONS,
    )


@app.route("/observations", methods=["GET", "POST"])
def observations():
    form_values = {"activity": "", "date": today_string(), "notes": "", "mood": "", "tags": ""}

    if request.method == "POST":
        submitted = {
            field: request.form.get(field, "").strip()
            for field in form_values
        }
        saved = add_observation(
            g.owner_id,
            submitted["activity"],
            submitted["date"],
            submitted["notes"],
            submitted["mood"],
            submitted["tags"],
        )
        return redirect(url_for("observations", saved="1" if saved else None))

    return render_template(
        "observations.html",
        form_values=form_values,
        observation_saved=request.args.get("saved") == "1",
        observations=get_observations(g.owner_id),
    )


@app.route("/resources")
def resources():
    return render_template(
        "resources.html",
        resource_types=RESOURCE_TYPES,
        resources=RESOURCES,
    )


if __name__ == "__main__":
    app.run()