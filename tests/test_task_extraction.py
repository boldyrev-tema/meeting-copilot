import json
from unittest.mock import Mock, patch

import pytest
import requests

from task_extraction import LLMCallError, LLMResponseParseError, extract_tasks


def _mock_groq_response(content_dict):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(content_dict)}}]
    }
    return mock_resp


@patch("task_extraction.requests.post")
def test_extract_tasks_returns_parsed_tasks(mock_post):
    mock_post.return_value = _mock_groq_response(
        {"tasks": [{"who": "Артём", "what": "сделать отчёт", "quote": "нужно сделать отчёт"}]}
    )

    tasks = extract_tasks("транскрипт...", {"Артём": "artem.boldyrev"}, api_key="fake")

    assert tasks == [{"who": "Артём", "what": "сделать отчёт", "quote": "нужно сделать отчёт"}]


@patch("task_extraction.requests.post")
def test_extract_tasks_returns_empty_list_when_no_tasks_found(mock_post):
    mock_post.return_value = _mock_groq_response({"tasks": []})

    tasks = extract_tasks("привет, как дела", {}, api_key="fake")

    assert tasks == []


@patch("task_extraction.requests.post")
def test_extract_tasks_raises_llm_call_error_on_network_failure(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")

    with pytest.raises(LLMCallError):
        extract_tasks("транскрипт", {}, api_key="fake")


@patch("task_extraction.requests.post")
def test_extract_tasks_raises_parse_error_on_invalid_json_content(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "не json"}}]}
    mock_post.return_value = mock_resp

    with pytest.raises(LLMResponseParseError):
        extract_tasks("транскрипт", {}, api_key="fake")


@patch("task_extraction.requests.post")
def test_extract_tasks_raises_parse_error_on_missing_keys(mock_post):
    mock_post.return_value = _mock_groq_response({"tasks": [{"who": "Артём"}]})

    with pytest.raises(LLMResponseParseError):
        extract_tasks("транскрипт", {}, api_key="fake")
