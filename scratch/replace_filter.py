import os
import glob

old_code = """    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(
            f'"GET {p} ' in msg or f'"POST {p} ' in msg or
            f'"HEAD {p} ' in msg or f'"OPTIONS {p} ' in msg
            for p in SILENT_PATHS
        )"""

new_code = """    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if not msg:
            req_line = getattr(record, "request_line", "")
            if req_line:
                msg = f'"{req_line}"'
        return not any(
            f'"GET {p} ' in msg or f'"POST {p} ' in msg or
            f'"HEAD {p} ' in msg or f'"OPTIONS {p} ' in msg
            for p in SILENT_PATHS
        )"""

for root, dirs, files in os.walk("/Users/sebastien.lavayssiere/Code/test-open-code"):
    if "scratch" in root:
        continue
    for file in files:
        if file == "logger.py":
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            if old_code in content:
                print(f"Replacing in {path}")
                content = content.replace(old_code, new_code)
                with open(path, "w") as f:
                    f.write(content)
