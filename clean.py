import subprocess
import re

out = subprocess.run(["python3", "-m", "flake8", "cv_api/src/cvs/routers/analytics_router.py", "--max-line-length=120", "--extend-ignore=W503"], capture_output=True, text=True)
lines_to_delete = []
for line in out.stdout.splitlines():
    if "F401" in line or "F811" in line:
        m = re.search(r'analytics_router\.py:(\d+):', line)
        if m:
            lines_to_delete.append(int(m.group(1)))

with open("cv_api/src/cvs/routers/analytics_router.py", "r") as f:
    content = f.readlines()

new_content = []
for i, line in enumerate(content):
    if i + 1 not in lines_to_delete:
        new_content.append(line)

with open("cv_api/src/cvs/routers/analytics_router.py", "w") as f:
    f.writelines(new_content)
