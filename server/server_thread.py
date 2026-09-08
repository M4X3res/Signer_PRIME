"""
ServerThread — запускает Flask в отдельном QThread.
UI общается с сервером только через сигналы и HTTP/SocketIO.
"""
from PyQt6.QtCore import QThread, pyqtSignal


class ServerThread(QThread):
    started_ok  = pyqtSignal(int)   # port
    error       = pyqtSignal(str)

    def __init__(self, port: int = 3000, parent=None):
        super().__init__(parent)
        self.port = port
        self.daemon = True   # setDaemon() убран в Python 3.10+
        
        # Увеличиваем размер стека для избежания STATUS_STACK_BUFFER_OVERRUN
        # на Windows при работе с Flask + SocketIO + Qt WebEngine
        self.setStackSize(8 * 1024 * 1024)  # 8 МБ вместо стандартных 1 МБ

    def run(self):
        try:
            from server.map_server import run
            self.started_ok.emit(self.port)
            run(self.port)
        except Exception as e:
            self.error.emit(str(e))