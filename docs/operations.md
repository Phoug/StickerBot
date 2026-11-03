# Эксплуатация StickerBot

Документ описывает сборку, проверки и работу контейнеров. Доставка на сервер,
DNS и HTTPS-прокси управляются отдельно. API и polling-бот запускаются в одном
экземпляре каждый. Файловая блокировка каталога данных запрещает второй процесс
API; это также защищает процедуру восстановления от работающего приложения.

## Воспроизводимая разработка

Поддерживаемое окружение проверок — Linux, CPython 3.14, Node.js 22 и FFmpeg
с libx264/libvpx-vp9. `flake.lock` закрепляет источник инструментов Nix.

```sh
nix develop
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock -r tests/requirements.lock
.venv/bin/python -m pip check
cd frontend
npm ci --no-audit --no-fund
```

`.venv`, `frontend/node_modules` и `.cache/{pip,npm}` сохраняются в рабочем
каталоге и исключены из Git и контекста Docker. Кэш ускоряет повторную установку;
версии фиксируют lock-файлы. В отличие от `/tmp`, это окружение не зависит от
очистки временного каталога. `nix develop` не устанавливает библиотеки Python
автоматически и не загружает приватную конфигурацию. Само приложение при обычном
запуске сохраняет прежнюю поддержку локальной конфигурации.

В тестах всегда используется `PYTHON_DOTENV_DISABLED=1` и фиктивные токены.

## Обновление зависимостей

`app/requirements.txt`, `backend/requirements.txt`, `tests/requirements.txt` —
диапазоны допустимых версий. `requirements.lock` — проверенный набор runtime;
`tests/requirements.lock` дополняет его библиотеками тестов. Эти lock-файлы
ориентированы на CPython 3.14/Linux; Windows-разработчикам доступен WSL.

Для обновления используйте чистое временное окружение и pip-tools:

```sh
python -m venv /tmp/stickerbot-locks
/tmp/stickerbot-locks/bin/python -m pip install pip-tools
/tmp/stickerbot-locks/bin/pip-compile --resolver=backtracking --strip-extras \
  --output-file requirements.lock app/requirements.txt backend/requirements.txt
/tmp/stickerbot-locks/bin/pip-compile --resolver=backtracking --strip-extras \
  --constraint requirements.lock --output-file tests/requirements.lock tests/requirements.txt
```

После обновления установите оба lock-файла в чистое окружение, выполните
`pip check`, pytest и проверку Docker-образа. Обновления yt-dlp и FFmpeg требуют
также контрольного скачивания публичной публикации тестовым ботом: функциональные
тесты не обращаются к соцсетям и Telegram. Не обновляйте установленные библиотеки
в работающем контейнере.

Node-образ сборки закреплён digest в Dockerfile. Python-образ задаётся
`PYTHON_IMAGE`: по умолчанию DHI, для независимой проверки — публичный
`python:3.14-slim-trixie`. Для строгого закрепления базовой ОС передайте выбранный
образ вместе с digest и регулярно обновляйте его. Пакеты ОС, включая FFmpeg,
обновляются при контролируемой пересборке; lock Python не фиксирует пакеты APT.
Перед установкой FFmpeg сборка восстанавливает `init-system-helpers`: утилита
`update-rc.d` нужна post-install скриптам зависимости `x11-common`, но может
отсутствовать в минимальном DHI-образе.

## CI и проверка образа

Checks запускается для PR и всех веток, а также вызывается перед сборкой релиза.
Python и frontend проверяются независимо, кэши привязаны к lock-файлам.
JUnit-отчёты сохраняются 14 дней. Actions закреплены commit SHA.

Обычный CI собирает образ на публичной базе. Release build дополнительно
проверяет свой образ DHI по результату сборки. SSH/SCP и серверный deploy job
не относятся к этим изменениям.

```sh
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest tests -q
cd frontend
npm run build
npm test
cd ..
docker build --build-arg PYTHON_IMAGE=python:3.14-slim-trixie -t stickerbot:check .
python3 scripts/check_image.py stickerbot:check
```

Проверка образа использует фиктивные секреты, отключённую внешнюю сеть,
непривилегированного пользователя и read-only корневую файловую систему.
Она проверяет `/ready`, `/app/`, закрытость приватного API, импорт бота,
реальный рендер VP9 и H.264-предпросмотр. Созданный тестовый контейнер удаляется.
Это не запускает настоящий polling и не публикует данные в Telegram.

Опциональный `docker build --target bot ...` создаёт образ polling-бота без
FFmpeg, backend и статики. Образ по умолчанию сохраняет обе команды запуска,
совместимые с существующим Compose.

## Ограничения выполнения

`MEDIA_CONCURRENCY` задаёт общий предел операций API, включая legacy-загрузки
и превью. При перегрузке сервер возвращает 503 с `Retry-After`, не создавая
неограниченной очереди. Загрузка multipart аутентифицируется и резервирует место
до записи тела в spool. Контролируются Content-Length и фактические полученные
байты. Тело запроса ограничено размером исходника плюс 1 МиБ для формы.

`MEDIA_JOB_TIMEOUT_SECONDS` ограничивает загрузку тела и бюджеты нативных
команд. yt-dlp работает в отдельном процессе: при таймауте в Linux завершается
вся группа процессов. Отмена запроса не освобождает слот занятого потока до
его фактического завершения. `FFMPEG_THREADS` ограничивает потоки кодеков и
фильтров. Нормализация фото ограничена числом пикселей; она не является
принудительно прерываемым subprocess-заданием.

Загрузчик не получает токены бота, общий секрет API и переменные прокси.
Проверяются DNS-ответы и адреса реальных соединений, в том числе при редиректах
и повторном разрешении имени. Разрешены публичные HTTP/HTTPS-адреса и порты
80/443. Внешние сетевые загрузчики FFmpeg/RTMP и прямые трансляции отключены;
если поток требует их, пользователь может загрузить файл из галереи.
FFmpeg обработки локальных файлов разрешает только протоколы file/pipe.

Compose ограничивает CPU, RAM, число процессов и размер временных каталогов;
rootfs read-only, capabilities сняты, повышение привилегий запрещено.
Параметры `API_CPU_LIMIT`, `API_MEMORY_LIMIT`, `BOT_CPU_LIMIT`, `BOT_MEMORY_LIMIT`
нужно подбирать по нагрузке и ресурсам хоста. tmpfs расходует RAM и входит в
лимит контейнера. Базовые значения не заменяют нагрузочного тестирования.
Контейнеры используют init и до пяти минут на корректное завершение операций.

Пока необходим один API worker. Перед масштабированием нужны общая очередь,
сохраняемое состояние заданий и распределённые блокировки публикаций.

## Проверки состояния и метрики

* `/health` — процесс API отвечает.
* `/ready` — существующая SQLite доступна для работы, таблицы существуют и
  обслуживание медиа не находится в ошибке и не просрочено.
* `/metrics` — Prometheus text format; требуется `X-API-Key`. Выдаёт количество
  запросов, суммарное время, использование бюджета медиа и время последней очистки.
  Идентификаторы пользователей и наборов не используются как метки.
* `python3 -m app.bot.health` — проверяет свежий heartbeat успешных GetUpdates;
  простой процесса без успешного polling не считается готовностью.
* `python3 -m backend.backup health` — проверяет свежесть последней успешной копии.

Логи — JSON с временем UTC, версией сборки и request_id. CI передаёт commit SHA
в build-аргумент APP_VERSION. HTTP-ответы содержат X-Request-ID.
Query string и настроенные секреты исключены из логов. Контейнерные логи
ротируются: local driver, до трёх файлов по 10 МиБ на сервис.

Статус unhealthy сам по себе не перезапускает Docker-контейнер. Restart policy
работает при выходе процесса. Нужны внешние уведомления: недоступность API,
устаревший polling или бэкап, OOM/перезапуски, нехватка места, рост времени
обработки и ошибок Telegram. Метрики и health endpoints не заменяют проверку
публичного маршрута и рабочего сценария тестовым ботом.

## Резервное копирование

Сервис `backup` запускается без токенов и внешней сети. Он создаёт первый
проверенный снимок после старта, затем повторяет операцию каждый час.
`BACKUP_INTERVAL_SECONDS` и `BACKUP_RETENTION_COUNT` управляют расписанием и
числом поколений; по умолчанию сохраняются 48 копий. Удаляются только файлы
собственного формата `stickerbot-<UTC timestamp>.sqlite3`; ручные копии сохраняются.

SQLite Online Backup API учитывает подтверждённые данные WAL. Снимок проверяется
через quick_check и наличие таблиц, публикуется атомарно с правами 0600.
Данные хранятся в `sticker-data`, снимки — в отдельном `sticker-backups`.
Для работы SQLite/WAL исходный том доступен процессу по filesystem в режиме rw,
но соединение источника открывается только mode=ro. Временные медиа не копируются.

**Копии на том же VPS не защищают от потери сервера.** Переносите проверенные
копии в независимое хранилище и проверяйте свежесть именно внешней копии.
Транспорт и доступы внешнего хранилища настраиваются отдельно.

Ручной снимок, с уникальным именем файла:

```sh
docker compose exec api python3 -m backend.backup create \
  --output /app/data/backups/manual-001.sqlite3
mkdir -p backups
docker compose cp api:/app/data/backups/manual-001.sqlite3 backups/manual-001.sqlite3
python3 -m backend.backup verify backups/manual-001.sqlite3
```

CLI не читает .env и не требует зависимостей приложения или секретов бота.
Для всех команд Compose требуется выбрать IMAGE_TAG как при обычном запуске.

## Проверка восстановления

```sh
python3 -m backend.backup restore backups/manual-001.sqlite3 \
  --data-dir /tmp/stickerbot-recovery-check
python3 -m backend.backup verify /tmp/stickerbot-recovery-check/stickerbot.sqlite3
```

Каталог назначения должен быть новым: восстановление не перезаписывает
существующую базу или WAL. Блокировка запрещает восстановление в каталог
работающего API. Для реального восстановления остановите API, сохраните старый
том, восстановите в новый и подключите его к единственному экземпляру API.
Проверьте `/ready` и реестр наборов до удаления старых данных.
После восстановления исходники без файлов запрашиваются заново; опубликованные
стикеры остаются в Telegram. Действия Telegram не откатываются вместе с SQLite.

`PRAGMA user_version=2` фиксирует текущую схему. Старые базы получают эту версию
при совместимом старте; база с более новой версией отвергается. Новые изменения
схемы требуют отдельной миграции, предварительного снимка и проверки
совместимости старого и нового кода. Не меняйте схему вручную в production.

### Publication schema migration (version 2)

Before deploying this version, create and verify a database snapshot. Startup
adds the nullable `media.published_replace_id` column to version 0/1 databases
and preserves their existing rows. The column records the target of a completed
replacement so retries cannot silently publish to a different target. Pack and
publication completion updates commit in one transaction.

Existing completed publications have no historical replacement target. Adding
retries remains compatible; retrying an old replacement can return a conflict.
Reopen the pack to inspect the published sticker before starting another edit.
Older application versions reject schema version 2. To roll back, restore the
pre-migration snapshot into a new data directory using the recovery procedure;
Telegram changes made after that snapshot are not rolled back.

## Практические проверки обслуживания

Проверяйте запуск после перезагрузки хоста, свободное место в данных и снимках,
возраст бэкапов, ротацию логов и периодическое восстановление на изолированном
окружении. У тестового окружения должны быть отдельный Telegram-бот, секреты
и тома; второй poller production-токена не запускается. Согласуйте допустимую
потерю данных и время восстановления, затем измерьте их на учебном восстановлении.
Очистку старых Docker-образов выполняйте с сохранением нужных версий и томов.
