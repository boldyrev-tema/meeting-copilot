# Meeting Copilot — Jira Task Detection MVP

После рабочего созвона читает транскрипт, записанный `live_copilot_poc`,
одним проходом LLM находит устно поручённые задачи и заводит тикеты в Jira.
Полный дизайн — `docs/superpowers/specs/2026-08-27-jira-task-detection-mvp-design.md`.

## Установка

```bash
cd ~/Desktop/meeting_copilot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Нужные ключи

Как и в `live_copilot_poc`, ключи лежат в `~/.credentials/`, не в репозитории:

- `~/.credentials/groq_api_key.env` — уже должен существовать, если
  `live_copilot_poc` настроен. Формат: `GROQ_API_KEY=...`
- `~/.credentials/jira_credentials.env` — новый файл, четыре строки:
  ```
  JIRA_BASE_URL=https://ВАШ-ДОМЕН.atlassian.net
  JIRA_EMAIL=твой-email-в-jira
  JIRA_API_TOKEN=токен-из-id.atlassian.com/manage-profile/security/api-tokens
  JIRA_PROJECT_KEY=КЛЮЧ-ПРОЕКТА
  ```
- `~/.credentials/meeting_copilot_telegram.env` — новый бот через BotFather:
  ```
  TELEGRAM_BOT_TOKEN=токен-от-botfather
  TELEGRAM_CHAT_ID=твой-chat-id
  ```
  Chat ID проще всего получить, написав боту любое сообщение и открыв
  `https://api.telegram.org/bot<TOKEN>/getUpdates` — в ответе будет
  `"chat":{"id": ...}`.

## Таблица имён

`name_mapping.json` в корне проекта — редактируется руками, формат:

```json
{
  "Имя, как оно звучит на созвоне": "jira-username"
}
```

## Запуск

```bash
cd ~/Desktop/meeting_copilot
source venv/bin/activate
python3 run.py
```

Скрипт сам берёт самый свежий необработанный файл из
`~/Desktop/live_copilot_poc/transcripts/`. Обработанные файлы переезжают в
`~/Desktop/live_copilot_poc/transcripts/processed/`.

## Тесты

```bash
python3 -m pytest -v
```

Все внешние вызовы (Groq, Jira, Telegram) в тестах замоканы — `pytest`
никогда не делает реальных сетевых запросов.

## Ручная проверка на реальных сервисах (не автоматизирована)

Сделать один раз перед тем, как полагаться на пайплайн по-настоящему:

1. Заполнить все три файла credentials выше реальными значениями.
2. Заполнить `name_mapping.json` реальными именами команды.
3. Провести короткий тестовый созвон 1-на-1 через `live_copilot_poc`, вслух
   поручить себе или собеседнику конкретную задачу.
4. Запустить `python3 run.py`.
5. **Это упадёт на первой же попытке — так и должно быть, вот почему.**
   `jira_client.py` сейчас комбинирует Jira Cloud-only эндпоинт/формат
   (`/rest/api/3/issue` с ADF-описанием) с Jira Server-only форматом поля
   assignee (`{"assignee": {"name": ...}}`). Эта комбинация не может
   заработать ни на одном из двух продуктов как есть: Jira Cloud отклонит
   `name`-стиль assignee (требует `accountId`), а Jira Server вообще не
   поддерживает v3 API и ADF-описания. Ожидай ошибку от Jira API на этом шаге
   и по её тексту определи, что чинить:
   - Если инстанс — **Jira Cloud**: замени в `jira_client.py`
     `{"name": assignee_username}` на `{"accountId": ...}`, а в
     `name_mapping.json` храни не username, а accountId (его можно достать
     через `GET /rest/api/3/myself` для себя или `GET /rest/api/3/user/search`
     для коллег).
   - Если инстанс — **Jira Server/Data Center**: замени эндпоинт на
     `/rest/api/2/issue` и формат `description` с ADF-объекта на обычную
     строку.
6. Проверить, что тикет реально появился в Jira с правильным исполнителем и
   текстом задачи.
7. Проверить, что в Telegram пришло сообщение с этим тикетом в списке
   «Созданы».
8. Проверить, что обработанный файл переехал в `transcripts/processed/`.
