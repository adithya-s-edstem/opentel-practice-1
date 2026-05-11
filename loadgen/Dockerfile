FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir requests==2.32.3

COPY loadgen.py .

CMD ["python", "loadgen.py"]
