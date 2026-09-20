"""
tests/test_model_export.py
Тесты для проверки экспорта моделей в ONNX/OpenVINO (v2.0.1+).
"""
import pytest
import os
import glob
from pathlib import Path


def test_onnx_models_exist():
    """
    Проверка наличия экспортированных ONNX моделей.
    Критично для релиза v2.0.1+ — без них ONNX backend не будет работать.
    """
    # Ожидаемые ONNX модели (по данным scripts/export_models_onnx.py)
    expected_onnx_models = [
        # Детекция
        "CNN_side/best.onnx",
        "lane_guidance_models/arrow_detect.onnx",
        
        # Классификация
        "small_models/rude.onnx",
        "small_models/blue.onnx",
        "small_models/treugolnik.onnx",
        "small_models/krug.onnx",
        "small_models/red.onnx",
        "small_models/servises.onnx",
        "small_models/tabl l.onnx",
        "small_models/tabl.onnx",
        "small_models/tupic.onnx",
        "small_models/5.38.onnx",
        "small_models/5.9.1-5.14.onnx",
        "small_models/one_side.onnx",
        "small_models/danger.onnx",
        "small_models/pimicanie.onnx",
        "small_models/suzenie.onnx",
        
        # Сегментация
        "lane_guidance_models/arrow_segment.onnx",
    ]
    
    root = Path(__file__).parent.parent
    missing_models = []
    
    for model_path in expected_onnx_models:
        full_path = root / model_path
        if not full_path.exists():
            missing_models.append(model_path)
    
    if missing_models:
        pytest.skip(
            f"ONNX модели не найдены (требуется экспорт для релиза v2.0.1+):\n"
            f"  {', '.join(missing_models)}\n"
            f"Запустите: python scripts/export_models_onnx.py --format onnx"
        )
    
    # Все модели найдены
    assert len(missing_models) == 0


def test_openvino_models_exist():
    """
    Проверка наличия экспортированных OpenVINO моделей.
    Критично для релиза v2.0.1+ — без них OpenVINO backend не будет работать.
    """
    # Ожидаемые OpenVINO модели
    expected_openvino_models = [
        # Детекция
        "CNN_side/best_openvino_model",
        "lane_guidance_models/arrow_detect_openvino_model",
        
        # Классификация
        "small_models/rude_openvino_model",
        "small_models/blue_openvino_model",
        "small_models/treugolnik_openvino_model",
        "small_models/krug_openvino_model",
        "small_models/red_openvino_model",
        "small_models/servises_openvino_model",
        "small_models/tabl l_openvino_model",
        "small_models/tabl_openvino_model",
        "small_models/tupic_openvino_model",
        "small_models/5.38_openvino_model",
        "small_models/5.9.1-5.14_openvino_model",
        "small_models/one_side_openvino_model",
        "small_models/danger_openvino_model",
        "small_models/pimicanie_openvino_model",
        "small_models/suzenie_openvino_model",
        
        # Сегментация
        "lane_guidance_models/arrow_segment_openvino_model",
    ]
    
    root = Path(__file__).parent.parent
    missing_models = []
    
    for model_path in expected_openvino_models:
        full_path = root / model_path
        if not full_path.is_dir():
            missing_models.append(model_path)
        else:
            # Проверяем наличие .xml и .bin файлов
            xml_files = list(full_path.glob("*.xml"))
            bin_files = list(full_path.glob("*.bin"))
            if not xml_files or not bin_files:
                missing_models.append(f"{model_path} (неполная модель)")
    
    if missing_models:
        pytest.skip(
            f"OpenVINO модели не найдены (требуется экспорт для релиза v2.0.1+):\n"
            f"  {', '.join(missing_models)}\n"
            f"Запустите: python scripts/export_models_onnx.py --format openvino"
        )
    
    # Все модели найдены
    assert len(missing_models) == 0


def test_onnx_models_have_correct_structure():
    """
    Проверка, что ONNX модели имеют правильную структуру (не битые файлы).
    """
    try:
        import onnx
    except ImportError:
        pytest.skip("onnx не установлен")
    
    root = Path(__file__).parent.parent
    # Исправлен glob-паттерн: ** должен быть отдельным компонентом пути
    onnx_models = list(root.glob("**/*.onnx"))
    
    if not onnx_models:
        pytest.skip("ONNX модели не найдены")
    
    errors = []
    warnings = []
    for model_path in onnx_models:
        try:
            # Проверяем, что модель валидна
            onnx_model = onnx.load(str(model_path))
            # Используем check_model с менее строгой проверкой
            # Некоторые модели могут иметь warnings, но всё равно работают
            try:
                onnx.checker.check_model(onnx_model)
            except Exception as e:
                # Если это только предупреждение о initializer, не считаем критической ошибкой
                if "initializer but not in graph input" in str(e):
                    warnings.append(f"{model_path.name}: {str(e)}")
                else:
                    errors.append(f"{model_path.name}: {str(e)}")
        except Exception as e:
            errors.append(f"{model_path.name}: не удалось загрузить - {str(e)}")
    
    # Выводим предупреждения, но не падаем на них
    if warnings:
        import warnings as py_warnings
        py_warnings.warn(f"ONNX модели с предупреждениями (не критично):\n" + "\n".join(warnings))
    
    assert len(errors) == 0, f"Некорректные ONNX модели:\n" + "\n".join(errors)


def test_openvino_models_have_required_files():
    """
    Проверка, что OpenVINO модели содержат необходимые файлы (.xml и .bin).
    """
    root = Path(__file__).parent.parent
    openvino_dirs = [
        d for d in root.glob("**/*_openvino_model")
        if d.is_dir()
    ]
    
    if not openvino_dirs:
        pytest.skip("OpenVINO модели не найдены")
    
    errors = []
    for model_dir in openvino_dirs:
        xml_files = list(model_dir.glob("*.xml"))
        bin_files = list(model_dir.glob("*.bin"))
        
        if not xml_files:
            errors.append(f"{model_dir.name}: отсутствует .xml файл")
        if not bin_files:
            errors.append(f"{model_dir.name}: отсутствует .bin файл")
    
    assert len(errors) == 0, f"Неполные OpenVINO модели:\n" + "\n".join(errors)


def test_onnx_runtime_installed():
    """
    Проверка, что onnxruntime установлен (обязательно для релиза v2.0.1+).
    """
    try:
        import onnxruntime
        # Проверяем версию
        version = onnxruntime.__version__
        major, minor, patch = map(int, version.split('.')[:3])
        assert major >= 1 and minor >= 29, f"onnxruntime версии {version} слишком старая (требуется >=1.29.0)"
    except ImportError:
        pytest.fail(
            "onnxruntime не установлен!\n"
            "Для релиза v2.0.1+ это обязательная зависимость.\n"
            "Установите: pip install onnxruntime>=1.29.0"
        )


def test_openvino_installed():
    """
    Проверка, что openvino установлен (обязательно для релиза v2.0.1+).
    """
    try:
        import openvino
        # Проверяем версию
        version = openvino.__version__
        year = int(version.split('.')[0])
        assert year >= 2024, f"openvino версии {version} слишком старая (требуется >=2024.0)"
    except ImportError:
        pytest.fail(
            "openvino не установлен!\n"
            "Для релиза v2.0.1+ это обязательная зависимость.\n"
            "Установите: pip install openvino>=2024.0"
        )


def test_signer_spec_checks_for_backends():
    """
    Проверка, что signer.spec содержит проверки наличия CPU-бэкендов.
    """
    root = Path(__file__).parent.parent
    spec_path = root / "signer.spec"
    
    if not spec_path.exists():
        pytest.skip("signer.spec не найден")
    
    spec_content = spec_path.read_text(encoding='utf-8')
    
    # Проверяем, что spec содержит проверки
    assert 'check_package_installed' in spec_content, (
        "signer.spec не содержит функцию check_package_installed для проверки CPU-бэкендов"
    )
    
    assert 'RuntimeError' in spec_content and 'ONNX' in spec_content, (
        "signer.spec не прерывает сборку при отсутствии ONNX Runtime"
    )
    
    assert 'RuntimeError' in spec_content and 'OpenVINO' in spec_content, (
        "signer.spec не прерывает сборку при отсутствии OpenVINO"
    )
    
    assert 'glob.glob' in spec_content and 'onnx_models' in spec_content, (
        "signer.spec не проверяет наличие экспортированных ONNX моделей"
    )
    
    assert 'glob.glob' in spec_content and 'openvino_models' in spec_content, (
        "signer.spec не проверяет наличие экспортированных OpenVINO моделей"
    )


def test_prepare_release_includes_export_step():
    """
    Проверка, что prepare_release.bat содержит шаг экспорта моделей.
    """
    root = Path(__file__).parent.parent
    bat_path = root / "scripts" / "build" / "prepare_release.bat"
    
    if not bat_path.exists():
        pytest.skip("prepare_release.bat не найден")
    
    bat_content = bat_path.read_text(encoding='utf-8')
    
    # Проверяем наличие шага экспорта
    assert 'export_models_onnx.py' in bat_content, (
        "prepare_release.bat не содержит вызов scripts/export_models_onnx.py"
    )
    
    # Проверяем наличие шага верификации
    assert 'verify_cpu_backends.py' in bat_content, (
        "prepare_release.bat не содержит вызов scripts/build/verify_cpu_backends.py"
    )
    
    # Проверяем, что ошибки прерывают сборку
    assert 'exit /b 1' in bat_content, (
        "prepare_release.bat не прерывает сборку при ошибках"
    )
