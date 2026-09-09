"""
Простая проверка BUG-1 fix без pytest.
"""
from configs.sign_models import _LazyModel

captured = {}

class FakeYOLOModel:
    predictor = None
    def predict(self, *a, **kw):
        captured['kwargs'] = kw
        return ["ok"]

lm = _LazyModel(lambda: "fake.pt", task="classify")
lm._model = FakeYOLOModel()
lm._backend = "onnx"

# Вызов через __call__
result = lm(object())

print("=" * 70)
print("BUG-1 TEST: __call__ должен форсировать device='cpu'")
print("=" * 70)
print(f"Captured kwargs: {captured}")
print(f"device in kwargs: {'device' in captured.get('kwargs', {})}")
print(f"device value: {captured.get('kwargs', {}).get('device')}")

if captured.get('kwargs', {}).get('device') == 'cpu':
    print("\n✅ ТЕСТ ПРОЙДЕН: __call__ корректно устанавливает device='cpu'")
else:
    print("\n❌ ТЕСТ ПРОВАЛЕН: __call__ не установил device='cpu'")
    exit(1)
