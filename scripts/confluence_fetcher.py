#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Confluence Server / Data Center Page Fetcher
Загружает содержимое страницы из корпоративного Confluence по REST API с использованием сессионной куки (Cookie / JSESSIONID).
Преобразует HTML/Storage формат страницы в чистый структурированный Markdown для LLM-агента.
"""

import sys
import os
import re
import json
import urllib.parse
from html.parser import HTMLParser
import urllib3
import requests

# Настройка UTF-8 для вывода в консоль Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Подавление предупреждений о самоподписанных корпоративных SSL-сертификатах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_PATH = os.path.expanduser(r"~/.gemini/config/confluence_config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Файл конфигурации не найден: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class ConfluenceHtmlToMarkdown(HTMLParser):
    """
    Легковесный и надежный конвертер Confluence Storage XHTML в Markdown.
    Не требует сторонних зависимостей (BeautifulSoup/lxml), использует встроенную библиотеку Python.
    """
    def __init__(self):
        super().__init__()
        self.output = []
        self.tag_stack = []
        self.in_table = False
        self.current_table_rows = []
        self.current_row = []
        self.current_cell = []
        self.is_header_cell = False
        self.in_code = False
        self.code_lang = ""
        self.code_content = []
        self.list_depth = 0
        self.list_type_stack = []
        self.ol_counter_stack = []

    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag)
        attrs_dict = dict(attrs)

        if tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag[1])
            self.output.append("\n\n" + ("#" * level) + " ")
        elif tag == "p":
            if not self.in_table:
                self.output.append("\n\n")
        elif tag == "br":
            self.output.append("\n")
        elif tag in ["strong", "b"]:
            self.output.append("**")
        elif tag in ["em", "i"]:
            self.output.append("*")
        elif tag == "code" and not self.in_code:
            self.output.append("`")
        elif tag == "a":
            href = attrs_dict.get("href", "")
            self.output.append("[")
            self._current_href = href
        elif tag == "ul":
            self.list_depth += 1
            self.list_type_stack.append("ul")
            self.output.append("\n")
        elif tag == "ol":
            self.list_depth += 1
            self.list_type_stack.append("ol")
            self.ol_counter_stack.append(1)
            self.output.append("\n")
        elif tag == "li":
            indent = "  " * (self.list_depth - 1)
            if self.list_type_stack and self.list_type_stack[-1] == "ol":
                idx = self.ol_counter_stack[-1]
                self.ol_counter_stack[-1] += 1
                self.output.append(f"\n{indent}{idx}. ")
            else:
                self.output.append(f"\n{indent}- ")
        elif tag == "table":
            self.in_table = True
            self.current_table_rows = []
        elif tag == "tr":
            self.current_row = []
        elif tag in ["th", "td"]:
            self.is_header_cell = (tag == "th")
            self.current_cell = []
        elif tag == "ac:structured-macro":
            macro_name = attrs_dict.get("ac:name", "")
            if macro_name == "code":
                self.in_code = True
                self.code_content = []
            elif macro_name in ["info", "note", "tip"]:
                self.output.append("\n\n> [!NOTE]\n> ")
            elif macro_name == "warning":
                self.output.append("\n\n> [!WARNING]\n> ")

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()

        if tag in ["strong", "b"]:
            self.output.append("**")
        elif tag in ["em", "i"]:
            self.output.append("*")
        elif tag == "code" and not self.in_code:
            self.output.append("`")
        elif tag == "a":
            href = getattr(self, "_current_href", "")
            self.output.append(f"]({href})")
        elif tag == "ul":
            if self.list_depth > 0:
                self.list_depth -= 1
            if self.list_type_stack:
                self.list_type_stack.pop()
            self.output.append("\n")
        elif tag == "ol":
            if self.list_depth > 0:
                self.list_depth -= 1
            if self.list_type_stack:
                self.list_type_stack.pop()
            if self.ol_counter_stack:
                self.ol_counter_stack.pop()
            self.output.append("\n")
        elif tag in ["th", "td"]:
            cell_text = "".join(self.current_cell).replace("\n", " ").strip()
            self.current_row.append((cell_text, self.is_header_cell))
        elif tag == "tr":
            if self.current_row:
                self.current_table_rows.append(self.current_row)
        elif tag == "table":
            self.in_table = False
            self.output.append("\n\n" + self._format_table(self.current_table_rows) + "\n\n")
            self.current_table_rows = []
        elif tag == "ac:structured-macro" and self.in_code:
            self.in_code = False
            code_text = "".join(self.code_content).strip()
            self.output.append(f"\n\n```{self.code_lang}\n{code_text}\n```\n\n")
            self.code_content = []

    def handle_data(self, data):
        if self.in_code:
            self.code_content.append(data)
        elif self.in_table and self.current_row is not None:
            self.current_cell.append(data)
        else:
            self.output.append(data)

    def _format_table(self, rows):
        if not rows:
            return ""
        max_cols = max(len(r) for r in rows)
        if max_cols == 0:
            return ""

        formatted_rows = []
        for r in rows:
            cells = [cell[0].replace("|", "\\|") for cell in r]
            while len(cells) < max_cols:
                cells.append("")
            formatted_rows.append("| " + " | ".join(cells) + " |")

        # Добавляем разделитель заголовка после 1-й строки
        separator = "| " + " | ".join(["---"] * max_cols) + " |"
        if len(formatted_rows) > 1:
            return formatted_rows[0] + "\n" + separator + "\n" + "\n".join(formatted_rows[1:])
        elif len(formatted_rows) == 1:
            return formatted_rows[0] + "\n" + separator
        return ""

    def get_markdown(self):
        text = "".join(self.output)
        # Очистка избыточных пустых строк
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def parse_target(target_input: str, default_base_url: str):
    target = target_input.strip()

    if target.isdigit():
        return {"type": "id", "id": target}

    match_page_id = re.search(r"pageId=(\d+)", target)
    if match_page_id:
        return {"type": "id", "id": match_page_id.group(1)}

    match_display = re.search(r"/display/([^/]+)/([^/?#]+)", target)
    if match_display:
        space_key = match_display.group(1)
        title = urllib.parse.unquote_plus(match_display.group(2))
        return {"type": "title", "space_key": space_key, "title": title}

    return {"type": "unknown", "raw": target}


def fetch_confluence_page(target_input: str):
    config = load_config()
    base_url = config.get("confluence_url", "").rstrip("/")
    cookie_str = config.get("cookie", "").strip()
    verify_ssl = config.get("verify_ssl", False)

    if not base_url:
        return {"error": "Не настроен confluence_url в ~/.gemini/config/confluence_config.json"}
    if not cookie_str or cookie_str == "JSESSIONID=YOUR_SESSION_COOKIE_HERE":
        return {
            "error": "Не указана сессионная кука Confluence!\n"
                     "Откройте Confluence в браузере -> F12 (DevTools) -> вкладка Application (или Network) -> "
                     "скопируйте значение JSESSIONID (или всю строку Cookie) и вставьте в файл:\n"
                     f"{CONFIG_PATH}"
        }

    if not ("=" in cookie_str):
        cookie_header = f"JSESSIONID={cookie_str}"
    else:
        cookie_header = cookie_str

    headers = {
        "Cookie": cookie_header,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ConfluenceFetcher/1.0"
    }

    target_info = parse_target(target_input, base_url)

    if target_info["type"] == "id":
        page_id = target_info["id"]
        api_url = f"{base_url}/rest/api/content/{page_id}?expand=body.storage,version,ancestors,space"
    elif target_info["type"] == "title":
        space = target_info["space_key"]
        title = urllib.parse.quote(target_info["title"])
        api_url = f"{base_url}/rest/api/content?spaceKey={space}&title={title}&expand=body.storage,version,ancestors,space"
    else:
        api_url = f"{base_url}/rest/api/content/{target_input}?expand=body.storage,version,ancestors,space"

    try:
        response = requests.get(api_url, headers=headers, verify=verify_ssl, timeout=20, allow_redirects=False)

        if response.status_code in [301, 302]:
            location = response.headers.get("Location", "")
            if "login.action" in location or "sso" in location:
                return {
                    "error": "Сессионная кука устарела или недействительна (сервер перенаправил на экран входа login.action).\n"
                             f"Пожалуйста, обновите JSESSIONID в файле {CONFIG_PATH}."
                }

        if response.status_code == 401:
            return {
                "error": "Ошибка авторизации Confluence (HTTP 401 Unauthorized).\n"
                         f"Проверьте правильность сессионной куки в {CONFIG_PATH}."
            }
        if response.status_code == 403:
            return {
                "error": "Доступ запрещен (HTTP 403 Forbidden).\n"
                         "У вашей учетной записи нет прав на просмотр этой страницы Confluence."
            }
        if response.status_code == 404:
            return {
                "error": f"Страница Confluence не найдена (HTTP 404). Проверьте URL или ID страницы: {target_input}"
            }

        response.raise_for_status()
        data = response.json()

        if "results" in data:
            if not data["results"]:
                return {"error": f"Страница не найдена по названию: {target_input}"}
            item = data["results"][0]
        else:
            item = data

        page_id = item.get("id")
        title = item.get("title", "Без названия")
        space_name = item.get("space", {}).get("name", "Не указано")
        space_key = item.get("space", {}).get("key", "")
        version_num = item.get("version", {}).get("number", 1)
        version_by = item.get("version", {}).get("by", {}).get("displayName", "Не указан")
        version_date = item.get("version", {}).get("when", "")[:10]

        storage_html = item.get("body", {}).get("storage", {}).get("value", "")

        parser = ConfluenceHtmlToMarkdown()
        parser.feed(storage_html)
        markdown_body = parser.get_markdown()

        web_link = f"{base_url}/pages/viewpage.action?pageId={page_id}"

        full_markdown = f"""# {title}

- **ID страницы**: {page_id}
- **Пространство**: {space_name} ({space_key})
- **Версия**: v{version_num} ({version_date}, автор: {version_by})
- **Ссылка**: {web_link}

---

{markdown_body}
"""

        return {
            "success": True,
            "page_id": page_id,
            "title": title,
            "space": space_name,
            "markdown": full_markdown
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"Ошибка сетевого соединения с Confluence ({base_url}): {str(e)}"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python confluence_fetcher.py <PAGE_ID_ИЛИ_URL>")
        print("Пример: python confluence_fetcher.py 138498965")
        print("Пример: python confluence_fetcher.py https://confluence.video.rt.ru/pages/viewpage.action?pageId=138498965")
        sys.exit(1)

    target = sys.argv[1]
    res = fetch_confluence_page(target)
    if res.get("success"):
        print(res["markdown"])
    else:
        print(f"ОШИБКА: {res.get('error')}", file=sys.stderr)
        sys.exit(1)
