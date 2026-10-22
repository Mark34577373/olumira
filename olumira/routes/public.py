"""Public product information. Never query workspace or care records here."""
from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import Blueprint, current_app, render_template, request, url_for, Response
from olumira.extensions import limiter
from olumira.forms import ContactForm

bp = Blueprint('public', __name__)

FEATURES = (
    ('care-plans', 'Care plans', 'Support that starts with the individual.', 'Connect priorities, goals, routines, boards and responsibilities around an authorized care profile.', 'For example, connect a morning routine and a communication board to one support plan.', 'plan'),
    ('routines', 'Visual Routine Studio', 'Make everyday routines easier to follow.', 'Customize ordered picture steps, use optional timers, schedule routines and review completed guided runs.', 'For example, adapt a fictional morning sequence, then open its step-by-step player.', 'routine'),
    ('communication', 'Communication boards', 'More ways to express what matters.', 'Configure picture cards and saved phrases, then open a distraction-free board with a prominent speech control. Speech depends on supported local browser voices.', 'For example, choose familiar cards for a snack-time conversation.', 'board'),
    ('handoffs', 'Caregiver handoffs', 'Keep everyone on the same page.', 'Review an editable handoff draft, select authorized recipients, share it and record acknowledgments.', 'For example, share a reviewed afternoon summary with the next caregiver.', 'handoff'),
    ('responsibilities', 'Shared responsibilities', 'A little support, shared.', 'Assign practical tasks, set due dates and follow their status in the selected workspace and profile.', 'For example, assign preparation of tomorrow’s activity bag.', 'tasks'),
    ('observations', 'Observations', 'Notice the little things that matter.', 'Record everyday moments, search the timeline and connect relevant records. These are caregiver notes, not diagnoses.', 'For example, note that a quiet reading break was enjoyed.', 'notes'),
    ('calendar', 'Calendar and reminders', 'See the shape of the day.', 'Bring scheduled routines, responsibilities and calendar events together, with configurable in-app reminders. Reminder processing must be operated separately; email and push reminders are not provided.', 'For example, review tomorrow’s routines alongside an outing.', 'calendar'),
    ('reports', 'Analytics and reports', 'Reflect on recorded activity.', 'Review descriptive routine history and observation summaries, with authorized report and export controls. Summaries do not provide clinical advice.', 'For example, review which guided routines were recorded as completed this week.', 'reports'),
    ('resources', 'Resource center', 'Useful guidance, close at hand.', 'Search categorized organizational guides and bookmark useful resources for later.', 'For example, save a guide to preparing a visual routine.', 'resources'),
    ('personalization', 'Accessibility and personalization', 'Make room for different preferences.', 'Choose larger text, reduced motion, stronger contrast and supported communication presentation preferences. Individual accessibility needs still require testing.', 'For example, use larger text and fewer visual effects on a shared device.', 'preferences'),
)


@bp.app_context_processor
def public_helpers():
    origin = current_app.config['PUBLIC_APP_URL'].rstrip('/')
    host = urlsplit(origin).hostname
    canonical = origin + request.path if host not in {'localhost', '127.0.0.1', '::1'} and current_app.config['APP_ENV'] == 'production' else None
    return dict(public_year=datetime.now(timezone.utc).year, public_features=FEATURES,
                public_canonical=canonical,
                signup_endpoint='auth.register' if current_app.config['REGISTRATION_ENABLED'] else 'public.contact',
                signup_label='Get Started' if current_app.config['REGISTRATION_ENABLED'] else 'Beta access information')


@bp.get('/welcome')
def home():
    return render_template('public/home.html', public_title='Care feels more connected, together.',
                           public_description='Thoughtful tools for family routines, picture communication, care plans and caregiver coordination. Explore the Olumira controlled beta.')


@bp.get('/features')
def features():
    return render_template('public/features.html', public_title='Thoughtful tools for everyday care', public_description='Explore Olumira care plans, visual routines, communication boards, handoffs, observations and shared schedules.')


@bp.get('/how-it-works')
def how_it_works():
    return render_template('public/how_it_works.html', public_title='From your first step to your everyday rhythm', public_description='Learn how Olumira accounts, workspaces, care profiles and authorized caregiver collaboration fit together.')


@bp.get('/about')
def about():
    return render_template('public/about.html', public_title='Built around the people behind everyday care.', public_description='Our purpose: practical, accessible tools that help families organize everyday support and stay connected.')


@bp.route('/contact', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def contact():
    form = ContactForm()
    status = 200
    if request.method == 'POST':
        status = 503 if form.validate_on_submit() else 422
        # The unavailable form must not reflect submitted personal content.
        for name in ('name', 'email', 'message', 'website'):
            form[name].data = ''
        form.inquiry.data = 'general'
    return render_template('public/contact.html', form=form, public_title='Let’s stay connected', public_description='Contact and controlled-beta access information for Olumira. Public submissions are not currently available.'), status


@bp.get('/privacy')
def privacy():
    return render_template('public/legal.html', kind='privacy', public_title='Privacy information — draft', public_description='Verified current Olumira data practices and outstanding privacy review. Draft information for fictional-data testing only.')


@bp.get('/terms')
def terms():
    return render_template('public/legal.html', kind='terms', public_title='Testing terms — draft', public_description='Olumira controlled-testing limitations and matters requiring legal review before public real-data use.')


@bp.get('/robots.txt')
def robots():
    return Response('User-agent: *\nDisallow: /\n', mimetype='text/plain')
