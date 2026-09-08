# Исправление долгого сохранения (2026-07-10 12:02)

## Проблема

Сохранение GeoJSON занимает **очень долгое время** (возможно бесконечное).

## Добавленные логи

Добавлено детальное логирование в `core/final_handler.py` для отслеживания прогресса в методе `_deduplicate()`:

```python
def _deduplicate(self, features: list[Feature]) -> list[Feature]:
    print(f"[FinalHandler] _deduplicate начат, features: {len(features)}")
    start_time = time.time()
    
    for idx, feat in enumerate(features):
        if idx % 100 == 0 and idx > 0:
            elapsed = time.time() - start_time
            print(f"[FinalHandler] _deduplicate прогресс: {idx}/{len(features)} ({elapsed:.1f}s)")
        # ... обработка ...
    
    elapsed = time.time() - start_time
    print(f"[FinalHandler] _deduplicate завершён: {len(result)} знаков ({elapsed:.1f}s)")
```

## Ожидаемые логи

```
[FinalHandler] _deduplicate начат, features: 158
[FinalHandler] _deduplicate прогресс: 100/158 (0.5s)
[FinalHandler] _deduplicate завершён: 155 знаков (0.8s)
```

## Диагностика

Следите за логами — последний лог перед зависанием покажет где проблема.

## Изменённые файлы

- **`core/final_handler.py`** — добавлено логирование прогресса дедупликации
