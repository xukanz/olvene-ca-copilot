# One image, three roles (方案规划 §2.1): ROLE=api | web | eval
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 ROLE=api
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api ./api
COPY web ./web
COPY eval ./eval
COPY brand ./brand
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh && useradd -m app
USER app
ENTRYPOINT ["./docker-entrypoint.sh"]
