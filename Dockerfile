# Minimal Dockerfile for RelayFreeLLM
# Follows Docker best practices for Python apps.

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only application source and minimal config to keep image small
COPY src/ ./src/
COPY settings.json ./

EXPOSE 8000

CMD ["python", "-m", "src.server"]
