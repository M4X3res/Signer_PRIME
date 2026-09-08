"""
tests/conftest.py
Общие фикстуры для pytest.
"""
import pytest
import sys


@pytest.fixture(scope="session")
def qapp():
    """
    Создаёт QApplication в offscreen режиме для тестов GUI компонентов.
    
    Использует platform "offscreen" чтобы не открывать реальные окна во время тестов.
    Фикстура session-scope, т.е. QApplication создаётся один раз на все тесты.
    """
    from PyQt6.QtWidgets import QApplication
    
    # Проверяем, не создано ли уже приложение
    app = QApplication.instance()
    
    if app is None:
        # Создаём новое приложение в offscreen режиме
        app = QApplication(["-platform", "offscreen"])
    
    yield app
    
    # Cleanup после всех тестов
    # QApplication.quit() не вызываем, т.к. это может вызвать проблемы
    # с другими тестами в той же сессии
