"""真实 Windows 桌面集成测试；API 使用本机 HTTP 桩，不测试模型识别能力。"""
import base64
import ctypes as ct
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from PIL import Image, ImageGrab


class Handler(BaseHTTPRequestHandler):
    status = 200
    output = ''
    delay = 0
    requests = []

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append((self.path, data))
        status, output, delay = self.status, self.output, self.delay
        time.sleep(delay)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        try:
            self.wfile.write(json.dumps({'choices': [{'finish_reason': 'stop',
                'message': {'content': output}}]}).encode())
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass


class WindowsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 常见截图 / 文本只在进程内备份，绝不落盘。
        cls.original_image = ImageGrab.grabclipboard()
        cls.original_text = None
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.environment = patch.dict(os.environ, {
            'FORMULA_API_BASE': f'http://127.0.0.1:{cls.server.server_port}/v1',
            'FORMULA_API_KEY': 'local-test-placeholder', 'FORMULA_MODEL': 'mock-vision'})
        cls.environment.start()
        cls.app = main.App()
        cls.app.root.update()
        try:
            cls.original_text = cls.app.root.clipboard_get()
        except main.tk.TclError:
            pass
        print('STARTUP: native tray + Tk event loop + global hotkey OK', flush=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.environment.stop()
        try:
            if cls.app.closed:
                cls.app = main.App()
            if isinstance(cls.original_image, Image.Image):
                stream = io.BytesIO()
                cls.original_image.convert('RGB').save(stream, 'BMP')
                raw = stream.getvalue()[14:]
                handle = main.kernel32.GlobalAlloc(2, len(raw))
                pointer = main.kernel32.GlobalLock(handle)
                ct.memmove(pointer, raw, len(raw))
                main.kernel32.GlobalUnlock(handle)
                if main.user32.OpenClipboard(cls.app.hwnd):
                    main.user32.EmptyClipboard()
                    main.user32.SetClipboardData(8, handle)
                    main.user32.CloseClipboard()
                print('CLEANUP: original image restored in memory', flush=True)
            elif cls.original_text is not None:
                main.write_clipboard(cls.original_text, cls.app.hwnd)
                print('CLEANUP: original text restored in memory', flush=True)
        finally:
            cls.app.close()
        print('CLEANUP: tray removed', flush=True)

    def setUp(self):
        Handler.status, Handler.output, Handler.delay = 200, '', 0
        Handler.requests.clear()
        self.app.busy = False
        if self.app.popup is not None and self.app.popup.winfo_exists():
            self.app.popup.destroy()
        self.app.popup = None

    def wait(self, predicate, seconds=7):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.root.update()
            if predicate():
                return
            time.sleep(0.02)
        self.fail('等待真实桌面事件超时')

    def trigger(self, seconds=7):
        # 独立进程发出真实按键，经过 Windows 键盘钩子，不直接调用回调。
        subprocess.run([sys.executable, '-c',
            "import keyboard,time; keyboard.press('ctrl');time.sleep(.06);keyboard.press('alt');time.sleep(.06);keyboard.press('l');time.sleep(.1);keyboard.release('l');keyboard.release('alt');keyboard.release('ctrl')"], check=True)
        self.wait(lambda: self.app.popup is not None and self.app.popup.winfo_exists(), seconds)
        self.assertTrue(self.app.popup.winfo_viewable())
        box = next(w for w in self.app.popup.winfo_children() if isinstance(w, main.tk.Text))
        return box.get('1.0', 'end-1c')

    def put_image(self):
        image = Image.new('RGB', (160, 60), 'white')
        stream = io.BytesIO()
        image.save(stream, 'BMP')
        raw = stream.getvalue()[14:]
        handle = main.kernel32.GlobalAlloc(2, len(raw))
        pointer = main.kernel32.GlobalLock(handle)
        ct.memmove(pointer, raw, len(raw))
        main.kernel32.GlobalUnlock(handle)
        self.assertTrue(main.user32.OpenClipboard(self.app.hwnd))
        try:
            self.assertTrue(main.user32.EmptyClipboard())
            self.assertTrue(main.user32.SetClipboardData(8, handle))
        finally:
            main.user32.CloseClipboard()
        actual = ImageGrab.grabclipboard()
        self.assertIsInstance(actual, Image.Image)
        return actual.tobytes(), main.user32.GetClipboardSequenceNumber()

    def unchanged(self, before):
        self.assertEqual(main.user32.GetClipboardSequenceNumber(), before[1])
        self.assertEqual(ImageGrab.grabclipboard().tobytes(), before[0])

    def test_01_real_hotkey_no_image(self):
        main.write_clipboard('clipboard sentinel', self.app.hwnd)
        sequence = main.user32.GetClipboardSequenceNumber()
        self.assertEqual(self.trigger(), '先用 Win+Shift+S 截图')
        self.assertEqual(main.user32.GetClipboardSequenceNumber(), sequence)
        self.assertEqual(self.app.root.clipboard_get(), 'clipboard sentinel')
        self.assertEqual(Handler.requests, [])

    def test_02_five_latex_results_via_real_http(self):
        # 这五项只是模拟服务返回的样例，不代表真实模型识别过五张图。
        formulas = [r'\int_0^1 x^2\,dx=\frac{1}{3}',
                    r'\lim_{x\to0}\frac{\sin x}{x}=1',
                    r'\begin{pmatrix}a&b\\c&d\end{pmatrix}',
                    r'\frac{\sqrt{x+1}}{x^2+1}', r'\alpha+\beta=\gamma']
        for formula in formulas:
            with self.subTest(formula=formula):
                self.setUp()
                self.put_image()
                Handler.output = formula
                self.assertEqual(self.trigger(), formula)
                self.assertEqual(self.app.root.clipboard_get(), formula)
                path, body = Handler.requests[-1]
                self.assertEqual(path, '/v1/chat/completions')
                self.assertEqual(body['messages'][0]['content'], main.PROMPT)
                encoded = body['messages'][1]['content'][0]['image_url']['url'].split(',', 1)[1]
                self.assertEqual(Image.open(io.BytesIO(base64.b64decode(encoded))).size, (160, 60))

    def test_03_empty_keeps_image(self):
        before = self.put_image()
        Handler.output = '   '
        self.assertIn('返回空内容', self.trigger())
        self.unchanged(before)

    def test_04_http_errors_keep_image(self):
        for status in [401, 404, 429, 500]:
            with self.subTest(status=status):
                self.setUp()
                before = self.put_image()
                Handler.status = status
                self.assertIn(f'HTTP {status}', self.trigger())
                self.unchanged(before)

    def test_05_missing_configuration_keeps_image(self):
        before = self.put_image()
        with patch.dict(os.environ, {'FORMULA_API_KEY': ''}):
            self.assertIn('FORMULA_API_KEY', self.trigger())
        self.unchanged(before)
        self.assertEqual(Handler.requests, [])

    def test_06_actual_thirty_second_timeout_keeps_image(self):
        before = self.put_image()
        Handler.delay = 32
        start = time.monotonic()
        self.assertIn('超时（30 秒）', self.trigger(seconds=36))
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 30)
        self.assertLess(elapsed, 35)
        self.unchanged(before)
        print(f'ACTUAL HTTP TIMEOUT: {elapsed:.2f}s, clipboard unchanged', flush=True)

    def test_07_does_not_overwrite_new_clipboard(self):
        self.put_image()
        Handler.delay, Handler.output = 0.6, 'x=1'
        subprocess.run([sys.executable, '-c',
            "import keyboard,time; keyboard.press('ctrl');time.sleep(.06);keyboard.press('alt');time.sleep(.06);keyboard.press('l');time.sleep(.1);keyboard.release('l');keyboard.release('alt');keyboard.release('ctrl')"], check=True)
        self.wait(lambda: bool(Handler.requests))
        main.write_clipboard('new user content', self.app.hwnd)
        self.wait(lambda: self.app.popup is not None and self.app.popup.winfo_exists())
        self.assertEqual(self.app.root.clipboard_get(), 'new user content')

    def test_075_write_failure_restores_image(self):
        before = self.put_image()
        real_set = main.user32.SetClipboardData
        def fail_text_only(format_id, handle):
            return 0 if format_id == 13 else real_set(format_id, handle)
        with patch.object(main.user32, 'SetClipboardData', side_effect=fail_text_only):
            with self.assertRaises(OSError):
                main.write_clipboard('x=1', self.app.hwnd)
        self.assertIsInstance(ImageGrab.grabclipboard(), Image.Image)
        self.assertEqual(ImageGrab.grabclipboard().tobytes(), before[0])

    def test_076_sequence_checked_under_lock(self):
        before = self.put_image()
        with self.assertRaisesRegex(OSError, '变化'):
            main.write_clipboard('x=1', self.app.hwnd, expected_sequence=before[1] - 1)
        self.unchanged(before)

    def test_08_native_tray_exit_menu(self):
        # 把托盘右键通知交给真实 Windows 窗口，再用按键选择原生“退出”菜单。
        def select_exit():
            time.sleep(0.6)
            subprocess.run([sys.executable, '-c',
                "import keyboard; keyboard.press_and_release('down'); keyboard.press_and_release('enter')"], check=True)
        threading.Thread(target=select_exit, daemon=True).start()
        main.user32.PostMessageW(self.app.hwnd, 0x8001, 1, 0x0205)
        self.wait(lambda: self.app.closed)
        self.assertTrue(self.app.closed)
        print('TRAY: native right-click menu -> Exit -> root destroyed OK', flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
