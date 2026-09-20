"""
Диагностика проблемы с координатами (Беларусь → Африка)
"""
import json
import sys

# Читаем GeoJSON
geojson_path = r'E:\Urban\vid\test\test_new_algo.geojson'

with open(geojson_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data.get('features', [])
print(f"Всего features: {len(features)}\n")

if features:
    feat = features[0]
    coords = feat['geometry']['coordinates']
    props = feat['properties']
    
    print("=== ПЕРВЫЙ ЗНАК ===")
    print(f"Тип: {props.get('type')}")
    print(f"Координаты (GeoJSON): {coords}")
    print(f"  Точка 1: lon={coords[0][0]:.6f}, lat={coords[0][1]:.6f}")
    print(f"  Точка 2: lon={coords[1][0]:.6f}, lat={coords[1][1]:.6f}")
    
    print(f"\ncar_coordinates (из properties):")
    car_x = eval(props.get('car_coordinates_x', '[]'))
    car_y = eval(props.get('car_coordinates_y', '[]'))
    
    if car_x and car_y:
        print(f"  car_x (EPSG:32635): {car_x[-1]:.1f}")
        print(f"  car_y (EPSG:32635): {car_y[-1]:.1f}")
        
        # Конвертируем правильно
        from pyproj import Transformer
        
        # Вариант 1: без always_xy (возвращает lat, lon)
        t1 = Transformer.from_crs('epsg:32635', 'epsg:4326')
        lat1, lon1 = t1.transform(car_x[-1], car_y[-1])
        print(f"\n  transformer.transform(car_x, car_y):")
        print(f"    → lat={lat1:.6f}, lon={lon1:.6f}")
        
        # Вариант 2: с always_xy (возвращает lon, lat)
        t2 = Transformer.from_crs('epsg:32635', 'epsg:4326', always_xy=True)
        lon2, lat2 = t2.transform(car_x[-1], car_y[-1])
        print(f"\n  transformer.transform(car_x, car_y, always_xy=True):")
        print(f"    → lon={lon2:.6f}, lat={lat2:.6f}")
        
        print(f"\n❌ ПРОБЛЕМА:")
        print(f"  GeoJSON содержит: lon={coords[0][0]:.6f}, lat={coords[0][1]:.6f}")
        print(f"  Беларусь должна быть: lon≈27.5, lat≈53.9")
        
        if abs(coords[0][1]) < 1.0:
            print(f"\n  ⚠️ Широта {coords[0][1]:.6f} близка к экватору (0°) — ОШИБКА!")
            print(f"  Похоже car_x и car_y перепутаны местами при конвертации")

print("\n=== ПРОВЕРКА CONVERTER ===")
from core.converter import Converter
conv = Converter()

# Тестовые координаты Минска в EPSG:32635
minsk_x = 549933  # Easting
minsk_y = 5979471  # Northing

print(f"Входные данные (EPSG:32635, Минск):")
print(f"  x={minsk_x}, y={minsk_y}")

result = conv.coordinateConverter(minsk_x, minsk_y, 'epsg:32635', 'epsg:4326')
print(f"\nConverter.coordinateConverter(x, y, '32635', '4326'):")
print(f"  → {result}")
print(f"  → Интерпретируется как: lat={result[0]:.6f}, lon={result[1]:.6f}")

print(f"\nОжидаемые координаты Минска: lat≈53.9, lon≈27.6")
if abs(result[0] - 27.6) < 1 and abs(result[1] - 53.9) < 1:
    print("  ❌ ОШИБКА: lat и lon перепутаны!")
elif abs(result[0] - 53.9) < 1 and abs(result[1] - 27.6) < 1:
    print("  ✅ Порядок правильный: (lat, lon)")
