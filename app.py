from flask import Flask, abort, redirect, render_template, request, url_for
from services.database import initialize_database, add_starter_routines
from services.routines import get_routines, get_progress, toggle_routine
from services.observations import add_observation, get_observations

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

initialize_database()
add_starter_routines()


@app.route("/")
def dashboard():
    routines = get_routines()
    completed_routines = sum(routine["completed"] for routine in routines)
    routine_count = len(routines)
    progress = get_progress()
    recent_observations = get_observations()[:2]

    return render_template(
        "dashboard.html",
        routines=routines,
        completed_routines=completed_routines,
        routine_count=routine_count,
        progress=progress,
        recent_observations=recent_observations,
    )


@app.route("/routines/<int:routine_id>/toggle", methods=["POST"])
def toggle_routine_completion(routine_id):
    if not toggle_routine(routine_id):
        abort(404)
    endpoint = {
        "dashboard": "dashboard",
        "routines": "routines",
    }.get(request.form.get("return_to"), "dashboard")
    return redirect(url_for(endpoint))


@app.route("/routines")
def routines():
    routines = get_routines()
    return render_template("routines.html", routines=routines)


@app.route("/routines/toggle/<int:routine_id>", methods=["POST"])
def toggle_routine_route(routine_id):
    if not toggle_routine(routine_id):
        abort(404)
    return redirect(url_for("routines"))


@app.route("/communication")
def communication():
    return render_template(
        "communication.html",
        communication_categories=("Needs", "Activities"),
        communication_options=COMMUNICATION_OPTIONS,
    )


@app.route("/observations", methods=["GET", "POST"])
def observations():
    form_values = {"activity": "", "date": "", "notes": "", "mood": "", "tags": ""}

    if request.method == "POST":
        form_values = {
            field: request.form.get(field, "").strip()
            for field in form_values
        }
        add_observation(
            form_values["activity"],
            form_values["date"],
            form_values["notes"],
            form_values["mood"],
            form_values["tags"],
        )
        return redirect(url_for("observations", saved="1"))

    return render_template(
        "observations.html",
        form_values=form_values,
        observation_saved=request.args.get("saved") == "1",
        observations=get_observations(),
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