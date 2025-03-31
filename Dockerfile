FROM python:3.9-slim

WORKDIR /app

COPY pyproject.toml ./

RUN pip install uv && uv install --no-cache-dir

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
