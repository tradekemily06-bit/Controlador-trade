FROM docker.io/library/node:22-alpine AS figma-build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ENV FIGMA_PUBLIC_URL=/painel
RUN pnpm run build

FROM docker.io/library/python:3.12-slim AS runtime

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=figma-build /app/dist ./figma-panel

ENV PYTHONUNBUFFERED=1
ENV PORT=7860

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '7860') + '/api/health/live', timeout=3).read()" || exit 1

CMD ["python", "app.py"]
