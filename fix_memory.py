import re

with open('platform-engineering/terraform/cloudrun.tf', 'r') as f:
    text = f.read()

# We need to add 'resources { limits = { memory = "1024Mi" } }' dynamically.
# It's actually easier to just add it inside the `containers { name = "api" ... }` block.
text = re.sub(
    r'(containers {\n\s*name\s*=\s*"api".*?\n)',
    r'\1      resources {\n        limits = {\n          memory = "1024Mi"\n        }\n      }\n',
    text,
    flags=re.DOTALL | re.MULTILINE
)

# Wait! The regex above is tricky with DOTALL.
