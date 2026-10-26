#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jira Server / Data Center Task Fetcher
Загружает данные задачи из корпоративной Jira по REST API с использованием Personal Access Token (PAT).
"""

import sys
import os
import json
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_PATH = os.path.expanduser(r"~/.gemini/config/jira_config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Файл конфигурации не найден: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_issue(issue_key: str):
    config = load_config()
    base_url = config.get("jira_url", "").rstrip("/")
    token = config.get("pat_token", "").strip()
    verify_ssl = config.get("verify_ssl", False)

    if not base_url or base_url == "https://jira.example.ru":
        return {
            "error": "Не настроен URL Jira. Укажите реальный адрес вашей Jira в файле ~/.gemini/config/jira_config.json"
        }
    if not token or token == "YOUR_PERSONAL_ACCESS_TOKEN_HERE":
        return {
            "error": "Не указан Personal Access Token (PAT). Укажите токен в файле ~/.gemini/config/jira_config.json"
        }

    api_url = f"{base_url}/rest/api/2/issue/{issue_key}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(api_url, headers=headers, verify=verify_ssl, timeout=15)
        if response.status_code == 401:
            return {"error": "Ошибка авторизации (401). Проверьте правильность Personal Access Token."}
        if response.status_code == 403:
            return {"error": "Доступ запрещен (403). У вашей учетной записи нет прав на просмотр этой задачи."}
        if response.status_code == 404:
            return {"error": f"Задача {issue_key} не найдена в Jira (404). Проверьте ключ задачи."}
        
        response.raise_for_status()
        data = response.json()
        fields = data.get("fields", {})

        summary = fields.get("summary", "Без названия")
        description = fields.get("description", "Описание отсутствует")
        issue_type = fields.get("issuetype", {}).get("name", "Не указан")
        status = fields.get("status", {}).get("name", "Не указан")
        priority = fields.get("priority", {}).get("name", "Не указан")
        components = [c.get("name") for c in fields.get("components", [])]
        
        links = []
        for link in fields.get("issuelinks", []):
            if "outwardIssue" in link:
                rel = link.get("type", {}).get("outward", "relates to")
                links.append(f"{rel} {link['outwardIssue'].get('key')}: {link['outwardIssue'].get('fields', {}).get('summary')}")
            elif "inwardIssue" in link:
                rel = link.get("type", {}).get("inward", "relates to")
                links.append(f"{rel} {link['inwardIssue'].get('key')}: {link['inwardIssue'].get('fields', {}).get('summary')}")

        md_output = f"""# [{issue_key}] {summary}

- **Тип задачи**: {issue_type}
- **Статус**: {status}
- **Приоритет**: {priority}
- **Компоненты**: {', '.join(components) if components else 'Не указаны'}
- **Ссылка**: {base_url}/browse/{issue_key}

## Описание задачи
{description}
"""
        if links:
            md_output += "\n## Связанные задачи\n" + "\n".join(f"- {l}" for l in links)

        return {"success": True, "markdown": md_output, "raw": fields}

    except requests.exceptions.RequestException as e:
        return {"error": f"Ошибка сетевого соединения с сервером Jira: {str(e)}"}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python jira_fetcher.py <ISSUE_KEY>")
        sys.exit(1)

    key = sys.argv[1].strip()
    result = fetch_issue(key)
    if "error" in result:
        print(f"❌ {result['error']}", file=sys.stderr)
        sys.exit(1)
    else:
        print(result["markdown"])
