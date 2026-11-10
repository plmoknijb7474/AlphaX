FROM python:3.13.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin alpha \
    && chown -R alpha:alpha /app
USER 10001:10001

EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --timeout 180 --access-logfile - --error-logfile - app:app"]
