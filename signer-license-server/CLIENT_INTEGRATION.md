# Интеграция сервера лицензий с клиентом Signer PRIME

После успешного деплоя сервера на Google Cloud Run нужно обновить клиентский код.

## Шаги интеграции

### 1. Получить публичный ключ Ed25519

При генерации ключей через `scripts/generate_ed25519_keys.py` вы получили:
- Приватный ключ (сохранён в Secret Manager)
- **Публичный ключ** (для клиента)

### 2. Обновить `licensing/public_key.py`

Откройте файл `../licensing/public_key.py` и замените содержимое:

```python
"""
Public Ed25519 key для проверки лицензионных токенов.
Соответствует приватному ключу на сервере.
"""

LICENSE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
<ВСТАВЬТЕ_ВАШ_ПУБЛИЧНЫЙ_КЛЮЧ_СЮДА>
-----END PUBLIC KEY-----
"""
```

### 3. Обновить `configs/settings.py`

Найдите секцию с `license_server_url` и обновите URL:

```python
# License Server
license_server_url: str = "https://signer-license-server-XXXXX-uc.a.run.app"  # Ваш Cloud Run URL
```

Получить URL можно командой:
```bash
gcloud run services describe signer-license-server \
  --region=us-central1 \
  --format="value(status.url)"
```

### 4. Выключить mock mode

Откройте `licensing/license_client.py` и измените:

```python
# Mock mode для разработки без сервера
LICENSE_MOCK_MODE = False  # Было True, теперь False
```

### 5. Создать тестовую лицензию

```bash
cd signer-license-server

python scripts/create_license_manual.py \
  --server-url https://your-server.run.app \
  --admin-key YOUR_ADMIN_API_KEY \
  --plan monthly \
  --days 30 \
  --devices 2
```

Сохраните выведенный лицензионный ключ (формат: `SGNR-XXXX-XXXX-XXXX-XXXX`).

### 6. Тестирование в приложении

1. Запустите Signer PRIME
2. При первом запуске откроется окно активации лицензии
3. Вставьте созданный лицензионный ключ
4. Нажмите "Активировать"
5. Проверьте, что статус изменился на "Активна"

### 7. Проверка функциональности

**Проверьте следующие сценарии:**

1. **Переактивация** — перезапустите приложение, лицензия должна автоматически обновиться
2. **Grace period** — отключите интернет, запустите приложение — должно работать офлайн (7 дней)
3. **Лимит устройств** — попробуйте активировать на другом компьютере (должно работать до достижения лимита)
4. **Деактивация** — в UI нажмите "Деактивировать устройство", слот должен освободиться

### 8. Проверка в базе данных

Через Adminer (если используете локальный dev) или Cloud SQL Console:

```sql
-- Просмотр лицензий
SELECT license_key, plan, status, max_devices, current_period_end 
FROM licenses;

-- Просмотр активных устройств
SELECT d.device_label, d.fingerprint_hash, d.last_seen, d.deactivated_at, l.license_key
FROM devices d
JOIN licenses l ON d.license_id = l.id
WHERE d.deactivated_at IS NULL;
```

## Troubleshooting

### Ошибка: "Failed to verify token signature"

**Причина:** Публичный ключ в клиенте не соответствует приватному ключу на сервере.

**Решение:**
1. Убедитесь, что скопировали правильный публичный ключ
2. Проверьте, что нет лишних пробелов/переносов строк
3. Перегенерируйте пару ключей и обновите оба (сервер и клиент)

### Ошибка: "Connection refused" или "Timeout"

**Причина:** Неверный URL сервера или сервер недоступен.

**Решение:**
1. Проверьте `license_server_url` в `configs/settings.py`
2. Убедитесь, что Cloud Run сервис запущен: `gcloud run services list`
3. Проверьте health check: `curl https://your-url.run.app/health`

### Ошибка: "INVALID_LICENSE"

**Причина:** Лицензионный ключ не найден в базе данных.

**Решение:**
1. Проверьте, что ключ создан: `python scripts/create_license_manual.py`
2. Проверьте базу данных: `SELECT * FROM licenses WHERE license_key = 'SGNR-...'`
3. Убедитесь, что сервер подключён к правильной БД

### Ошибка: "DEVICE_LIMIT_REACHED"

**Причина:** Все слоты устройств заняты.

**Решение:**
1. Деактивируйте неиспользуемое устройство через UI
2. Или вручную в БД: `UPDATE devices SET deactivated_at = NOW() WHERE id = '...'`
3. Или купите план с бо́льшим лимитом устройств

## Мониторинг

### Логи Cloud Run

```bash
gcloud run services logs read signer-license-server \
  --region=us-central1 \
  --limit=50
```

### Метрики

В Google Cloud Console → Cloud Run → signer-license-server → Metrics:
- Request count
- Request latency
- Error rate
- Active instances

### Алерты (рекомендуется настроить)

1. **High error rate** — > 5% ошибок за 5 минут
2. **Latency spike** — p95 > 1 секунда
3. **Database connection errors**
4. **Stripe webhook failures**

## Безопасность Production

- [ ] Обновите `ADMIN_API_KEY` на длинный случайный ключ (32+ символов)
- [ ] Ограничьте CORS в `app/main.py`: укажите конкретные домены вместо `["*"]`
- [ ] Настройте Cloud Armor для защиты от DDoS (если высокий трафик)
- [ ] Включите Cloud SQL backups: `gcloud sql instances patch --backup-start-time=03:00`
- [ ] Ротация секретов: регулярно обновляйте ключи через Secret Manager
