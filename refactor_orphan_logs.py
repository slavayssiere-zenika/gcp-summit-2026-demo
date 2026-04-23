import os
import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    
    # regex to find: except Exception as e:\n  ... logging.error(...) blocks that do not have `raise` or `return` inside them
    # But since regex for this is complex, we'll just search for `logging.error(f"Failed to report error` which is what we just injected.
    
    # Let's replace the inject_error_handlers.py generated logging.error with raise
    content = re.sub(
        r'(except Exception as e:\s*logging\.error\(f"Failed to report error to prompts_api: \{e\}"\))',
        r'\1\n            raise e',
        content
    )
    
    # Also in agent.py
    # except Exception as e:
    #     logger.error(f"[FinOps] Failed to log usage to BQ: {e}")
    content = re.sub(
        r'(except Exception as e:\s*logger\.error\(f"\[FinOps\] Failed to log usage to BQ: \{e\}"\))',
        r'\1\n                        raise e',
        content
    )

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Refactored orphan log in: {filepath}")
        return True
    return False

if __name__ == "__main__":
    count = 0
    for root, dirs, files in os.walk("."):
        if ".venv" in root or "__pycache__" in root or "node_modules" in root or ".gcloud" in root or "venv" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if process_file(filepath):
                    count += 1
    print(f"Refactored {count} files.")
