# Multi-stage build. `base` holds only production dependencies (requirements.txt), so the
# final `runtime` image -- what actually ships and what `docker compose up` builds by
# default, since no target is specified for the `backend` service -- never contains pytest
# or any dev-only package. `test` is a separate stage built FROM base that layers
# requirements-dev.txt (pytest, httpx) and the test suite on top of the exact same production
# dependencies, so tests run against what actually ships. It is only built when explicitly
# requested (see docker-compose.yml's `backend-test` service, gated behind the `test` profile)
# and is never part of the default `docker compose up --build` flow.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system caseforge && useradd --system --gid caseforge caseforge


FROM base AS test

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY --chown=caseforge:caseforge app ./app
COPY --chown=caseforge:caseforge alembic ./alembic
COPY --chown=caseforge:caseforge alembic.ini ./alembic.ini
COPY --chown=caseforge:caseforge pytest.ini ./pytest.ini
COPY --chown=caseforge:caseforge tests ./tests

USER caseforge

CMD ["python", "-m", "pytest"]


FROM base AS runtime

COPY --chown=caseforge:caseforge app ./app
COPY --chown=caseforge:caseforge alembic ./alembic
COPY --chown=caseforge:caseforge alembic.ini ./alembic.ini
COPY --chown=caseforge:caseforge entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

USER caseforge

CMD ["./entrypoint.sh"]
