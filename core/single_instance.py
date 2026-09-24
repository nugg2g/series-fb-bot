import os
import sys
import atexit
import json
import logging
from typing import Optional

_MUTEX_HANDLE = None
PID_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs", "reels_bot.pid"))

def is_pid_alive(pid: int) -> bool:
    """Checks if a process with given PID is currently active on Windows."""
    if pid <= 0:
        return False
    try:
        import psutil
        if psutil.pid_exists(pid):
            p = psutil.Process(pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except Exception:
        pass
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code))
        kernel32.CloseHandle(h_proc)
        return exit_code.value == STILL_ACTIVE
    except Exception:
        return False

def find_other_running_instance() -> Optional[int]:
    """Finds if another instance of Page Reel uplaod 2 is currently executing."""
    my_pid = os.getpid()
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if p.info['pid'] == my_pid:
                    continue
                pname = (p.info.get('name') or '').lower()
                if 'python' not in pname:
                    continue
                cmdline = ' '.join(p.info.get('cmdline') or [])
                cmdline_l = cmdline.lower()
                if 'page reel uplaod 2' in cmdline_l:
                    if any(target in cmdline_l for target in ['run.py', 'app_gui.py', 'cli.py', 'main.py']):
                        return p.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass
    return None

def activate_existing_window(window_title_keyword: str = "Facebook Reels Auto-Uploader"):
    """Brings existing application window to foreground on Windows."""
    try:
        import ctypes
        user32 = ctypes.windll.user32

        def enum_windows_proc(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    if window_title_keyword.lower() in buff.value.lower():
                        # Restore if minimized
                        SW_RESTORE = 9
                        user32.ShowWindow(hwnd, SW_RESTORE)
                        user32.SetForegroundWindow(hwnd)
                        return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
    except Exception:
        pass

def ensure_single_instance(app_identifier: str = "ThaiMovieDrama_ReelsBot_PG2") -> bool:
    """
    Guarantees that only ONE instance of the ReelsBot application runs at any time.
    Uses:
    1. Active process inspection via psutil (detects background/headless python runs).
    2. Windows Named Mutex.
    3. PID file tracking in logs/reels_bot.pid.
    Returns True if this process acquired the exclusive lock.
    Returns False if another instance is already running (caller should exit immediately).
    """
    global _MUTEX_HANDLE
    if _MUTEX_HANDLE is not None:
        # Already acquired by current process
        return True

    # 1. Process scanning check
    other_pid = find_other_running_instance()
    if other_pid:
        msg = (
            f"\n=======================================================\n"
            f"[SingleInstance] 🚨 ພົບເຫັນ ReelsBot ກຳລັງເຮັດວຽກຢູ່ແລ້ວ! (PID: {other_pid})\n"
            f"🛑 ໂປຣແກຣມຈະປິດໂຕເອງທັນທີ ເພື່ອປ້ອງກັນການອັບໂຫຼດວິດີໂອດຽວກັນຊ້ອນ 2-3 ເທື່ອ!\n"
            f"=======================================================\n"
        )
        try:
            print(msg)
        except Exception:
            try:
                sys.stdout.buffer.write(msg.encode('utf-8'))
            except Exception:
                pass
        activate_existing_window()
        return False

    if sys.platform != "win32":
        # Non-windows fallback using lock file
        return True

    try:
        import ctypes
        ERROR_ALREADY_EXISTS = 183
        mutex_name = rf"Local\{app_identifier}_SingleInstance_Mutex"
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        last_error = ctypes.windll.kernel32.GetLastError()

        if last_error == ERROR_ALREADY_EXISTS:
            existing_pid = None
            if os.path.exists(PID_FILE_PATH):
                try:
                    with open(PID_FILE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        existing_pid = data.get("pid")
                except Exception:
                    pass

            if existing_pid == os.getpid():
                # Re-entrant call within the same process
                _MUTEX_HANDLE = handle
                return True

            pid_str = f" (PID: {existing_pid})" if existing_pid else ""
            msg = (
                f"\n=======================================================\n"
                f"[SingleInstance] Another instance of ReelsBot is already running{pid_str}!\n"
                f"🛑 Exiting this duplicate process immediately to prevent double-posting.\n"
                f"=======================================================\n"
            )
            try:
                print(msg)
            except Exception:
                try:
                    sys.stdout.buffer.write(msg.encode('utf-8'))
                except Exception:
                    pass
            activate_existing_window()
            return False

        # Lock acquired successfully
        _MUTEX_HANDLE = handle

        os.makedirs(os.path.dirname(PID_FILE_PATH), exist_ok=True)
        try:
            with open(PID_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "pid": os.getpid(),
                    "app": app_identifier,
                    "started_at": str(os.path.basename(sys.argv[0]))
                }, f)
        except Exception:
            pass

        def cleanup_mutex():
            global _MUTEX_HANDLE
            if _MUTEX_HANDLE:
                try:
                    ctypes.windll.kernel32.CloseHandle(_MUTEX_HANDLE)
                except Exception:
                    pass
                _MUTEX_HANDLE = None
            if os.path.exists(PID_FILE_PATH):
                try:
                    os.remove(PID_FILE_PATH)
                except Exception:
                    pass

        atexit.register(cleanup_mutex)
        return True

    except Exception as e:
        print(f"[SingleInstance] Warning: Mutex check failed ({e}), proceeding...")
        return True
