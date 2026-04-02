import re
import os

services = ['users_api', 'items_api', 'competencies_api', 'cv_api', 'prompts_api']

for svc in services:
    # 1. database.py
    for fname in [f"{svc}/database.py", f"{svc}/database.py"]:
        if os.path.exists(fname):
            with open(fname, "r") as f:
                content = f.read()
            # remove def init_db():... to end of file if it's there
            content = re.sub(r'\n+def init_db\(\):[\s\S]*', '', content)
            if 'init_db' in content: 
                print(f"Warning: init_db still in {fname}")
            with open(fname, "w") as f:
                f.write(content)
                
    # 2. main.py
    main_file = f"{svc}/main.py"
    if os.path.exists(main_file):
        with open(main_file, "r") as f:
            content = f.read()
            
        content = re.sub(r'\n+background_tasks = set\(\)\n*', '\n\n', content)
        content = re.sub(r'\n+def safe_init_db\(\):[\s\S]*?(?=\n@app\.on_event)', '\n\n', content)
        content = re.sub(r'\n+@app\.on_event\("startup"\)\nasync def startup_event\(\):[\s\S]*?(?=\nFastAPIInstrumentor|\nSQLAlchemyInstrumentor|\napp\.include_router)', '\n\n', content)
        content = content.replace("from database import engine, init_db", "from database import engine")
        
        with open(main_file, "w") as f:
            f.write(content)
        print(f"Patched {main_file}")

