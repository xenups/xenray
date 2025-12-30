"""Process utilities."""
import ctypes
import os
import subprocess
from typing import List, Optional

import psutil

from src.core.logger import logger
from src.utils.platform_utils import Platform, PlatformUtils


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
    def has_vpn_privileges(binary_paths: List[str] = None) -> bool:
        """
        Check if the system has privileges to run VPN (Tun mode).
        On Linux, this checks for CAP_NET_ADMIN on binaries or root.
        On Windows/macOS, checks for Admin/Root.

        Args:
            binary_paths: List of absolute paths to binaries (sing-box, xray) to check capabilities for.

        Returns:
            True if privileged enough, False otherwise.
        """
        # If we are already admin/root, we are good
        if ProcessUtils.is_admin():
            return True

        # On Linux, check for capabilities
        if PlatformUtils.get_platform() == Platform.LINUX and binary_paths:
            try:
                import shutil
                getcap = shutil.which("getcap")
                
                # Check standard locations if which() failed
                if not getcap:
                     for p in ["/sbin/getcap", "/usr/sbin/getcap", "/usr/bin/getcap"]:
                         if os.path.exists(p):
                             getcap = p
                             break
                
                if not getcap or not os.path.exists(getcap):
                    logger.debug(f"[ProcessUtils] getcap not found")
                    return False

                logger.debug(f"[ProcessUtils] Checking capabilities using {getcap}")

                all_good = True
                files_checked = 0
                for binary in binary_paths:
                    if not os.path.exists(binary):
                        logger.debug(f"[ProcessUtils] Binary not found: {binary}")
                        continue
                    
                    files_checked += 1
                    # Check if binary has cap_net_admin
                    try:
                        result = subprocess.run(
                            [getcap, binary], 
                            capture_output=True, 
                            text=True, 
                            check=False
                        )
                        output = result.stdout.strip()
                        logger.debug(f"[ProcessUtils] getcap {binary} -> {output}")
                        
                        # Output format: /path/to/binary cap_net_admin,cap_net_bind_service=ep
                        if "cap_net_admin" not in output:
                            logger.warning(f"[ProcessUtils] Missing cap_net_admin on {binary}")
                            all_good = False
                            break
                    except Exception as e:
                        logger.error(f"[ProcessUtils] Failed to run getcap: {e}")
                        all_good = False
                        break
                
                # If we didn't check any files, that's technically a pass (no binaries to restrict) 
                # or a fail (paths wrong). Safer to pass if paths just don't exist yet but assume they will work?
                # Actually, if binary_paths were provided but none found, we should probably warn, but returning True 
                # maintains "innocent until proven guilty" logic.
                return all_good

            except Exception as e:
                logger.error(f"[ProcessUtils] Error checking capabilities: {e}")
                return False

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
                stdout_handle = open(stdout_file, "a", encoding="utf-8")
                stdout = stdout_handle
            else:
                stdout = subprocess.PIPE

            if stderr_file:
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

        if platform == Platform.WINDOWS:
            ProcessUtils._restart_as_admin_windows()
        elif platform == Platform.MACOS:
            ProcessUtils._restart_as_admin_macos()
        else:
            ProcessUtils._restart_as_admin_linux()

    @staticmethod
    def _restart_as_admin_linux():
        """Restart as admin on Linux using pkexec."""
        import sys
        
        try:
            # Reconstruct the command
            # If frozen (PyInstaller), sys.executable is the app binary
            # If source, sys.executable is python, sys.argv[0] is script
            
            cmd = []
            if getattr(sys, "frozen", False):
                cmd = [sys.executable]
            else:
                cmd = [sys.executable] + sys.argv
                
            logger.info(f"Restarting as admin (pkexec): {cmd}")
            
            # Use pkexec with env to preserve display
            # We use 'env' command as the executable for pkexec to run, 
            # so we can pass environment variables
            
            pkexec_cmd = ["pkexec", "env"]
            
            # Preserve critical X11/Wayland env vars
            for var in ["DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"]:
                val = os.environ.get(var)
                if val:
                    pkexec_cmd.append(f"{var}={val}")
            
            # Add the actual command
            pkexec_cmd.extend(cmd)
            
            subprocess.Popen(pkexec_cmd)
            
            # Exit current instance
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"Failed to restart as admin on Linux: {e}")
            # Fallback to logging instructions
            logger.warning(
                "Automatic restart failed. "
                "VPN mode requires root privileges on Linux. "
                "Please run with: sudo poetry run xenray"
            )

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

    @staticmethod
    def _restart_as_admin_linux():
        """Restart as admin on Linux using pkexec (PolicyKit).

        This method uses pkexec to request root privileges on Linux.
        pkexec is part of PolicyKit and provides a graphical authentication dialog.
        We use 'env' to pass DISPLAY and XAUTHORITY so the GUI can connect to X11.
        """
        import os
        import shutil
        import subprocess
        import sys

        try:
            # Check if pkexec is available
            pkexec_path = shutil.which("pkexec")
            if not pkexec_path:
                logger.error("pkexec not found. Please install PolicyKit (policykit-1 package)")
                return

            # Get display environment variables - required for GUI to work
            display = os.environ.get("DISPLAY", ":0")
            xauthority = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
            wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
            xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")

            # Get the executable path
            if getattr(sys, "frozen", False):
                # Running as compiled PyInstaller executable
                executable = sys.executable
                app_cmd = [executable]
            else:
                # Running as Python script
                python_exe = sys.executable
                script_path = sys.argv[0]

                # Use the full path to the script
                if not os.path.isabs(script_path):
                    script_path = os.path.abspath(script_path)

                app_cmd = [python_exe, script_path]

            # Build command with env to pass display variables
            # pkexec env DISPLAY=:0 XAUTHORITY=/path python script.py
            env_cmd = ["env", f"DISPLAY={display}", f"XAUTHORITY={xauthority}"]

            # Add Wayland variables if present
            if wayland_display:
                env_cmd.append(f"WAYLAND_DISPLAY={wayland_display}")
            if xdg_runtime_dir:
                env_cmd.append(f"XDG_RUNTIME_DIR={xdg_runtime_dir}")

            cmd = [pkexec_path] + env_cmd + app_cmd

            logger.info(f"Requesting admin privileges via pkexec: {' '.join(cmd)}")

            # Launch the new instance with pkexec
            # Use Popen to start the process and detach
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from current session
            )

            if process.pid:
                logger.info(f"Successfully launched new instance with admin privileges (PID: {process.pid})")
                # Exit current instance
                sys.exit(0)
            else:
                logger.error("Failed to launch admin instance")

        except Exception as e:
            logger.error(f"Failed to restart as admin on Linux: {e}")
            import traceback

            traceback.print_exc()
