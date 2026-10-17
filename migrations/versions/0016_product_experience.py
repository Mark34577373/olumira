"""Additive core product and premium setup tables; preserve existing records."""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = "0016"
down_revision = "0015"
branch_labels = depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "\nCREATE TABLE resources (\n\tid VARCHAR(40) NOT NULL, \n\ttitle VARCHAR(120) NOT NULL, \n\tsummary VARCHAR(500) NOT NULL, \n\tcontent TEXT NOT NULL, \n\tcategory VARCHAR(60) NOT NULL, \n\ttags VARCHAR(200) NOT NULL, \n\tpublisher VARCHAR(120) NOT NULL, \n\texternal_url VARCHAR(1000), \n\tpublication_date VARCHAR(10), \n\treviewed_at VARCHAR(10), \n\tpublished BOOLEAN NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n"
        )
        op.execute("CREATE INDEX ix_resources_category ON resources (category)")
        op.execute(
            "\nCREATE TABLE resource_bookmarks (\n\tuser_id VARCHAR(32) NOT NULL, \n\tresource_id VARCHAR(40) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (user_id, resource_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(resource_id) REFERENCES resources (id)\n)\n\n"
        )
    if dialect == "postgresql":
        op.execute(
            "\nCREATE TABLE resources (\n\tid VARCHAR(40) NOT NULL, \n\ttitle VARCHAR(120) NOT NULL, \n\tsummary VARCHAR(500) NOT NULL, \n\tcontent TEXT NOT NULL, \n\tcategory VARCHAR(60) NOT NULL, \n\ttags VARCHAR(200) NOT NULL, \n\tpublisher VARCHAR(120) NOT NULL, \n\texternal_url VARCHAR(1000), \n\tpublication_date VARCHAR(10), \n\treviewed_at VARCHAR(10), \n\tpublished BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n"
        )
        op.execute("CREATE INDEX ix_resources_category ON resources (category)")
        op.execute(
            "\nCREATE TABLE resource_bookmarks (\n\tuser_id VARCHAR(32) NOT NULL, \n\tresource_id VARCHAR(40) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (user_id, resource_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(resource_id) REFERENCES resources (id)\n)\n\n"
        )

    table = sa.table(
        "resources",
        sa.column("id", sa.String),
        sa.column("title", sa.String),
        sa.column("summary", sa.String),
        sa.column("content", sa.Text),
        sa.column("category", sa.String),
        sa.column("tags", sa.String),
        sa.column("publisher", sa.String),
        sa.column("published", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    timestamp = datetime.now(timezone.utc)
    rows = [
        {
            "id": "guide-01",
            "title": "Visual Communication",
            "summary": "Tools and ideas for supporting communication.",
            "content": "Using pictures, symbols, and simple visual choices can help make communication easier.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Communication",
            "tags": "communication, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-02",
            "title": "Choice Boards",
            "summary": "Quick ways to offer choices during the day.",
            "content": "Put a few high-frequency choices on a board so the person can point or choose without needing long explanations.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Communication",
            "tags": "communication, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-03",
            "title": "Building Routines",
            "summary": "Ideas for creating predictable routines.",
            "content": "Keep steps consistent and visible, and pair each routine with a clear visual cue to reduce stress and confusion.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Daily routines",
            "tags": "daily routines, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-04",
            "title": "Transition Helpers",
            "summary": "Gentle supports for the move between activities.",
            "content": "Use a 5-minute warning, a countdown card, or a first-then visual to make transitions calmer and clearer.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Daily routines",
            "tags": "daily routines, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-05",
            "title": "Short Activity Ideas",
            "summary": "Simple activities for movement and engagement.",
            "content": "Rotate between sensory play, music, outdoor exploration, and calm-down activities to keep the day balanced.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Activities",
            "tags": "activities, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-06",
            "title": "Movement Breaks",
            "summary": "Small movement activities for a reset.",
            "content": "Short movement, music, or sensory breaks can help reset energy without turning the day into a long activity block.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Activities",
            "tags": "activities, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-07",
            "title": "Learning at Home",
            "summary": "Gentle, visual learning supports.",
            "content": "Break tasks into small steps, celebrate progress, and use visuals to reinforce routines and skills at home.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Learning",
            "tags": "learning, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-08",
            "title": "Skill Building",
            "summary": "Simple progress-focused practice ideas.",
            "content": "Practice one skill at a time with visual supports and repeated short opportunities for success.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Learning",
            "tags": "learning, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-09",
            "title": "Safety Check",
            "summary": "Basic safety routines to review regularly.",
            "content": "Reinforce handwashing, bathroom routines, supervision expectations, and clear household safety steps.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Safety",
            "tags": "safety, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-10",
            "title": "Emergency Steps",
            "summary": "Key reminders for calm and clear routines.",
            "content": "Keep a calm, simple safety flow on paper so responses stay clear even when the day feels busy.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Safety",
            "tags": "safety, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-11",
            "title": "Caregiver Support",
            "summary": "Helpful reminders and support ideas.",
            "content": "Keep your plan realistic, build in breaks, and rely on visual supports to help everyone stay consistent.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Caregiver support",
            "tags": "caregiver support, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-12",
            "title": "Self Care",
            "summary": "Simple ways to recharge during busy days.",
            "content": "Short breaks, routines for rest, and shared check-ins can help sustain energy and reduce overwhelm.\n\nGeneral organizational ideas from Olumira. Choose what fits the person’s preferences. This is not clinical, diagnostic or emergency-response guidance.",
            "category": "Caregiver support",
            "tags": "caregiver support, organization",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-13",
            "title": "Shared handoff notes",
            "summary": "Keep practical information in one shared place.",
            "content": "Write down what is ready, the next planned activity, and any practical questions. Assign a clear recipient and acknowledge the handoff after reviewing it. Keep unnecessary personal details out of shared summaries.",
            "category": "Family collaboration",
            "tags": "handoffs, organization, collaboration",
            "publisher": "Olumira · general organizational guide",
        },
        {
            "id": "guide-14",
            "title": "Accessible picture layouts",
            "summary": "Make a picture board comfortable to use.",
            "content": "Offer a manageable set of familiar pictures. Try larger cards, clear text and the distraction-free board view. Ask the person which presentation they prefer. Revisit the layout together when their needs change.",
            "category": "Accessibility",
            "tags": "pictures, communication, accessibility",
            "publisher": "Olumira · general organizational guide",
        },
    ]
    op.bulk_insert(
        table,
        [
            dict(row, published=True, created_at=timestamp, updated_at=timestamp)
            for row in rows
        ],
    )


def downgrade():
    raise RuntimeError("Back up and review new records before any downgrade.")
