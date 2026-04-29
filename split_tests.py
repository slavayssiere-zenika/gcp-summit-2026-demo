import os

with open("/tmp/test_main_dump.py", "r") as f:
    lines = f.readlines()

crud_lines = []
analysis_lines = []

# common header
header = []
for i in range(24):
    header.append(lines[i])

# Basic Tests to test_list_missions
for i in range(24, 68):
    crud_lines.append(lines[i])

# Mock fixtures for analysis
analysis_header = []
for i in range(44, 55):
    analysis_header.append(lines[i])

# Analysis tests
for i in range(68, 279):
    analysis_lines.append(lines[i])

# Staffing tests to end
for i in range(279, len(lines)):
    crud_lines.append(lines[i])

with open("missions_api/test_crud.py", "w") as f:
    f.writelines(header + crud_lines)

with open("missions_api/test_analysis.py", "w") as f:
    f.writelines(header + analysis_header + analysis_lines)

