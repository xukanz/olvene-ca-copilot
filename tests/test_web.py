import os

os.environ["LLM_MODE"] = "mock"
os.environ.pop("API_URL", None)


def test_web_generate_flow():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(__import__("pathlib").Path(__file__).resolve().parent.parent / "web" / "app.py"), default_timeout=30).run()
    assert not at.exception
    at.selectbox[0].select("S6-02").run()  # selecting a case fills the form, no button
    assert not at.exception
    assert next(w for w in at.text_input if w.label == "称呼").value == "潘女士"
    assert at.selectbox(key="scenario").value == "price_objection"
    assert len(at.session_state["dialog_df"]) > 0
    gen = next(b for b in at.button if b.label == "生成 3 条话术")
    gen.click().run()
    assert not at.exception
    assert len(at.session_state["result"]["candidates"]) == 3
