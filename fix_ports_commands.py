import re

with open('platform-engineering/terraform/cloudrun.tf', 'r') as f:
    text = f.read()

# 1. For `mcp` sidecar, inject `command = ["python"]` and `args = ["mcp_app.py"]` right after `name = "mcp"`
text = re.sub(
    r'(name\s*=\s*"mcp"\n\s*image\s*=\s*var\.default_image.*?)\n',
    r'\1\n      command = ["python"]\n      args = ["mcp_app.py"]\n',
    text
)

# 2. For `api` containers in ALL services (mcp, prompts, agent), they must bind to 8080.
# We inject `command = ["uvicorn"]` and `args = ["main:app", "--host", "0.0.0.0", "--port", "8080"]`
# We search for `name = "api"` and `image = var.default_image`
text = re.sub(
    r'(name\s*=\s*"api"\n\s*image\s*=\s*var\.default_image.*?)\n',
    r'\1\n      command = ["uvicorn"]\n      args = ["main:app", "--host", "0.0.0.0", "--port", "8080"]\n',
    text
)

with open('platform-engineering/terraform/cloudrun.tf', 'w') as f:
    f.write(text)

print("cloudrun.tf successfully updated with explicit container commands.")
