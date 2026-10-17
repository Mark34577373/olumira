from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Unbound extensions allow independent application instances in tests.
db = SQLAlchemy()
migrate = Migrate()
