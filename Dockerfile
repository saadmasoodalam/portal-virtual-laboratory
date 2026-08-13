FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       python3.12 \
       python3-pip \
       python3-venv \
       gmsh \
       getdp \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . /workspace

RUN python3.12 -m pip install --break-system-packages -e '.[dev]'

CMD ["python3.12", "-m", "pytest"]
