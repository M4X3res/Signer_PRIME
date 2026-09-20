"""CPU bookkeeping regression tests; no weights or ML runtime required."""
import logging
import types
import unittest
from unittest.mock import Mock

from tests.test_audit_regressions import load_methods


def output(label, confidence):
    scalar = types.SimpleNamespace(cpu=lambda: types.SimpleNamespace(numpy=lambda: confidence))
    return types.SimpleNamespace(names={0: label}, probs=types.SimpleNamespace(
        top1conf=scalar, data=types.SimpleNamespace(tolist=lambda: [confidence])))


class Cache(dict):
    def put(self, key, value):
        self[key] = value


def scenario(fail_main=False, fail_sub=False, cached=False, method=None):
    hashes, calls = [], []
    def image_hash(crop):
        hashes.append(crop)
        return str(crop)

    def model(crops, **kwargs):
        calls.append(('main', list(crops), kwargs))
        if fail_main and len(crops) > 1:
            raise RuntimeError('static batch')
        return [output('danger', .9) for _ in crops]

    def submodel(crops, **kwargs):
        calls.append(('sub', list(crops), kwargs))
        if fail_sub and len(crops) > 1:
            raise RuntimeError('static batch')
        return [output('warning', .4 if crop == 2 else .95) for crop in crops]

    namespace = dict(model_dict={'treugolnik': model}, sub_models={'danger': submodel},
                     compute_image_hash=image_hash, logger=logging.getLogger(__name__),
                     np=types.SimpleNamespace(argmax=lambda values: 0))
    if method is None:
        method = load_methods('core/detector.py', 'Detector', ['_run_cnn_batch'],
                              **namespace)._run_cnn_batch
    else:
        method = method(namespace)
    cache = Cache()
    if cached:
        cache['sub_danger:1'] = ('cached_warning', .8)
    obj = types.SimpleNamespace(_cnn_cache=cache, CLASSIFY_IMGSZ=32, CONF_CNN=.5,
                                _counter=1, _maybe_save_error_frame=Mock())
    result = method(obj, [1, 2, 3], 'treugolnik')
    return result, dict(cache), calls, obj._maybe_save_error_frame.call_args_list, hashes


class BatchOverheadTests(unittest.TestCase):
    def test_batch_fallback_cache_and_threshold(self):
        for fail_main, fail_sub in ((False, False), (True, False), (False, True)):
            for cached in (False, True):
                with self.subTest(fail_main=fail_main, fail_sub=fail_sub, cached=cached):
                    result, cache, calls, errors, hashes = scenario(fail_main, fail_sub, cached)
                    self.assertEqual(result, ['cached_warning' if cached else 'warning', -1, 'warning'])
                    self.assertEqual(cache['treugolnik:2'], ('warning', .4))
                    self.assertEqual(cache['treugolnik:3'], ('warning', .95))
                    self.assertEqual(len(errors), 1)
                    self.assertEqual(sorted(hashes), [1, 2, 3])
                    self.assertTrue(all(call[2] == {'imgsz': 32, 'verbose': False} for call in calls))


if __name__ == '__main__':
    unittest.main()
