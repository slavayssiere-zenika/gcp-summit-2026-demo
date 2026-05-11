import json
import os
import httpx
import urllib.parse

def main():
    token_path = os.path.expanduser("~/.cache/zenika_mcp_cli_token.json")
    with open(token_path, "r") as f:
        data = json.load(f)
        token = data["token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "https://prd.zenika.slavayssiere.fr/api/prompts"
    
    response = httpx.get(f"{base_url}/?limit=500", headers=headers)
    response.raise_for_status()
    prompts = response.json().get("prompts", [])
    
    error_prompts = [p for p in prompts if p["key"].startswith("error_correction:")]
    
    report_lines = ["# SRE Report\n"]
    for p in error_prompts:
        try:
            val = json.loads(p["value"])
            report_lines.append(f"## {p['key']}")
            report_lines.append(f"**Service**: {val.get('service')}")
            report_lines.append(f"**Original Error**: {val.get('original_error')}")
            report_lines.append(f"**Rule**: {val.get('rule')}")
            report_lines.append(f"**Context**: ```\n{val.get('context')}\n```\n")
        except:
            report_lines.append(f"## {p['key']}")
            report_lines.append(f"**Value**: {p['value']}\n")
            
    with open("sre_report.md", "w") as f:
        f.write("\n".join(report_lines))
        
    print(f"Generated sre_report.md with {len(error_prompts)} errors.")

if __name__ == "__main__":
    main()
