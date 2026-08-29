import json
from unittest.mock import Mock, patch

import pytest
import requests

from summary_extraction import extract_qa_pairs
from task_extraction import LLMCallError, LLMResponseParseError


def _mock_groq_response(content_dict):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(content_dict)}}]
    }
    return mock_resp


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_returns_parsed_items(mock_post):
    mock_post.return_value = _mock_groq_response(
        {
            "items": [
                {
                    "question": "Когда релиз?",
                    "answer": "В пятницу",
                    "quote": "релиз в пятницу",
                }
            ]
        }
    )

    items = extract_qa_pairs("транскрипт...", api_key="fake")

    assert items == [
        {"question": "Когда релиз?", "answer": "В пятницу", "quote": "релиз в пятницу"}
    ]


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_returns_empty_list_when_nothing_substantive(mock_post):
    mock_post.return_value = _mock_groq_response({"items": []})

    items = extract_qa_pairs("привет, как дела", api_key="fake")

    assert items == []


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_llm_call_error_on_network_failure(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")

    with pytest.raises(LLMCallError):
        extract_qa_pairs("транскрипт", api_key="fake")


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_parse_error_on_invalid_json_content(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "не json"}}]}
    mock_post.return_value = mock_resp

    with pytest.raises(LLMResponseParseError):
        extract_qa_pairs("транскрипт", api_key="fake")


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_parse_error_when_answer_is_not_a_string(mock_post):
    mock_post.return_value = _mock_groq_response(
        {"items": [{"question": "Когда релиз?", "answer": None, "quote": "релиз в пятницу"}]}
    )

    with pytest.raises(LLMResponseParseError):
        extract_qa_pairs("транскрипт", api_key="fake")


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_parse_error_when_items_is_not_a_list(mock_post):
    mock_post.return_value = _mock_groq_response({"items": "not a list"})

    with pytest.raises(LLMResponseParseError):
        extract_qa_pairs("транскрипт", api_key="fake")
