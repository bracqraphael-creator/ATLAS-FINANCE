# Image du moteur de calcul, pour l'hébergement (Railway, Scaleway, OVHcloud…).
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY atlas ./atlas
RUN pip install --no-cache-dir .
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn atlas.api:app --host 0.0.0.0 --port ${PORT}"]
