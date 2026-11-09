"""End-to-end plumbing in mock mode: every test case produces exactly 3 candidates."""
import os

os.environ["LLM_MODE"] = "mock"

from api.cases import case_to_request, load_cases  # noqa: E402
from api.pipeline.run import run_pipeline  # noqa: E402


def test_all_cases_run_in_mock_mode():
    cases = load_cases()
    assert len(cases) == 50
    for c in cases:
        resp = run_pipeline(case_to_request(c, use_screenshots=False))
        assert len(resp.candidates) == 3
        assert resp.meta["prompt_version"]


def test_api_endpoints():
    from fastapi.testclient import TestClient

    from api.main import app

    cl = TestClient(app)
    assert cl.get("/healthz").json()["ok"]
    assert len(cl.get("/v1/meta").json()["scenarios"]) == 6
    case = load_cases()[0]
    body = case_to_request(case, use_screenshots=False).model_dump()
    r = cl.post("/v1/generate", json=body)
    assert r.status_code == 200, r.text
    assert len(r.json()["candidates"]) == 3
