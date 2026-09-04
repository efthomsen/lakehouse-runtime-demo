# The exact image submitted to Azure Batch (see batch/task-template.json).
# Build and run identically on a laptop:
#   docker build -t lakehouse-runtime-demo -f docker/Dockerfile .
#   docker run --rm -v "$PWD/data:/data" lakehouse-runtime-demo \
#     python -m ingest.main --run-id RUN-0001 \
#       --window-start 2026-09-01T00:00:00Z --window-end 2026-09-02T00:00:00Z \
#       --table-uri /data/bronze/orders_raw --source synthetic-data/orders_sample.json

FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY synthetic-data ./synthetic-data

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m"]
CMD ["ingest.main", "--help"]
