FROM python:3.11-slim AS base

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

EXPOSE 8000
CMD ["uvicorn", "bank_rag.interface.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
