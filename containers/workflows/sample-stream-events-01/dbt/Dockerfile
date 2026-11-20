FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app/dbt

RUN chmod +x /app/dbt/run-dbt.sh \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["/app/dbt/run-dbt.sh"]
