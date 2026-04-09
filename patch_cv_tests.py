import re

with open('cv_api/test_main.py', 'r') as f:
    content = f.read()

# Replace test_get_user_cv
content = re.sub(
    r'mock_db = MagicMock\(\)\s*mock_profile = MagicMock\(user_id=1, source_url="http://test.com/cv.pdf"\)\s*mock_db\.query\(\)\.filter\(\)\.first\.return_value = mock_profile',
    '''mock_db = AsyncMock()
    mock_profile = MagicMock(user_id=1, source_url="http://test.com/cv.pdf")
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_profile
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result''',
    content
)

# test_get_user_cv Not found case
content = re.sub(
    r'mock_db\.query\(\)\.filter\(\)\.first\.return_value = None',
    'mock_scalars.first.return_value = None',
    content
)

# test_search_candidates
content = re.sub(
    r'mock_db = MagicMock\(\)\s*# Mock Gemini embedding\s*emb_res = MagicMock\(\)\s*emb_res\.embeddings = \[MagicMock\(values=\[0\.1, 0\.2, 0\.3\]\)\]\s*mock_genai\.models\.embed_content\.return_value = emb_res\s*# Mock Database cosine response\s*mock_db\.query\(\)\.filter\(\)\.order_by\(\)\.limit\(\)\.all\.return_value = \[\s*\(MagicMock\(user_id=1\), 0\.1\),\s*\(MagicMock\(user_id=2\), 0\.4\)\s*\]',
    '''mock_db = AsyncMock()
    # Mock Gemini embedding
    emb_res = MagicMock()
    emb_res.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]
    mock_genai.models.embed_content.return_value = emb_res
    
    # Mock Database cosine response
    mock_result = MagicMock()
    mock_result.all.return_value = [(MagicMock(user_id=1), 0.1), (MagicMock(user_id=2), 0.4)]
    mock_db.execute.return_value = mock_result''',
    content
)


# test_import_and_analyze_cv
content = re.sub(
    r'mock_db = MagicMock\(\)',
    'mock_db = AsyncMock()',
    content
)

# test_recalculate_tree
content = re.sub(
    r'mock_profile = MagicMock\(raw_content="My CV content"\)\s*mock_db\.query\(\)\.all\.return_value = \[mock_profile\]',
    '''mock_profile = MagicMock(raw_content="My CV content")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_profile]
    mock_db.execute.return_value = mock_result''',
    content
)

# test_recalculate_tree_no_profiles
content = re.sub(
    r'mock_db\.query\(\)\.all\.return_value = \[\]',
    '''mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result''',
    content
)

with open('cv_api/test_main.py', 'w') as f:
    f.write(content)
