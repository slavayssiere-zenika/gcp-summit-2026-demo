import re

with open('platform-engineering/terraform/cloudrun.tf', 'r') as f:
    text = f.read()

# Revert MCP command
text = text.replace('      command = ["python"]\n      args = ["mcp_app.py"]\n', '')

# Revert API command
text = text.replace('      command = ["uvicorn"]\n      args = ["main:app", "--host", "0.0.0.0", "--port", "8080"]\n', '')

with open('platform-engineering/terraform/cloudrun.tf', 'w') as f:
    f.write(text)

