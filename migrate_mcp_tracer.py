import re
import os

files_to_fix = [
    ("competencies_api/mcp_server.py", "competencies-api-mcp"),
    ("drive_api/mcp_server.py", "drive-api-mcp"),
    ("prompts_api/mcp_server.py", "prompts-api-mcp")
]

for file_path, service_name in files_to_fix:
    with open(file_path, "r") as f:
        content = f.read()

    # The pattern to match:
    # sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
    # ... down to ...
    # tracer = trace.get_tracer(__name__)
    pattern = r"sampling_rate\s*=\s*float\([^)]*\).*?tracer\s*=\s*trace\.get_tracer\([^)]*\)"
    replacement = f"tracer = setup_mcp_tracer_provider(\"{service_name}\")"

    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # We also need to add the import `from shared.mcp_server_utils import setup_mcp_tracer_provider` if it's missing.
    if "setup_mcp_tracer_provider" not in new_content:
        # Not needed for competencies_api/mcp_server.py because it already imports it!
        # Let's add it near `from mcp.server import`
        new_content = re.sub(r"(from mcp\.server import)", r"from shared.mcp_server_utils import setup_mcp_tracer_provider\n\1", new_content, count=1)
    
    with open(file_path, "w") as f:
        f.write(new_content)
    
    print(f"Fixed {file_path}")
