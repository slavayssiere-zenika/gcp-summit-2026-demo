import re
import os

with open("competencies_api/mcp_server.py", "r") as f:
    content = f.read()

# match everything from "@server.call_tool()" to the end
match = re.search(r"@server\.call_tool\(\).*$", content, re.DOTALL)
if match:
    call_tool_body = match.group(0)
    
    # regex to find blocks
    blocks = re.split(r'\n\s+(?:el)?if name == "(.*?)":', call_tool_body)
    
    # blocks[0] is preamble
    # blocks[1] is name, blocks[2] is code...
    
    tools_code = {}
    
    for i in range(1, len(blocks), 2):
        name = blocks[i]
        code = blocks[i+1]
        
        # fix indentation
        lines = code.split("\n")
        
        # skip lines before try or something? no, the code is standard.
        # it might have empty lines or comments.
        
        # let's just create a function for each
        func_code = f"""
async def handle_{name}(client, arguments: dict, headers: dict, api_base_url: str):
"""
        
        # remove extra indent
        for line in lines:
            if line.startswith("                "):
                func_code += line[12:] + "\n"
            elif line.startswith("            "):
                func_code += line[12:] + "\n"
            elif line.strip():
                func_code += "    " + line.strip() + "\n"
            else:
                func_code += "\n"
                
        # if there are returns that do not use TextContent... wait, they all use TextContent, so we need imports.
        tools_code[name] = func_code
        
    print(f"Extracted {len(tools_code)} tools.")
    
    import json
    with open("tools_extracted.json", "w") as f:
        json.dump(tools_code, f, indent=2)

