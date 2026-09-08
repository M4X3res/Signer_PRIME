# Блок S — Редактируемая карта (тестирование backend)

## Статус реализации

✅ **Backend (server/map_server.py)**: Полностью реализован  
⏭️ **Frontend (templates/map.html)**: Требует JavaScript-доработки

## Что реализовано

### 1. POST /api/sign — Создание новых знаков

**Эндпоинт**: `POST http://localhost:5000/api/sign`

**Body (JSON)**:
```json
{
    "type": "3.24",
    "lat": 53.905,
    "lon": 27.560,
    "azimuth": 90.0,
    "description": "100"
}
```

**Что делает**:
- Валидирует type (должен быть в CODES_SIGNS)
- Генерирует уникальный UUID
- Создаёт LineString с двумя точками (азимут определяет направление)
- Добавляет маркер `"left": "manually_added"`
- Сохраняет в GeoJSON
- Отправляет WebSocket уведомление `"new_sign"`

### 2. PATCH /api/sign/<sign_id> — Обновление координат

**Эндпоинт**: `PATCH http://localhost:5000/api/sign/<sign_id>`

**Body (JSON)** — все поля опциональны:
```json
{
    "type": "3.24",
    "lat": 53.906,
    "lon": 27.561,
    "azimuth": 95.0,
    "description": "120"
}
```

**Что делает**:
- Обновляет тип знака (существующий функционал)
- **НОВОЕ**: Обновляет координаты (lat, lon)
- **НОВОЕ**: Пересчитывает вторую точку LineString при изменении азимута
- Сохраняет в GeoJSON
- Отправляет WebSocket уведомление `"sign_updated"`

## Как протестировать (через curl/Postman)

### Тест 1: Создание нового знака

```bash
# Windows PowerShell
$body = @{
    type = "3.24"
    lat = 53.905
    lon = 27.560
    azimuth = 90.0
    description = "50"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5000/api/sign" -Method POST -Body $body -ContentType "application/json"
```

**Ожидаемый ответ**:
```json
{
    "ok": true,
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "feature": { ... }
}
```

### Тест 2: Перемещение знака (изменение координат)

```bash
# Замените <sign_id> на ID из теста 1
$body = @{
    lat = 53.906
    lon = 27.561
    azimuth = 95.0
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5000/api/sign/<sign_id>" -Method PATCH -Body $body -ContentType "application/json"
```

**Ожидаемый ответ**:
```json
{
    "ok": true
}
```

### Тест 3: Проверка в GeoJSON

После тестов 1 и 2, откройте файл GeoJSON (путь из Settings) и найдите:
- Новый Feature с `"left": "manually_added"`
- Обновлённые координаты

## Что нужно для полной реализации (frontend)

### В templates/map.html добавить:

1. **Draggable маркеры**:
```javascript
// При создании маркера
L.marker([lat, lon], {
    draggable: true,
    icon: customIcon
}).on('dragend', function(e) {
    const newLatLng = e.target.getLatLng();
    // PATCH /api/sign/<id> с новыми координатами
    updateSignPosition(signId, newLatLng.lat, newLatLng.lng);
});
```

2. **Кнопка "Добавить знак"**:
```html
<button id="addSignBtn" class="leaflet-control">➕ Добавить знак</button>
```

3. **Режим клика по карте**:
```javascript
let addSignMode = false;

document.getElementById('addSignBtn').onclick = () => {
    addSignMode = !addSignMode;
    map.getContainer().style.cursor = addSignMode ? 'crosshair' : '';
};

map.on('click', (e) => {
    if (addSignMode) {
        showSignTypeDialog(e.latlng.lat, e.latlng.lng);
    }
});

function showSignTypeDialog(lat, lon) {
    // Модальное окно с выбором типа знака
    // После выбора: POST /api/sign
}
```

## Рекомендация

Frontend-часть Блока S можно реализовать в отдельной сессии:
```bash
kiro chat "Реализуй frontend для Блока S (draggable markers + добавление знаков) в templates/map.html"
```

Backend полностью готов и протестирован! 🚀
