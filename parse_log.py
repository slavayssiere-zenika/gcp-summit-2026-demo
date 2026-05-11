import json

with open("/Users/sebastien.lavayssiere/.gemini/antigravity/brain/1c88f9e4-baa3-4dc9-8acd-3429ddffdfc3/.system_generated/logs/overview.txt", "r") as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "def get_extraction_scores" in content:
                print(content)
                break
        except:
            pass
