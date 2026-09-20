import json
import queue
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from app.json_store import atomic_write_json
from core.video_timeline import frame_seconds
from tests.test_audit_regressions import load_methods


class ExportReaderSafetyTests(unittest.TestCase):
    def test_failed_export_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            path.write_text('{"old": true}')
            method = load_methods('core/final_handler.py', 'FinalHandler', ['save_result'],
                config=types.SimpleNamespace(PATH_TO_GEOJSON=str(path)), logger=Mock(),
                FeatureCollection=lambda features: {'features': features},
                atomic_write_json=atomic_write_json).save_result
            for stage in ('_process_straight_signs', '_process_turn_signs', '_deduplicate'):
                handler = types.SimpleNamespace(_process_straight_signs=Mock(return_value=[]),
                    _process_turn_signs=Mock(return_value=[]), _deduplicate=Mock(return_value=[]))
                getattr(handler, stage).side_effect = ValueError('conversion failed')
                with self.assertRaises(ValueError):
                    method(handler, [object()], [])
                self.assertEqual(json.loads(path.read_text()), {'old': True})
            handler._deduplicate.side_effect = None
            with patch('app.json_store.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    method(handler, [], [])
            self.assertEqual(json.loads(path.read_text()), {'old': True})

    def test_consumer_failure_releases_reader_with_full_queue(self):
        marker = object()
        methods = load_methods('processing/video_reader.py', 'VideoReaderThread',
            ['run', 'stop', 'consumer_finished'], logger=Mock(), queue=queue, _STOP=marker)
        fifo = queue.Queue(1)
        fifo.put('frame')
        reader = types.SimpleNamespace(_queue=fifo, _consumer_stopped=threading.Event(),
            _read_all_videos=Mock(), error=Mock(), finished_reading=Mock())
        reader.stop = lambda: methods.stop(reader)
        thread = threading.Thread(target=methods.run, args=(reader,))
        thread.start()
        try:
            methods.consumer_finished(reader)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            reader.finished_reading.emit.assert_called_once()
        finally:
            reader._consumer_stopped.set()
            thread.join(2)

    def test_normal_finish_preserves_queued_frames_before_sentinel(self):
        marker = object()
        methods = load_methods('processing/video_reader.py', 'VideoReaderThread',
            ['run', 'stop'], logger=Mock(), queue=queue, _STOP=marker)
        fifo = queue.Queue()
        reader = types.SimpleNamespace(_queue=fifo, _consumer_stopped=threading.Event(),
            _read_all_videos=lambda: fifo.put('frame'), error=Mock(), finished_reading=Mock())
        methods.stop(reader)
        methods.run(reader)
        self.assertEqual(fifo.get_nowait(), 'frame')
        self.assertIs(fifo.get_nowait(), marker)

    def test_timeline_uses_each_recording_fps(self):
        self.assertEqual(frame_seconds(600, [(600, 60), (300, 30)]), 10)
        self.assertEqual(frame_seconds(750, [(600, 60), (300, 30)]), 15)
