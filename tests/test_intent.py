"""Intent classifier tests."""

import pytest
from app.core.intent.classifier import classify_intent, IntentOutput


async def test_rule_human_keyword_match():
    intent, source, confidence = await classify_intent(
        user_input="我要投诉你们",
        human_keywords=["投诉", "退款"],
        retrieval_results=[],
        llm_client=None,
    )
    assert intent == "human"
    assert source == "rule_human"
    assert confidence == 1.0


async def test_rule_faq_when_has_results():
    intent, source, confidence = await classify_intent(
        user_input="退货要几天",
        human_keywords=["投诉"],
        retrieval_results=[{"doc_id": "1", "score": 0.9}],
        llm_client=None,
    )
    assert intent == "faq"
    assert source == "rule_faq"
    assert confidence == 0.8


async def test_fallback_when_no_match_no_results_no_llm():
    intent, source, confidence = await classify_intent(
        user_input="今天天气怎么样",
        human_keywords=["投诉"],
        retrieval_results=[],
        llm_client=None,
    )
    assert intent == "human"
    assert source == "llm"
    assert confidence == 0.0


async def test_llm_classifier_called(mocker):
    # Mock LLM client that returns faq with high confidence
    mock_llm = mocker.AsyncMock()
    mock_llm.chat_structured.return_value = IntentOutput(intent="faq", confidence=0.9)

    intent, source, confidence = await classify_intent(
        user_input="什么尺码合适",
        human_keywords=["投诉"],
        retrieval_results=[],  # no results, forces LLM path
        llm_client=mock_llm,
        confidence_threshold=0.6,
    )
    assert intent == "faq"
    assert source == "llm"
    assert confidence == 0.9
    mock_llm.chat_structured.assert_called_once()
