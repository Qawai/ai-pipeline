FROM python:3.11-slim

# opencode необходим для работы агентов (вызывается как подпроцесс)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/opencode.tar.gz \
      https://github.com/anomalyco/opencode/releases/latest/download/opencode-linux-x64.tar.gz \
    && tar -xzf /tmp/opencode.tar.gz -C /usr/local/bin \
    && chmod +x /usr/local/bin/opencode \
    && rm -f /tmp/opencode.tar.gz
RUN opencode --version

WORKDIR /app
COPY . .

ENV PORT=8787
EXPOSE 8787
CMD ["python", "server.py"]
