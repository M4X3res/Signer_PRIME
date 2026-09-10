# Изменения: использование 7z.exe вместо 7za.exe

## Изменено

Система автообновлений теперь использует `7z.exe` и `7z.dll` из директории `installer\` вместо `7za.exe` из `assets\`.

### Причина

Файлы `7z.exe` и `7z.dll` уже присутствуют в `installer\` для работы Inno Setup инсталлятора. Нет смысла дублировать их в `assets\`.

## Изменённые файлы

1. **updater.py**
   - Добавлена константа `SEVEN_ZIP_EXE = "7z.exe"`
   - `launch_updater_and_exit()` теперь передаёт путь к `7z.exe` как параметр `--7z`

2. **updater_main.py**
   - `extract_update()` принимает `seven_zip_exe: Path` как параметр
   - `main()` парсит аргумент `--7z` и передаёт его в `extract_update()`

3. **signer.spec**
   - Копирует `installer\7z.exe` и `installer\7z.dll` в сборку
   - Проверяет наличие обоих файлов перед сборкой

4. **build.bat**
   - Проверяет наличие `installer\7z.exe` и `installer\7z.dll`
   - Копирует оба файла в `dist\Signer\`

5. **BUILD_AUTOUPDATE.md**
   - Обновлены требования (используется `7z.exe` и `7z.dll` из `installer\`)
   - Обновлены команды копирования
   - Обновлена структура директории
   - Обновлён troubleshooting

6. **AUTOUPDATE_IMPLEMENTATION_REPORT.md**
   - Обновлены все упоминания `7za.exe` на `7z.exe` и `7z.dll`

7. **assets/7ZA_README.md**
   - Обновлён для отражения изменений

## Результат

Теперь для сборки требуется только проверить наличие `installer\7z.exe` и `installer\7z.dll`, которые уже должны быть в репозитории для работы Inno Setup.

Запустите `build.bat` для автоматической сборки с проверкой всех зависимостей.
