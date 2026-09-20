"""Dependency-free checks for optimizations which preserve recognition inputs."""
from bisect import bisect_left
import math
import random
import types
import unittest
from unittest.mock import Mock

from tests.test_audit_regressions import load_methods


def gps_handler(offsets):
    methods = load_methods("core/gpx_handler.py", "GPXHandler", [
        "_interpolation_segments", "get_interpolated", "_interpolate_angle"],
        math=math, bisect_left=bisect_left, GPSPoint=types.SimpleNamespace)
    obj = types.SimpleNamespace(_points=[types.SimpleNamespace(
        time_offset_s=t, latitude=53 + i / 10000, longitude=27 + i / 10000,
        course=(359 + i * 13) % 360, speed=float(i % 70), elevation=float(i % 19))
        for i, t in enumerate(offsets)])
    obj._interpolation_segments = types.MethodType(methods._interpolation_segments, obj)
    obj.get_interpolated = types.MethodType(methods.get_interpolated, obj)
    obj._interpolate_angle = methods._interpolate_angle.__func__
    return obj


class GPSParityTests(unittest.TestCase):
    def assert_matches_linear_scan(self, offsets, queries):
        optimized = gps_handler(offsets)
        reference = gps_handler(offsets)
        # Original traversal and unchanged production interpolation arithmetic.
        reference._interpolation_segments = lambda t: range(len(reference._points) - 1)
        for t in queries:
            with self.subTest(t=t):
                self.assertEqual(optimized.get_interpolated(t * 60, 60),
                                 reference.get_interpolated(t * 60, 60))

    def test_long_track_exact_parity(self):
        rng = random.Random(47)
        offsets = [i * .75 for i in range(3000)]
        self.assert_matches_linear_scan(offsets,
            [-1, 0, .375, .75, 2249.25, 3000] + [rng.uniform(0, 2250) for _ in range(500)])

    def test_duplicates_and_unordered_timestamps(self):
        for offsets in ([0, 1, 1, 1, 2, 4], [0, 3, 1, 2, 4], [0, 1, float('nan'), 3, 4]):
            self.assert_matches_linear_scan(offsets, [0, .5, 1, 1.5, 2, 3, 3.5, 4])

    def test_empty_and_single_point(self):
        self.assert_matches_linear_scan([], [-1, 0, 1])
        self.assert_matches_linear_scan([0], [-1, 0, 1])

    def test_index_rebuilt_after_reload_and_append(self):
        handler = gps_handler([0, 1, 2])
        handler.get_interpolated(.5, 1)
        replacement = gps_handler([0, 10, 20])
        handler._points = replacement._points
        self.assertEqual(handler.get_interpolated(5, 1), replacement.get_interpolated(5, 1))
        handler._points.append(gps_handler([30])._points[0])
        self.assertEqual(list(handler._interpolation_segments(25)), [2])

    def test_sorted_track_checks_only_one_segment(self):
        handler = gps_handler(range(30000))
        self.assertEqual(list(handler._interpolation_segments(25000.5)), [25000])


class RecognitionWorkTests(unittest.TestCase):
    def test_empty_frame_does_not_calculate_coordinates(self):
        methods = load_methods("processing/detector_thread.py", "DetectorThread", ["_build_detected"])
        # No GPS/model dependencies are available: any access would fail.
        self.assertEqual(methods._build_detected(types.SimpleNamespace(), [], None), [])

    def test_subclassification_reuses_hash_and_preserves_model_inputs(self):
        def output(label):
            confidence = Mock()
            confidence.cpu.return_value.numpy.return_value = .95
            data = Mock()
            data.tolist.return_value = [.1, .95]
            return types.SimpleNamespace(probs=types.SimpleNamespace(top1conf=confidence, data=data),
                                         names={1: label})
        base_model = Mock(return_value=[output("danger")])
        sub_model = Mock(return_value=[output("1.1")])
        image_hash = Mock(return_value="same-hash")
        methods = load_methods("core/detector.py", "Detector", ["_run_cnn_model"],
            compute_image_hash=image_hash, model_dict={"treugolnik": base_model},
            sub_models={"danger": sub_model},
            np=types.SimpleNamespace(argmax=lambda values: max(range(len(values)), key=values.__getitem__)))
        cache = Mock()
        cache.get.return_value = None
        detector = types.SimpleNamespace(_cnn_cache=cache, CONF_CNN=.5, CLASSIFY_IMGSZ=32, _counter=1)
        crop = object()
        self.assertEqual(methods._run_cnn_model(detector, crop, "treugolnik"), "1.1")
        image_hash.assert_called_once_with(crop)
        base_model.assert_called_once_with(crop, imgsz=32, verbose=False)
        sub_model.assert_called_once_with(crop, imgsz=32, verbose=False)
        cache.put.assert_any_call("sub_danger:same-hash", ("1.1", .95))
        cache.put.assert_any_call("treugolnik:same-hash", ("1.1", .95))


if __name__ == "__main__":
    unittest.main()
