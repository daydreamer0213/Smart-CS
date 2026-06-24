"""Sliding window memory tests."""

from app.core.conversation.memory import count_tokens, build_context


def test_count_tokens():
    messages = [{"role": "user", "content": "hello"}]
    assert count_tokens(messages) > 0


def test_build_context_within_limits():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    result = build_context(history, max_tokens=2000, max_turns=10)
    assert len(result) == 2


def test_build_context_trims_old_turns():
    history = []
    for i in range(20):
        history.append({"role": "user", "content": f"message {i}"})
        history.append({"role": "assistant", "content": f"response {i}"})
    result = build_context(history, max_tokens=2000, max_turns=3)
    assert len(result) <= 6  # 3 turns = 6 messages max
    # Should contain most recent messages
    assert history[-1]["content"] in [m["content"] for m in result]


def test_empty_history():
    assert build_context([], max_tokens=2000, max_turns=10) == []
