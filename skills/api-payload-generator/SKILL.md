---
name: api-payload-generator
description: Генератор API-проверок, cURL-запросов, Postman-коллекций и негативных пейлоадов (фаззинг JSON, мутации типов, пропуск обязательных полей, проверка статус-кодов) по OpenAPI/Swagger спецификациям.
---

# SKILL: api-payload-generator (Генератор API проверок и пейлоадов)

## 1. Роль и Назначение
Навык предназначен для ускорения тестирования REST/HTTP API. Превращает Swagger/OpenAPI спеку или пример JSON-запроса в полный набор готовых **cURL-запросов**, готовые коллекции для **Postman / Bruno** и матрицу негативных проверок бэкенда.

---

## 2. Матрица мутации пейлоада (Negative Payload Mutations)

Для каждого эндпоинта создается серия запросов, проверяющих устойчивость бэкенда:

### 2.1. Валидация структуры схемы (Schema Validation)
1. **Пустое тело**: Отправка `{}` на эндпоинт создания/изменения (Ожидаемый результат: `400 Bad Request`).
2. **Пропуск обязательных полей (Missing Required Fields)**: Поочередное удаление каждого обязательного ключа из JSON (проверка информативности валидационного ответа бэкенда).
3. **Отправка `null`**: Передача `null` в поля, не допускающие пустых значений (`nullable: false`).
4. **Несовпадение типов (Type Mismatch)**:
   - Передача строки вместо числа: `"amount": "one thousand"`.
   - Передача числа вместо массива: `"items": 123`.
   - Передача строки вместо boolean: `"isActive": "yes"`.
5. **Недокументированные поля (Mass Assignment Probes)**: Добавление лишних ключей (например, `"role": "ADMIN"`, `"isVerified": true`). Бэкенд должен либо игнорировать их, либо возвращать 400, но ни в коем случае не перезаписывать права.

### 2.2. Граничные значения числовых полей
- Отрицательные числа: `-1`, `-0.01` (где разрешены только положительные).
- Ноль: `0`.
- Переполнение: `2147483648` (int32 overflow), `9223372036854775808` (int64 overflow).
- Дробные числа вместо целых: `10.5` для количества штук.

### 2.3. Заголовки и авторизация (Auth & Headers)
- Запрос без заголовка `Authorization` ➔ `401 Unauthorized`.
- Запрос с токеном другого пользователя / роли (IDOR-проверка) ➔ `403 Forbidden`.
- Запрос с заголовком `Content-Type: text/plain` вместо `application/json` ➔ `415 Unsupported Media Type`.
- Дублирование запроса с одинаковым заголовком `X-Idempotency-Key` (проверка идемпотентности платежей/создания).

---

## 3. Стандарты форматирования вывода

### 3.1. Формат cURL (готов к вставке в терминал или Postman Import)
Запросы оформляются в виде валидных multiline cURL с экранированием:

```bash
curl --location --request POST 'https://api.example.com/v1/users' \
--header 'Content-Type: application/json' \
--header 'Authorization: Bearer <TOKEN>' \
--header 'X-Request-ID: test-run-001' \
--data-raw '{
  "username": "qa_tester",
  "email": "test@example.com",
  "age": 25
}'
```

### 3.2. Матрица проверок эндпоинта (API Test Matrix)

```markdown
| ID проверки | Тип проверки | Поле / Заголовок | Передаваемое значение | Ожидаемый статус | Ожидаемый код ошибки |
|---|---|---|---|---|---|
| API-001 | Positive (Happy Path) | Full Payload | Валидные данные | 201 Created | - |
| API-002 | Negative (Missing field) | `email` | Поле удалено | 400 Bad Request | `REQUIRED_FIELD_MISSING` |
| API-003 | Negative (Type mismatch) | `age` | `"twenty"` | 400 Bad Request | `INVALID_TYPE` |
| API-004 | Security (Auth missing) | `Authorization` | Заголовок опущен | 401 Unauthorized | `UNAUTHORIZED` |
| API-005 | Security (IDOR) | `userId` в пути | Чужой `user_id_999` | 403 Forbidden | `ACCESS_DENIED` |
```

---

## 4. Паттерн экспорта в Postman Collection v2.1 (JSON)

При запросе агент генерирует фрагмент Postman Collection JSON, который можно сохранить в файл `.json` и импортировать в Postman в один клик:

```json
{
  "info": {
    "name": "API Test Suite",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Positive: Create User",
      "request": {
        "method": "POST",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"username\": \"qa_user\"\n}"
        },
        "url": {
          "raw": "{{baseUrl}}/api/v1/users",
          "host": ["{{baseUrl}}"],
          "path": ["api", "v1", "users"]
        }
      }
    }
  ]
}
```
