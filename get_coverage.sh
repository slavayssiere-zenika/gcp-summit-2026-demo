#!/bin/bash
export PYTHONPATH=$PWD
echo "Coverage Report" > cov_summary.txt
for svc in users_api missions_api cv_api competencies_api items_api prompts_api agent_hr_api agent_missions_api agent_commons agent_router_api analytics_mcp drive_api agent_ops_api; do
  echo "Processing $svc..."
  cd $svc
  python3 -m pytest --cov=src --cov=./ --cov-report=term-missing > coverage_output.txt 2>&1
  # Get the TOTAL line
  total_line=$(grep "TOTAL" coverage_output.txt)
  echo "$svc: $total_line" >> ../cov_summary.txt
  cd ..
done
cat cov_summary.txt
