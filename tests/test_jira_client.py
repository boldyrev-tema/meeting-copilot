from unittest.mock import Mock, patch

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
