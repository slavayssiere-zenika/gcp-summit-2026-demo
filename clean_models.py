import os
import re

directories = ["cv_api/src", "competencies_api/src", "missions_api/src", "prompts_api/src"]

# Regex: match os.getenv("VAR_NAME", "gemini-...") or os.getenv('VAR_NAME', 'gemini-...')
pattern = re.compile(r"""os\.getenv\((['"])([^'"]+)\1,\s*(['"])gemini-[^'"]+\3\)""")

files_modified = 0

for d in directories:
    for root, dirs, files in os.walk(d):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r") as file:
                    content = file.read()
                
                new_content, count = pattern.subn(r"os.getenv(\1\2\1)", content)
                if count > 0:
                    with open(path, "w") as file:
                        file.write(new_content)
                    print(f"Cleaned {count} occurrences in {path}")
                    files_modified += 1

print(f"Total files modified: {files_modified}")
