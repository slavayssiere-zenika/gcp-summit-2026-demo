import os
import re

dirs = ["users_api", "items_api", "competencies_api", "cv_api", "prompts_api", "drive_api"]

for d in dirs:
    path = os.path.join(d, "main.py")
    if not os.path.exists(path):
        continue
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Step 1: Add response: Response argument
    if "async def health():" in content:
        content = content.replace("async def health():", "async def health(response: Response):")
    
    # Step 2: Inject response.status_code = 503
    pattern = re.compile(r"(@app\.get\(\"/health\"\)\nasync def health\(response: Response\):\n\s+if await database\.check_db_connection\(\):\n\s+return \{\"status\": \"healthy\"\}\n)(\s+)(return \{\"status\": \"unhealthy\"\})", re.DOTALL)
    
    replacement = r"\1\2response.status_code = 503\n\2\3"
    new_content = pattern.sub(replacement, content)
    
    if content != new_content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Patched {path}")
    else:
        print(f"No regex match in {path}")
