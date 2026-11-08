import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RecognitionTests(unittest.TestCase):
    def test_openai_image_request_and_latex(self):
        import base64
        import io
        import main
        from PIL import Image
        environment = {'FORMULA_API_BASE': 'https://example.invalid/v1/',
                       'FORMULA_API_KEY': 'unit-test-placeholder',
                       'FORMULA_MODEL': 'vision-test'}
        with patch.dict('os.environ', environment), patch.object(main.requests, 'post') as post:
            response = post.return_value
            response.__enter__.return_value = response
            response.status_code = 200
            response.json.return_value = {
                'choices': [{'finish_reason': 'stop', 'message': {'content': r'\\frac{1}{2}'}}]}
            self.assertEqual(main.recognize(Image.new('RGB', (9, 7))), r'\\frac{1}{2}')
            args, kwargs = post.call_args
            self.assertEqual(args[0], 'https://example.invalid/v1/chat/completions')
            self.assertEqual(kwargs['timeout'], 30)
            self.assertFalse(kwargs['allow_redirects'])
            self.assertEqual(kwargs['headers']['Authorization'], 'Bearer unit-test-placeholder')
            payload = kwargs['json']
            self.assertFalse(payload['stream'])
            self.assertEqual(payload['model'], 'vision-test')
            self.assertEqual(payload['messages'][0]['content'],
                '你是公式识别器。只输出图片中公式的 LaTeX 源码本身：不要解释、不要 markdown 代码块包裹、不要加 $$ 或 $ 定界符。识别不出就返回空字符串。')
            url = payload['messages'][1]['content'][0]['image_url']['url']
            self.assertTrue(url.startswith('data:image/png;base64,'))
            decoded = Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1])))
            self.assertEqual(decoded.size, (9, 7))

    def test_empty_malformed_and_truncated_responses(self):
        import main
        from PIL import Image
        environment = {'FORMULA_API_BASE': 'https://example.invalid/v1',
                       'FORMULA_API_KEY': 'unit-test-placeholder', 'FORMULA_MODEL': 'vision-test'}
        cases = [{}, {'choices': []}, {'choices': [{'message': {'content': None}}]},
                 {'choices': [{'message': {'content': ''}}]},
                 {'choices': [{'message': {'content': '  '}}]},
                 {'choices': [{'finish_reason': 'length', 'message': {'content': 'x='}}]}]
        with patch.dict('os.environ', environment), patch.object(main.requests, 'post') as post:
            response = post.return_value
            response.__enter__.return_value = response
            response.status_code = 200
            for data in cases:
                with self.subTest(data=data):
                    response.json.return_value = data
                    with self.assertRaises(ValueError):
                        main.recognize(Image.new('RGB', (3, 3)))

    def test_outer_wrappers_removed(self):
        import main
        from PIL import Image
        environment = {'FORMULA_API_BASE': 'https://example.invalid/v1',
                       'FORMULA_API_KEY': 'unit-test-placeholder', 'FORMULA_MODEL': 'vision-test'}
        with patch.dict('os.environ', environment), patch.object(main.requests, 'post') as post:
            response = post.return_value
            response.__enter__.return_value = response
            response.status_code = 200
            for text in ['$x=1$', '$$x=1$$', r'\[x=1\]', r'\(x=1\)', '```latex\nx=1\n```']:
                with self.subTest(text=text):
                    response.json.return_value = {'choices': [{'message': {'content': text}}]}
                    self.assertEqual(main.recognize(Image.new('RGB', (3, 3))), 'x=1')

    def test_invalid_json_has_correct_reason(self):
        import main
        from PIL import Image
        environment = {'FORMULA_API_BASE': 'https://example.invalid/v1',
                       'FORMULA_API_KEY': 'unit-test-placeholder', 'FORMULA_MODEL': 'vision-test'}
        with patch.dict('os.environ', environment), patch.object(main.requests, 'post') as post:
            response = post.return_value
            response.__enter__.return_value = response
            response.status_code = 200
            response.json.side_effect = main.requests.exceptions.JSONDecodeError('not JSON', '<html>', 0)
            with self.assertRaisesRegex(ValueError, 'JSON'):
                main.recognize(Image.new('RGB', (3, 3)))

    def test_sigint_exits_mainloop(self):
        import main
        import signal
        app = main.App()
        app.root.after(100, lambda: signal.raise_signal(signal.SIGINT))
        app.run()
        self.assertTrue(app.closed)

    def test_windows_app_available(self):
        import main
        self.assertTrue(hasattr(main, 'App'), '尚未实现托盘 / Tk 主循环')

    def test_missing_image_does_not_call_api(self):
        self.assertIsNotNone(importlib.util.find_spec('main'), '尚未实现 main.py')
        import main
        from PIL import Image
        with patch.object(main.ImageGrab, 'grabclipboard', return_value=None), \
             patch.object(main, 'recognize') as api:
            with self.assertRaisesRegex(ValueError, '先用 Win\\+Shift\\+S 截图'):
                main.read_formula()
            api.assert_not_called()
        # 文件列表不是截图；不能偷偷读磁盘中的图片。
        with patch.object(main.ImageGrab, 'grabclipboard', return_value=['formula.png']):
            with self.assertRaisesRegex(ValueError, '先用 Win'):
                main.read_formula()


if __name__ == '__main__':
    unittest.main(verbosity=2)
