import re

with open('cv_api/test_main.py', 'r') as f:
    content = f.read()

content = content.replace("def override_get_db():", "async def override_get_db():")
content = re.sub(r'lambda: mock_db', 'lambda: mock_db', content)

with open('cv_api/test_main.py', 'w') as f:
    f.write(content)
