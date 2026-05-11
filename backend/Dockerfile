FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# `db upgrade` is idempotent — running it on every boot is the standard
# pattern for single-replica setups. For multi-replica deployments you'd
# move this to a one-shot init container instead.
CMD ["sh", "-c", "flask db upgrade && flask run --host=0.0.0.0 --port=5000"]
