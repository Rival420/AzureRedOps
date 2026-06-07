# Remote MCP server for the AzureRedOps Console.
# Thin, authenticated MCP wrapper over the FastAPI backend — no Azure deps needed,
# so a slim Python base is enough (unlike the backend's Playwright image).
FROM python:3.12-slim

WORKDIR /app

COPY mcp_server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server/server.py ./server.py

ENV PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=9000 \
    MCP_PATH=/mcp \
    BACKEND_URL=http://backend:8000

EXPOSE 9000

CMD ["python", "server.py"]
