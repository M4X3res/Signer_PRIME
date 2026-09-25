"""Regression checks without Qt/ML dependencies: execute production methods.

Run with: python -m unittest tests.test_audit_regressions -v
"""
import ast
from contextlib import nullcontext
import logging
import os
from pathlib import Path
import pickle
import queue
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def source_tree(path):
    return ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))


def load_methods(path, class_name, names, **namespace):
    cls = next(n for n in source_tree(path).body
               if isinstance(n, ast.ClassDef) and n.name == class_name)
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[
        ast.alias(name="annotations")], level=0)] + nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(ROOT / path), "exec"), namespace)
    return types.SimpleNamespace(**{name: namespace[name] for name in names})


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "checkpoint.pkl"
        self.config = types.SimpleNamespace(**{key: 0 for key in (
            "INDEX_OF_FRAME", "INDEX_OF_VIDEO", "INDEX_OF_All_FRAME", "INDEX_OF_GPS",
            "FRAME_STEP", "VIDEOS", "PATH_TO_VIDEO", "PATH_TO_GPX", "PATH_TO_GEOJSON")})
        self.config.PATH_TO_EXTRA_LAYERS = ''
        self.handler = types.SimpleNamespace(result_signs=["pending"], signs=["active"], turns=[])
        self.obj = types.SimpleNamespace(
            _last_checkpoint_time=0, CHECKPOINT_INTERVAL=60, CHECKPOINT_PATH=str(self.path),
            _detector_pool=None, _detector=types.SimpleNamespace(
                _sign_handler=self.handler, _frames_processed=1, _signs_found=2),
            _result_q=queue.Queue())
        self.obj._result_q.put("queued")
        self.methods = load_methods("processing/processing_controller.py", "ProcessingController",
                                    ["save_checkpoint"], config=self.config, logger=Mock())
        self.joblib = types.ModuleType("joblib")
        def dump(data, path, **kwargs):
            Path(path).write_bytes(pickle.dumps(data))
        self.joblib.dump = dump

    def test_checkpoint_includes_queue_without_consuming_it(self):
        with patch.dict(sys.modules, {"joblib": self.joblib}):
            self.methods.save_checkpoint(self.obj)
        data = pickle.loads(self.path.read_bytes())
        self.assertEqual(data["signs"]["result_signs"], ["queued", "pending"])
        self.assertEqual(data["signs"]["active_signs"], ["active"])
        self.assertEqual(self.obj._result_q.get_nowait(), "queued")
        self.assertEqual(self.handler.result_signs, ["pending"])

    def test_failed_replacement_preserves_previous_checkpoint(self):
        self.path.write_bytes(b"previous checkpoint")
        with patch.dict(sys.modules, {"joblib": self.joblib}), patch(
                "os.replace", side_effect=OSError("disk error")):
            self.methods.save_checkpoint(self.obj)
        self.assertEqual(self.path.read_bytes(), b"previous checkpoint")


class ResultQueueTests(unittest.TestCase):
    def test_all_results_survive_long_run_and_bounded_queue(self):
        controller_methods = load_methods(
            "processing/processing_controller.py", "ProcessingController",
            ["_create_queues", "get_result_signs"], queue=queue, logging=logging)
        detector_methods = load_methods("processing/detector_thread.py", "DetectorThread",
                                        ["_flush_result_signs"], queue=queue)
        cls = next(n for n in source_tree("processing/processing_controller.py").body
                   if isinstance(n, ast.ClassDef) and n.name == "ProcessingController")
        queue_limit = next(ast.literal_eval(n.value) for n in cls.body
                           if isinstance(n, ast.Assign) and
                           any(isinstance(t, ast.Name) and t.id == "RESULT_QUEUE_SIZE" for t in n.targets))
        for limit in (queue_limit, 2):
            with self.subTest(limit=limit):
                controller = types.SimpleNamespace(FRAME_QUEUE_SIZE=2, RESULT_QUEUE_SIZE=limit,
                                                   _detector_pool=None)
                controller_methods._create_queues(controller)
                handler = types.SimpleNamespace(result_signs=list(range(6001)))
                detector = types.SimpleNamespace(_result_q=controller._result_q, _sign_handler=handler)
                controller._detector = detector
                detector_methods._flush_result_signs(detector)
                detector_methods._flush_result_signs(detector)
                self.assertEqual(controller_methods.get_result_signs(controller), list(range(6001)))
                self.assertEqual(controller_methods.get_result_signs(controller), [])


class VideoReaderTests(unittest.TestCase):
    def read_frames(self, start_video=0, start_frame=0, rates=None):
        cfg = types.SimpleNamespace(INDEX_OF_VIDEO=start_video, INDEX_OF_FRAME=start_frame,
                                    VIDEOS=["first.mp4", "second.mp4"], PATH_TO_VIDEO="recordings",
                                    FRAME_STEP=5, VIDEO_FPS=2)
        counts = {"first.mp4": 12, "second.mp4": 7}
        class Capture:
            def __init__(self, path):
                self.count = counts[os.path.basename(path)]
                self.fps = (rates or {}).get(os.path.basename(path), 2)
                self.pos = 0
            def isOpened(self): return True
            def release(self): pass
            def getBackendName(self): return "fake"
            def set(self, *args): pass
            def get(self, prop):
                return {"COUNT": self.count, "FPS": self.fps, "POS": self.pos}.get(prop, 100)
            def grab(self):
                if self.pos >= self.count: return False
                self.pos += 1
                return True
            def retrieve(self): return True, object()
            def read(self): return self.grab(), object()
        cv = types.SimpleNamespace(VideoCapture=Capture, CAP_PROP_FRAME_COUNT="COUNT",
            CAP_PROP_FPS="FPS", CAP_PROP_POS_FRAMES="POS", CAP_PROP_FRAME_WIDTH="WIDTH",
            CAP_PROP_FRAME_HEIGHT="HEIGHT", CAP_PROP_BUFFERSIZE="BUFFER", CAP_PROP_FOURCC="FOURCC")
        log = Mock(handlers=[])
        log.addHandler.side_effect = log.handlers.append
        with tempfile.TemporaryDirectory() as temp:
            methods = load_methods("processing/video_reader.py", "VideoReaderThread", [
                "_read_all_videos", "_count_total_frames"], config=cfg, cv2=cv,
                RawFrame=types.SimpleNamespace, queue=queue, os=os, logging=logging,
                logger=Mock(), profiler=types.SimpleNamespace(measure=lambda *a: nullcontext()),
                __file__=str(Path(temp) / "processing" / "video_reader.py"))
            reader = types.SimpleNamespace(_stop=False, _paused=False, _next_cap=None,
                _queue=queue.Queue(), started_reading=Mock(), video_switched=Mock(),
                error=Mock(), progress=Mock(), FRAME_COUNT_SAFETY_MARGIN=1.0,
                _open_video_with_fallback=Capture, _prefetch_next_video=Mock())
            reader._count_total_frames = lambda: methods._count_total_frames(reader)
            # Simulate detector updating the global resume indices while reading.
            def change_indices(*args):
                cfg.INDEX_OF_VIDEO = 1
                cfg.INDEX_OF_FRAME = 999
            reader.video_switched.emit.side_effect = change_indices
            try:
                with patch("logging.getLogger", return_value=log):
                    methods._read_all_videos(reader)
            finally:
                for handler in log.handlers: handler.close()
        return list(reader._queue.queue)

    def test_unequal_lengths_include_skipped_tail_frames(self):
        frames = self.read_frames()
        self.assertEqual([f.abs_frame_number for f in frames], [5, 10, 17])
        self.assertEqual([f.gps_index for f in frames], [2, 5, 8])

    def test_mixed_fps_and_resume_preserve_elapsed_time(self):
        rates = {'first.mp4': 2, 'second.mp4': 1}
        frames = self.read_frames(rates=rates)
        self.assertEqual([f.timestamp_s for f in frames], [2.5, 5.0, 11.0])
        resumed = self.read_frames(start_video=1, rates=rates)
        self.assertEqual(resumed[0].timestamp_s, frames[-1].timestamp_s)

    def test_resume_second_video_uses_real_previous_length(self):
        frames = self.read_frames(start_video=1, start_frame=2)
        self.assertEqual([(f.video_index, f.frame_number, f.abs_frame_number) for f in frames],
                         [(1, 7, 19)])


class VideoIndexTests(unittest.TestCase):
    def test_selected_folder_and_cache_invalidation(self):
        cfg = types.SimpleNamespace(PATH_TO_VIDEO="folder_a", VIDEOS=["first.mp4", "second.mp4"],
                                    VIDEO_FRAME_COUNTS=[], FRAMES_PER_VIDEO=63600)
        opened = []
        def capture(path):
            opened.append(path)
            count = 100 if "folder_a" in path else 200
            return types.SimpleNamespace(isOpened=lambda: True, get=lambda prop: count,
                                         release=lambda: None)
        ns = {"config": cfg, "cv2": types.SimpleNamespace(VideoCapture=capture,
              CAP_PROP_FRAME_COUNT=1), "os": os, "_cached_video_paths": ()}
        nodes = [n for n in source_tree("core/video_index.py").body if isinstance(n, ast.FunctionDef)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "core/video_index.py", "exec"), ns)
        self.assertEqual(ns["resolve_video_and_frame"](150), (1, 50))
        self.assertEqual(opened[0], os.path.normcase(os.path.abspath("folder_a/first.mp4")))
        ns["resolve_video_and_frame"](150)
        self.assertEqual(len(opened), 2)
        cfg.PATH_TO_VIDEO = "folder_b"
        self.assertEqual(ns["resolve_video_and_frame"](150), (0, 150))
        self.assertEqual(len(opened), 4)


class MapNotificationTests(unittest.TestCase):
    def test_count_and_ready_events_are_delivered(self):
        functions = [n for n in source_tree("server/map_server.py").body
                     if isinstance(n, ast.FunctionDef) and n.name == "emit_processing_finished"]
        self.assertEqual(len(functions), 1)
        ns = {"socketio": Mock(), "logger": Mock(), "_processing_active": True, "_data_ready": False}
        exec(compile(ast.Module(body=functions, type_ignores=[]), "server/map_server.py", "exec"), ns)
        ns["emit_processing_finished"](42)
        ns["socketio"].emit.assert_any_call("processing_finished", {
            "count": 42, "ready": True, "finished": True})
        ns["socketio"].emit.assert_any_call("data_ready", {"ready": True})
        self.assertFalse(ns["_processing_active"])
        self.assertTrue(ns["_data_ready"])
        ns["emit_processing_finished"]()


class SaveLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.methods = load_methods("ui/main_window.py", "MainWindow", [
            "_on_finish", "_on_save_error", "_on_save_finished", "closeEvent"],
            theme_manager=types.SimpleNamespace(tokens={
                "success": "green", "error": "red", "warning": "yellow"}))
        self.window = types.SimpleNamespace(
            _finish_called=False, _controller=Mock(), _save_results=Mock(),
            page_processing=Mock(), page_dashboard=Mock(), status_bar=Mock(),
            results_saved=Mock(), _reload_editor_after_save=Mock())

    def test_starting_save_keeps_checkpoint_and_does_not_announce_success(self):
        self.methods._on_finish(self.window)
        self.methods._on_finish(self.window)
        self.window._controller.save_checkpoint.assert_called_once_with(force=True)
        self.window._controller.delete_checkpoint.assert_not_called()
        self.window._save_results.assert_called_once_with()
        self.window.page_processing.set_progress.assert_not_called()
        self.assertTrue(self.window._saving_results)

    def test_failed_save_keeps_checkpoint(self):
        self.methods._on_save_error(self.window, "disk full")
        self.window._controller.delete_checkpoint.assert_not_called()
        self.assertFalse(self.window._saving_results)

    def test_successful_save_removes_checkpoint(self):
        server = types.ModuleType("server.map_server")
        server.emit_processing_finished = Mock()
        qt = types.ModuleType("PyQt6.QtCore")
        qt.QTimer = Mock()
        access = types.ModuleType("licensing.access")
        access.get_manager = lambda: None
        with patch.dict(sys.modules, {"server.map_server": server, "PyQt6.QtCore": qt, "licensing.access": access}):
            self.methods._on_save_finished(self.window, 12)
        self.window._controller.delete_checkpoint.assert_called_once_with()
        server.emit_processing_finished.assert_called_once_with(12)
        self.assertFalse(self.window._saving_results)

    def test_window_cannot_close_during_save(self):
        self.window._saving_results = True
        event = Mock()
        self.methods.closeEvent(self.window, event)
        event.ignore.assert_called_once_with()
        event.accept.assert_not_called()


if __name__ == "__main__":
    unittest.main()
