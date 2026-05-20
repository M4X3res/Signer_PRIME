"""
debug_crash.py
"""
import sys

print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}")

print("\n[1] PyQt6...")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# ВАЖНО
QApplication.setAttribute(
    Qt.ApplicationAttribute.AA_ShareOpenGLContexts
)

# ВАЖНО
from PyQt6.QtWebEngineWidgets import QWebEngineView

print("    OK")

print("\n[2] OpenCV...")
import cv2
print(f"    OK {cv2.__version__}")

print("\n[3] numpy...")
import numpy as np
print(f"    OK {np.__version__}")

print("\n[4] configs.config...")
from configs import config
print("    OK")

print("\n[5] configs.sign_data...")
from configs import sign_data
print("    OK")

print("\n[6] core.frame...")
from core.frame import DetectedSign
print("    OK")

print("\n[7] core.sign...")
from core.sign import TrackedSign
print("    OK")

print("\n[8] ui.themes...")
from ui.themes.theme_manager import theme_manager
print("    OK")

print("\n[9] ultralytics (только импорт)...")
try:
    from ultralytics import YOLO
    print("    OK")
except Exception as e:
    print(f"    FAIL: {e}")

print("\n[10] configs.sign_models (lazy)...")
from configs import sign_models
print("    OK")

print("\n[11] easyocr (только импорт)...")
try:
    import easyocr
    print("    OK")
except Exception as e:
    print(f"    FAIL: {e}")

print("\n[12] QApplication...")
app = QApplication(sys.argv)
print("    OK")

print("\n[13] processing.processing_controller...")
try:
    from processing.processing_controller import ProcessingController
    print("    OK")
except Exception as e:
    print(f"    FAIL: {e}")

print("\n[14] ui.main_window...")
try:
    from ui.main_window import MainWindow
    print("    OK")
except Exception as e:
    import traceback
    traceback.print_exc()

print("\n[15] MainWindow()...")
try:
    from ui.main_window import MainWindow

    w = MainWindow()
    w.show()

    print("    OK")

    sys.exit(app.exec())

except Exception as e:
    import traceback
    traceback.print_exc()

print("\nDone")