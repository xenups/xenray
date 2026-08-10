"""Process utilities."""

import ctypes
import os
import subprocess
from typing import List, Optional

import psutil

from src.core.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES
from src.core.logger import logger
from src.utils.platform_utils import PlatformUtils


def truncate_log_file_inplace(
    log_file: str,
    max_bytes: int = LOG_MAX_BYTES,
    keep_bytes: int = 512 * 1024,
) -> bool:
    """Truncate a log file in-place, retaining the last ``keep_bytes`` of lines.

    Safe for Windows even when an active subprocess holds a write lock on the file.
    """
    if not os.path.exists(log_file):
        return False
    try:
        size = os.path.getsize(log_file)
        if size < max_bytes:
            return False

        logger.info(f"[ProcessUtils] In-place truncating oversized log ({size} bytes >= {max_bytes}): {log_file}")
        with open(log_file, "r+", encoding="utf-8", errors="ignore") as f:
            f.seek(0, os.SEEK_END)
            curr_size = f.tell()
            if curr_size < max_bytes:
                return False

            read_pos = max(0, curr_size - keep_bytes)
            f.seek(read_pos)
            if read_pos > 0:
                f.readline()  # Skip incomplete partial line

            tail_content = f.read()
            f.seek(0)
            f.write("[... Log truncated at 5 MB ceiling ...]\n" + tail_content)
            f.truncate()
            f.flush()
        return True
    except Exception as e:
        logger.warning(f"[ProcessUtils] In-place log truncation failed for {log_file}: {e}")
        return False


def cleanup_tmp_log_dir(max_bytes: int = LOG_MAX_BYTES) -> None:
    """Scan TMPDIR and remove all legacy log backups and truncate any oversized active logs."""
    from src.core.constants import TMPDIR

    if not os.path.exists(TMPDIR):
        return

    try:
        for file_name in os.listdir(TMPDIR):
            file_path = os.path.join(TMPDIR, file_name)
            if not os.path.isfile(file_path):
                continue
            try:
                # 1. Unconditionally purge old rotated backup files (.1, .2, .3, .old, .bak)
                if file_name.endswith((".1", ".2", ".3", ".old", ".bak")) or ".log." in file_name:
                    try:
                        os.remove(file_path)
                        logger.info(f"[ProcessUtils] Deleted old rotated log backup: {file_name}")
                    except OSError:
                        pass
                    continue

                # 2. Truncate any active log file exceeding max_bytes (5 MB)
                size = os.path.getsize(file_path)
                if size >= max_bytes:
                    truncate_log_file_inplace(file_path, max_bytes=max_bytes, keep_bytes=64 * 1024)
            except OSError:
                pass
    except Exception as e:
        logger.debug(f"[ProcessUtils] Error during temp log directory cleanup: {e}")


def purge_all_logs_on_connect() -> None:
    """Clear/truncate all *.log files and purge backup files in TMPDIR on new connection.

    Ensures every new connection starts with a fresh, clean log file.
    """
    from src.core.constants import TMPDIR

    if not os.path.exists(TMPDIR):
        return

    logger.info("[ProcessUtils] Clearing all log files on new connection attempt...")
    try:
        for file_name in os.listdir(TMPDIR):
            file_path = os.path.join(TMPDIR, file_name)
            if not os.path.isfile(file_path):
                continue
            try:
                # 1. Unconditionally remove rotated backup files (.1, .2, .3, .old, .bak)
                if file_name.endswith((".1", ".2", ".3", ".old", ".bak")) or ".log." in file_name:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                    continue

                # 2. Clear/truncate all *.log files
                if file_name.endswith(".log"):
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write("[... Log cleared on new connection start ...]\n")
                            f.flush()
                    except OSError:
                        # Fallback if locked by open handle
                        truncate_log_file_inplace(file_path, max_bytes=0, keep_bytes=0)
            except OSError:
                pass
    except Exception as e:
        logger.debug(f"[ProcessUtils] Error clearing log files on connect: {e}")


def rotate_oversized_log_file(
    log_file: str,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    """Rotate a log file if it exceeds ``max_bytes``.

    If file renaming fails (e.g. Windows file lock by running subprocess),
    falls back to safe in-place tail truncation so the log file never exceeds 5 MB.
    """
    if not os.path.exists(log_file):
        return
    try:
        size = os.path.getsize(log_file)
    except OSError:
        return
    if size < max_bytes:
        return

    logger.info(f"[ProcessUtils] Rotating oversized log ({size} bytes >= {max_bytes}): {log_file}")

    # Drop oldest backup.
    oldest = f"{log_file}.{backup_count}"
    if os.path.exists(oldest):
        try:
            os.remove(oldest)
        except OSError:
            pass

    # Shift backups down: .N-1 -> .N, ..., .1 -> .2.
    for i in range(backup_count - 1, 0, -1):
        src = f"{log_file}.{i}"
        dst = f"{log_file}.{i + 1}"
        if os.path.exists(src):
            try:
                # If backup file itself is oversized, purge it instead of shifting
                if os.path.exists(src) and os.path.getsize(src) >= max_bytes:
                    os.remove(src)
                else:
                    os.replace(src, dst)
            except OSError:
                pass

    # Try moving current file to .1 and starting a fresh file
    try:
        os.replace(log_file, f"{log_file}.1")
        with open(log_file, "w", encoding="utf-8"):
            pass  # Truncate/create fresh file; handle closed by context manager
    except OSError:
        # Windows file lock by running subprocess — fallback to in-place tail truncation!
        truncate_log_file_inplace(log_file, max_bytes=max_bytes)


class ProcessUtils:
    """Utility class for process management."""

    @staticmethod
    def is_running(pid: int) -> bool:
        """
        Check if a process is running.

        Args:
            pid: Process ID

        Returns:
            True if running, False otherwise
        """
        return psutil.pid_exists(pid)

    @staticmethod
    def is_admin() -> bool:
        """
        Check if the current process has administrator privileges.

        Returns:
            True if admin, False otherwise
        """
        try:
            if os.name == "nt":
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.geteuid() == 0
        except (OSError, AttributeError) as e:
            logger.debug(f"Error checking admin status: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking admin status: {e}")
            return False

    @staticmethod
    def kill_process(pid: int, force: bool = False) -> bool:
        """
        Kill a process.

        Args:
            pid: Process ID
            force: If True, use kill(), otherwise terminate()

        Returns:
            True if successful, False otherwise
        """
        if not ProcessUtils.is_running(pid):
            return True

        try:
            process = psutil.Process(pid)
            if force:
                process.kill()  # SIGKILL equivalent
            else:
                process.terminate()  # SIGTERM equivalent

            # Wait for process to exit (non-blocking check)
            try:
                process.wait(timeout=1)
            except psutil.TimeoutExpired:
                # Process didn't exit in time, but that's okay
                pass

            return True
        except psutil.NoSuchProcess:
            return True  # Already dead
        except psutil.AccessDenied:
            # Can't kill due to permissions - log but don't fail
            logger.warning(f"Access denied when trying to kill process {pid} - it may require admin rights")
            return False
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return False

    @staticmethod
    def run_command(
        cmd: List[str],
        stdout_file: Optional[str] = None,
        stderr_file: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Optional[subprocess.Popen]:
        """
        Run a command and return the process.

        Args:
            cmd: Command and arguments
            stdout_file: File to redirect stdout to
            stderr_file: File to redirect stderr to
            timeout: Timeout in seconds (not used for Popen, kept for compatibility)

        Returns:
            Popen object or None if failed
        """
        if not cmd or not isinstance(cmd, list):
            logger.error("Invalid command: must be a non-empty list")
            return None

        stdout_handle = None
        stderr_handle = None
        try:
            if stdout_file:
                # Enforce the 5 MB ceiling before appending subprocess output.
                rotate_oversized_log_file(stdout_file)
                stdout_handle = open(stdout_file, "a", encoding="utf-8")
                stdout = stdout_handle
            else:
                stdout = subprocess.PIPE

            if stderr_file:
                # Enforce the 5 MB ceiling before appending subprocess output.
                rotate_oversized_log_file(stderr_file)
                stderr_handle = open(stderr_file, "a", encoding="utf-8")
                stderr = stderr_handle
            else:
                stderr = subprocess.PIPE

            proc = subprocess.Popen(
                cmd,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            return proc
        except (OSError, IOError) as e:
            logger.error(f"Failed to open file or run command {' '.join(cmd)}: {e}")
            # Close handles if opened
            if stdout_handle:
                try:
                    stdout_handle.close()
                except Exception:
                    pass
            if stderr_handle:
                try:
                    stderr_handle.close()
                except Exception:
                    pass
            return None
        except (subprocess.SubprocessError, ValueError) as e:
            logger.error(f"Failed to run command {' '.join(cmd)}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error running command {' '.join(cmd)}: {e}")
            return None

    @staticmethod
    def run_command_sync(cmd: List[str], timeout: Optional[int] = None) -> Optional[tuple]:
        """
        Run a command synchronously and return output.

        Args:
            cmd: Command and arguments
            timeout: Timeout in seconds

        Returns:
            Tuple of (stdout, stderr) or None if failed
        """
        if not cmd or not isinstance(cmd, list):
            logger.error("Invalid command: must be a non-empty list")
            return None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return stdout, stderr
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            proc.kill()
            proc.communicate()  # Clean up
            return None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Failed to run command {' '.join(cmd)}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error running command {' '.join(cmd)}: {e}")
            return None

    @staticmethod
    def kill_process_by_name(name: str) -> bool:
        """
        Kill all processes with the given name.

        Args:
            name: Process name (e.g. "xray.exe")

        Returns:
            True if at least one matching process was killed, False otherwise
        """
        try:
            killed_any = False
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"] and proc.info["name"].lower() == name.lower():
                        logger.info(f"Killing process {proc.info['name']} (PID: {proc.info['pid']})")
                        proc.kill()
                        killed_any = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return killed_any
        except Exception as e:
            logger.error(f"Failed to kill process by name '{name}': {e}")
            return False

    @staticmethod
    def kill_process_tree(pid: Optional[int] = None) -> None:
        """
        Kill a process and all its children.

        Args:
            pid: Process ID to kill, or None for current process
        """
        try:
            if pid is None:
                pid = os.getpid()

            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            # Kill children first
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass  # Already dead
                except psutil.AccessDenied:
                    logger.warning(f"Access denied killing child process {child.pid}")
                except Exception as e:
                    logger.debug(f"Error killing child {child.pid}: {e}")

            # Kill parent
            try:
                parent.kill()
            except psutil.NoSuchProcess:
                pass  # Already dead
            except psutil.AccessDenied:
                logger.warning(f"Access denied killing process {pid}")
        except psutil.NoSuchProcess:
            pass  # Process already dead
        except (psutil.AccessDenied, OSError) as e:
            logger.warning(f"Error killing process tree {pid}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error killing process tree {pid}: {e}")

    @staticmethod
    def restart_as_admin():
        """Restart the application with admin privileges."""
        from src.utils.platform_utils import PlatformUtils

        platform = PlatformUtils.get_platform()

        if platform == "windows":
            ProcessUtils._restart_as_admin_windows()
        elif platform == "macos":
            ProcessUtils._restart_as_admin_macos()
        else:
            logger.warning("restart_as_admin is not supported on Linux")

    @staticmethod
    def _restart_as_admin_windows():
        """Restart as admin on Windows using ShellExecuteW."""
        import ctypes
        import os
        import sys
        import time

        import psutil

        try:
            # Get the executable path
            if getattr(sys, "frozen", False):
                executable = sys.executable
            else:
                executable = sys.executable

            logger.info(f"Restarting as admin: {executable}")

            # STEP 1: Kill all child processes FIRST (to release file locks)
            # This prevents PyInstaller temp directory lock issues
            current_pid = os.getpid()
            try:
                parent = psutil.Process(current_pid)
                children = parent.children(recursive=True)

                logger.info(f"Killing {len(children)} child processes before restart...")
                for child in children:
                    try:
                        child_name = child.name().lower()
                        logger.debug(f"Killing child process: {child.pid} ({child_name})")
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                    except Exception as e:
                        logger.debug(f"Failed to kill child {child.pid}: {e}")

                # Brief pause to let processes fully terminate
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"Error cleaning up child processes: {e}")

            # STEP 2: Launch new admin instance via ShellExecuteW
            result = ctypes.windll.shell32.ShellExecuteW(
                None,  # hwnd
                "runas",  # lpOperation - triggers UAC elevation
                executable,  # lpFile
                "",  # lpParameters
                None,  # lpDirectory
                1,  # nShowCmd - SW_SHOWNORMAL
            )

            # ShellExecuteW returns > 32 on success
            if result > 32:
                logger.info(f"ShellExecuteW succeeded (code {result}). Terminating current process...")
                # STEP 3: Terminate immediately using ExitProcess
                # This bypasses PyInstaller's cleanup which can fail on locked files
                ctypes.windll.kernel32.ExitProcess(0)
            else:
                logger.error(f"ShellExecuteW failed with code {result}")
                # Error code 5 = User cancelled UAC, don't exit
                if result == 5:
                    logger.info("User cancelled UAC prompt")

        except Exception as e:
            logger.error(f"Failed to restart as admin: {e}")
            import traceback

            traceback.print_exc()

    @staticmethod
    def _restart_as_admin_macos():
        """Restart as admin on macOS using osascript."""
        import subprocess
        import sys

        try:
            # Get the executable path
            if getattr(sys, "frozen", False):
                # Running as compiled app
                # If it's an .app bundle, we need to use the .app path
                executable = sys.executable

                # Check if we're inside a .app bundle
                if ".app/Contents/MacOS" in executable:
                    # Get the .app path
                    app_path = executable.split(".app/Contents/MacOS")[0] + ".app"
                    # Use 'open' command to launch the app
                    script = f'do shell script "open -a \\"{app_path}\\"" with administrator privileges'
                else:
                    # Direct executable
                    script = f'do shell script "\\"{executable}\\"" with administrator privileges'
            else:
                # Running as Python script
                executable = sys.executable
                script_path = sys.argv[0]
                script = f'do shell script "\\"{executable}\\" \\"{script_path}\\"" ' "with administrator privileges"

            logger.info("Requesting admin privileges via osascript...")

            # Execute AppleScript to request admin privileges
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("Successfully launched new instance with admin privileges")
                # Exit current instance
                sys.exit(0)
            else:
                logger.error(f"osascript failed: {result.stderr}")
                if "User canceled" in result.stderr or "(-128)" in result.stderr:
                    logger.info("User cancelled admin prompt")

        except Exception as e:
            logger.error(f"Failed to restart as admin on macOS: {e}")
            import traceback

            traceback.print_exc()
