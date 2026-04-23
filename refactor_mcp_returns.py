import os
import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    
    # Target:
    # except Exception as e:
    #     return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    # Replace with:
    # except Exception as e:
    #     return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

    content = re.sub(
        r'except Exception as e:\s*return \[TextContent\(type="text",\s*text=f"Error:\s*\{str\(e\)\}"\)\]',
        r'except Exception as e:\n            import json\n            return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]',
        content
    )

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Refactored MCP returns in: {filepath}")
        return True
    return False

if __name__ == "__main__":
    count = 0
    for root, dirs, files in os.walk("."):
        if ".venv" in root or "__pycache__" in root or "node_modules" in root or ".gcloud" in root or "venv" in root:
            continue
        for file in files:
            if file == "mcp_server.py" or file == "mcp_app.py":
                filepath = os.path.join(root, file)
                if process_file(filepath):
                    count += 1
    print(f"Refactored {count} files.")
