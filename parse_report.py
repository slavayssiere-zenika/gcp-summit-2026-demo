with open("test_report.txt", "r") as f:
    content = f.read()

services = content.split("======================================\nService: ")
for s in services[1:]:
    if s.startswith("cv_api"):
        print(s)
