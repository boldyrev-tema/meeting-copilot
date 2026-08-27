from unittest.mock import Mock, patch

import pytest
import requests

from telegram_notify import TelegramSendError, send_telegram_message


@patch("telegram_notify.requests.post")
def test_send_telegram_message_posts_to_correct_url_and_payload(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_post.return_value = mock_resp

    send_telegram_message("bot-token", "12345", "привет")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/botbot-token/sendMessage"
    assert kwargs["json"] == {"chat_id": "12345", "text": "привет"}


@patch("telegram_notify.requests.post")
def test_send_telegram_message_raises_on_failure(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")

    with pytest.raises(TelegramSendError):
        send_telegram_message("bot-token", "12345", "привет")


@patch("telegram_notify.requests.post")
def test_send_telegram_message_scrubs_bot_token_from_error(mock_post):
    fake_token = "123456:AAFakeSecretBotToken"
    mock_post.side_effect = requests.exceptions.HTTPError(
        f"401 Client Error: Unauthorized for url: "
        f"https://api.telegram.org/bot{fake_token}/sendMessage"
    )

    with pytest.raises(TelegramSendError) as exc_info:
        send_telegram_message(fake_token, "12345", "привет")

    message = str(exc_info.value)
    assert fake_token not in message
    assert "<TOKEN>" in message
