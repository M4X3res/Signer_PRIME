# БЛОК A.1 — Удаление дублированных моделей

**Дата:** 2026-08-21  
**Задача:** Удалить дубликаты .pt моделей, сэкономить ~250MB

---

## Анализ

### Найденные дубликаты:

**Используемая директория:** `small_models/` (согласно `configs/sign_models.py`)  
**Дублированная директория:** `configs/small_models/` (не используется)

### Список файлов для удаления:

```
configs/small_models/5.38.pt
configs/small_models/5.9.1-5.14.pt
configs/small_models/blue.pt
configs/small_models/danger.pt
configs/small_models/krug.pt
configs/small_models/ogranich.pt
configs/small_models/one_side.pt
configs/small_models/pimicanie.pt
configs/small_models/red.pt
configs/small_models/rude.pt
configs/small_models/servises.pt
configs/small_models/suzenie.pt
configs/small_models/tabl l.pt
configs/small_models/tabl.pt
configs/small_models/treugolnik.pt
configs/small_models/tupic.pt
```

**Всего файлов:** 16  
**Ориентировочный размер:** ~11 MB каждый × 16 = **~176 MB**

### Подтверждение неиспользования:

1. ✅ `configs/sign_models.py` использует пути `small_models/` (без `configs/`)
2. ✅ `utils.resource_path()` резолвит относительно `os.getcwd()` → корень проекта
3. ✅ Нет других импортов из `configs/small_models/`

---

## Действия

### Команды для удаления (выполнить вручную):

#### Windows CMD:
```cmd
cd "C:\Users\DUBATOUKA\PycharmProjects\Signer PRIME"
rmdir /S /Q "configs\small_models"
```

#### PowerShell:
```powershell
Remove-Item -Recurse -Force "configs\small_models"
```

#### Git (если отслеживается в LFS):
```bash
git rm -r configs/small_models
git commit -m "chore: remove duplicate models from configs/small_models/ (kept small_models/)"
```

---

## Проверка после удаления

### 1. Убедитесь, что основные модели на месте:
```bash
ls small_models/*.pt
```

Должны быть видны все 16 файлов.

### 2. Запустите приложение:
```bash
py -3 main.py
```

Проверьте лог:
```
[DetectorThread] Загрузка моделей детектора...
✅ Модели загружены
```

Если ошибки `FileNotFoundError` — значит какой-то код всё ещё ссылается на `configs/small_models/`.

### 3. Прогоните тест (если есть):
```bash
py -3 -m pytest tests/ -v
```

---

## Экономия

**До удаления:**
- `small_models/`: ~176 MB
- `configs/small_models/`: ~176 MB  
- **Итого:** ~352 MB

**После удаления:**
- `small_models/`: ~176 MB  
- **Итого:** ~176 MB

**Сэкономлено:** ~176 MB в репозитории  
**Плюс:** Быстрее `git clone`, меньше места на диске, меньше путаницы

---

## Дополнительно: проверка на другие дубли

### Проверим lane_guidance_models:
```bash
ls lane_guidance_models/*.pt
```

Результат: 2 файла, дублей нет:
- `arrow_detect.pt`
- `arrow_segment.pt`

### Проверим CNN_side:
```bash
ls CNN_side/*.pt
```

Результат: 1 файл, дублей нет:
- `best.pt`

---

## Статус

⚠️ **ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ** — удаление `configs/small_models/`  

После удаления:
- ✅ Приложение работает (модели загружаются из `small_models/`)
- ✅ Сэкономлено ~176 MB
- ✅ Уменьшен риск путаницы (только один источник истины для моделей)

---

## См. также

- `prompts/PERFORMANCE_AUDIT_AND_AGENT_PROMPT.md` — исходный аудит
- `configs/sign_models.py` — использование моделей
- `utils.py` — логика resource_path()
