FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY frontend ./frontend
COPY build_frontend.py ./
COPY app ./app
RUN python build_frontend.py && mkdir -p /app/data && adduser --disabled-password --gecos "" --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3); raise SystemExit(0 if r.status==200 else 1)"
CMD ["gunicorn","--bind","0.0.0.0:8080","--workers","2","--threads","4","--timeout","240","app.app:app"]
