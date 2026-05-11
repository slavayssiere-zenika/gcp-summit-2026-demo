import re
import os

with open("cv_api/tests/test_main.py", "r") as f:
    content = f.read()

# Define the preamble
preamble = """import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from database import get_db
from fastapi.testclient import TestClient
from main import app
from src.auth import security, verify_jwt
from src.cvs.schemas import CVImportStep, CVResponse
from src.cvs.models import CVProfile

os.environ['SECRET_KEY'] = 'testsecret'

async def override_get_db():
    db = AsyncMock()
    yield db

def override_verify_jwt():
    return {"sub": "test", "role": "admin"}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt
app.dependency_overrides[security] = lambda: MagicMock(credentials="testtoken")

client = TestClient(app)
"""

analytics_funcs = [
    "test_recalculate_tree",
    "test_recalculate_tree_no_auth",
    "test_recalculate_tree_bad_token",
    "test_recalculate_tree_not_admin",
    "test_recalculate_tree_no_client",
    "test_recalculate_tree_already_running",
    "test_reanalyze_returns_json_immediately",
    "test_reanalyze_url_without_google_doc_id",
    "test_reanalyze_drive_api_unavailable_degraded",
    "test_reanalyze_no_cvs_in_db",
    "test_reanalyze_status_proxies_drive_api",
    "test_reanalyze_not_admin",
    "_make_extraction_scores_mocks",
    "test_extraction_scores_calculated",
    "test_extraction_scores_uncalculated",
    "test_extraction_scores_users_api_failure",
    "_make_reanalyze_mocks"
]

search_funcs = [
    "test_search_candidates",
    "test_search_candidates_no_client",
    "test_search_candidates_embed_fail"
]

import_funcs = [
    "test_import_and_analyze_cv",
    "test_import_cv_steps_on_truncated_document",
    "test_import_cv_steps_on_zero_competencies",
    "test_import_cv_steps_structure",
    "test_cv_response_has_steps_and_warnings",
    "test_fetch_cv_content_internal_url",
    "test_fetch_cv_content_invalid_scheme",
    "test_import_cv_no_auth",
    "test_import_cv_genai_not_configured",
    "test_import_cv_prompt_fail",
    "test_import_cv_not_a_cv_boolean_check",
    "_make_full_import_mocks",
    "test_import_cv_with_folder_name_zenika_nomenclature",
    "test_import_cv_folder_name_priority_over_llm",
    "test_import_cv_folder_name_single_word_ignored",
    "test_import_cv_without_folder_name_llm_fallback",
    "test_import_cv_schema_folder_name_optional"
]

def extract_funcs(content, funcs):
    extracted = ""
    for func in funcs:
        pattern = r"(def " + func + r"\(.*?\):(?:\n(?:(?:[ \t]+.*)|(?:)))+)"
        match = re.search(pattern, content)
        if match:
            extracted += match.group(1) + "\n\n"
            content = content.replace(match.group(1), "")
    return content, extracted

content, analytics_code = extract_funcs(content, analytics_funcs)
content, search_code = extract_funcs(content, search_funcs)
content, import_code = extract_funcs(content, import_funcs)

with open("cv_api/tests/test_analytics_router.py", "w") as f:
    f.write(preamble + "\n" + analytics_code)

with open("cv_api/tests/test_search_router.py", "w") as f:
    f.write(preamble + "\n" + search_code)

with open("cv_api/tests/test_import_router.py", "w") as f:
    f.write(preamble + "\n" + import_code)

with open("cv_api/tests/test_main.py", "w") as f:
    f.write(content)

print("Split completed successfully!")
