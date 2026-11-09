import os

os.environ["LLM_MODE"] = "mock"
os.environ.pop("API_URL", None)


def test_web_generate_flow():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(__import__("pathlib").Path(__file__).resolve().parent.parent / "web" / "app.py"), default_timeout=30).run()
    assert not at.exception
    at.selectbox[0].select_index(1).run()
    at.button[0].click().run()  # 载入
    assert at.session_state["name"]
    gen = next(b for b in at.button if b.label == "生成 3 条话术")
    gen.click().run()
    assert not at.exception
    assert len(at.session_state["result"]["candidates"]) == 3
