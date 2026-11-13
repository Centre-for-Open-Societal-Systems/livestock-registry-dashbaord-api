FROM python:3.11-slim
WORKDIR /src
COPY requirements.txt requirements-dev.txt ./
RUN python -m pip install --no-cache-dir -r requirements-dev.txt && python -m pip check
COPY pyproject.toml ./
COPY app/ app/
COPY tests/ tests/
COPY ci/ ci/
CMD ["bash", "ci/validate.sh"]
