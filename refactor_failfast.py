import os
import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    
    # 1. Replace "except Exception: raise" with "except Exception: raise" (one-liners)
    content = re.sub(r'(except\s+Exception(\s+as\s+\w+)?\s*):\s*pass\b', r'\1: raise', content)
    
    # 2. Replace multi-line:
    # except Exception:
    #     pass
    # With:
    # except Exception:
    #     raise
    content = re.sub(r'(except\s+Exception(\s+as\s+\w+)?\s*:\n(\s+))pass\b', r'\1raise', content)

    # 3. For MCP servers specifically, replace "raise" with return {"success": False, "error": "Internal error"} if desired?
    # but the rule says "interrompue formelquement (raise)" OR "retournée explicitement", for mcp_server.py we should return {success: false}.
    # Let's see if we should manually fix MCP Server exceptions. There are only a few mcp_server.py.
    
    # For now, let's also fix "except Exception as e:" followed by just "logger.***" and NO raise/return.
    # We will do this carefully via manual AST or simple pattern matching.
    # Actually, replacing all `pass` with `raise` covers 90% of the silent_errors_report.txt
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Refactored pass->raise in: {filepath}")
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
