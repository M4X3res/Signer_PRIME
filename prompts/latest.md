Контекст: проект Signer PRIME (RoadScanner) с системой лицензирования
(licensing/, signer-license-server/) и автообновлений (updater/).
Нужно исправить 4 конкретных бага перед production-релизом. Не трогай
логику обработки видео (core/, processing/, server/map_server.py).

ЗАДАЧА 1 (КРИТИЧНО): Исправить фиктивную проверку dev-ключа
Файл: licensing/public_key.py
- Функция _check_production_key() сравнивает sha256(LICENSE_PUBLIC_KEY_PEM)
  с константой DEV_KEY_SHA256, но эта константа не соответствует реальному
  хэшу текущего PEM-значения, поэтому проверка никогда не срабатывает.
- Исправление: пересчитай DEV_KEY_SHA256 = hashlib.sha256(текущий
  LICENSE_PUBLIC_KEY_PEM.encode()).hexdigest() и захардкодь ПРАВИЛЬНОЕ
  значение константой (чтобы проверка реально ловила случай "забыли
  заменить ключ перед сборкой прод-релиза"). Добавь юнит-тест в
  tests/test_licensing.py: подставить текущий dev PEM через monkeypatch,
  выставить sys.frozen=True и проверить, что импорт модуля кидает
  RuntimeError. И второй тест: с другим (не dev) PEM модуль импортируется
  без ошибок при sys.frozen=True.

ЗАДАЧА 2 (КРИТИЧНО): license_server_url должен доходить до реального клиента
Файлы: configs/settings.py, scripts/build/prepare_release.bat (или
эквивалентный build-скрипт), README/RELEASE.md
- Проблема: default license_server_url — это URL-заглушка, а override
  идёт только через переменную окружения SIGNER_LICENSE_SERVER_URL,
  которой не будет у конечного пользователя после установки .exe.
- Исправление: добавь в AppSettings.load() дополнительный источник —
  чтение из файла build_config.json (или прямо из version.json, если
  архитектурно проще) рядом с exe/скриптом, который генерируется/
  редактируется ПЕРЕД сборкой релиза командой из RELEASE.md. Приоритет:
  1) SIGNER_LICENSE_SERVER_URL (для разработчиков) 2) значение из
  build_config.json 3) дефолт в dataclass. Обнови RELEASE.md: добавь
  обязательный шаг "Перед prepare_release.bat открыть configs/settings.py
  и/или build_config.json и прописать реальный URL Cloud Run сервиса",
  и добавь автоматическую проверку в начале prepare_release.bat:
  если в этом файле остался домен "license.signer-prime.com" —
  выводить явную ошибку и прерывать сборку (аналогично уже
  существующей runtime-проверке в AppSettings.load()).

ЗАДАЧА 3: CLI для создания internal-лицензий
Файл: signer-license-server/scripts/create_license_manual.py
- Строка: choices=["monthly", "quarterly", "yearly"] для --plan.
- Исправление: добавить "internal" в choices. Убедиться, что справка
  (epilog) в argparse содержит пример создания internal-лицензии:
  python scripts/create_license_manual.py --plan internal --days 3650 --devices 50

ЗАДАЧА 4: Реальные Stripe Price ID
Файл: signer-license-server/app/services/stripe_service.py
- STRIPE_PRICE_TO_PLAN содержит placeholder-значения
  ("price_monthly_prod" и т.д.), которые никогда не совпадут с реальным
  Stripe Price ID.
- Исправление: НЕ хардкодь конкретные ID (они появятся только после
  создания продуктов в Stripe Dashboard пользователем), но:
  a) вынеси маппинг в переменные окружения / Settings
     (STRIPE_PRICE_ID_MONTHLY, STRIPE_PRICE_ID_QUARTERLY, STRIPE_PRICE_ID_YEARLY)
     через app/config.py::Settings, со сборкой словаря в рантайме;
  b) если переменная не задана — логируй явный warning при старте
     приложения "STRIPE_PRICE_ID_MONTHLY не задан, оплата по месячному
     плану не будет создавать лицензии";
  c) обнови .env.example и signer-license-server/README.md разделом
     "Настройка Stripe Price ID" с точным описанием, откуда взять эти ID
     (Stripe Dashboard → Product catalog → нужная цена → Price ID начинается
     с price_...).

ЗАДАЧА 5 (по возможности): CORS по умолчанию
Файл: signer-license-server/app/config.py
- cors_allowed_origins: str = "*" — оставь дефолт как есть для локальной
  разработки, но убедись, что README.md и deploy_gcloud.sh явно требуют
  задать CORS_ALLOWED_ORIGINS при продакшен-деплое (уже частично есть —
  проверь, что warning в app/main.py действительно виден в логах Cloud Run
  при первом запуске).

После всех правок: прогнать tests/test_licensing.py и
signer-license-server/tests/ (pytest), убедиться что всё зелёное.
Не менять поведение уже работающих механизмов (grace period, refresh
интервалы, race-condition защита, email-отправка, resume-докачка
обновлений) — они корректны и трогать их не нужно.