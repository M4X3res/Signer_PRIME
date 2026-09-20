# PyArmor Runtime Fix - Решение проблемы ImportError

## Проблема

После сборки через `scripts\build\prepare_release.bat` приложение падало с ошибкой:

```
File "main.py", line 2, in <module>
File "...\dist\Signer\_internal\pyarmor_runtime_000000\__init__.py", line 2, in <module>
    from ..pyarmor_runtime_000000 import __pyarmor__
ImportError: attempted relative import beyond top-level package
```

## Корневая причина

Проект требует **ДВА независимых PyArmor runtime**:

1. **Корневой runtime** (для `main.py`) - должен быть в `_internal/pyarmor_runtime_000000/`
   - `main.py` импортирует: `from pyarmor_runtime_000000 import __pyarmor__` (абсолютный импорт)
   
2. **Вложенный runtime** (для `licensing/*.py`) - должен быть в `_internal/licensing/pyarmor_runtime_000000/`
   - Модули лицензирования импортируют: `from .pyarmor_runtime_000000 import __pyarmor__` (относительный импорт)

### Что было не так:

1. **`obfuscate_licensing.py`**: Обфусцировал ВСЕ файлы (`main.py` + `licensing/*`) ОДНОЙ командой PyArmor с флагом `-i licensing`, что создавало только вложенный runtime

2. **`signer.spec`**: Дедуплицировал runtime по `basename`, брал только ПЕРВЫЙ найденный `pyarmor_runtime_000000` и помещал его в корень - получался НЕПРАВИЛЬНЫЙ runtime (вложенный вместо корневого)

3. **Результат**: В `_internal/pyarmor_runtime_000000/` попадала копия вложенного runtime с относительным импортом `from ..pyarmor_runtime_000000`, который на верхнем уровне не может разрешиться

## Решение

### 1. Исправлен `scripts/build/obfuscate_licensing.py`

**Было:** Один вызов PyArmor с флагом `-i licensing` для всех файлов

**Стало:** Два раздельных вызова PyArmor:

```python
# ШАГ 1: Обфусцировать main.py БЕЗ -i (runtime в корне)
cmd_main = [
    "pyarmor", "gen",
    "-O", str(obf_dir),
    # НЕТ -i флага
    "main.py"
]

# ШАГ 2: Обфусцировать licensing/*.py С -i licensing (runtime внутри)
cmd_licensing = [
    "pyarmor", "gen",
    "-O", str(obf_dir),
    "-i", "licensing",
    "licensing/license_manager.py",
    "licensing/license_client.py",
    "licensing/device_fingerprint.py",
    "licensing/public_key.py",
]
```

**Результат:**
- `build/obfuscated/pyarmor_runtime_XXXXXX/` - корневой runtime для main.py
- `build/obfuscated/licensing/pyarmor_runtime_XXXXXX/` - вложенный runtime для licensing/*

### 2. Исправлен `signer.spec`

**Было:** Дедупликация по basename - брался только один runtime

```python
seen = set()
for rt_dir in pyarmor_runtime_dirs:
    rt_name = os.path.basename(rt_dir)
    if rt_name not in seen:
        seen.add(rt_name)
        datas.append((rt_dir, rt_name))  # Оба в одно место!
```

**Стало:** Сохранение относительных путей - каждый runtime в своё место

```python
for rt_dir in pyarmor_runtime_dirs:
    # Вычисляем относительный путь от build/obfuscated/
    rel_path = os.path.relpath(rt_dir, _obfuscated_root)
    path_parts = rel_path.split(os.sep)
    
    if len(path_parts) == 1:
        # Корневой: pyarmor_runtime_XXXXXX -> _internal/pyarmor_runtime_XXXXXX/
        dest_path = path_parts[-1]
    else:
        # Вложенный: licensing/pyarmor_runtime_XXXXXX -> _internal/licensing/pyarmor_runtime_XXXXXX/
        dest_path = rel_path
    
    datas.append((rt_dir, dest_path))
```

**Результат:** PyInstaller копирует КАЖДЫЙ runtime с сохранением структуры

### 3. Исправлен `scripts/build/restore_originals.py`

Добавлено удаление корневого runtime (раньше удалялся только вложенный):

```python
# Корневой runtime
for item in root.iterdir():
    if item.is_dir() and item.name.startswith("pyarmor_runtime"):
        shutil.rmtree(item)

# Вложенный runtime в licensing/
for item in (root / "licensing").iterdir():
    if item.is_dir() and item.name.startswith("pyarmor_runtime"):
        shutil.rmtree(item)
```

## Итоговая структура после сборки

```
dist/Signer/
├── Signer.exe
└── _internal/
    ├── pyarmor_runtime_000000/          ← Корневой runtime (для main.py)
    │   ├── __init__.py                   (самодостаточный, БЕЗ относительного импорта)
    │   └── ...
    └── licensing/
        ├── pyarmor_runtime_000000/      ← Вложенный runtime (для licensing/*)
        │   ├── __init__.py               (может содержать относительный импорт)
        │   └── ...
        ├── license_manager.pyc
        ├── license_client.pyc
        └── ...
```

## Как проверить локально

### Шаг 1: Тестирование обфускации (без полной сборки)

```bash
# Запустить обфускацию
python scripts\build\obfuscate_licensing.py

# Проверить структуру
python scripts\build\test_obfuscation.py
```

`test_obfuscation.py` покажет:
- Сколько runtime директорий создано
- Где они находятся (корень / licensing/)
- Какие импорты в их `__init__.py`

**Ожидаемый результат:**
```
Found 2 runtime directories:

Runtime: pyarmor_runtime_000000
Type: ROOT (for main.py)
✓ OK: Appears to be correct root runtime

Runtime: licensing/pyarmor_runtime_000000
Type: NESTED (for licensing/*)
✓ OK: Nested runtime structure

✅ Structure looks correct!
```

### Шаг 2: Полная сборка

```bash
scripts\build\prepare_release.bat
```

### Шаг 3: Проверка финальной структуры

```bash
# Проверить наличие ОБОИХ runtime
dir dist\Signer\_internal\pyarmor_runtime_000000
dir dist\Signer\_internal\licensing\pyarmor_runtime_000000

# Запустить приложение
dist\Signer\Signer.exe
```

**Ожидаемый результат:** Приложение запускается без ImportError

## Техническое объяснение разрешения импортов

### main.py (корневой уровень):
```python
from pyarmor_runtime_000000 import __pyarmor__
```
↓
Ищет: `_internal/pyarmor_runtime_000000/__init__.py` (абсолютный путь от корня)
✓ Находит: корневой runtime с самодостаточной реализацией

### licensing/license_client.py (вложенный модуль):
```python
from .pyarmor_runtime_000000 import __pyarmor__
```
↓
Ищет: `_internal/licensing/pyarmor_runtime_000000/__init__.py` (относительно licensing/)
✓ Находит: вложенный runtime внутри licensing/

## Критические изменения

1. ✅ `scripts/build/obfuscate_licensing.py` - два раздельных вызова PyArmor
2. ✅ `signer.spec` - без дедупликации, с сохранением относительных путей
3. ✅ `scripts/build/restore_originals.py` - удаление обоих runtime
4. ✅ `scripts/build/test_obfuscation.py` - NEW: скрипт тестирования структуры

## Changelog

- **БАГ ИСПРАВЛЕН**: ImportError при запуске Signer.exe после обфускации
- Разделена обфускация main.py (корневой runtime) и licensing/* (вложенный runtime)
- Исправлена логика копирования PyArmor runtime в PyInstaller spec
- Добавлен тестовый скрипт для проверки структуры обфускации
