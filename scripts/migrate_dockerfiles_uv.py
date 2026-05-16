import os
import re

directories = [
    "users_api", "items_api", "competencies_api", "missions_api",
    "cv_api", "drive_api", "prompts_api", "agent_hr_api",
    "agent_ops_api", "agent_router_api", "agent_missions_api",
    "analytics_mcp", "monitoring_mcp"
]

def migrate_dockerfile(filepath, service_name):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    with open(filepath, "r") as f:
        content = f.read()
    
    # 1. Replace builder base image to include uv
    builder_start = r"FROM python:3.13-slim AS builder"
    uv_builder = "FROM python:3.13-slim AS builder\nCOPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/"
    content = content.replace(builder_start, uv_builder)

    # 2. Replace pip requirements installation with uv
    # Pattern to match the whole COPY requirements ... RUN pip wheel block
    old_pip_block_pattern = r"COPY " + service_name + r"/requirements\.txt \.\nRUN grep -v \"zenika-shared-schemas\" requirements\.txt > /tmp/req_public\.txt \\\n    && pip wheel --no-cache-dir --wheel-dir /app/wheels -r /tmp/req_public\.txt"
    
    uv_install_block = f"""COPY {service_name}/pyproject.toml {service_name}/uv.lock ./
RUN uv venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN uv pip install -r pyproject.toml"""
    
    content = re.sub(old_pip_block_pattern, uv_install_block, content, flags=re.MULTILINE)

    # 3. Handle Artifact registry block (zenika-shared-schemas)
    old_ar_block = r"RUN --mount=type=secret,id=ar_token \\\n    sh -c 'PIP_EXTRA_INDEX_URL=\"https://oauth2accesstoken:\$\(cat /run/secrets/ar_token\)@\$\{PYTHON_AR_REPO\}/simple/\" pip wheel --no-cache-dir --wheel-dir /app/wheels \"zenika-shared-schemas\$\{SHARED_VERSION:\+==\$SHARED_VERSION\}\"'"
    new_ar_block = r"""RUN --mount=type=secret,id=ar_token \
    sh -c 'UV_EXTRA_INDEX_URL="https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" uv pip install "zenika-shared-schemas${SHARED_VERSION:+==$SHARED_VERSION}"'"""
    
    content = re.sub(old_ar_block, new_ar_block, content, flags=re.MULTILINE)

    # 4. Handle agent_commons block (for agents)
    old_commons_block = r"RUN pip wheel --no-cache-dir --wheel-dir /app/wheels /agent_commons/"
    new_commons_block = r"RUN uv pip install /agent_commons/"
    content = content.replace(old_commons_block, new_commons_block)

    # 5. Runtime stage - ensure we do not run apt-get again if it's already there
    # the runtime stage is mostly correct since it copies /app/.venv

    with open(filepath, "w") as f:
        f.write(content)
    
    print(f"Migrated {filepath}")

for d in directories:
    migrate_dockerfile(f"{d}/Dockerfile", d)

