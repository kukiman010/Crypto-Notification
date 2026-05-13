# Деплой (Docker + systemd)

## Локально через Compose

1. Скопируйте пример БД и при необходимости поправьте пароли:

   `cp deploy/db.conf.docker.example configs/db.conf`

2. Положите токены в `configs/telegram.key` и `configs/coinmarketcap.key` (формат CMC — см. `systems/configure.py`).

3. Из корня репозитория:

   `docker compose build && docker compose up -d`

Логи приложения: каталог `logs/` на хосте (смонтирован в контейнер).

## systemd (как у демо vk_gpt)

Контейнер должен называться `crypto_notification` (задано в `docker-compose.yml`).

1. Один раз подготовить образ и контейнер без автозапуска:

   `docker compose build && docker compose up --no-start`

2. Установить unit:

   `sudo cp deploy/crypto-notification.service /etc/systemd/system/`

   `sudo systemctl daemon-reload && sudo systemctl enable --now crypto-notification`

При перезагрузке сервера Docker поднимет уже созданный контейнер; `Restart=always` перезапустит сервис при падении процесса `docker start -a`.
