with open("cv_api/pytest.log") as f:
    text = f.read()
    if "=========================== short test summary info ============================" in text:
        idx = text.find("=========================== short test summary info ============================")
        print(text[idx:])
