# Настройка Inno Download Plugin (IDP)

## Что это?

Inno Download Plugin (IDP) добавляет продвинутый прогресс-бар скачивания в Inno Setup с:
- ✅ Общим процентом скачивания
- ✅ Процентом текущего файла
- ✅ Скоростью скачивания (МБ/с, КБ/с)
- ✅ Автоматическим возобновлением прерванных загрузок
- ✅ Кнопкой повтора при ошибках

## Установка IDP

### Вариант 1: Автоматическая установка (рекомендуется)

1. Скачайте IDP:
   ```powershell
   Invoke-WebRequest -Uri "https://raw.githubusercontent.com/DomGries/IDP-Releases/main/idp.iss" -OutFile "installer\idp.iss"
   ```

2. Скомпилируйте installer:
   ```cmd
   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\SignerInstaller.iss
   ```

### Вариант 2: Ручная установка

1. Откройте https://mitrich.net23.net/?idp
2. Скачайте последнюю версию `idp.iss`
3. Поместите файл в папку `installer/`
4. Скомпилируйте installer

### Вариант 3: Установка в Inno Setup (глобально)

1. Скачайте `idp.iss` с https://mitrich.net23.net/?idp
2. Скопируйте в:
   ```
   C:\Program Files (x86)\Inno Setup 6\
   ```
3. IDP будет доступен во всех проектах через `#include <idp.iss>`

## Проверка установки

После компиляции запустите `SignerInstaller.exe`:

✅ **С IDP**: Вы увидите детальное окно скачивания с:
- Название текущего файла
- Процент текущего файла
- Общий прогресс (файл X из Y)
- Скорость скачивания в реальном времени
- Прогресс-бар с процентами

❌ **Без IDP**: Установщик не скомпилируется и выдаст ошибку:
```
Error: Could not find include file 'idp.iss'
```

## Если не хотите использовать IDP

Если IDP вызывает проблемы, можно вернуться к стандартному методу:

1. Откройте `installer\SignerInstaller.iss`
2. Закомментируйте строку:
   ```iss
   ; #include <idp.iss>
   ```
3. Удалите весь код в секции `[Code]` связанный с IDP
4. Используйте старую версию с `Flags: external download` (см. git history)

**Минус**: Не будет детального прогресса, только стандартный прогресс-бар Inno Setup.

## Альтернатива: Встроенный downloader

Если IDP не подходит, можно использовать встроенный PowerShell-downloader с прогрессом:

```pascal
function DownloadFileWithProgress(const URL, FileName: String; Size: Int64): Boolean;
var
  PSScript: String;
  ResultCode: Integer;
begin
  PSScript := 
    'param($url,$dest,$size) ' +
    '$client = New-Object System.Net.WebClient; ' +
    '$client.DownloadProgressChanged += { ' +
    '  $percent = $_.ProgressPercentage; ' +
    '  Write-Progress -Activity "Скачивание" -Status "$percent%" -PercentComplete $percent ' +
    '}; ' +
    '$client.DownloadFileAsync($url, $dest).Wait(); ';
  
  Result := Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -Command "' + PSScript + '" ' +
    '-url "' + URL + '" -dest "' + ExpandConstant('{tmp}\' + FileName) + '" -size ' + IntToStr(Size),
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) and (ResultCode = 0);
end;
```

Но это решение менее надёжно, чем IDP.

## Рекомендация

**Используйте IDP** - это стандартный, надёжный плагин, который:
- Поддерживается сообществом Inno Setup
- Используется в тысячах коммерческих установщиков
- Имеет встроенную обработку ошибок
- Автоматически возобновляет загрузки
- Показывает профессиональный UI

Скачайте один раз и забудьте о проблемах со скачиванием!
