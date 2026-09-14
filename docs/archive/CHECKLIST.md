# Чеклист проверки исправлений перед релизом

Используйте этот чеклист для проверки всех исправлений.

## ✅ ЗАДАЧА 1: Dev-ключ проверка

- [ ] `licensing/public_key.py`: DEV_KEY_SHA256 = "499ac7ed9b140bb3da49c0a7a429ac9bf1b7dd25154260a0810c5d89aa69d276"
- [ ] Тесты добавлены: `tests/test_licensing.py::TestProductionKeyCheck`
- [ ] Запустить: `python -m pytest tests/test_licensing.py::TestProductionKeyCheck -v`
- [ ] Проверить вручную:
  ```bash
  python -c "import hashlib; key = open('licensing/public_key.py').read().split('LICENSE_PUBLIC_KEY_PEM = \"\"\"')[1].split('\"\"\"')[0]; print(hashlib.sha256(key.encode()).hexdigest())"
  ```

## ✅ ЗАДАЧА 2: license_server_url конфигурация

- [ ] `configs/settings.py`: метод `load()` содержит чтение `build_config.json`
- [ ] `build_config.json.example` создан
- [ ] `.gitignore` содержит `build_config.json`
- [ ] `scripts/build/prepare_release.bat`: проверка [0/5] добавлена
- [ ] `scripts/build/prepare_release.bat`: копирование `build_config.json` в dist
- [ ] `RELEASE.md`: добавлен шаг 2 "Настройте URL сервера лицензий"
- [ ] Проверить вручную:
  - Попробовать запустить `prepare_release.bat` без `build_config.json` → должна быть ошибка
  - Создать `build_config.json` с placeholder URL → должна быть ошибка
  - Создать с реальным URL → должно пройти

## ✅ ЗАДАЧА 3: Internal-лицензии в CLI

- [ ] `signer-license-server/scripts/create_license_manual.py`: choices содержит "internal"
- [ ] Справка (epilog) содержит пример internal-лицензии
- [ ] Проверить вручную:
  ```bash
  python signer-license-server/scripts/create_license_manual.py --help | grep internal
  ```

## ✅ ЗАДАЧА 4: Stripe Price ID

- [ ] `signer-license-server/app/config.py`: добавлены поля `stripe_price_id_*`
- [ ] `signer-license-server/app/config.py`: метод `get_stripe_price_to_plan_map()` добавлен
- [ ] `signer-license-server/app/services/stripe_service.py`: удалён хардкод `STRIPE_PRICE_TO_PLAN`
- [ ] `signer-license-server/app/services/stripe_service.py`: используется `self.price_to_plan`
- [ ] `signer-license-server/app/main.py`: логирование Stripe Price ID при старте
- [ ] `signer-license-server/.env.example`: добавлены `STRIPE_PRICE_ID_*`
- [ ] `signer-license-server/README.md`: раздел "Настройка Stripe Price ID" добавлен
- [ ] Проверить вручную:
  ```bash
  grep -r "price_monthly_prod" signer-license-server/app/services/
  # Не должно быть совпадений
  ```

## ✅ ЗАДАЧА 5: CORS warnings

- [ ] `signer-license-server/app/main.py`: содержит warning про wildcard CORS
- [ ] `signer-license-server/scripts/deploy_gcloud.sh`: содержит warning про CORS_ALLOWED_ORIGINS
- [ ] Проверить вручную:
  ```bash
  grep -i "wildcard" signer-license-server/app/main.py
  grep -i "CORS_ALLOWED_ORIGINS" signer-license-server/scripts/deploy_gcloud.sh
  ```

## 🧪 Тестирование

### Быстрая проверка
```bash
python test_fixes.py
```

### Полные тесты
```bash
# Клиентские тесты
python -m pytest tests/test_licensing.py -v

# Серверные тесты (требуется Docker для testcontainers)
cd signer-license-server
pytest tests/ -v
```

## 📋 Перед релизом

1. [ ] Все тесты проходят
2. [ ] `build_config.json` создан и заполнен реальным URL
3. [ ] Production Ed25519 ключи сгенерированы
4. [ ] Публичный ключ обновлён в `licensing/public_key.py`
5. [ ] `DEV_KEY_SHA256` пересчитан для нового ключа (если это новый dev-ключ)
6. [ ] Stripe Price IDs настроены в переменных окружения Cloud Run
7. [ ] CORS_ALLOWED_ORIGINS задан для production
8. [ ] `prepare_release.bat` выполняется без ошибок
9. [ ] Архивы созданы в `release/`
10. [ ] Чексуммы проверены

## 📝 Итоговая проверка

Запустите:
```bash
python test_fixes.py
```

Если все тесты проходят — можно приступать к сборке релиза.
