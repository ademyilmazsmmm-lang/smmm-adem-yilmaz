# Şimdilik yalın Python imajı (TOPLAYICI=dosya/ornek). Luca toplayıcı eklenince taban imaj
# mcr.microsoft.com/playwright/python:<sürüm>-noble olmalı ve lucabot klasörü özel depodan eklenmelidir.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Istanbul DATA_DIR=/data
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
EXPOSE 8000
# Tek işçi şart: zamanlayıcı bu süreçte çalışır.
CMD ["sh", "-c", "uvicorn app.web:app_fabrikasi --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
