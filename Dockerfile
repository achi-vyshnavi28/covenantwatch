# CovenantWatch API. Build: docker build -t covenantwatch .   Run: docker run -p 8901:8901 -e GEMINI_API_KEY=... covenantwatch
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 COVENANTWATCH_DB=/app/data/covenantwatch.sqlite3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY covenantwatch/ covenantwatch/
COPY app/ app/
COPY evals/ evals/
COPY data/filings/ data/filings/
COPY data/register.json data/register.json
RUN useradd -m cw && chown -R cw /app
USER cw
EXPOSE 8901
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8901/health')"
CMD ["sh", "-c", "python -m covenantwatch.simulate && uvicorn covenantwatch.api:app --host 0.0.0.0 --port 8901"]
