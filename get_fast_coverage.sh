#!/bin/bash
export PYTHONPATH=$PWD
echo "Coverage Report" > cov_summary.txt
for svc in users_api missions_api cv_api competencies_api items_api prompts_api agent_hr_api agent_missions_api agent_commons agent_router_api analytics_mcp drive_api agent_ops_api; do
  echo "Processing $svc..."
  cd $svc
  ignore_arg=""
  if [ -f "tests/test_contract.py" ]; then
    ignore_arg="--ignore=tests/test_contract.py"
  fi
  python3 -m pytest --cov=src --cov=./ $ignore_arg --cov-report=term-missing > coverage_output.txt 2>&1
  total_line=$(grep "TOTAL" coverage_output.txt)
  echo "$svc: $total_line" >> ../cov_summary.txt
  cd ..
done
cat cov_summary.txt
