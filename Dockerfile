FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SMARTSPEND_CLOUD=1
WORKDIR /app
COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt \
    && useradd --create-home --uid 10001 smartspend
COPY --chown=smartspend:smartspend backend ./backend
COPY --chown=smartspend:smartspend frontend ./frontend
USER smartspend
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn backend.api_server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
