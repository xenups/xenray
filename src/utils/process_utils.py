"""Process utilities."""
import ctypes
import os
import signal
import subprocess
import sys
from typing import List, Optional

import psutil

from src.core.logger import logger


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
            if os.name == 'nt':
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.geteuid() == 0
        except Exception:
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
        timeout: Optional[int] = None
    ) -> Optional[subprocess.Popen]:
        """
        Run a command and return the process.
        
        Args:
            cmd: Command and arguments
            stdout_file: File to redirect stdout to
            stderr_file: File to redirect stderr to
            timeout: Timeout in seconds
            
        Returns:
            Popen object or None if failed
        """
        try:
            stdout = open(stdout_file, "a") if stdout_file else subprocess.PIPE
            stderr = open(stderr_file, "a") if stderr_file else subprocess.PIPE
            
            proc = subprocess.Popen(
                cmd,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return proc
        except Exception as e:
            logger.error(f"Failed to run command {' '.join(cmd)}: {e}")
            return None
    
    @staticmethod
    def run_command_sync(
        cmd: List[str],
        timeout: Optional[int] = None
    ) -> Optional[tuple]:
        """
        Run a command synchronously and return output.
        
        Args:
            cmd: Command and arguments
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (stdout, stderr) or None if failed
        """
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return stdout, stderr
        except Exception as e:
            logger.error(f"Failed to run command {' '.join(cmd)}: {e}")
            return None

    @staticmethod
    def kill_process_tree(pid=None):
        """Kill a process and all its children."""
        import psutil
        import signal
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
                    pass
            
            # Kill parent
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            pass

    @staticmethod
    def restart_as_admin():
        """Restart the application with admin privileges."""
        import sys
        import os
        import ctypes
        import psutil
        import time
        
        if os.name != 'nt':
            logger.warning("restart_as_admin is only supported on Windows")
            return

        try:
            # Get the executable path
            if getattr(sys, 'frozen', False):
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
                None,           # hwnd
                "runas",        # lpOperation - triggers UAC elevation
                executable,     # lpFile
                "",             # lpParameters
                None,           # lpDirectory
                1               # nShowCmd - SW_SHOWNORMAL
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


