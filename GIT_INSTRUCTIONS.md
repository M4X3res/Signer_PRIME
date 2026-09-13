# Инструкция для Git Commit & Push

## ✅ Готово к коммиту

Все изменения добавлены в staging area (`git add -A` выполнено).

## Автоматический способ (выберите один)

### Вариант 1: Batch скрипт (Windows CMD)
```bash
git_commit_and_push.bat
```

### Вариант 2: PowerShell скрипт
```powershell
.\git_commit_push.ps1
```

### Вариант 3: Bash скрипт (Git Bash)
```bash
bash git_commit_push.sh
```

Все скрипты используют подготовленное сообщение коммита из `.git_commit_msg.txt`.

## Ручной способ

### Быстрый (одна команда)
```bash
git commit -F .git_commit_msg.txt && git push
```

### Пошаговый

1. **Создать коммит:**
```bash
git commit -F .git_commit_msg.txt
```

2. **Выполнить push:**
```bash
git push
```

### Альтернатива (короткое сообщение)
```bash
git commit -m "fix: production bugfixes (tasks 1-5)" && git push
```

## Проверка после push

```bash
# Проверить статус
git status

# Посмотреть последний коммит
git log -1

# Проверить удалённую ветку
git log origin/main -1
```

## Изменённые файлы в коммите

**Клиент (6):**
- `.gitignore`
- `configs/settings.py`
- `licensing/public_key.py`
- `RELEASE.md`
- `scripts/build/prepare_release.bat`
- `tests/test_licensing.py`

**Сервер (6):**
- `signer-license-server/.env.example`
- `signer-license-server/README.md`
- `signer-license-server/app/config.py`
- `signer-license-server/app/main.py`
- `signer-license-server/app/services/stripe_service.py`
- `signer-license-server/scripts/create_license_manual.py`

**Новые файлы (10):**
- `build_config.json.example`
- `test_fixes.py`
- `run_all_tests.bat`
- `git_commit_and_push.bat`
- `BUGFIXES_README.md`
- `SUMMARY.md`
- `QUICKREF.md`
- `FIXES_REPORT.md`
- `CHECKLIST.md`
- `FILES_CHANGES.md`
- `INDEX.md`

**Итого:** 22 файла (12 изменённых + 10 новых)
