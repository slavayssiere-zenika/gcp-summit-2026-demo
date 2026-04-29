#!/bin/bash
SERVICES=(
  "users_api" "missions_api" "cv_api" "competencies_api" "items_api" "prompts_api" "drive_api"
  "agent_router_api" "agent_hr_api" "agent_ops_api" "agent_missions_api"
  "analytics_mcp" "agent_commons"
)

echo "# Test and Coverage Report" > test_report.txt

for service in "${SERVICES[@]}"; do
  if [ -d "$service" ]; then
    echo "======================================" >> test_report.txt
    echo "Service: $service" >> test_report.txt
    echo "======================================" >> test_report.txt
    
    cd "$service"
    
    # Check if there are any test files
    if ls test_*.py 1> /dev/null 2>&1 || ls tests/test_*.py 1> /dev/null 2>&1; then
      export PYTHONPATH=$PWD
      python3 -m pytest --cov=src --cov=./ --cov-report=term-missing 2>&1 | tee -a ../test_report.txt
      echo "Exit code: ${PIPESTATUS[0]}" >> ../test_report.txt
    else
      echo "No tests found." >> ../test_report.txt
    fi
    
    cd ..
  fi
done
