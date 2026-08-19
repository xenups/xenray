"""Process utilities — pure process lifecycle and management."""

from __future__ import annotations

import os
import subprocess
from typing import List, Optional

import psutil

from src.core.logger import logger
from src.platform.factory import get_process_adapter
from src.utils.log_utils import (
    cleanup_tmp_log_dir,
    purge_all_logs_on_connect,
    rotate_oversized_log_file,
    truncate_log_file_inplace,
)

ctypes = None


class ProcessUtils:
    """Utility class for process lifecycle management."""

    @staticmethod
    def is_running(pid: int) -> bool:
        """Check if a process is running."""
        return psutil.pid_exists(pid)

    @staticmethod
    def is_admin() -> bool:
        """Check if the current process has administrator privileges."""
        if ctypes is not None and hasattr(ctypes, "windll"):
            try:
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            except Exception:
                return False
        return get_process_adapter().is_elevated()

    @staticmethod
    def kill_process(pid: int, force: bool = False) -> bool:
        """Kill a process by PID."""
        if not ProcessUtils.is_running(pid):
            return True

        try:
            process = psutil.Process(pid)
            if force:
                process.kill()
            else:
                process.terminate()

            try:
                process.wait(timeout=1)
            except psutil.TimeoutExpired:
                pass

            return True
        except psutil.NoSuchProcess:
            return True
        except psutil.AccessDenied:
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
        """Run a command asynchronously with platform-specific flags."""
        if not cmd or not isinstance(cmd, list):
            logger.error("Invalid command: must be a non-empty list")
            return None

        stdout_handle = None
        stderr_handle = None
        try:
            if stdout_file:
                rotate_oversized_log_file(stdout_file)
                stdout_handle = open(stdout_file, "a", encoding="utf-8")
                stdout = stdout_handle
            else:
                stdout = subprocess.PIPE

            if stderr_file:
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
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
            )
            return proc
        except (OSError, IOError) as e:
            logger.error(f"Failed to open file or run command {' '.join(cmd)}: {e}")
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
        """Run a command synchronously and return output."""
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
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return stdout, stderr
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            proc.kill()
            proc.communicate()
            return None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Failed to run command {' '.join(cmd)}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error running command {' '.join(cmd)}: {e}")
            return None

    @staticmethod
    def kill_process_by_name(name: str) -> bool:
        """[DEPRECATED / SAFETY BLOCKED] Use PID-targeted termination instead."""
        logger.warning(
            f"[ProcessUtils] kill_process_by_name('{name}') blocked for system safety. Use PID-targeted termination."
        )
        return False

    @staticmethod
    def kill_process_tree(pid: Optional[int] = None) -> None:
        """Kill a process and all its children."""
        try:
            if pid is None:
                pid = os.getpid()

            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
                except psutil.AccessDenied:
                    logger.warning(f"Access denied killing child process {child.pid}")
                except Exception as e:
                    logger.debug(f"Error killing child {child.pid}: {e}")

            try:
                parent.kill()
            except psutil.NoSuchProcess:
                pass
            except psutil.AccessDenied:
                logger.warning(f"Access denied killing process {pid}")
        except psutil.NoSuchProcess:
            pass
        except (psutil.AccessDenied, OSError) as e:
            logger.warning(f"Error killing process tree {pid}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error killing process tree {pid}: {e}")

    @staticmethod
    def restart_as_admin() -> None:
        """Restart the application with administrative privileges."""
        get_process_adapter().restart_as_admin()


__all__ = [
    "ProcessUtils",
    "truncate_log_file_inplace",
    "cleanup_tmp_log_dir",
    "purge_all_logs_on_connect",
    "rotate_oversized_log_file",
]
