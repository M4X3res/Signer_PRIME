# Промпт для ИИ-агента: исправление автообновления и подготовка лицензирования к продакшену

Контекст: проект Signer PRIME (RoadScanner). Нужно исправить критический баг
автообновления и подготовить систему лицензирования к продакшену.

---

## ЗАДАЧА 1 (КРИТИЧНО, сделать первым)

В файле `updater/updater.py`, функция `launch_updater_and_exit`, есть строка:

```python
if getattr(sys, "frozen", false):
```

Замени `false` на `False` (Python-булев литерал). Это опечатка, вызывающая
`NameError` при каждом вызове функции, что полностью ломает применение обновлений.

После исправления найди все места в кодовой базе, где встречается такая же
опечатка (`grep -rn "getattr(sys, \"frozen\", false)"` и просто `false)` рядом
с `getattr`/`sys.frozen`), и поправь их тоже.

---

## ЗАДАЧА 2

В `configs/settings.py` замени дефолтное значение `license_server_url` на значение,
переданное через переменную окружения `SIGNER_LICENSE_SERVER_URL` (уже частично
реализовано — проверь, что override действительно применяется, и добавь явный
warning в лог, если используется URL-заглушка `"https://license.signer-prime.com"`
в frozen-сборке — это признак незавершённой настройки перед релизом).

---

## ЗАДАЧА 3

В `licensing/public_key.py` добавь runtime-проверку: если публичный ключ совпадает
с известным dev-ключом (захардкодь хэш дев-ключа для сравнения), при старте в
frozen-сборке (`getattr(sys, "frozen", False) == True`) выводи явную ошибку в лог
"КРИТИЧНО: используется тестовый публичный ключ лицензирования в production-сборке"
и не позволяй продолжить (`raise RuntimeError`), чтобы невозможно было случайно
выпустить релиз с тестовым ключом.

---

## ЗАДАЧА 4

В `device_fingerprint.py` добавь fallback для `_get_disk_serial()` и `_get_mac_address()`
через PowerShell `Get-CimInstance` (`Win32_DiskDrive`, `Win32_NetworkAdapter`),
используемый если результат `wmic` пустой (на случай отсутствия `wmic` на новых
сборках Windows). Сохрани текущую сигнатуру функций и порядок fallback'ов.

---

## ЗАДАЧА 5

Почисти dead code в `processing/processing_controller.py::load_checkpoint` —
удали недостижимые строки после `return False` внутри `except`-блока.

---

## ЗАДАЧА 6 (опционально, для лицензий на организацию)

В `signer-license-server/app/schemas.py` расширь `CreateLicenseRequest.plan` pattern
до `"^(monthly|quarterly|yearly|internal)$"`, и в `app/services/license_service.py` /
`stripe_service.py` убедись, что `"internal"` никогда не приходит из Stripe webhook
(только через admin API), а `licensing/license_manager.py` / `license_dialog.py`
корректно отображают название плана `"internal"` как "Внутренняя лицензия" в UI.

---

## ЗАДАЧА 7 (отправка ключа лицензии клиенту по email после оплаты)

В `signer-license-server/app/services/stripe_service.py`, метод
`handle_checkout_completed`, есть комментарий:

```python
# TODO: Отправить email с ключом лицензии клиенту
# Получите email через session["customer_details"]["email"]
```

Сейчас это не реализовано — после успешной оплаты клиент создаёт лицензию в
базе, но никогда не узнаёт свой лицензионный ключ, если не смотреть вручную в
базу данных. Нужно:

1. Добавить отправку email с лицензионным ключом клиенту сразу после успешного
   создания `License` в `handle_checkout_completed`, используя email из
   `session["customer_details"]["email"]`.
2. Выбрать транспортный сервис — SendGrid или Postmark (оба имеют простой REST
   API и Python SDK). Добавить зависимость в `signer-license-server/requirements.txt`
   (например `sendgrid>=6.0.0` или `postmarker>=1.0`).
3. Добавить в `signer-license-server/app/config.py` (класс `Settings`) новые поля:
   - `email_provider: str = "sendgrid"` (или `"postmark"`)
   - `email_api_key: str = ""`
   - `email_from_address: str = "noreply@your-domain.com"`
   - `email_from_name: str = "Signer PRIME"`
   Прокинуть их через переменные окружения аналогично остальным секретам
   (задокументировать в `.env.example` и в `scripts/deploy_gcloud.sh` — добавить
   создание секрета `email-api-key` в Secret Manager и передачу через
   `--set-secrets`).
4. Создать новый модуль `signer-license-server/app/services/email_service.py`
   с классом `EmailService`, методом `send_license_key(to_email: str, license_key: str, plan: str, expires_at: datetime) -> bool`.
   Письмо должно содержать: лицензионный ключ, план подписки, дату окончания,
   краткую инструкцию "Введите этот ключ в приложении Signer PRIME при первом
   запуске". Обернуть отправку в try/except — ошибка отправки email НЕ должна
   ронять обработку webhook (лицензия уже создана и валидна, письмо — это
   удобство, а не критический путь). При ошибке отправки — залогировать через
   `logger.error` с деталями, чтобы можно было вручную переслать ключ.
5. Вызвать `EmailService.send_license_key(...)` в конце `handle_checkout_completed`
   после успешного `db.commit()`, передав email из
   `session.get("customer_details", {}).get("email")`. Если email отсутствует в
   session — залогировать warning и не пытаться отправить письмо (не падать).
6. Добавить юнит-тест в `signer-license-server/tests/` (например
   `test_email_service.py` или расширить существующий тест Stripe webhook),
   мокающий вызов внешнего email API, проверяющий:
   - письмо отправляется с правильным ключом при наличии email в session;
   - обработка webhook не падает, если email отсутствует;
   - обработка webhook не падает, если отправка email вызвала исключение
     (сеть недоступна, невалидный API-ключ и т.п.) — лицензия при этом всё
     равно должна быть создана и закоммичена в БД.
7. Обновить `signer-license-server/README.md` и `CLIENT_INTEGRATION.md`,
   добавив шаг настройки email-провайдера в раздел деплоя.

---

## Общие требования к выполнению

После каждой правки прогони `pytest` в `signer-license-server/tests` и убедись,
что ничего не сломано. Не трогай `core/`, `processing/` (кроме задачи 5),
`server/map_server.py`, `templates/map.html`.
