FROM python:3.11-slim-bookworm

WORKDIR /app
ENV PYTHONBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
COPY skills ./skills
COPY migrations ./migrations
COPY alembic.ini .

EXPOSE 8000
CMD ["uvicorn", "trading_desk.api.main.app", "--host", "0.0.0.0", "--port", "8000"]