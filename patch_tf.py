import os
import re

path = "platform-engineering/terraform/cloudrun.tf"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

def replacer(match):
    block = match.group(0)
    block = re.sub(r"initial_delay_seconds\s*=\s*\d+", "initial_delay_seconds = 15", block)
    block = re.sub(r"failure_threshold\s*=\s*\d+", "failure_threshold     = 20", block)
    return block

# Match dynamic "startup_probe" { ... } blocks
# The regex looks for dynamic "startup_probe" and capturing everything until the inner http_get {
pattern = re.compile(r'dynamic "startup_probe" \{[\s\S]*?http_get \{')

new_content = pattern.sub(replacer, content)

with open(path, "w", encoding="utf-8") as f:
    f.write(new_content)
print("Patched startup_probe inside cloudrun.tf")
