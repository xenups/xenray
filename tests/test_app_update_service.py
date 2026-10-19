"""Unit tests for AppUpdateService and xenray_updater.ps1 script."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if sys.platform == "win32":
    import msvcrt

from src.services.installer.app_update_service import _EMBEDDED_UPDATER_SCRIPT, AppUpdateService


def test_get_embedded_updater_script():
    """Verify that get_embedded_updater_script returns robust powershell content."""
    script = AppUpdateService.get_embedded_updater_script()
    assert isinstance(script, str)
    assert len(script) > 500
    assert "param(" in script
    assert "ZipPath" in script
    assert "AppDir" in script
    assert "ExePath" in script
    assert "System.Windows.Forms" in script
    assert "xenray_staging_" in script
    assert "xenray_backup_" in script
    assert "Expand-Archive" in script
    assert "Copy-Item" in script
    assert "Invoke-XenrayDeploymentFailure" in script


def test_embedded_script_matches_disk_script():
    """Ensure embedded script in AppUpdateService strictly matches scripts/xenray_updater.ps1."""
    project_root = Path(__file__).resolve().parents[1]
    disk_script_path = project_root / "scripts" / "xenray_updater.ps1"
    assert disk_script_path.exists(), f"Updater script missing on disk: {disk_script_path}"

    disk_content = disk_script_path.read_text(encoding="utf-8")
    disk_norm = disk_content.replace("\r\n", "\n").strip()
    emb_norm = _EMBEDDED_UPDATER_SCRIPT.replace("\r\n", "\n").strip()

    assert emb_norm == disk_norm, (
        "Divergence detected between _EMBEDDED_UPDATER_SCRIPT in app_update_service.py "
        "and scripts/xenray_updater.ps1. Keep both scripts identical!"
    )


def test_updater_route_cleanup_safety():
    """Verify that xenray_updater.ps1 inspects adapter ownership before route removal."""
    script = AppUpdateService.get_embedded_updater_script()

    # Must NOT contain blind, unconditional route deletion
    assert "route delete 0.0.0.0 10.0.0.2 2>$null" not in script
    assert "route delete 0.0.0.0 10.0.0.2\n" not in script

    # Must verify TUN adapter identity (SINGTUN / xenray-tun / sing-tun / wintun)
    assert "SINGTUN" in script
    assert "xenray-tun" in script
    assert "sing-tun" in script
    assert "Get-NetRoute" in script
    assert "isTunAdapter" in script
    assert "isTunGateway" in script


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_route_decision_logic_synthetic():
    """Verify route-classification/deletion decision logic using synthetic route and adapter data.

    Required test cases:
    1. Known XenRay TUN adapter with an eligible route (SINGTUN, xenray-tun).
    2. Physical adapter with gateway 10.0.0.2 (Intel, Realtek).
    3. Unknown or inaccessible adapter (missing or empty alias and description).
    4. TUN-like description with conflicting or ambiguous identity (e.g. OpenVPN, WireGuard).
    5. Non-default route (e.g. subnet 192.168.1.0/24 or 10.0.0.0/8).
    """
    script = AppUpdateService.get_embedded_updater_script()
    start_idx = script.find("function Test-IsXenrayTunRouteEligible")
    assert start_idx != -1, "Test-IsXenrayTunRouteEligible function missing from updater script"

    brace_start = script.find("{", start_idx)
    depth = 0
    end_idx = brace_start
    for i in range(brace_start, len(script)):
        if script[i] == "{":
            depth += 1
        elif script[i] == "}":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
    fn_def = script[start_idx:end_idx]

    cases = [
        # 1. Known XenRay TUN adapter with an eligible route
        {
            "id": "known_xenray_tun_singtun",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "SINGTUN",
            "desc": "sing-tun Tunnel",
            "expected": True,
        },
        {
            "id": "known_xenray_tun_wintun",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "xenray-tun",
            "desc": "wintun Userspace Tunnel",
            "expected": True,
        },
        # 2. Physical adapter with gateway 10.0.0.2
        {
            "id": "physical_intel_adapter_10_0_0_2",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "Ethernet 1",
            "desc": "Intel(R) Ethernet Connection I219-V",
            "expected": False,
        },
        {
            "id": "physical_realtek_adapter_10_0_0_2",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "Ethernet",
            "desc": "Realtek PCIe GbE Family Controller",
            "expected": False,
        },
        # 3. Unknown or inaccessible adapter
        {
            "id": "unknown_inaccessible_empty",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "",
            "desc": "",
            "expected": False,
        },
        {
            "id": "unknown_inaccessible_whitespace",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "   ",
            "desc": "   ",
            "expected": False,
        },
        # 4. TUN-like description with conflicting or ambiguous identity
        {
            "id": "conflicting_openvpn_tun",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "OpenVPN TUN",
            "desc": "TAP-Windows Adapter V9",
            "expected": False,
        },
        {
            "id": "conflicting_wireguard_tun",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "WireGuard Tunnel",
            "desc": "WireGuard Tunnel",
            "expected": False,
        },
        {
            "id": "ambiguous_virtual_adapter",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "Local Area Connection",
            "desc": "Generic Virtual Network Adapter",
            "expected": False,
        },
        {
            "id": "unrelated_vpn_generic_wintun_desc_0_0_0_0",
            "dest": "0.0.0.0/0",
            "next_hop": "0.0.0.0",
            "alias": "OtherVPN",
            "desc": "Wintun Userspace Tunnel",
            "expected": False,
        },
        {
            "id": "unrelated_vpn_generic_wintun_desc_10_0_0_2",
            "dest": "0.0.0.0/0",
            "next_hop": "10.0.0.2",
            "alias": "OtherVPN",
            "desc": "Wintun Userspace Tunnel",
            "expected": False,
        },
        # 5. Non-default route
        {
            "id": "non_default_route_subnet",
            "dest": "192.168.1.0/24",
            "next_hop": "10.0.0.2",
            "alias": "SINGTUN",
            "desc": "sing-tun Tunnel",
            "expected": False,
        },
        {
            "id": "non_default_route_class_a",
            "dest": "10.0.0.0/8",
            "next_hop": "10.0.0.2",
            "alias": "SINGTUN",
            "desc": "sing-tun Tunnel",
            "expected": False,
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as cases_file:
        cases_file.write(json.dumps(cases))
        cases_path = cases_file.name

    ps_code = f"""param([string]$JsonPath)

{fn_def}

$jsonContent = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8
$testCases = ConvertFrom-Json $jsonContent
$results = @{{}}

foreach ($c in $testCases) {{
    $res = Test-IsXenrayTunRouteEligible `
        -DestinationPrefix $c.dest `
        -NextHop $c.next_hop `
        -InterfaceAlias $c.alias `
        -InterfaceDescription $c.desc
    $results[$c.id] = [bool]$res
}}

$results | ConvertTo-Json -Compress
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as ps_file:
        ps_file.write(ps_code)
        ps_path = ps_file.name

    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_path, "-JsonPath", cases_path],
            capture_output=True,
            text=True,
            check=True,
        )
        actual_results = json.loads(proc.stdout.strip())
        for c in cases:
            case_id = c["id"]
            expected = c["expected"]
            actual = actual_results.get(case_id)
            assert actual == expected, (
                f"Synthetic route decision failed for '{case_id}': expected {expected}, got {actual}. "
                f"Params: dest={c['dest']}, next_hop={c['next_hop']}, alias={c['alias']}, desc={c['desc']}"
            )
    finally:
        if os.path.exists(cases_path):
            os.remove(cases_path)
        if os.path.exists(ps_path):
            os.remove(ps_path)


def test_create_updater_script(tmp_path):
    """Verify that create_updater_script creates launcher and runner scripts."""
    fake_zip = str(tmp_path / "test_update.zip")
    fake_app_dir = str(tmp_path / "app")
    Path(fake_zip).write_text("dummy zip content")
    os.makedirs(fake_app_dir, exist_ok=True)

    launcher_path = AppUpdateService.create_updater_script(fake_zip, fake_app_dir)
    assert launcher_path is not None
    assert os.path.exists(launcher_path)

    launcher_content = Path(launcher_path).read_text(encoding="utf-8")
    assert "xenray_updater_run.ps1" in launcher_content
    assert fake_zip in launcher_content
    assert fake_app_dir in launcher_content


def test_create_updater_script_preserves_drive_root(tmp_path):
    """Verify create_updater_script preserves trailing separator on drive roots and strips standard paths."""
    fake_zip = str(tmp_path / "test_update.zip")
    Path(fake_zip).write_text("dummy zip content")

    # 1. Drive root installation path (D:\)
    launcher_path_drive = AppUpdateService.create_updater_script(fake_zip, "D:\\")
    assert launcher_path_drive is not None
    content_drive = Path(launcher_path_drive).read_text(encoding="utf-8")
    assert '-AppDir "D:\\"' in content_drive
    assert '-AppDir "D:"' not in content_drive

    # 2. Standard subdirectory path should still have trailing separator stripped
    launcher_path_sub = AppUpdateService.create_updater_script(fake_zip, "C:\\Program Files\\XenRay\\")
    assert launcher_path_sub is not None
    content_sub = Path(launcher_path_sub).read_text(encoding="utf-8")
    assert '-AppDir "C:\\Program Files\\XenRay"' in content_sub


@patch("subprocess.Popen")
@patch("threading.Thread")
def test_apply_update_orchestration(mock_thread, mock_popen, tmp_path):
    """Verify apply_update disconnects VPN and launches updater script on Windows."""
    fake_zip = str(tmp_path / "update.zip")
    Path(fake_zip).write_text("test")

    from src.core.connection_manager import ConnectionManager

    mock_cm = MagicMock(spec=ConnectionManager)

    with (
        patch("sys.platform", "win32"),
        patch("src.core.container.get_connection_manager", return_value=mock_cm),
        patch.object(AppUpdateService, "create_updater_script", return_value="C:\\fake\\launcher.ps1") as mock_create,
        patch("subprocess.CREATE_NO_WINDOW", 0x08000000, create=True),
    ):
        success = AppUpdateService.apply_update(fake_zip)
        assert success is True

        # Verify VPN was disconnected cleanly
        mock_cm.disconnect.assert_called_once()

        # Verify updater script was created and launched
        mock_create.assert_called_once()
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert "powershell.exe" in args[0]
        assert "C:\\fake\\launcher.ps1" in args[0]

        # Verify deferred exit thread was started
        mock_thread.assert_called_once()


@patch("subprocess.Popen")
@patch("threading.Thread")
def test_apply_update_with_callback(mock_thread, mock_popen, tmp_path):
    """Verify apply_update invokes custom disconnect callback if provided on Windows."""
    fake_zip = str(tmp_path / "update.zip")
    Path(fake_zip).write_text("test")

    mock_cb = MagicMock()

    with (
        patch("sys.platform", "win32"),
        patch.object(AppUpdateService, "create_updater_script", return_value="C:\\fake\\launcher.ps1"),
        patch("subprocess.CREATE_NO_WINDOW", 0x08000000, create=True),
    ):
        success = AppUpdateService.apply_update(fake_zip, disconnect_callback=mock_cb)
        assert success is True
        mock_cb.assert_called_once()


@patch("subprocess.Popen")
@patch("threading.Thread")
def test_apply_update_unsupported_platform_rejected(mock_thread, mock_popen, tmp_path):
    """Verify apply_update returns False on non-Windows platforms without teardown or exit."""
    fake_zip = str(tmp_path / "update.zip")
    Path(fake_zip).write_text("test")

    mock_cb = MagicMock()
    from src.core.connection_manager import ConnectionManager

    mock_cm = MagicMock(spec=ConnectionManager)

    with (
        patch("sys.platform", "linux"),
        patch("src.core.container.get_connection_manager", return_value=mock_cm),
        patch.object(AppUpdateService, "create_updater_script") as mock_create,
    ):
        success = AppUpdateService.apply_update(fake_zip, disconnect_callback=mock_cb)
        assert success is False

        # No disconnect callback or manager disconnect called
        mock_cb.assert_not_called()
        mock_cm.disconnect.assert_not_called()

        # No updater script created or launched
        mock_create.assert_not_called()
        mock_popen.assert_not_called()
        mock_thread.assert_not_called()


def _extract_powershell_function(script: str, fn_name: str) -> str:
    """Extract a PowerShell function definition by name using balanced braces."""
    target = f"function {fn_name}"
    start_idx = script.find(target)
    assert start_idx != -1, f"Function '{fn_name}' not found in updater script"
    brace_start = script.find("{", start_idx)
    assert brace_start != -1, f"Opening brace for '{fn_name}' not found"
    depth = 0
    end_idx = brace_start
    for i in range(brace_start, len(script)):
        if script[i] == "{":
            depth += 1
        elif script[i] == "}":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
    return script[start_idx:end_idx]


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_process_termination_permitted_and_forbidden_scoping(tmp_path):
    """Verify Stop-XenrayProcessesInsideAppDir terminates permitted processes
    genuinely inside TargetAppDir and strictly preserves out-of-scope processes,
    the caller/test runner, and processes with missing/invalid paths.
    """
    script = AppUpdateService.get_embedded_updater_script()
    fn_def = _extract_powershell_function(script, "Stop-XenrayProcessesInsideAppDir")

    in_scope_app = tmp_path / "app"
    out_scope_dir = tmp_path / "outside"
    in_scope_app.mkdir()
    out_scope_dir.mkdir()

    # Create distinct executables named XenRay.exe in in-scope and out-of-scope directories
    # using Windows cmd.exe as the base native executable.
    cmd_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
    assert cmd_exe.exists(), f"Native Windows cmd.exe not found at {cmd_exe}"

    in_scope_exe = in_scope_app / "XenRay.exe"
    out_scope_exe = out_scope_dir / "XenRay.exe"
    shutil.copy2(cmd_exe, in_scope_exe)
    shutil.copy2(cmd_exe, out_scope_exe)

    # Launch dedicated child processes with bounded execution
    p_in = subprocess.Popen([str(in_scope_exe), "/c", "ping -n 60 127.0.0.1 > nul"])
    p_out = subprocess.Popen([str(out_scope_exe), "/c", "ping -n 60 127.0.0.1 > nul"])

    try:
        ps_code = f"""
function Log($msg) {{ Write-Output "LOG: $msg" }}
{fn_def}

# Run Stop-XenrayProcessesInsideAppDir scoped only to in_scope_app, passing current python process as CallerProcessID
Stop-XenrayProcessesInsideAppDir -TargetAppDir '{str(in_scope_app)}' -CallerProcessID {os.getpid()}
"""
        ps_file = tmp_path / "test_termination.ps1"
        ps_file.write_text(ps_code, encoding="utf-8")

        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_file)],
            capture_output=True,
            text=True,
            check=True,
        )

        # 1. Permitted termination: Verify in-scope child process was terminated within bounded wait
        try:
            p_in.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pytest.fail("In-scope process was NOT terminated by Stop-XenrayProcessesInsideAppDir within bounded wait")

        assert p_in.poll() is not None, "In-scope process must be terminated"
        assert f"Terminating process inside AppDir: XenRay (PID: {p_in.pid}" in res.stdout

        # 2. Forbidden termination: Verify out-of-scope process was preserved
        assert p_out.poll() is None, "Out-of-scope process must NOT be terminated"
        assert f"Preserving process XenRay (PID: {p_out.pid}) located outside AppDir" in res.stdout

        # 3. Caller / test runner process preservation
        assert f"Preserving process python (PID: {os.getpid()}) located outside AppDir" in res.stdout

    finally:
        # Deterministic cleanup with bounded waits to ensure no leaked processes or file locks
        for p in (p_in, p_out):
            if p.poll() is None:
                p.kill()
                try:
                    p.wait(timeout=5)
                except Exception:
                    pass


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_process_termination_safety_caller_pid_and_path_scoping(tmp_path):
    """Verify that Stop-XenrayProcessesInsideAppDir strictly enforces directory boundary

    and does NOT allow CallerProcessID or target process names to authorize termination
    when the executable path is missing, inaccessible, or outside TargetAppDir.
    """
    script = AppUpdateService.get_embedded_updater_script()
    fn_def = _extract_powershell_function(script, "Stop-XenrayProcessesInsideAppDir")

    app_dir = tmp_path / "app"
    app_dir.mkdir()

    # Case 1: CallerProcessID provided for current Python process (located outside app_dir)
    # The process must NOT be terminated and must be logged as preserved.
    ps_script_1 = f"""
function Log($msg) {{ Write-Output $msg }}
{fn_def}

Stop-XenrayProcessesInsideAppDir -TargetAppDir '{str(app_dir)}' -CallerProcessID {os.getpid()}
"""
    ps_file_1 = tmp_path / "test_caller_pid.ps1"
    ps_file_1.write_text(ps_script_1, encoding="utf-8")

    res_1 = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_file_1)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Preserving process python" in res_1.stdout
    assert f"PID: {os.getpid()}" in res_1.stdout

    # Case 2: CallerProcessID is an invalid / non-existent PID
    ps_script_2 = f"""
function Log($msg) {{ Write-Output $msg }}
{fn_def}

Stop-XenrayProcessesInsideAppDir -TargetAppDir '{str(app_dir)}' -CallerProcessID 999999
Write-Output "FINISHED_SAFELY"
"""
    ps_file_2 = tmp_path / "test_invalid_pid.ps1"
    ps_file_2.write_text(ps_script_2, encoding="utf-8")

    res_2 = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_file_2)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "FINISHED_SAFELY" in res_2.stdout

    # Case 3: TargetAppDir normalization failure
    ps_script_3 = f"""
function Log($msg) {{ Write-Output $msg }}
{fn_def}

Stop-XenrayProcessesInsideAppDir -TargetAppDir "invalid::path::\0" -CallerProcessID {os.getpid()}
"""
    ps_file_3 = tmp_path / "test_bad_path.ps1"
    ps_file_3.write_text(ps_script_3, encoding="utf-8")

    res_3 = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_file_3)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Could not normalize TargetAppDir" in res_3.stdout or "Preserving all processes" in res_3.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_powershell_actual_rollback_execution(tmp_path):
    """Verify that the actual PowerShell rollback code restores pre-existing files,

    removes newly introduced files/directories within managed destination scope,
    and preserves unrelated user data.
    """
    script = AppUpdateService.get_embedded_updater_script()
    fn_manifest = _extract_powershell_function(script, "New-XenrayBackupManifest")
    fn_rollback = _extract_powershell_function(script, "Invoke-XenrayRollback")

    app_dir = tmp_path / "app"
    staging_dir = tmp_path / "staging"
    backup_dir = tmp_path / "backup"

    app_dir.mkdir()
    staging_dir.mkdir()

    # 1. Pre-existing files in installation
    (app_dir / "XenRay.exe").write_text("v1.0", encoding="utf-8")
    (app_dir / "core").mkdir()
    (app_dir / "core" / "sing-box.exe").write_text("sb-1.0", encoding="utf-8")
    (app_dir / "core" / "pre_existing_empty").mkdir()
    (app_dir / "user_data").mkdir()
    (app_dir / "user_data" / "profiles.json").write_text("user-preserved-data", encoding="utf-8")

    # 2. Files in staged update (replacements + new additions)
    (staging_dir / "XenRay.exe").write_text("v2.0", encoding="utf-8")
    (staging_dir / "core").mkdir()
    (staging_dir / "core" / "sing-box.exe").write_text("sb-2.0", encoding="utf-8")
    (staging_dir / "core" / "new_engine.exe").write_text("new-engine-bin", encoding="utf-8")
    (staging_dir / "core" / "new_staged_empty").mkdir()
    (staging_dir / "new_plugin").mkdir()
    (staging_dir / "new_plugin" / "plugin.dll").write_text("plugin-binary", encoding="utf-8")
    (staging_dir / "new_empty_folder").mkdir()

    ps_code = f"""
param(
    [string]$AppDir,
    [string]$BackupDir,
    [string]$ContentRoot
)

$global:LogMessages = [System.Collections.Generic.List[string]]::new()
function Log($msg) {{ $global:LogMessages.Add($msg) }}

{fn_manifest}

{fn_rollback}

# 1. Create pre-update backup and record manifest using real PowerShell implementation
$manifest = New-XenrayBackupManifest -AppDir $AppDir -BackupDir $BackupDir -ContentRoot $ContentRoot
Write-Output "MANIFEST_COUNT=$($manifest.Count)"

# 2. Simulate deployment copy (copy update package over AppDir)
Get-ChildItem -LiteralPath $ContentRoot | ForEach-Object {{
    Copy-Item -LiteralPath $_.FullName -Destination $AppDir -Recurse -Force
}}

# 3. Execute real PowerShell rollback implementation
$rbSuccess = Invoke-XenrayRollback -AppDir $AppDir -BackupDir $BackupDir `
    -ContentRoot $ContentRoot -PreExistingFiles $manifest
Write-Output "ROLLBACK_SUCCESS=$rbSuccess"
foreach ($m in $global:LogMessages) {{ Write-Output "LOG: $m" }}
"""
    ps_file = tmp_path / "test_real_rollback.ps1"
    ps_file.write_text(ps_code, encoding="utf-8")

    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_file),
            "-AppDir",
            str(app_dir),
            "-BackupDir",
            str(backup_dir),
            "-ContentRoot",
            str(staging_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify rollback reported success
    assert "ROLLBACK_SUCCESS=True" in proc.stdout
    assert "MANIFEST_COUNT=2" in proc.stdout
    assert "LOG: Restored backed-up files from backup directory." in proc.stdout
    assert "LOG: Rollback: Removing newly introduced file:" in proc.stdout

    # Verify pre-existing files restored to v1.0
    assert (app_dir / "XenRay.exe").read_text(encoding="utf-8") == "v1.0"
    assert (app_dir / "core" / "sing-box.exe").read_text(encoding="utf-8") == "sb-1.0"

    # Verify user data preserved
    assert (app_dir / "user_data" / "profiles.json").read_text(encoding="utf-8") == "user-preserved-data"

    # Verify pre-existing empty directory is preserved (not pruned)
    assert (app_dir / "core" / "pre_existing_empty").exists()

    # Verify newly introduced files and folders removed
    assert not (app_dir / "core" / "new_engine.exe").exists()
    assert not (app_dir / "core" / "new_staged_empty").exists()
    assert not (app_dir / "new_plugin" / "plugin.dll").exists()
    assert not (app_dir / "new_plugin").exists()
    assert not (app_dir / "new_empty_folder").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_powershell_actual_rollback_missing_backup_dir(tmp_path):
    """Verify Invoke-XenrayRollback returns false when backup dir is missing."""
    script = AppUpdateService.get_embedded_updater_script()
    fn_rollback = _extract_powershell_function(script, "Invoke-XenrayRollback")

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    non_existent_backup = tmp_path / "non_existent_backup"

    ps_code = f"""
param(
    [string]$AppDir,
    [string]$BackupDir,
    [string]$ContentRoot
)

$global:LogMessages = [System.Collections.Generic.List[string]]::new()
function Log($msg) {{ $global:LogMessages.Add($msg) }}

{fn_rollback}

$res = Invoke-XenrayRollback -AppDir $AppDir -BackupDir $BackupDir -ContentRoot $ContentRoot
Write-Output "RESULT=$res"
foreach ($m in $global:LogMessages) {{ Write-Output "LOG: $m" }}
"""
    ps_file = tmp_path / "test_missing_backup.ps1"
    ps_file.write_text(ps_code, encoding="utf-8")

    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_file),
            "-AppDir",
            str(app_dir),
            "-BackupDir",
            str(non_existent_backup),
            "-ContentRoot",
            str(app_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "RESULT=False" in proc.stdout
    assert "LOG: ERROR: Backup directory not found for rollback" in proc.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_powershell_actual_rollback_mid_operation_restoration_failure(tmp_path):
    """Verify that Invoke-XenrayRollback returns false and logs errors when a deterministic
    filesystem failure occurs during restoration of backed-up files.
    """
    script = AppUpdateService.get_embedded_updater_script()
    fn_manifest = _extract_powershell_function(script, "New-XenrayBackupManifest")
    fn_rollback = _extract_powershell_function(script, "Invoke-XenrayRollback")

    app_dir = tmp_path / "app"
    backup_dir = tmp_path / "backup"
    staging_dir = tmp_path / "staging"

    app_dir.mkdir()
    backup_dir.mkdir()
    staging_dir.mkdir()

    # Pre-existing file in backup that needs to be restored to app_dir
    (backup_dir / "XenRay.exe").write_text("v1.0-backup", encoding="utf-8")
    locked_file = app_dir / "XenRay.exe"
    locked_file.write_text("v2.0-corrupt", encoding="utf-8")

    # Inject a deterministic Windows filesystem lock on destination file
    f_lock = open(locked_file, "r+b")
    msvcrt.locking(f_lock.fileno(), msvcrt.LK_NBLCK, 4)

    try:
        ps_code = f"""
param(
    [string]$AppDir,
    [string]$BackupDir,
    [string]$ContentRoot
)

$global:LogMessages = [System.Collections.Generic.List[string]]::new()
function Log($msg) {{ $global:LogMessages.Add($msg) }}

{fn_manifest}
{fn_rollback}

$res = Invoke-XenrayRollback -AppDir $AppDir -BackupDir $BackupDir -ContentRoot $ContentRoot
Write-Output "RESULT=$res"
foreach ($m in $global:LogMessages) {{ Write-Output "LOG: $m" }}
"""
        ps_file = tmp_path / "test_rb_restore_fail.ps1"
        ps_file.write_text(ps_code, encoding="utf-8")

        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps_file),
                "-AppDir",
                str(app_dir),
                "-BackupDir",
                str(backup_dir),
                "-ContentRoot",
                str(staging_dir),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        assert "RESULT=False" in proc.stdout
        assert "LOG: CRITICAL: Rollback failed:" in proc.stdout
        assert "locked a portion of the file" in proc.stdout or "cannot access the file" in proc.stdout

        # Verify backup remains preserved and untouched
        assert (backup_dir / "XenRay.exe").read_text(encoding="utf-8") == "v1.0-backup"

    finally:
        try:
            msvcrt.locking(f_lock.fileno(), msvcrt.LK_UNLCK, 4)
        except Exception:
            pass
        f_lock.close()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_powershell_actual_rollback_mid_operation_pruning_failure(tmp_path):
    """Verify that Invoke-XenrayRollback returns false and logs errors when a deterministic
    filesystem failure occurs during pruning of newly introduced files.
    """
    script = AppUpdateService.get_embedded_updater_script()
    fn_manifest = _extract_powershell_function(script, "New-XenrayBackupManifest")
    fn_rollback = _extract_powershell_function(script, "Invoke-XenrayRollback")

    app_dir = tmp_path / "app"
    backup_dir = tmp_path / "backup"
    staging_dir = tmp_path / "staging"

    app_dir.mkdir()
    backup_dir.mkdir()
    staging_dir.mkdir()

    # Newly introduced file present in staging and deployed to app_dir (not in pre-existing manifest)
    (staging_dir / "new_tool.exe").write_text("v1.0-new", encoding="utf-8")
    new_file = app_dir / "new_tool.exe"
    new_file.write_text("v1.0-new", encoding="utf-8")

    # Inject deterministic filesystem lock preventing removal
    f_lock = open(new_file, "r+b")
    msvcrt.locking(f_lock.fileno(), msvcrt.LK_NBLCK, 4)

    try:
        ps_code = f"""
param(
    [string]$AppDir,
    [string]$BackupDir,
    [string]$ContentRoot
)

$global:LogMessages = [System.Collections.Generic.List[string]]::new()
function Log($msg) {{ $global:LogMessages.Add($msg) }}

{fn_manifest}
{fn_rollback}

$res = Invoke-XenrayRollback -AppDir $AppDir -BackupDir $BackupDir -ContentRoot $ContentRoot
Write-Output "RESULT=$res"
foreach ($m in $global:LogMessages) {{ Write-Output "LOG: $m" }}
"""
        ps_file = tmp_path / "test_rb_prune_fail.ps1"
        ps_file.write_text(ps_code, encoding="utf-8")

        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps_file),
                "-AppDir",
                str(app_dir),
                "-BackupDir",
                str(backup_dir),
                "-ContentRoot",
                str(staging_dir),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        assert "RESULT=False" in proc.stdout
        assert "LOG: CRITICAL: Rollback failed:" in proc.stdout
        assert "Cannot remove item" in proc.stdout or "cannot access the file" in proc.stdout

    finally:
        try:
            msvcrt.locking(f_lock.fileno(), msvcrt.LK_UNLCK, 4)
        except Exception:
            pass
        f_lock.close()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell updater tests require Windows")
def test_powershell_production_failure_handling_retains_backup(tmp_path):
    """Verify that the production failure-handling path (Invoke-XenrayDeploymentFailure)
    retains the backup directory intact and exits unsuccessfully when rollback fails mid-operation.
    """
    script = AppUpdateService.get_embedded_updater_script()
    fn_rollback = _extract_powershell_function(script, "Invoke-XenrayRollback")
    fn_deploy_failure = _extract_powershell_function(script, "Invoke-XenrayDeploymentFailure")

    app_dir = tmp_path / "app"
    backup_dir = tmp_path / "backup"
    staging_dir = tmp_path / "staging"

    app_dir.mkdir()
    backup_dir.mkdir()
    staging_dir.mkdir()

    # Pre-existing files in backup
    (backup_dir / "XenRay.exe").write_text("v1.0-critical-backup", encoding="utf-8")
    (backup_dir / "config.json").write_text('{"preserved": true}', encoding="utf-8")

    locked_dest = app_dir / "XenRay.exe"
    locked_dest.write_text("v2.0-corrupt", encoding="utf-8")

    # Inject failure by locking destination file
    f_lock = open(locked_dest, "r+b")
    msvcrt.locking(f_lock.fileno(), msvcrt.LK_NBLCK, 4)

    try:
        ps_code = f"""
param(
    [string]$AppDir,
    [string]$BackupDir,
    [string]$ContentRoot
)

$global:LogMessages = [System.Collections.Generic.List[string]]::new()
function Log($msg) {{ $global:LogMessages.Add($msg) }}

{fn_rollback}
{fn_deploy_failure}

# Simulate Step 9 & Step 10 production failure handling
$copySuccess = $false
if (-not $copySuccess) {{
    $rbSuccess = Invoke-XenrayDeploymentFailure -AppDir $AppDir -BackupDir $BackupDir `
        -ContentRoot $ContentRoot -SuppressDialog
    Write-Output "DEPLOY_FAILURE_ROLLBACK_RESULT=$rbSuccess"
    foreach ($m in $global:LogMessages) {{ Write-Output "LOG: $m" }}
    exit 1
}}

# Step 10 would clean up backup dir if copy succeeded (unreachable on failure)
Remove-Item -LiteralPath $BackupDir -Recurse -Force
"""
        ps_file = tmp_path / "test_production_fail.ps1"
        ps_file.write_text(ps_code, encoding="utf-8")

        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps_file),
                "-AppDir",
                str(app_dir),
                "-BackupDir",
                str(backup_dir),
                "-ContentRoot",
                str(staging_dir),
            ],
            capture_output=True,
            text=True,
        )

        # 1. Verify unsuccessful exit
        assert proc.returncode == 1, f"Production failure handler must exit with code 1, got {proc.returncode}"
        assert "DEPLOY_FAILURE_ROLLBACK_RESULT=False" in proc.stdout

        # 2. Verify error logging and backup retention logging
        assert "LOG: CRITICAL: Rollback failed:" in proc.stdout
        assert "LOG: CRITICAL: Rollback failed. Preserving backup directory at:" in proc.stdout

        # 3. Verify backup directory was retained and not deleted
        assert backup_dir.exists(), "Backup directory MUST be retained when rollback fails"
        assert (backup_dir / "XenRay.exe").read_text(encoding="utf-8") == "v1.0-critical-backup"
        assert (backup_dir / "config.json").read_text(encoding="utf-8") == '{"preserved": true}'

    finally:
        try:
            msvcrt.locking(f_lock.fileno(), msvcrt.LK_UNLCK, 4)
        except Exception:
            pass
        f_lock.close()
