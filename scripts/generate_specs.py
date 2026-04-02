import subprocess
import os
import sys

apis = ["agent_api", "competencies_api", "cv_api", "drive_api", "items_api", "prompts_api", "users_api"]

extractor_code = """
import os
import sys

try:
    # Set pythonpath to current and parent to avoid shadow imports and allow absolute imports
    sys.path.insert(0, os.getcwd())
    sys.path.insert(0, os.path.dirname(os.getcwd()))
    try:
        from main import app
    except ImportError:
        from src.main import app
    schema = app.openapi()
    
    md_lines = ["\\n## 📡 Schema OpenAPI Auto-Généré\\n"]
    for path, methods in schema.get("paths", {}).items():
        for method, details in methods.items():
            summary = details.get("summary", "")
            md_lines.append(f"- **{method.upper()}** `{path}` : {summary}")
            
    md_block = "\\n".join(md_lines)
    
    spec_file = "spec.md"
    content = ""
    if os.path.exists(spec_file):
        with open(spec_file, "r") as f:
            content = f.read()
    
    if "## 📡 Schema OpenAPI Auto-Généré" in content:
        content = content.split("## 📡 Schema OpenAPI Auto-Généré")[0]
        
    with open(spec_file, "w") as f:
        f.write(content.strip() + "\\n" + md_block + "\\n")
    print(f"✅ Spec generated for {os.path.basename(os.getcwd())}")
except Exception as e:
    print(f"❌ Error generating spec for {os.getcwd()}: {e}")
    sys.exit(1)
"""

failed = False
for api in apis:
    if not os.path.isdir(api):
        continue
    # Use the test_env python path which has the fastapi libs
    p = subprocess.run(["../test_env/bin/python", "-c", extractor_code], cwd=api)
    if p.returncode != 0:
        failed = True

if failed:
    sys.exit(1)
