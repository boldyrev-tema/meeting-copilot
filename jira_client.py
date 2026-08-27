import json

import requests


class JiraTicketResult:
    def __init__(self, success: bool, url: str = None, error: str = None):
        self.success = success
        self.url = url
        self.error = error


def create_ticket(base_url, email, api_token, project_key, assignee_username, summary, description):
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                ],
            },
            "issuetype": {"name": "Task"},
            # See Task 5's "Known unverified detail" note in the plan:
            # Jira Cloud may require {"accountId": ...} here instead of "name".
            "assignee": {"name": assignee_username},
        }
    }

    try:
        resp = requests.post(
            f"{base_url}/rest/api/3/issue",
            json=payload,
            auth=(email, api_token),
            timeout=30,
        )
        resp.raise_for_status()
        key = resp.json()["key"]
    except (requests.exceptions.RequestException, KeyError, json.JSONDecodeError) as e:
        return JiraTicketResult(success=False, error=str(e))

    return JiraTicketResult(success=True, url=f"{base_url}/browse/{key}")
