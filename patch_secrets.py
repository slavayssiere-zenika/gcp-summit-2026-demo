import os

files = ['cv_api/test_main.py', 'drive_api/tests/test_router.py', 'cv_api/test_mcp_app.py', 'cv_api/test_mcp_tools.py', 'drive_api/tests/test_mcp_app.py']

for f_path in files:
    if os.path.exists(f_path):
        with open(f_path, 'r') as f:
            content = f.read()
            if "SECRET_KEY" not in content:
                content = "import os\nos.environ['SECRET_KEY'] = 'testsecret'\n" + content
        with open(f_path, 'w') as f:
            f.write(content)
