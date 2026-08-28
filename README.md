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

Путь можно переопределить переменной окружения `MEETING_COPILOT_TRANSCRIPTS_DIR`
(см. следующий раздел) — полезно, если `live_copilot_poc` не установлен на
этой машине.

## Быстрый тест без live_copilot_poc

Если `live_copilot_poc` не установлен (например, тестируешь на чужой
машине) — не обязательно его разворачивать. Можно указать любую свою папку
с транскриптом через переменную окружения:

```bash
cd ~/Desktop/meeting_copilot
source venv/bin/activate
mkdir -p ~/my_transcripts
cp sample_transcripts/example_with_task.txt ~/my_transcripts/
MEETING_COPILOT_TRANSCRIPTS_DIR=~/my_transcripts python3 run.py
```

`sample_transcripts/example_with_task.txt` — готовый пример с одним реальным
поручением задачи (условному «Ивану») и посторонней светской репликой,
которую скрипт должен проигнорировать. Имя в файле («Иван») уже есть в
закоммиченном `name_mapping.json` как плейсхолдер — для осмысленного теста
с реальным Jira-исполнителем поправь `name_mapping.json` под своё имя/логин
перед запуском.

Обязательно нужен свой `~/.credentials/groq_api_key.env` — без него скрипт
падает сразу на детекте задачи, до всего остального.

`~/.credentials/jira_credentials.env` тоже обязателен для полного прогона,
**но не обязательно с рабочими значениями** — если задач хотя бы одна,
скрипт загружает Jira-креденшлы ДО проверки цитаты/имени, и без файла упадёт
раньше, чем успеет что-то показать. Проще всего вписать туда что угодно
похожее на правду:
```
JIRA_BASE_URL=https://example.invalid
JIRA_EMAIL=test@example.com
JIRA_API_TOKEN=fake
JIRA_PROJECT_KEY=TEST
```
Реальный HTTP-запрос уйдёт в никуда и корректно провалится — но к этому
моменту детект задачи, проверка на галлюцинацию и сопоставление имени уже
отработают, и результат будет виден в отчёте как «❌ Ошибка создания
тикета», а не потеряется.

`~/.credentials/meeting_copilot_telegram.env` можно пропустить полностью —
без него скрипт корректно остановится на последнем шаге и не отправит
отчёт, но полный текст отчёта к этому моменту уже напечатан в терминал.

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
