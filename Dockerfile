FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

WORKDIR /app

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=7860

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '7860') + '/api/health', timeout=3).read()" || exit 1

CMD ["python", "app.py"]
