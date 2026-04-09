import re

with open('cv_api/test_main.py', 'r') as f:
    content = f.read()

content = content.replace(
    'def test_health():',
    'def test_health(mocker):\n    mocker.patch("database.check_db_connection", new=AsyncMock(return_value=True))'
)

with open('cv_api/test_main.py', 'w') as f:
    f.write(content)
