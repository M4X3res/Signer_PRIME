import ast
import json
import math
import tempfile
import types
import unittest
from bisect import bisect_left
from pathlib import Path
from unittest.mock import Mock, patch

from app.json_store import atomic_write_json
from core.video_timeline import format_video_time
from tests.test_audit_regressions import load_methods


class GPXEditorTimeTests(unittest.TestCase):
    def test_speed_uses_timestamps_for_dense_and_irregular_tracks(self):
        names = ['get_speed_at_time', 'get_interpolated', '_interpolation_segments', '_interpolate_angle']
        methods = load_methods('core/gpx_handler.py', 'GPXHandler', names,
            math=math, bisect_left=bisect_left, GPSPoint=lambda **kwargs: types.SimpleNamespace(**kwargs))
        gpx = types.SimpleNamespace()
        for name in names:
            fn = getattr(methods, name)
            setattr(gpx, name, fn if name == '_interpolate_angle' else
                    lambda *args, fn=fn: fn(gpx, *args))
        def point(t, speed):
            return types.SimpleNamespace(time_offset_s=t, speed=speed,
                latitude=53., longitude=27., course=0., elevation=0.)
        gpx._points = [point(i / 10, 0 if i < 20 else 35) for i in range(101)]
        self.assertEqual(gpx.get_speed_at_time(10), 35)
        gpx._points = [point(0, 0), point(4, 20), point(10, 50)]
        self.assertEqual(gpx.get_speed_at_time(7), 35)
        gpx._points = []
        self.assertIsNone(gpx.get_speed_at_time(10))

    def test_repeated_save_and_return_to_original_type(self):
        tree = ast.parse(Path('ui/widgets/error_editor_page.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ErrorEditorPage')
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'save_geojson')
        node.decorator_list = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'signs.json'
            path.write_text(json.dumps({'features': [{'properties': {'id': '1', 'type': 'A'}}]}))
            ns = dict(config=types.SimpleNamespace(PATH_TO_GEOJSON=str(path)), geojson=json,
                atomic_write_json=atomic_write_json, CODES_SIGNS={}, TYPE_SIGNS_WITH_TEXT=[],
                QTimer=Mock(), theme_manager=types.SimpleNamespace(tokens={'success': 'green'}))
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'editor-save', 'exec'), ns)
            rec = types.SimpleNamespace(id='1', type='A', new_type='B', text='',
                                        new_text='', modified=True, deleted=False)
            view = types.SimpleNamespace(_model=Mock(), _btn_save=Mock(), _restyle_badges=Mock())
            view._model.all_records.return_value = [rec]
            with patch('app.json_store.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    ns['save_geojson'](view)
            self.assertTrue(rec.modified)
            self.assertEqual(rec.type, 'A')
            ns['save_geojson'](view)
            self.assertFalse(rec.modified)
            self.assertEqual(rec.type, 'B')
            rec.new_type = 'A'
            rec.modified = rec.new_type != rec.type
            ns['save_geojson'](view)
            self.assertEqual(json.loads(path.read_text())['features'][0]['properties']['type'], 'A')
            self.assertFalse(rec.modified)

    def test_local_video_time_uses_own_fps(self):
        timeline = [(6000, 60), (3000, 30), (2500, 25)]
        self.assertEqual(format_video_time(300, 1, timeline), '0:10')
        self.assertEqual(format_video_time(300, 0, timeline), '0:05')
        self.assertEqual(format_video_time(1500, 2, timeline), '1:00')
        self.assertEqual(format_video_time(300, 0, [], 30), '0:10')


if __name__ == '__main__':
    unittest.main()
