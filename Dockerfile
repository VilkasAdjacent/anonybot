FROM python:3.11
COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /bin/uv
WORKDIR /bot
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version /bot/
RUN uv sync --locked --no-dev
COPY . /bot
CMD ["uv", "run", "--no-sync", "anonybot.py"]
