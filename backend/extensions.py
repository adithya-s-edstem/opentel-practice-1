"""Flask extension singletons.

Kept in their own module so any file can `from extensions import db` without
risking a circular import on `app`. The actual binding to a Flask app happens
in `create_app()` via `db.init_app(app)`.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
