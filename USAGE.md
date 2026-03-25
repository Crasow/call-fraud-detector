# Call Analyzer

Анализирует телефонные звонки на мошенничество с помощью Gemini AI.
Поддерживает произвольные профили анализа для любых задач обработки аудио.

## Ключевая фича: асинхронная очередь обработки

Раньше загрузка блокировала HTTP-запрос на ~30 сек. Теперь:

1. Загрузил файл — мгновенно получил "Принято"
2. Фоновый воркер подхватывает задачу из БД и отправляет в Gemini
3. До 5 звонков обрабатываются параллельно
4. Веб-интерфейс автоматически обновляется каждые 3 сек (HTMX polling)

## Профили анализа

По умолчанию система детектирует мошенничество (fraud detection). Но можно создавать **профили** — кастомные инструкции для Gemini, позволяющие анализировать звонки под любую задачу.

### Режимы промпта

| Режим | Описание |
|-------|----------|
| `custom` | Полностью свой промпт — пишешь текст целиком |
| `template` | Шаблонный — задаёшь роль эксперта, задачу, поля для JSON |

### Trigger words

К любому профилю можно добавить список триггерных слов. Gemini дополнительно проверит их наличие в разговоре.

### Три сценария работы

1. **Без профиля** — стандартная фрод-детекция. Результат: `AnalysisResult` (is_fraud, fraud_score, categories, reasons)
2. **С профилем (custom)** — Gemini получает ваш промпт целиком. Результат: `ProfileResult` (произвольный JSON)
3. **С профилем (template)** — промпт собирается из полей: эксперт, задача, поля JSON. Результат: `ProfileResult`

### Двойная система результатов

| Тип | Когда | Поля |
|-----|-------|------|
| `AnalysisResult` | Анализ без профиля | `is_fraud`, `fraud_score`, `fraud_categories`, `reasons`, `transcript` |
| `ProfileResult` | Анализ с профилем | `data` (произвольный JSON от Gemini), `transcript` |

---

## Как пользоваться

### Веб-интерфейс

Открыть `http://localhost:8080`

- Drag & drop аудиофайл или кликнуть для выбора
- **(Опционально)** Выбрать профиль анализа из выпадающего списка
- Нажать Analyze
- Спиннер покажет статус, результат появится автоматически
- Поддерживаемые форматы: WAV, MP3, OGG, FLAC, M4A, WebM

#### Управление профилями

- `/profiles` — список всех профилей
- `/profiles/new` — создание нового профиля
- `/profiles/{id}/edit` — редактирование профиля

### REST API

```bash
# Загрузить на анализ (мгновенный ответ)
curl -F file=@call.wav http://localhost:8080/api/v1/calls/analyze
# -> {"id": "uuid", "status": "pending"}

# Загрузить с профилем анализа
curl -F file=@call.wav -F profile_id=<uuid> http://localhost:8080/api/v1/calls/analyze

# Проверить статус
curl http://localhost:8080/api/v1/calls/{id}
# -> {..., "status": "done", "analysis": {...}}
# или с профилем: {..., "status": "done", "profile_result": {...}}

# Список всех звонков (с пагинацией)
curl http://localhost:8080/api/v1/calls?page=1&size=20

# Webhook для интеграций
curl -F file=@call.wav http://localhost:8080/api/v1/webhook/call
curl -F file=@call.wav -F profile_id=<uuid> http://localhost:8080/api/v1/webhook/call

# Статистика
curl http://localhost:8080/api/v1/stats
```

#### Profile API

```bash
# Создать профиль
curl -X POST http://localhost:8080/api/v1/profiles \
  -F name="Качество обслуживания" \
  -F prompt_mode=template \
  -F expert="анализ качества обслуживания" \
  -F main_task="Оцени качество обслуживания клиента оператором" \
  -F fields_for_json="score,politeness,resolution,summary" \
  -F 'trigger_words=["спасибо","жалоба","претензия"]'

# Список профилей
curl http://localhost:8080/api/v1/profiles

# Получить профиль
curl http://localhost:8080/api/v1/profiles/{id}

# Обновить профиль
curl -X PUT http://localhost:8080/api/v1/profiles/{id} \
  -F name="Новое имя"

# Удалить профиль
curl -X DELETE http://localhost:8080/api/v1/profiles/{id}
```

### CLI

```bash
ca analyze call.wav                    # Прямой анализ (фрод-детекция)
ca analyze call.wav --profile-id <uuid> # Анализ с профилем
ca analyze-dir ./calls/                # Пакетный анализ папки
ca analyze-dir ./calls/ --profile-id <uuid>
ca list                                # Последние результаты
ca stats                               # Статистика
ca watch                               # Следить за папкой
ca serve                               # Запустить веб-сервер
```

#### Управление профилями через CLI

```bash
# Создать профиль (custom mode)
ca profile create --name "Мой профиль" --custom-prompt "Проанализируй звонок..."

# Создать профиль (template mode)
ca profile create --name "QA" --prompt-mode template \
  --expert "контроль качества" \
  --main-task "Оцени качество обслуживания" \
  --fields-for-json "score,summary"

# Список профилей
ca profile list

# Обновить профиль
ca profile update <uuid> --name "Новое имя" --trigger-words "спасибо,жалоба"
```

### Docker

```bash
docker compose up -d --build
```

## Статусы звонка

| Статус       | Значение                          |
|--------------|-----------------------------------|
| `pending`    | В очереди, ждёт обработки         |
| `processing` | Gemini анализирует                |
| `done`       | Готово, есть результат            |
| `error`      | Ошибка (см. `error_message`)      |

При рестарте сервиса зависшие `processing` задачи автоматически возвращаются в `pending`.
