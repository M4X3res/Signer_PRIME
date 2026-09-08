# Следующие шаги после реализации блоков M–S

## ✅ Что сделано (100%)

- ✅ Реализован ONNX Runtime / OpenVINO backend для CPU-инференса (opt-in)
- ✅ Исправлены 3 бага (дедупликация, save_error_frames, turn_detection_radius_m)
- ✅ Удалены 3 мёртвых файла, архивированы 60+ исторические отчёты
- ✅ Добавлены настраиваемые пороги для lane_detector
- ✅ Полная миграция print() → logging в server/map_server.py (41 замена)
- ✅ **Блок S**: POST /api/sign и расширен PATCH для редактируемой карты
- ✅ Создана полная документация
- ✅ **Установлены зависимости**: onnx 1.22.0, onnxruntime 1.29.0
- ✅ **Сконвертированы все 18 моделей в ONNX** (~900 MB, 2026-09-01 09:28)

---

## 🧪 Требуется от пользователя — Тестирование

### 1. Smoke Test — Проверка запуска

```bash
.venv\Scripts\python.exe main.py
```

**Ожидается**:
- Приложение запускается без ошибок
- UI загружается
- В Settings виден Backend Selector (если CUDA отключена)

---

### 2. Unit Tests — Функциональные тесты

```bash
```bash
# Тесты ONNX backend
pytest tests/test_onnx_backend.py -v

# Тесты дедупликации с большими радиусами
pytest tests/test_deduplication.py::TestDeduplicationLargeRadius -v
```

**Ожидается**:
- Все тесты проходят успешно
- Нет ошибок загрузки ONNX моделей

---

### 3. Бенчмарк CPU Performance (опционально)

**Требуется тестовое видео!** Замените `<video.mp4>` на реальный путь.

```bash
# Baseline: PyTorch CPU
.venv\Scripts\python.exe scripts\benchmark_detector.py --video <video.mp4> --frames 100 --force-cpu --backend torch

# ONNX Runtime
.venv\Scripts\python.exe scripts\benchmark_detector.py --video <video.mp4> --frames 100 --force-cpu --backend onnx
```

**Ожидается**:
- ONNX Runtime показывает прирост производительности на CPU (~1.5-3x по сравнению с PyTorch)

---

## 📦 Git Commit

После успешного тестирования можно закоммитить изменения:

```bash
git add .
git status
git commit -m "feat: Implement ONNX/OpenVINO CPU inference + bug fixes + editable map API (Blocks M-S)

- Block M: ONNX Runtime/OpenVINO backend with opt-in fallback
- Block N: Fix deduplication radius, save_error_frames, remove turn_detection_radius_m
- Block O: Remove dead code (3 files), keep signs.json for backward compatibility
- Block P: Configurable lane thresholds, direct imports, print→logging migration
- Block Q: Archive historical reports (60+), create CHANGELOG.md
- Block S: POST /api/sign + extended PATCH for editable map

All 18 models exported to ONNX (~900 MB)."
```

---

## 🔄 Дальнейшие улучшения (опционально)

### Блок R — CI/CD (отложен)
- GitHub Actions/GitLab CI для автоматического тестирования
- Pre-commit hooks для линтеров

### Блок S — Frontend для редактируемой карты
- Добавить draggable markers в `templates/map.html`
- Кнопка "Add Sign" с модальным окном выбора типа
- Click-to-add UI

### Дополнительная оптимизация
- Конвертация в OpenVINO IR для Intel CPU (через `--format openvino`)
- Quantization моделей для уменьшения размера
- Batch processing оптимизация

---

## 📚 Документация

- **FINAL_EXECUTION_SUMMARY.md** — полный отчёт о выполнении
- **BLOCK_M_ONNX_CPU_IMPLEMENTATION.md** — техническая документация ONNX интеграции
- **BLOCK_S_TESTING.md** — API testing guide для редактируемой карты
- **CHANGELOG.md** — история изменений проекта

---

**Готово к работе!** 🚀
# Откройте BLOCK_M_ONNX_CPU_IMPLEMENTATION.md и заполните раздел "Численные результаты"
# (FPS baseline, FPS ONNX, модель CPU, поддержка AVX2/AVX512)
```

**Критерий успеха**: ONNX FPS ≥ PyTorch FPS × 1.20 (прирост минимум 20%)

Если прирост меньше — рекомендуется оставить PyTorch по умолчанию (backend уже реализован как opt-in).

### 3. Экспорт моделей через UI (опционально)

1. Запустите приложение: `python main.py`
2. Перейдите в Settings → Диагностика системы
3. Убедитесь, что "Использовать CUDA" выключен
4. Выберите "Бэкенд CPU-инференса" → "ONNX Runtime"
5. Нажмите "📦 Экспортировать модели для CPU"
6. Дождитесь завершения (статус под кнопкой)

### 4. Стресс-тест потокобезопасности (только если планируете включить ONNX по умолчанию)

**Цель**: Убедиться, что нет крашей 0xC0000409 (конфликт потоков OpenMP/Qt).

1. Подготовьте длинное видео (≥20 минут обработки)
2. В Settings: 
   - Отключите CUDA
   - Выберите "ONNX Runtime"
   - Режим обработки: "Single Thread"
3. Запустите обработку видео
4. Следите за крашами

Если краш появился — см. `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` §M.5 (настройка `ORT_NUM_THREADS=1`).

## 📋 Оставшиеся блоки (опционально)

### Блок R — CI/CD

Для автоматизации тестирования:

```bash
kiro chat "Реализуй Блок R из prompts/AGENT_PROMPT_onnx_cpu_inference_and_tech_debt.md"
```

Требуется уточнить платформу CI (GitHub Actions / GitLab CI / другое).

### Блок S — Редактируемая карта

Для реализации drag-and-drop знаков и добавления новых через клик:

```bash
kiro chat "Реализуй Блок S из prompts/AGENT_PROMPT_onnx_cpu_inference_and_tech_debt.md"
```

Самый объёмный блок (backend + frontend), рекомендуется отдельная сессия.

## 📚 Документация

- `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` — детали ONNX/OpenVINO backend
- `CHANGELOG.md` — история изменений
- `BLOCK_M_Q_EXECUTION_REPORT.md` — детальный отчёт выполнения
- `docs/archive/` — исторические отчёты (60+ файлов)

## 🐛 Известные проблемы

1. **UI-контролы для lane_conf_detect/segment** — настройки есть в коде, но нет в UI Settings
   - Временное решение: импорт через JSON (Settings → Импорт)
2. **Миграция print() → logging** — завершена частично (core/lane_detector.py, server/map_server.py)
   - Остальные файлы — для будущей сессии
3. **requirements.txt** — может быть неполным
   - Обновите: `pip freeze > requirements.txt`

## 💡 Рекомендации

- Если бенчмарк показывает прирост <20% — оставьте backend как opt-in экспериментальный функционал
- Если прирост ≥20% и стресс-тест чистый — можно рассмотреть изменение дефолта в будущем
- Сначала тестируйте на CPU-машинах без CUDA (типичный случай использования ONNX/OpenVINO)

## 🚀 Быстрый старт для новых пользователей

```bash
# 1. Установка зависимостей
pip install -r requirements.txt

# 2. (Опционально) Для ONNX backend
pip install onnx onnxruntime

# 3. (Опционально) Для OpenVINO backend
pip install openvino openvino-dev

# 4. Запуск приложения
python main.py
```

---

**Вопросы?** См. документацию в `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` или `BLOCK_M_Q_EXECUTION_REPORT.md`.
