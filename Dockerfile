FROM python:3.12-slim
WORKDIR /app
COPY sim ./sim
COPY web ./web
ENV PORT=8080
USER 65534:65534
# STUDIO_EXPLAIN=1 turns on the Ask Nemotron button; it needs TOKEN_FACTORY_API_KEY. Without it the page is replay-only.
CMD ["sh", "-c", "exec python -m sim.swarm_studio --store /tmp/swarm-replays --host 0.0.0.0 --port ${PORT:-8080} ${STUDIO_EXPLAIN:+--allow-explain}"]
