import requests


class TelegramSendError(Exception):
    pass


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise TelegramSendError(str(e).replace(bot_token, "<TOKEN>")) from e
