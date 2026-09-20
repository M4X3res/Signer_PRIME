"""One online authority for desktop actions and the embedded map server."""
from functools import wraps

_manager = None


def set_manager(manager):
    global _manager
    _manager = manager


def get_manager():
    return _manager


def online_action(function):
    """Check online after an action; a known denial still prevents new work."""
    @wraps(function)
    def guarded(self, *args, **kwargs):
        from PyQt6.QtWidgets import QMessageBox
        manager = get_manager()
        if manager is None or not manager.has_online_access():
            QMessageBox.warning(self, 'Лицензия', 'Работа заблокирована: требуется проверка лицензии.')
            if manager is not None:
                manager.verify_access_async(lambda status, error: None)
            if function.__name__ == '_save_results':
                self._on_save_error('Результаты не экспортированы: нет подтверждения лицензии. Прогресс сохранён.')
            return
        key = '_license_pending_' + function.__name__
        if getattr(self, key, False):
            return
        setattr(self, key, True)
        def checked(status, error):
            setattr(self, key, False)
        try:
            return function(self, *args, **kwargs)
        finally:
            manager.verify_access_async(checked)
    return guarded
