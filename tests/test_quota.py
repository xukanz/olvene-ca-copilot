import os
from pathlib import Path

import pytest

os.environ["LLM_MODE"] = "mock"
os.environ.pop("API_URL", None)

APP = str(Path(__file__).resolve().parent.parent / "web" / "app.py")


def test_memory_quota_per_user_and_global(monkeypatch):
    import web.quota as q

    monkeypatch.setattr(q, "USER_DAILY_LIMIT", 2)
    monkeypatch.setattr(q, "GLOBAL_DAILY_LIMIT", 3)
    m = q._MemoryQuota()
    m.consume("a@x.com")
    m.consume("a@x.com")
    with pytest.raises(q.QuotaExceeded):
        m.consume("a@x.com")  # per-user cap
    m.consume("b@x.com")
    with pytest.raises(q.QuotaExceeded):
        m.consume("c@x.com")  # global cap
    assert m.used("a@x.com") == (2, 3)


def test_login_required_blocks_app(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("REQUIRE_LOGIN", "1")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert [b.label for b in at.button] == ["使用 Google 登录"]
    assert "生成 3 条话术" not in [b.label for b in at.button]


def test_quota_exceeded_shows_warning(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import web.quota as q

    monkeypatch.setattr(q, "_quota", q._MemoryQuota())
    monkeypatch.setattr(q, "USER_DAILY_LIMIT", 1)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox[0].select("S6-02").run()
    gen = lambda: next(b for b in at.button if b.label == "生成 3 条话术")  # noqa: E731
    gen().click().run()
    assert len(at.session_state["result"]["candidates"]) == 3
    gen().click().run()
    assert not at.exception
    assert any("额度已用完" in w.value for w in at.warning)


def test_privacy_page_is_public(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("REQUIRE_LOGIN", "1")
    at = AppTest.from_file(str(Path(APP).parent / "pages" / "privacy.py"), default_timeout=30).run()
    assert not at.exception
    assert "隐私说明" in at.markdown[0].value
