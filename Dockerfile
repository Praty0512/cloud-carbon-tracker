# Cloud Carbon Tracker -- Streamlit frontend + FastAPI backend, single image.
# Which process runs is chosen at `docker run`/compose time (see
# docker-compose.yml): `streamlit run app.py` or `uvicorn main:app`.

FROM python:3.11-slim AS base

# psycopg2-binary/cryptography need build tooling only if wheels aren't
# available for the target platform; keep the image small by not installing
# a full build-essential unless it turns out to be needed for your platform.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root runtime user.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8501 8000

# Default: run the Streamlit UI. Override the command in docker-compose.yml
# (or `docker run ... uvicorn main:app --host 0.0.0.0 --port 8000`) to run
# the FastAPI backend instead.
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
