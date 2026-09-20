"""Run separately: these tests require QApplication, not QCoreApplication."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import Mock
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtGui import QCloseEvent
from ui.widgets.update_dialog import UpdateDialog


class UpdateDialogLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = UpdateDialog.__new__(UpdateDialog)
        QDialog.__init__(self.dialog)
        self.dialog.download_worker = Mock()
        self.dialog.download_worker.isRunning.return_value = True
        self.dialog._worker_active = True
        self.dialog._pending_result = None
        self.dialog._download_ready = False
        for name in ('status_label', 'later_btn', 'update_btn', 'progress_bar'):
            setattr(self.dialog, name, Mock())
        self.applied = Mock()
        self.dialog.update_applied.connect(self.applied)
        self.dialog.show()

    def tearDown(self):
        self.dialog.download_worker.isRunning.return_value = False
        self.dialog._worker_active = False
        self.dialog.reject()

    def finish_worker(self):
        self.dialog.download_worker.isRunning.return_value = False
        self.dialog._on_worker_finished()

    def test_escape_waits_for_cancellation(self):
        self.dialog.reject()
        self.dialog.download_worker.cancel.assert_called_once()
        self.assertTrue(self.dialog.isVisible())
        self.finish_worker()
        self.assertFalse(self.dialog.isVisible())
        self.applied.assert_not_called()

    def test_window_close_waits_and_ignores_late_success(self):
        event = QCloseEvent()
        self.dialog.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.dialog._on_download_finished()
        self.finish_worker()
        self.applied.assert_not_called()
        self.assertFalse(self.dialog.isVisible())

    def test_success_waits_until_thread_finishes(self):
        self.dialog._on_download_finished()
        self.applied.assert_not_called()
        self.finish_worker()
        self.applied.assert_called_once()

    def test_retry_cannot_replace_running_worker(self):
        worker = self.dialog.download_worker
        self.dialog._start_download()
        self.assertIs(self.dialog.download_worker, worker)


if __name__ == '__main__':
    unittest.main()
