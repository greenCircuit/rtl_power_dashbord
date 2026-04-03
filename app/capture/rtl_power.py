import subprocess
import threading
from datetime import datetime

from app.config import DATA_DIR


class RTLPowerCapture:
    def __init__(self):
        self._process = None
        self._thread = None
        self._current_session = None
        self._status = "idle"
        self._error = None

    @property
    def status(self):
        return self._status

    @property
    def current_session(self):
        return self._current_session

    @property
    def error(self):
        return self._error

    def start(self, freq_start: str, freq_end: str, freq_step: str,
              interval: int = 10, duration: str = None) -> str:
        if self._process and self._process.poll() is None:
            raise RuntimeError("Capture already running")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = DATA_DIR / f"{session_id}.csv"

        cmd = [
            "rtl_power",
            "-f", f"{freq_start}:{freq_end}:{freq_step}",
            "-i", str(interval),
        ]
        if duration:
            cmd.extend(["-e", duration])
        cmd.append(str(output_file))

        self._error = None
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            self._status = "error"
            self._error = "rtl_power not found — install it with: sudo apt install rtl-sdr"
            raise RuntimeError(self._error)
        self._current_session = session_id
        self._status = "running"

        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

        return session_id

    def stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._status = "stopped"

    def _monitor(self):
        _, stderr = self._process.communicate()
        if self._process.returncode == 0:
            self._status = "completed"
        else:
            self._status = "error"
            self._error = stderr.decode(errors="replace").strip()


# Module-level singleton shared by API routes and Dash callbacks
capture = RTLPowerCapture()
