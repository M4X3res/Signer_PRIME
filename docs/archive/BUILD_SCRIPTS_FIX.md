# ✅ ИСПРАВЛЕНО: Проблема с обфускацией при сборке

## Проблема
```
python.exe: can't open file '...\obfuscate_licensing.py': [Errno 2] No such file or directory
ERROR: Obfuscation failed
```

## Причина
Файл `scripts/build/obfuscate_licensing.py` отсутствовал после реорганизации проекта.

## Решение

Созданы/обновлены 4 файла:

### 1. `scripts/build/obfuscate_licensing.py` ✅ СОЗДАН
**Назначение:** Обфускация модулей лицензирования с PyArmor

**Логика:**
- Создаёт backup оригинальных файлов → `build/backup_originals/`
- Обфусцирует файлы → `build/obfuscated/`
- Копирует обфусцированные файлы ПОВЕРХ оригинальных
- Копирует PyArmor runtime в `licensing/pyarmor_runtime_*/`

**Обфусцируемые файлы:**
- `main.py`
- `licensing/*.py`
- `ui/widgets/license_dialog.py`

---

### 2. `scripts/build/restore_originals.py` ✅ СОЗДАН
**Назначение:** Восстановление оригинальных файлов после сборки

**Логика:**
- Восстанавливает файлы из `build/backup_originals/`
- Удаляет PyArmor runtime из `licensing/`

Автоматически вызывается после успешной сборки.

---

### 3. `scripts/build/prepare_release.bat` ✅ ОБНОВЛЁН
**Изменения:**
- Исправлены пути: `python` → `.venv\Scripts\python.exe`
- Исправлены пути: `pyinstaller` → `.venv\Scripts\pyinstaller.exe`
- Добавлен автоматический вызов `restore_originals.py` после сборки
- Упрощена логика: обфусцированные файлы заменяют оригинальные in-place

**Новая логика сборки:**
```
[3/7] Обфускация (если PyArmor установлен)
  ↓ Backup оригиналов
  ↓ Обфускация
  ↓ Замена оригиналов обфусцированными

[4/7] Сборка PyInstaller
  ↓ Сборка из обфусцированных файлов

[4/7] Восстановление
  ↓ Возврат оригинальных файлов
```

---

### 4. `scripts/build/QUICK_BUILD_GUIDE.md` ✅ СОЗДАН
Краткая инструкция по сборке для быстрого старта.

---

## Теперь работает

```bash
# Сборка релиза
scripts\build\prepare_release.bat

# Результат:
# - Обфускация (если PyArmor установлен)
# - Сборка Signer.exe и Updater.exe
# - Автоматическое восстановление оригиналов
# - Готовый релиз в release/
```

---

## Если PyArmor не установлен

Скрипт автоматически:
- Обнаружит отсутствие PyArmor
- Выведет предупреждение
- **Продолжит сборку БЕЗ обфускации**

Это нормально для dev-сборок. Для production используйте:
```bash
pip install pyarmor
```

---

## Файлы для коммита

```
Новые файлы:
+ scripts/build/obfuscate_licensing.py
+ scripts/build/restore_originals.py
+ scripts/build/QUICK_BUILD_GUIDE.md

Изменённые файлы:
M scripts/build/prepare_release.bat
M scripts/build/README.md
```

---

**Статус:** ✅ Готово к сборке релиза
