FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup --system bot \
    && adduser --system --ingroup bot bot

COPY app ./app
RUN mkdir -p /app/data \
    && chown -R bot:bot /app \
    && chmod 700 /app/data

USER bot
VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
