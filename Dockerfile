FROM python:3.13-slim AS build

WORKDIR /app
RUN python -m venv /opt/place-twins
COPY .docker/runtime-requirements.txt /dependencies/runtime-requirements.txt
RUN /opt/place-twins/bin/pip install \
    --no-cache-dir \
    --requirement /dependencies/runtime-requirements.txt
COPY pyproject.toml README.md ./
COPY src ./src
RUN /opt/place-twins/bin/pip install --no-cache-dir --no-deps .

FROM python:3.13-slim

ENV DASH_PRECOMPUTE_ARTIFACTS=/app/artifacts \
    PATH=/opt/place-twins/bin:$PATH \
    PORT=8080 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --create-home --uid 10001 place-twins
COPY --from=build /opt/place-twins /opt/place-twins

ARG PLACE_TWINS_BUILD
ENV PLACE_TWINS_BUILD=$PLACE_TWINS_BUILD
COPY --chown=place-twins:place-twins artifacts/current.json ./artifacts/current.json
COPY --chown=place-twins:place-twins artifacts/bundles/${PLACE_TWINS_BUILD} ./artifacts/bundles/${PLACE_TWINS_BUILD}
RUN python -c "import os; from dash_precompute.catalog import ArtifactCatalog; catalog = ArtifactCatalog('artifacts'); assert catalog.build_id == os.environ['PLACE_TWINS_BUILD']; catalog.validate_all()"

USER place-twins
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8080') + '/health', timeout=3)"

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} dash_precompute.wsgi:server"]
