"""Windows 公式截图转 LaTeX。截图请使用 Win+Shift+S。"""
import base64
import io
import os
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageGrab

PROMPT = "你是公式识别器。只输出图片中公式的 LaTeX 源码本身：不要解释、不要 markdown 代码块包裹、不要加 $$ 或 $ 定界符。识别不出就返回空字符串。"


def recognize(image):
    names = ('FORMULA_API_BASE', 'FORMULA_API_KEY', 'FORMULA_MODEL')
    values = [os.environ.get(name, '').strip() for name in names]
    missing = [name for name, value in zip(names, values) if not value]
    if missing:
        raise ValueError('缺少环境变量：' + '、'.join(missing))
    base, key, model = values
    parts = urlsplit(base)
    if (parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment):
        raise ValueError('FORMULA_API_BASE 必须是无账号、查询参数和片段的 http(s) API 根地址')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    payload = {
        'model': model, 'stream': False,
        'messages': [
            {'role': 'system', 'content': PROMPT},
            {'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {
                    'url': 'data:image/png;base64,' + encoded}}
            ]}
        ]
    }
    try:
        with requests.post(base.rstrip('/') + '/chat/completions',
                           headers={'Authorization': 'Bearer ' + key},
                           json=payload, timeout=30, allow_redirects=False) as response:
            if 300 <= response.status_code < 400:
                raise ValueError('API 返回重定向；请检查 FORMULA_API_BASE')
            response.raise_for_status()
            data = response.json()
    except requests.Timeout:
        raise ValueError('API 请求超时（30 秒），剪贴板未改动') from None
    except requests.HTTPError as exc:
        status = exc.response.status_code
        reason = {401: 'API key 无效', 403: '没有调用权限',
                  404: 'API 地址或模型不存在', 429: '额度不足或调用过于频繁'}.get(status, '服务端拒绝请求')
        raise ValueError(f'API HTTP {status}：{reason}，剪贴板未改动') from None
    except requests.exceptions.JSONDecodeError:
        raise ValueError('API 未返回有效 JSON；请检查 API 地址，剪贴板未改动') from None
    except requests.RequestException:
        raise ValueError('API 网络连接失败，请检查网络、代理和 API 地址；剪贴板未改动') from None
    except (ValueError, TypeError):
        raise ValueError('API 未返回有效 JSON（或发生重定向）；请检查 API 地址，剪贴板未改动') from None
    try:
        choice = data['choices'][0]
        if choice.get('finish_reason') not in (None, 'stop'):
            raise ValueError('模型输出被截断或拦截，剪贴板未改动')
        text = choice['message']['content']
        if not isinstance(text, str):
            raise TypeError
    except (KeyError, IndexError, TypeError):
        raise ValueError('API 响应缺少有效 choices[0].message.content，剪贴板未改动') from None
    # 防御性移除模型偶尔附带的外层包装，不改公式本身。
    text = text.strip()
    if text.startswith('```') and text.endswith('```') and '\n' in text:
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    for left, right in [('$$', '$$'), ('$', '$'), (r'\[', r'\]'), (r'\(', r'\)')]:
        if text.startswith(left) and text.endswith(right):
            text = text[len(left):-len(right)].strip()
            break
    if not text or text in ('""', "''"):
        raise ValueError('模型未识别出公式（返回空内容），剪贴板未改动')
    return text


def read_formula():
    image = ImageGrab.grabclipboard()
    if not isinstance(image, Image.Image):
        raise ValueError("先用 Win+Shift+S 截图")
    return recognize(image)


# 不引入托盘库；仅用标准库调用 Windows API（指针类型兼容 32/64 位）。
import ctypes as ct
from ctypes import wintypes as wt
import queue
import signal
import threading
import tkinter as tk
import keyboard

if os.name == 'nt':
    user32 = ct.WinDLL('user32', use_last_error=True)
    shell32 = ct.WinDLL('shell32', use_last_error=True)
    kernel32 = ct.WinDLL('kernel32', use_last_error=True)
    WNDPROC = ct.WINFUNCTYPE(ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASS(ct.Structure):
        _fields_ = [('style', wt.UINT), ('proc', WNDPROC), ('cls_extra', ct.c_int),
                    ('wnd_extra', ct.c_int), ('instance', wt.HINSTANCE),
                    ('icon', wt.HICON), ('cursor', wt.HANDLE), ('background', wt.HBRUSH),
                    ('menu', wt.LPCWSTR), ('name', wt.LPCWSTR)]

    class NOTIFYICONDATA(ct.Structure):
        _fields_ = [('size', wt.DWORD), ('hwnd', wt.HWND), ('id', wt.UINT),
                    ('flags', wt.UINT), ('callback', wt.UINT), ('icon', wt.HICON),
                    ('tip', wt.WCHAR * 128), ('state', wt.DWORD), ('state_mask', wt.DWORD),
                    ('info', wt.WCHAR * 256), ('version', wt.UINT),
                    ('info_title', wt.WCHAR * 64), ('info_flags', wt.DWORD),
                    ('guid', ct.c_byte * 16), ('balloon_icon', wt.HICON)]

    # 每个 API 声明返回值与参数，避免 64 位句柄被默认 c_int 截断。
    for dll, name, restype, argtypes in [
        (kernel32, 'GetModuleHandleW', wt.HMODULE, [wt.LPCWSTR]),
        (kernel32, 'GlobalAlloc', wt.HGLOBAL, [wt.UINT, ct.c_size_t]),
        (kernel32, 'GlobalLock', ct.c_void_p, [wt.HGLOBAL]),
        (kernel32, 'GlobalUnlock', wt.BOOL, [wt.HGLOBAL]),
        (kernel32, 'GlobalFree', wt.HGLOBAL, [wt.HGLOBAL]),
        (kernel32, 'GlobalSize', ct.c_size_t, [wt.HGLOBAL]),
        (user32, 'RegisterClassW', wt.ATOM, [ct.POINTER(WNDCLASS)]),
        (user32, 'UnregisterClassW', wt.BOOL, [wt.LPCWSTR, wt.HINSTANCE]),
        (user32, 'CreateWindowExW', wt.HWND, [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR,
            wt.DWORD, ct.c_int, ct.c_int, ct.c_int, ct.c_int,
            wt.HWND, wt.HMENU, wt.HINSTANCE, ct.c_void_p]),
        (user32, 'DefWindowProcW', ct.c_ssize_t, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]),
        (user32, 'DestroyWindow', wt.BOOL, [wt.HWND]),
        (user32, 'LoadIconW', wt.HICON, [wt.HINSTANCE, ct.c_void_p]),
        (user32, 'RegisterWindowMessageW', wt.UINT, [wt.LPCWSTR]),
        (user32, 'CreatePopupMenu', wt.HMENU, []),
        (user32, 'AppendMenuW', wt.BOOL, [wt.HMENU, wt.UINT, ct.c_size_t, wt.LPCWSTR]),
        (user32, 'TrackPopupMenu', wt.BOOL, [wt.HMENU, wt.UINT, ct.c_int, ct.c_int,
            ct.c_int, wt.HWND, ct.c_void_p]),
        (user32, 'DestroyMenu', wt.BOOL, [wt.HMENU]),
        (user32, 'GetCursorPos', wt.BOOL, [ct.POINTER(wt.POINT)]),
        (user32, 'SetForegroundWindow', wt.BOOL, [wt.HWND]),
        (user32, 'PostMessageW', wt.BOOL, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]),
        (user32, 'GetClipboardSequenceNumber', wt.DWORD, []),
        (user32, 'OpenClipboard', wt.BOOL, [wt.HWND]),
        (user32, 'EmptyClipboard', wt.BOOL, []),
        (user32, 'GetClipboardData', wt.HANDLE, [wt.UINT]),
        (user32, 'EnumClipboardFormats', wt.UINT, [wt.UINT]),
        (user32, 'SetClipboardData', wt.HANDLE, [wt.UINT, wt.HANDLE]),
        (user32, 'CloseClipboard', wt.BOOL, []),
        (shell32, 'Shell_NotifyIconW', wt.BOOL, [wt.DWORD, ct.POINTER(NOTIFYICONDATA)]),
    ]:
        function = getattr(dll, name)
        function.restype, function.argtypes = restype, argtypes


def write_clipboard(text, hwnd, expected_sequence=None):
    """先分配内存，确认 API 成功后才打开、改写系统剪贴板。"""
    raw = (text + '\0').encode('utf-16-le')
    handle = kernel32.GlobalAlloc(0x0002, len(raw))
    if not handle:
        raise OSError('无法分配剪贴板内存')
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise OSError('无法锁定剪贴板内存')
        ct.memmove(pointer, raw, len(raw))
        kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(hwnd):
            raise OSError('剪贴板被其他程序占用，请稍后重试')
        backups = []
        try:
            # 锁内复查，其他程序不能在检查与写入之间更新剪贴板。
            if expected_sequence is not None and expected_sequence != user32.GetClipboardSequenceNumber():
                raise OSError('识别期间剪贴板已变化，本次未写入，请重新截图')
            # 在清空前复制原截图 DIB / DIBV5 和纯文本到独立内存；不落盘。
            for format_id in (8, 17, 13):
                original = user32.GetClipboardData(format_id)
                if not original:
                    continue
                size = kernel32.GlobalSize(original)
                source = kernel32.GlobalLock(original)
                if not size or not source:
                    raise OSError('无法备份原剪贴板，本次未写入')
                backup = None
                try:
                    backup = kernel32.GlobalAlloc(2, size)
                    destination = kernel32.GlobalLock(backup) if backup else None
                    if not destination:
                        raise OSError('无法备份原剪贴板，本次未写入')
                    ct.memmove(destination, source, size)
                    kernel32.GlobalUnlock(backup)
                    backups.append((format_id, backup))
                    backup = None
                finally:
                    kernel32.GlobalUnlock(original)
                    if backup:
                        kernel32.GlobalFree(backup)
            if not backups and user32.EnumClipboardFormats(0):
                raise OSError('无法安全备份该剪贴板格式，本次未写入')
            if not user32.EmptyClipboard():
                raise OSError('Windows 无法打开剪贴板写入，原内容未改动')
            if not user32.SetClipboardData(13, handle):
                restored = False
                for index, (format_id, backup) in enumerate(backups):
                    if user32.SetClipboardData(format_id, backup):
                        backups[index] = (format_id, None)
                        restored = True
                if backups and not restored:
                    raise OSError('Windows 写入及回滚均失败，原剪贴板未能恢复，请重新截图')
                raise OSError('Windows 无法写入 LaTeX，原剪贴板内容已恢复')
            handle = None  # SetClipboardData 成功后由系统接管内存。
        finally:
            user32.CloseClipboard()
            for _, backup in backups:
                if backup:
                    kernel32.GlobalFree(backup)
    finally:
        if handle:
            kernel32.GlobalFree(handle)


class App:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('本工具仅支持 Windows')
        self.root = tk.Tk()
        self.root.withdraw()
        self.events = queue.Queue()
        self.busy = False
        self.closed = False
        self.popup = None
        self.hwnd = None
        self.hotkey = None
        self.icon_added = False
        self.class_name = 'FormulaLatexTray_' + str(os.getpid())
        self.instance = kernel32.GetModuleHandleW(None)
        self.proc = WNDPROC(self.window_proc)  # 必须保留引用，防止回调被回收。
        self.wc = WNDCLASS(proc=self.proc, instance=self.instance, name=self.class_name)
        try:
            if not user32.RegisterClassW(ct.byref(self.wc)):
                raise ct.WinError(ct.get_last_error())
            self.hwnd = user32.CreateWindowExW(0, self.class_name, 'FormulaLatexTray',
                0, 0, 0, 0, 0, None, None, self.instance, None)
            if not self.hwnd:
                raise ct.WinError(ct.get_last_error())
            self.restart_message = user32.RegisterWindowMessageW('TaskbarCreated')
            self.tray = NOTIFYICONDATA(size=ct.sizeof(NOTIFYICONDATA), hwnd=self.hwnd,
                id=1, flags=7, callback=0x8001, icon=user32.LoadIconW(None, 32512),
                tip='公式截图转 LaTeX · Ctrl+Alt+L')
            if not shell32.Shell_NotifyIconW(0, ct.byref(self.tray)):
                raise OSError('无法创建 Windows 托盘图标')
            self.icon_added = True
            self.hotkey = keyboard.add_hotkey('ctrl+alt+l',
                lambda: self.events.put(('trigger', None, None)))
            self.root.after(80, self.poll)
        except Exception:
            self.close()
            raise

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == 0x8001 and lparam in (0x0205, 0x007B):
            menu = user32.CreatePopupMenu()
            try:
                user32.AppendMenuW(menu, 0, 1, '退出')
                point = wt.POINT()
                user32.GetCursorPos(ct.byref(point))
                user32.SetForegroundWindow(hwnd)
                command = user32.TrackPopupMenu(menu, 0x0102, point.x, point.y, 0, hwnd, None)
                user32.PostMessageW(hwnd, 0, 0, 0)
                if command == 1:
                    self.events.put(('quit', None, None))
            finally:
                user32.DestroyMenu(menu)
            return 0
        if message == getattr(self, 'restart_message', -1):
            shell32.Shell_NotifyIconW(0, ct.byref(self.tray))
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def worker(self, sequence):
        try:
            text = read_formula()
            self.events.put(('result', text, sequence))
        except (ValueError, OSError) as exc:
            # 只展示我们自己生成的提示；绝不回显可能包含 key 的请求对象。
            self.events.put(('error', str(exc), None))
        except Exception:
            self.events.put(('error', '识别失败：图片编码或 API 响应异常，剪贴板未改动', None))

    def show_popup(self, title, text):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.destroy()
        window = self.popup = tk.Toplevel(self.root)
        window.title(title)
        window.geometry('600x230')
        window.attributes('-topmost', True)
        tk.Label(window, text=title, anchor='w', padx=12, pady=8).pack(fill='x')
        box = tk.Text(window, wrap='word', font=('Consolas', 12), padx=10, pady=8)
        box.insert('1.0', text)
        box.configure(state='disabled')
        box.pack(fill='both', expand=True, padx=12)
        tk.Button(window, text='确定', command=window.destroy).pack(pady=10)
        window.bind('<Escape>', lambda event: window.destroy())
        window.lift()

    def poll(self):
        try:
            while True:
                kind, text, sequence = self.events.get_nowait()
                if kind == 'quit':
                    self.close()
                    return
                if kind == 'trigger' and not self.busy:
                    self.busy = True
                    threading.Thread(target=self.worker,
                        args=(user32.GetClipboardSequenceNumber(),), daemon=True).start()
                elif kind in ('result', 'error'):
                    self.busy = False
                    if kind == 'result':
                        if sequence != user32.GetClipboardSequenceNumber():
                            self.show_popup('公式截图转 LaTeX：提示',
                                '识别期间剪贴板已变化，为避免覆盖新内容，本次未写入。请重新截图识别。')
                            continue
                        try:
                            write_clipboard(text, self.hwnd, expected_sequence=sequence)
                        except OSError as exc:
                            self.show_popup('公式截图转 LaTeX：复制失败', str(exc))
                            continue
                        self.show_popup('公式截图转 LaTeX：已复制', text)
                    else:
                        self.show_popup('公式截图转 LaTeX：提示', text)
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(80, self.poll)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.hotkey is not None:
            keyboard.remove_hotkey(self.hotkey)
        if self.icon_added:
            shell32.Shell_NotifyIconW(2, ct.byref(self.tray))
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
        user32.UnregisterClassW(self.class_name, self.instance)
        self.root.destroy()

    def run(self):
        old_handler = signal.signal(signal.SIGINT,
            lambda signum, frame: self.events.put(('quit', None, None)))
        try:
            self.root.mainloop()
        finally:
            signal.signal(signal.SIGINT, old_handler)
            self.close()


if __name__ == '__main__':
    try:
        App().run()
    except Exception:
        # 启动错误也使用 GUI 告知，兼容 pythonw 无控制台启动。
        from tkinter import messagebox
        messagebox.showerror('公式截图转 LaTeX：启动失败',
            '启动失败，请检查依赖、Windows 桌面会话及热键权限。可在终端运行以排查。')
        raise
