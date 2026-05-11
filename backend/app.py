"""Flask application factory.

Owns the boot sequence and nothing else. Concerns live elsewhere:

  - models.py        SQLAlchemy ORM models
  - schemas.py       Pydantic input validation
  - services.py      Data-access functions (CRUD via SQLAlchemy 2.0)
  - routes.py        HTTP endpoints (Blueprint, thin handlers)
  - metrics.py       Custom OTel instruments + record helpers
  - observability.py OTel SDK wiring (traces / metrics / logs)
"""

import logging
import os

from flask import Flask
from flask_cors import CORS

from extensions import db, migrate
from metrics import init_metrics
from observability import setup_observability
from routes import api

log = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://todo:todo@db:5432/todo",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    CORS(app)
    db.init_app(app)

    # Import models so they register on db.metadata before Alembic
    # introspects them for autogenerate.
    import models  # noqa: F401

    # Schema lives in migrations/ now — `flask db upgrade` (run from the
    # container's entrypoint) applies them. No more create_all().
    migrate.init_app(app, db)

    # Wire up OpenTelemetry. Must happen AFTER db.init_app so the engine
    # exists for the SQLAlchemy instrumentation to wrap.
    meter = setup_observability(app)
    init_metrics(meter)

    app.register_blueprint(api)
    log.info("todo-backend started")
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
