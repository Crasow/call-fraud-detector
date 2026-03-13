# Call Fraud Detector

Анализирует телефонные звонки на мошенничество с помощью Gemini AI.

## Ключевая фича: асинхронная очередь обработки

Раньше загрузка блокировала HTTP-запрос на ~30 сек. Теперь:

1. Загрузил файл — мгновенно получил "Принято"
2. Фоновый воркер подхватывает задачу из БД и отправляет в Gemini
3. До 5 звонков обрабатываются параллельно
4. Веб-интерфейс автоматически обновляется каждые 3 сек (HTMX polling)

## Как пользоваться

### Веб-интерфейс

Открыть `http://localhost:8080`

- Drag & drop аудиофайл или кликнуть для выбора
- Нажать Analyze
- Спиннер покажет статус, результат появится автоматически
- Поддерживаемые форматы: WAV, MP3, OGG, FLAC, M4A, WebM

### REST API

```bash
# Загрузить на анализ (мгновенный ответ)
curl -F file=@call.wav http://localhost:8080/api/v1/calls/analyze
# -> {"id": "uuid", "status": "pending"}

# Проверить статус
curl http://localhost:8080/api/v1/calls/{id}
# -> {..., "status": "done", "analysis": {...}}

# Список всех звонков
curl http://localhost:8080/api/v1/calls

# Webhook для интеграций
curl -F file=@call.wav http://localhost:8080/api/v1/webhook/call

# Статистика
curl http://localhost:8080/api/v1/stats
```

### CLI

```bash
cfd analyze call.wav        # Прямой анализ (синхронный)
cfd analyze-dir ./calls/    # Пакетный анализ папки
cfd list                    # Последние результаты
cfd stats                   # Статистика
cfd watch                   # Следить за папкой
cfd serve                   # Запустить веб-сервер
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
