# Автоматическое добавление в PATH при установке

## Изменения в SignerInstaller.iss

### ✅ Что добавлено

Инсталлятор теперь **автоматически добавляет** в системную переменную PATH следующие компоненты:

1. **NVIDIA CUDA Toolkit** → `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin`
2. **FFmpeg** → `C:\Program Files\ffmpeg\bin`
3. **K-Lite Codec Pack** → `C:\Program Files\K-Lite Codec Pack\MPC-HC64`

### 🔧 Реализация

#### 1. Новые функции в секции `[Code]`

**`AddDirToPath(DirPath: String): Boolean`**
- Проверяет существование директории
- Читает текущий системный PATH из реестра
- Проверяет, что путь еще не добавлен (case-insensitive)
- Добавляет путь в PATH
- Записывает изменения в реестр (`HKEY_LOCAL_MACHINE`)
- Триггерит обновление окружения через `setx`

**`RemoveDirFromPath(DirPath: String): Boolean`**
- Удаляет путь из PATH при деинсталляции
- Case-insensitive поиск и удаление
- Корректно обрабатывает разделители (`;`)

**`FindCudaBinPath(): String`**
- Автоматически находит последнюю установленную версию CUDA
- Ищет в `Program Files` и `Program Files (x86)`
- Возвращает путь к `bin` директории (например, `v12.6\bin`)

#### 2. Модификация `CurStepChanged(CurStep: TSetupStep)`

В секции `ssPostInstall` после установки каждого компонента вызывается `AddDirToPath()`:

```pascal
{ CUDA }
if AddDirToPath(CudaPath) then
  Log('✓ CUDA added to PATH: ' + CudaPath)

{ FFmpeg }
if AddDirToPath(ExpandConstant('{pf}\ffmpeg\bin')) then
  Log('✓ FFmpeg added to PATH')

{ K-Lite }
if AddDirToPath(KLiteInstallPath) then
  Log('✓ K-Lite added to PATH')
```

#### 3. Новая процедура `CurUninstallStepChanged`

При деинсталляции (`usPostUninstall`) автоматически удаляет все добавленные пути из PATH:

```pascal
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RemoveDirFromPath(FindCudaBinPath);
    RemoveDirFromPath(ExpandConstant('{pf}\ffmpeg\bin'));
    RemoveDirFromPath(ExpandConstant('{pf}\K-Lite Codec Pack\MPC-HC64'));
    RemoveDirFromPath(ExpandConstant('{pf32}\K-Lite Codec Pack\MPC-HC64'));
  end;
end;
```

#### 4. Флаг в секции `[Setup]`

```ini
ChangesEnvironment=yes
```

Этот флаг уведомляет Windows, что инсталлятор изменяет переменные окружения.

### 📋 Логирование

Все операции с PATH логируются в файл установки:

```
AddDirToPath: Successfully added: C:\Program Files\ffmpeg\bin
✓ FFmpeg added to PATH
RemoveDirFromPath: Successfully removed: C:\Program Files\ffmpeg\bin
```

### 🔒 Права доступа

- Требуются права администратора (`PrivilegesRequired=admin`)
- Изменения применяются к **системной** переменной PATH (для всех пользователей)
- Используется ключ реестра: `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment`

### ⚠️ Важно

1. **Перезапуск терминала:** После установки нужно перезапустить терминал/CMD/PowerShell для применения изменений PATH

2. **Уведомление пользователя:** Для FFmpeg показывается MessageBox с информацией о добавлении в PATH

3. **Безопасность:** Функция проверяет наличие дубликатов перед добавлением

4. **Откат при деинсталляции:** Все изменения PATH автоматически откатываются при удалении программы

### 🧪 Проверка после установки

После установки и перезапуска терминала выполните:

```cmd
where nvcc
where ffmpeg
where mpc-hc64.exe
```

Должны отобразиться полные пути к исполняемым файлам.

### 📝 Commit

```
a778879 - feat(installer): auto-add CUDA, FFmpeg, K-Lite to PATH on install
```

**Изменения:**
- +234 строк добавлено
- -10 строк удалено
- Полностью обратная совместимость (не ломает существующую функциональность)

---

**Автор:** Kiro AI Agent  
**Дата:** 2026-09-16
