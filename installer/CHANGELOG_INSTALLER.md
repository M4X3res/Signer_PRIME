# Changelog - SignerInstaller.iss

## Последнее обновление (2026-09-15)

### ✅ Исправлено

#### 1. Кнопка "Повторить загрузку" теперь работает корректно

**Проблема:**
- При прерывании загрузки и повторном нажатии кнопки установщик мог зависать или падать
- Внутреннее состояние `TDownloadWizardPage` не очищалось между попытками

**Решение:**
- Добавлен `DownloadPage.Clear` в начале каждой попытки загрузки в цикле retry
- Список файлов теперь пересобирается перед каждым вызовом `Download()`
- Это официально рекомендуемый паттерн Inno Setup для страниц загрузки

**Код изменения:**
```pascal
repeat
  RetryDownload := False;
  DownloadPage.Clear;  // ← Добавлено!
  
  { Добавляем файлы заново }
  for I := 1 to {#SIGNER_PART_COUNT} do
    DownloadPage.Add(...);
  
  AddOptionalComponentsToDownload;
  DownloadPage.Download;
  ...
until not RetryDownload;
```

### 🆕 Добавлено

#### 2. Восстановлена функциональность загрузки дополнительных компонентов

**Компоненты:**
- **NVIDIA CUDA Toolkit** (~3.2 МБ сетевой установщик, полная установка ~3 ГБ)
  - URL: `https://developer.download.nvidia.com/compute/cuda/12.6.0/network_installers/cuda_12.6.0_windows_network.exe`
  - Автоматически определяется наличие CUDA на системе
  - Установка: тихая (`-s`)

- **FFmpeg** (~115 МБ)
  - URL: `https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip`
  - Автоматически определяется наличие в PATH
  - Распаковывается в `Program Files\ffmpeg`
  - Пользователю показывается информация о добавлении в PATH

- **K-Lite Codec Pack** (~60 МБ)
  - URL: `https://files2.codecguide.com/K-Lite_Codec_Pack_1995_Standard.exe`
  - Автоматически определяется через реестр
  - Установка: тихая (`/VERYSILENT /NORESTART`)

**Типы установки:**
```
[Types]
Name: "full"     - Полная установка (с CUDA, FFmpeg, K-Lite)
Name: "compact"  - Только базовая программа
Name: "custom"   - Выборочная установка
```

**Автоопределение:**
- Если компонент уже установлен в системе, он не отмечается для загрузки
- Функции детекции:
  - `DetectCuda()` - проверяет наличие папки CUDA Toolkit
  - `DetectFFmpeg()` - проверяет PATH и стандартные пути установки
  - `DetectKLite()` - проверяет ключи реестра

**Установка компонентов:**
- Происходит в фазе `ssPostInstall` (после распаковки основного архива)
- CUDA: запускается с параметром `-s` (silent)
- FFmpeg: распаковывается через 7z.exe в `Program Files`
- K-Lite: запускается с параметрами `/VERYSILENT /NORESTART`
- Все временные файлы удаляются после установки

### 📝 Структурные изменения

#### Новые функции:

```pascal
function DetectCuda: Boolean;
function DetectFFmpeg: Boolean;
function DetectKLite: Boolean;
procedure AddOptionalComponentsToDownload;
```

#### Обновлённые функции:

- `InitializeWizard` - добавлено упоминание опциональных компонентов в welcome message
- `NextButtonClick` - добавлен вызов `AddOptionalComponentsToDownload` в retry-цикле
- `CurStepChanged` - добавлена установка опциональных компонентов в `ssPostInstall`

#### Новые константы:

```pascal
#define CUDA_URL "https://developer.download.nvidia.com/compute/cuda/12.6.0/network_installers/cuda_12.6.0_windows_network.exe"
#define CUDA_SIZE 3200000
#define FFMPEG_URL "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
#define FFMPEG_SIZE 115000000
#define KLITE_URL "https://files2.codecguide.com/K-Lite_Codec_Pack_1995_Standard.exe"
#define KLITE_SIZE 60000000
```

## Обновление URL и версий

При необходимости обновления URL компонентов измените константы в начале файла:

```pascal
; ──────────────────────────────────────────────────────────────────
; Optional components — URLs for additional downloads
; ──────────────────────────────────────────────────────────────────
#define CUDA_URL "..."
#define FFMPEG_URL "..."
#define KLITE_URL "..."
```

## Тестирование

Перед выпуском релиза рекомендуется протестировать:

1. ✅ Полная установка (full) - все компоненты
2. ✅ Компактная установка (compact) - только Signer
3. ✅ Прерывание загрузки и повторная попытка
4. ✅ Установка с уже установленными компонентами (CUDA/FFmpeg/K-Lite)
5. ✅ Проверка установки каждого компонента отдельно

## История изменений

- **2026-09-15 09:38**: **КРИТИЧНО:** Исправлен `Result := True` в except на `Result := False` (исключение пробрасывалось, окно зависало)
- **2026-09-15 09:33**: Попытка исправления через убирание вложенности try-except-finally (не помогло)
- **2026-09-15 09:30**: Исправлена ошибка `'#13#10'` → `#13#10` в сообщениях об ошибках
- **2026-09-15 09:00**: Добавлена поддержка опциональных компонентов, исправлена кнопка повтора загрузки
- **2026-09-14**: Улучшен прогресс-бар, добавлена проверка SHA-256
- **2026-09-13**: Первая версия с многотомным архивом
