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
        self.setDaemon(True)

    def run(self):
        try:
            from server.map_server import run
            self.started_ok.emit(self.port)
            run(self.port)
        except Exception as e:
            self.error.emit(str(e))