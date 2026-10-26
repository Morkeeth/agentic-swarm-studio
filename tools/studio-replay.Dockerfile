FROM python:3.12-slim
WORKDIR /app
COPY sim ./sim
COPY web/studio ./web/studio
ENV PORT=8080
USER 65534:65534
CMD ["sh", "-c", "exec python -m sim.swarm_studio --store /tmp/swarm-replays --host 0.0.0.0 --port ${PORT:-8080}"]
