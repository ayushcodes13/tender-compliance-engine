FROM node:22-bookworm-slim

ENV NODE_ENV=production
WORKDIR /app

# Keep OCR available on the free Node host without adding it to the runtime's
# npm dependency tree. Uploaded PDFs are still processed only in the request.
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates poppler-utils tesseract-ocr \
  && rm -rf /var/lib/apt/lists/*

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web ./
RUN npm run build

EXPOSE 10000
CMD ["sh", "-c", "npm run start -- --hostname 0.0.0.0 --port ${PORT:-10000}"]
