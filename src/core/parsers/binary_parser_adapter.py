"""Adapter for invoking the compiled libXray CLI parser binary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger

from src.core.constants import USE_LIBXRAY_PARSER, XRAY_PARSER_EXECUTABLE
from src.core.parsers.base import build_minimal_config


class LibXrayParserAdapter:
    """Invokes compiled Go libXray CLI binary (xray-parser) via subprocess."""

    @staticmethod
    def get_executable_path() -> str:
        """Return the configured or discovered path to xray-parser binary."""
        override = os.getenv("XRAY_PARSER_PATH")
        if override and os.path.exists(override):
            return override
        return XRAY_PARSER_EXECUTABLE

    @classmethod
    def is_available(cls) -> bool:
        """Check if the compiled xray-parser binary exists and is executable."""
        path = cls.get_executable_path()
        return bool(path and os.path.isfile(path) and os.access(path, os.X_OK | os.R_OK))

    @classmethod
    def parse(cls, link: str, timeout: float = 3.0) -> Dict[str, Any]:
        """
        Parse proxy share link via compiled xray-parser CLI binary.

        Args:
            link: Raw proxy share link (vless://, vmess://, trojan://, ss://, etc.)
            timeout: Subprocess execution timeout in seconds.

        Returns:
            Dict containing {"name": str, "config": dict} matching XenRay contract.

        Raises:
            ValueError: If parsing fails or output is malformed.
        """
        if not link or not isinstance(link, str):
            raise ValueError("Link must be a non-empty string")

        binary_path = cls.get_executable_path()
        if not cls.is_available():
            raise FileNotFoundError(f"xray-parser binary not found or not executable at {binary_path}")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            proc = subprocess.run(
                [binary_path, "-stdin"],
                input=link.strip().encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error(f"[LibXrayParserAdapter] Execution timed out after {timeout}s")
            raise ValueError(f"Parser timed out after {timeout}s") from exc
        except OSError as exc:
            logger.error(f"[LibXrayParserAdapter] Failed to execute {binary_path}: {exc}")
            raise ValueError(f"Failed to execute parser binary: {exc}") from exc

        stdout_text = proc.stdout.decode("utf-8", errors="replace").strip()

        try:
            payload = json.loads(stdout_text) if stdout_text else {}
        except json.JSONDecodeError as exc:
            stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
            logger.error(f"[LibXrayParserAdapter] Invalid JSON output (exit {proc.returncode}): {stderr_text}")
            raise ValueError(f"Failed to parse binary output: {exc}") from exc

        if proc.returncode != 0 or not payload.get("success", False):
            err_msg = payload.get("error") or proc.stderr.decode("utf-8", errors="replace").strip() or "Unknown error"
            raise ValueError(f"xray-parser failed: {err_msg}")

        name = payload.get("name") or "Proxy Server"
        outbound = payload.get("outbound")
        if not outbound:
            raise ValueError("No outbound configuration returned by xray-parser")

        config = build_minimal_config(outbound)
        return {"name": name, "config": config, "outbound": outbound}

    @classmethod
    def parse_with_fallback(
        cls,
        link: str,
        fallback_func: Callable[[str], Dict[str, Any]],
        timeout: float = 3.0,
        shadow_test: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute libXray parser with automatic fallback to Python parser.

        Args:
            link: Share link.
            fallback_func: Python parser function to call on fallback or shadow comparison.
            timeout: Subprocess timeout.
            shadow_test: If True, executes both and logs structural differences.

        Returns:
            Parsed {"name": str, "config": dict}
        """
        use_binary = USE_LIBXRAY_PARSER and cls.is_available()

        if not use_binary:
            return fallback_func(link)

        try:
            result = cls.parse(link, timeout=timeout)

            if shadow_test:
                cls._perform_shadow_diff(link, result, fallback_func)

            return result
        except Exception as exc:
            logger.warning(f"[LibXrayParserAdapter] Binary parse failed ({exc}), falling back to Python parser")
            return fallback_func(link)

    @classmethod
    def _perform_shadow_diff(
        cls,
        link: str,
        binary_res: Dict[str, Any],
        fallback_func: Callable[[str], Dict[str, Any]],
    ) -> None:
        """Run fallback parser and log any structural discrepancies."""
        try:
            python_res = fallback_func(link)
            b_out = binary_res.get("config", {}).get("outbounds", [{}])[0]
            p_out = python_res.get("config", {}).get("outbounds", [{}])[0]

            diffs = []
            if b_out.get("protocol") != p_out.get("protocol"):
                diffs.append(f"protocol: {b_out.get('protocol')} != {p_out.get('protocol')}")

            b_stream = b_out.get("streamSettings", {})
            p_stream = p_out.get("streamSettings", {})

            if b_stream.get("security") != p_stream.get("security"):
                diffs.append(f"security: {b_stream.get('security')} != {p_stream.get('security')}")
            if b_stream.get("network") != p_stream.get("network"):
                diffs.append(f"network: {b_stream.get('network')} != {p_stream.get('network')}")

            if diffs:
                logger.info(f"[LibXrayParserAdapter] Shadow test diff for {link[:30]}...: {', '.join(diffs)}")
        except Exception as err:
            logger.debug(f"[LibXrayParserAdapter] Shadow test comparison error: {err}")

    @classmethod
    def parse_batch(cls, text_or_links: str | list[str], timeout: float = 10.0) -> list[Dict[str, Any]]:
        """
        Parse multiple proxy links in a single batch invocation via xray-parser -batch.

        Args:
            text_or_links: Newline-separated link string or list of link strings.
            timeout: Execution timeout in seconds.

        Returns:
            List of {"name": str, "config": dict, "outbound": dict}
        """
        if isinstance(text_or_links, list):
            payload_str = "\n".join(s.strip() for s in text_or_links if s.strip())
        else:
            payload_str = text_or_links.strip()

        if not payload_str:
            return []

        binary_path = cls.get_executable_path()
        if not cls.is_available():
            raise FileNotFoundError(f"xray-parser binary not found at {binary_path}")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            proc = subprocess.run(
                [binary_path, "-stdin", "-batch"],
                input=payload_str.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"Batch parser timed out after {timeout}s") from exc

        stdout_text = proc.stdout.decode("utf-8", errors="replace").strip()
        try:
            data = json.loads(stdout_text) if stdout_text else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse batch output: {exc}") from exc

        if proc.returncode != 0 or not data.get("success", False):
            err_msg = data.get("error") or "Batch parse failed"
            raise ValueError(err_msg)

        raw_items = data.get("items", [])
        items = []
        for it in raw_items:
            ob = it.get("outbound")
            if not ob:
                continue
            n = it.get("name") or "Proxy"
            cfg = build_minimal_config(ob)
            items.append({"name": n, "config": cfg, "outbound": ob})

        return items

    @classmethod
    def get_xray_version(cls, timeout: float = 2.0) -> Optional[str]:
        """
        Query the embedded Xray-core version from the xray-parser binary.

        Returns:
            Version string (e.g. '26.9.9') or None if binary unavailable or call fails.
        """
        if not cls.is_available():
            return None

        binary_path = cls.get_executable_path()
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            proc = subprocess.run(
                [binary_path, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                timeout=timeout,
            )
            data = json.loads(proc.stdout.decode("utf-8", errors="replace").strip() or "{}")
            if data.get("success"):
                return data.get("version")
        except Exception as exc:
            logger.debug(f"[LibXrayParserAdapter] Failed to query xray version: {exc}")
        return None

    @classmethod
    def validate_config(cls, config: Dict[str, Any] | str, timeout: float = 3.0) -> Tuple[bool, Optional[str]]:
        """
        Validate full Xray JSON configuration using embedded core testXray builder.

        Args:
            config: Config dict or JSON string.
            timeout: Subprocess timeout in seconds.

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if not cls.is_available():
            return True, None  # Cannot validate if binary unavailable; assume pass

        binary_path = cls.get_executable_path()
        payload_str = json.dumps(config) if isinstance(config, dict) else str(config).strip()

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            proc = subprocess.run(
                [binary_path, "-test"],
                input=payload_str.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                timeout=timeout,
            )
            data = json.loads(proc.stdout.decode("utf-8", errors="replace").strip() or "{}")
            if data.get("success"):
                return True, None
            return False, data.get("error") or "Configuration validation failed"
        except Exception as exc:
            return False, str(exc)
