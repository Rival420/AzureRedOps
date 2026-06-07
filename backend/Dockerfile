# Playwright image ships Python + Chromium + all browser dependencies,
# giving the auth-interactive flow full parity inside the container.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
# Bundled datasets + TLS material used by the core tool.
COPY includes /includes

ENV AZUREREDOPS_INCLUDES=/includes \
    AZUREREDOPS_WEB=/includes/web \
    PLAYWRIGHT_HEADLESS=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000
# PKCE callback listener (auth-app) binds here when used.
EXPOSE 2342

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
