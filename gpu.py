"""Make the app run on the dedicated GPU of a laptop with two graphics chips.

Windows picks the GPU per program. A Python app can't choose by itself, so we use the
same per-app switch as *Settings -> System -> Display -> Graphics* ("High performance"):
HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences, value = program path,
data = "GpuPreference=2;". It takes effect when the program starts, so the app restarts.
"""
from __future__ import annotations

import ctypes
import os
import sys
import winreg

PREF_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
ADAPTER_KEY = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
DEDICATED = ("nvidia", "geforce", "quadro", "radeon rx", "radeon pro", "arc a")


def process_exe() -> str:
    """Path of the program that really runs (a venv's pythonw.exe hands off to the base one)."""
    buf = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetModuleFileNameW(None, buf, len(buf))
    return buf.value


def interpreter_exes() -> list[str]:
    """python.exe and pythonw.exe of the interpreter that renders (both, so either launch works)."""
    exe = process_exe()
    folder = os.path.dirname(exe)
    out = [exe]
    for name in ("python.exe", "pythonw.exe"):
        p = os.path.join(folder, name)
        if os.path.exists(p) and p.lower() != exe.lower():
            out.append(p)
    return out


def adapters() -> list[str]:
    names = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ADAPTER_KEY) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(k, sub) as s:
                        names.append(winreg.QueryValueEx(s, "DriverDesc")[0])
                except OSError:
                    pass
    except OSError:
        pass
    return names


def is_dedicated(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in DEDICATED)


def dedicated_adapter() -> str | None:
    return next((a for a in adapters() if is_dedicated(a)), None)


def preference(exe: str) -> int | None:
    """0 = let Windows decide, 1 = power saving, 2 = high performance, None = not set."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PREF_KEY) as k:
            val = winreg.QueryValueEx(k, exe)[0]
    except OSError:
        return None
    for part in str(val).split(";"):
        if part.startswith("GpuPreference="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                return None
    return None


def set_high_performance(on: bool = True) -> list[str]:
    """Set (or remove) "High performance" for this interpreter. Returns the paths changed."""
    changed = []
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PREF_KEY) as k:
        for exe in interpreter_exes():
            if on:
                winreg.SetValueEx(k, exe, 0, winreg.REG_SZ, "GpuPreference=2;")
            else:
                try:
                    winreg.DeleteValue(k, exe)
                except OSError:
                    continue
            changed.append(exe)
    return changed


def status(renderer: str) -> tuple[str, str]:
    """(state, message) for the HUD. state: ok | can_switch | ignored | single."""
    dgpu = dedicated_adapter()
    if is_dedicated(renderer) or dgpu is None:
        return ("ok" if dgpu else "single"), ""
    if preference(process_exe()) == 2:
        return "ignored", (f"Set to {dgpu} in Windows, but the driver still uses {short(renderer)} "
                           "- see README (NVIDIA Control Panel)")
    return "can_switch", f"Running on {short(renderer)} - press G to switch to {short(dgpu)}"


def short(name: str) -> str:
    n = name.replace("(TM)", "").replace("(R)", "").replace("Laptop GPU", "").replace("  ", " ")
    for k in ("NVIDIA GeForce ", "NVIDIA "):
        n = n.replace(k, "NVIDIA ")
    return n.split("/")[0].strip()


def restart():
    """Start the app again with the same arguments, then the caller closes this instance."""
    import subprocess
    args = [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]
    subprocess.Popen(args, close_fds=True, cwd=os.path.dirname(os.path.abspath(sys.argv[0])))
