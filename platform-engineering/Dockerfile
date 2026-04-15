# ==========================================
# Builder Stage: Fetch Terraform & deps
# ==========================================
FROM google/cloud-sdk:slim AS builder

ENV TERRAFORM_VERSION="1.7.5"
RUN apt-get update && apt-get install -y wget unzip \
    && wget https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip \
    && unzip terraform_${TERRAFORM_VERSION}_linux_amd64.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/terraform

# Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt --target=/tmp/deps

# ==========================================
# Final Stage: Run as non-root
# ==========================================
FROM google/cloud-sdk:slim

# Create non-root user
RUN useradd -m -s /bin/bash appuser

# Copy Terraform from builder
COPY --from=builder /usr/local/bin/terraform /usr/local/bin/terraform

# Copy Python dependencies from builder
COPY --from=builder /tmp/deps /usr/lib/python3/dist-packages/

# Set working directory
WORKDIR /app

# Switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Copy application files
COPY --chown=appuser:appuser . /app/

# On Cloud Run Job, args are overridden by the execute command, but we provide a default ENTRYPOINT
ENTRYPOINT ["python3", "manage_env.py"]
CMD ["-h"]
