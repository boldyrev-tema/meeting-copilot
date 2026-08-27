from unittest.mock import Mock, patch

import json
import requests

from jira_client import create_ticket


@patch("jira_client.requests.post")
def test_create_ticket_success_returns_url(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"key": "PROJ-42"}
    mock_post.return_value = mock_resp

    result = create_ticket(
        base_url="https://example.atlassian.net",
        email="a@b.com",
        api_token="tok",
        project_key="PROJ",
        assignee_username="artem.boldyrev",
        summary="Сделать отчёт",
        description="Цитата: «нужно сделать отчёт»",
    )

    assert result.success is True
    assert result.url == "https://example.atlassian.net/browse/PROJ-42"
    assert result.error is None


@patch("jira_client.requests.post")
def test_create_ticket_failure_returns_error_without_raising(mock_post):
    mock_post.side_effect = requests.exceptions.HTTPError("403 Forbidden")

    result = create_ticket(
        base_url="https://example.atlassian.net",
        email="a@b.com",
        api_token="tok",
        project_key="PROJ",
        assignee_username="unknown.user",
        summary="Сделать отчёт",
        description="Цитата: «нужно сделать отчёт»",
    )

    assert result.success is False
    assert result.url is None
    assert "403" in result.error


@patch("jira_client.requests.post")
def test_create_ticket_missing_key_in_response_returns_failure_not_raises(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"id": "12345"}  # Missing "key" field
    mock_post.return_value = mock_resp

    result = create_ticket(
        base_url="https://example.atlassian.net",
        email="a@b.com",
        api_token="tok",
        project_key="PROJ",
        assignee_username="artem.boldyrev",
        summary="Сделать отчёт",
        description="Цитата: «нужно сделать отчёт»",
    )

    assert result.success is False
    assert result.url is None
    assert result.error is not None


@patch("jira_client.requests.post")
def test_create_ticket_json_decode_error_returns_failure_not_raises(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
    mock_post.return_value = mock_resp

    result = create_ticket(
        base_url="https://example.atlassian.net",
        email="a@b.com",
        api_token="tok",
        project_key="PROJ",
        assignee_username="artem.boldyrev",
        summary="Сделать отчёт",
        description="Цитата: «нужно сделать отчёт»",
    )

    assert result.success is False
    assert result.url is None
    assert result.error is not None
