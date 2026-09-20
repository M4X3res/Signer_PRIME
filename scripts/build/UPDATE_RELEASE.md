# Обновление релиза v2.0.0

## Быстрый старт

После выполнения `prepare_release.bat` и получения новых файлов в `release/`:

```powershell
.\scripts\build\upload_release.ps1
```

Скрипт автоматически:
1. Обнаружит существующий релиз v2.0.0
2. Предложит обновить его
3. Удалит **только asset'ы** (файлы) из релиза
4. Загрузит новые файлы из `release/`
5. Сохранит тег, описание и статус релиза

## Что обновляется

- ✅ **Все части архива** Signer.7z.001 - Signer.7z.041
- ✅ **checksum.sha256** - контрольные суммы
- ✅ **README.md, release_notes.txt, BUILD_AUTOUPDATE.md** - документация

## Что НЕ изменяется

- ❌ Тег релиза (v2.0.0)
- ❌ Название релиза (Signer PRIME v2.0.0)
- ❌ Описание релиза
- ❌ Статус (draft/prerelease/published)

## Важно

### Installer будет продолжать работать

`installer/SignerInstaller.iss` уже настроен на v2.0.0 и 41 часть архива.
После обновления релиза installer автоматически будет скачивать **новые файлы**.

### Проверка целостности

Installer проверяет SHA-256 каждой части по `checksum.sha256`, поэтому:
- Всегда загружайте актуальный `checksum.sha256`
- Убедитесь, что `prepare_release.bat` успешно выполнился

### Если изменилось количество частей

Если в будущем изменится:
- Количество частей архива (не 41)
- Размер частей (не 100MB)
- Версия приложения (не 2.0.0)

Обновите `installer/SignerInstaller.iss`:
```iss
#define SIGNER_PART_COUNT 41  ; <-- Новое количество
#define RELEASE_TAG "v2.0.0"   ; <-- Новый тег
```

И добавьте/удалите соответствующие `Source:` записи в секции `[Files]`.

## Примеры использования

### Обновить текущий релиз v2.0.0

```powershell
.\scripts\build\upload_release.ps1
```

### Создать новый релиз v2.1.0

1. Обновите `version.json`:
   ```json
   {"version": "2.1.0"}
   ```

2. Запустите:
   ```powershell
   .\scripts\build\upload_release.ps1
   ```

3. Обновите `installer/SignerInstaller.iss`:
   ```iss
   #define AppVersion "2.1.0"
   #define RELEASE_TAG "v2.1.0"
   ```

### Создать черновик релиза

```powershell
.\scripts\build\upload_release.ps1 -Draft
```

## Откат изменений

Если что-то пошло не так:

1. **Удалить релиз полностью**:
   ```powershell
   gh release delete v2.0.0 --repo M4X3res/Signer_PRIME --yes
   ```

2. **Восстановить из старой версии**:
   - Скачайте старые файлы из бэкапа
   - Положите в `release/`
   - Запустите `upload_release.ps1`

## Troubleshooting

### Ошибка "Release not found"

Релиз v2.0.0 не существует. Создайте его:
```powershell
.\scripts\build\upload_release.ps1
```

### Ошибка "Asset not found"

Один из файлов отсутствует в `release/`. Проверьте:
```powershell
dir release\Signer.7z.* | measure-object
```
Должно быть **41 файл** (.001 - .041).

### GitHub CLI не авторизован

```powershell
gh auth login
```

### Медленная загрузка

GitHub имеет ограничения на скорость загрузки. При больших файлах (4GB) процесс может занять 10-30 минут.

## Автоматизация

Для CI/CD используйте:

```powershell
$env:GH_TOKEN = "your_github_token"
.\scripts\build\prepare_release.bat
.\scripts\build\upload_release.ps1 -Draft  # Создать черновик для проверки
```

После проверки опубликуйте:
```powershell
gh release edit v2.0.0 --repo M4X3res/Signer_PRIME --draft=false
```
