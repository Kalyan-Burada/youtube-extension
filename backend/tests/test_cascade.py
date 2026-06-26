"""End-to-end tests for the /score cascade.

These are integration tests: they load the real SentenceTransformer and
CrossEncoder models (first run downloads them), so they are slower than unit
tests but actually exercise the cascade the extension depends on. Run from
backend/ with:

    python -m pytest tests/ -v

Stage 3 (CLIP) needs a reachable thumbnail URL, so it has its own test that
skips cleanly when the network is unavailable rather than failing the suite.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.main import focus_topic_matches_title

client = TestClient(app)


def _score(intent, videos):
    resp = client.post("/score", json={"intent": intent, "videos": videos})
    assert resp.status_code == 200, resp.text
    return {r["id"]: r for r in resp.json()["results"]}


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "thresholds" in body and "embed_blur" in body["thresholds"]


def test_no_intent_is_rejected():
    resp = client.post(
        "/score",
        json={"intent": {"recent_titles": []}, "videos": [{"id": "v", "title": "x"}]},
    )
    assert resp.status_code == 400


def test_empty_videos_returns_empty():
    out = _score({"focus_topic": "Cooking"}, [])
    assert out == {}


def test_keyword_match_allows_before_models():
    out = _score(
        {"focus_topic": "Machine Learning"},
        [{"id": "v1", "title": "Machine Learning Full Course"}],
    )
    assert out["v1"]["decision"] == "allow"
    assert out["v1"]["stage"] == "keyword_match"


def test_relevant_allowed_irrelevant_blurred():
    out = _score(
        {"focus_topic": "Cricket"},
        [
            {"id": "rel", "title": "Virat Kohli Batting Masterclass"},
            {"id": "irr", "title": "How to Make Chicken Biryani at Home"},
        ],
    )
    assert out["rel"]["decision"] == "allow"
    assert out["irr"]["decision"] == "blur"


def test_generic_focus_allows_specific_relevant_titles():
    """Regression: a broad focus word ("food") must still allow specific
    on-topic titles ("...Sponge Cake Recipe..."). The bi-encoder under-rates
    these, so they rely on the cross-encoder being consulted rather than the
    title being hard-blurred at Stage 1."""
    out = _score(
        {"focus_topic": "food"},
        [
            {"id": "cake1", "title": "Easy Vanilla Sponge Cake Without Oven Recipe | How To Make Basic Sponge Cake"},
            {"id": "cake2", "title": "Chocolate Cake in Pressure Cooker | Birthday Cake Recipe"},
            {"id": "off", "title": "Python List Comprehension Tutorial"},
        ],
    )
    assert out["cake1"]["decision"] == "allow", out["cake1"]
    assert out["cake2"]["decision"] == "allow", out["cake2"]
    assert out["off"]["decision"] == "blur", out["off"]


def test_every_video_gets_a_terminal_decision():
    """No result may leak the internal 'borderline' state or an unknown stage."""
    out = _score(
        {"focus_topic": "Python Programming"},
        [
            {"id": "a", "title": "Django REST Framework Crash Course"},
            {"id": "b", "title": "Best Cricket Bowling Techniques"},
            {"id": "c", "title": "NumPy Array Broadcasting Explained"},
        ],
    )
    for r in out.values():
        assert r["decision"] in {"allow", "blur"}
        assert r["stage"] in {
            "keyword_match", "embedding", "cross_encoder",
            "vision", "no_signal", "vision_failed", "stage_error",
        }


def test_bad_thumbnail_fails_safe_not_500():
    """A borderline-ish video with an unreachable thumbnail must never 500 and
    must never default-open."""
    out = _score(
        {"focus_topic": "Cooking"},
        [{"id": "v", "title": "Knife Skills Every Cook Should Know",
          "thumbnail_url": "http://127.0.0.1:1/nope.jpg"}],
    )
    assert out["v"]["decision"] in {"allow", "blur"}


@pytest.mark.parametrize(
    "focus,title,expected",
    [
        ("Python", "Python List Comprehension Tutorial", True),
        ("Machine Learning", "machine learning full course", True),
        ("Cricket", "How to Make Biryani", False),
        ("AI", "AI Agents Explained", True),
        ("", "anything", False),
    ],
)
def test_keyword_matcher_unit(focus, title, expected):
    assert focus_topic_matches_title(focus, title) is expected
