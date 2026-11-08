import ctypes as ct
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
user32 = ct.WinDLL('user32')
user32.FindWindowW.argtypes = [ct.c_wchar_p, ct.c_wchar_p]
user32.FindWindowW.restype = ct.c_void_p
process = subprocess.Popen([sys.executable, str(root / 'main.py')],
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
try:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if user32.FindWindowW('FormulaLatexTray_' + str(process.pid), 'FormulaLatexTray'):
            break
        if process.poll() is not None:
            raise RuntimeError(f'main.py early exit: {process.returncode}')
        time.sleep(.05)
    else:
        raise RuntimeError('entrypoint did not create tray window')
    print('ENTRYPOINT main.py: live PID and native tray window verified', flush=True)
    user32.PostMessageW.argtypes = [ct.c_void_p, ct.c_uint, ct.c_size_t, ct.c_ssize_t]
    hwnd = user32.FindWindowW('FormulaLatexTray_' + str(process.pid), 'FormulaLatexTray')
    user32.PostMessageW(hwnd, 0x8001, 1, 0x0205)
    time.sleep(.3)
    import keyboard
    keyboard.press_and_release('down')
    keyboard.press_and_release('enter')
    process.wait(timeout=5)
    if process.returncode != 0:
        raise RuntimeError(f'entrypoint exit code: {process.returncode}')
    print('ENTRYPOINT tray menu Exit: process returned 0; tray cleaned up', flush=True)
finally:
    if process.poll() is None:
        process.kill()
        process.wait()
probe = root / 'tests' / 'probe_hotkey.py'
probe.unlink(missing_ok=True)
print('Temporary debugging probe removed', flush=True)
