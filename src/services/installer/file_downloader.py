"""Core download responsibility — HTTP streaming with retry, proxy fallback, and timeouts.

Owns: Xray-core and sing-box core archive downloads with automatic fallback to
direct system networking if proxy or local connection fails.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from typing import Callable, Optional

import requests
from loguru import logger

from src.platform.constants import (
    XRAY_DOWNLOAD_CHUNK_SIZE,
    XRAY_DOWNLOAD_CONNECT_TIMEOUT,
    XRAY_DOWNLOAD_MAX_RETRIES,
    XRAY_DOWNLOAD_MIN_FILE_SIZE,
    XRAY_DOWNLOAD_READ_TIMEOUT,
)


class FileDownloader:
    """Stream downloads a file from a URL with retries, direct fallback, and explicit timeouts."""

    def __init__(
        self,
        connect_timeout: float = XRAY_DOWNLOAD_CONNECT_TIMEOUT,
        read_timeout: float = XRAY_DOWNLOAD_READ_TIMEOUT,
        chunk_size: int = XRAY_DOWNLOAD_CHUNK_SIZE,
        min_file_size: int = XRAY_DOWNLOAD_MIN_FILE_SIZE,
        max_retries: int = XRAY_DOWNLOAD_MAX_RETRIES,
    ):
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._chunk_size = chunk_size
        self._min_file_size = min_file_size
        self._max_retries = max_retries

    @staticmethod
    def _create_session(direct: bool = False) -> requests.Session:
        """Create a requests session; direct=True forces bypassing local/system proxy."""
        session = requests.Session()
        if direct:
            session.trust_env = False
            session.proxies = {"http": None, "https": None}
        return session

    def download(
        self,
        url: str,
        dest_path: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        label: Optional[str] = None,
    ) -> Optional[str]:
        """Download *url* to *dest_path*; returns path on success, else None.

        *label* (e.g. the archive filename) is used in progress/log messages so
        the UI reports what is actually being fetched.
        """
        name = label or os.path.basename(dest_path)
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)

        use_direct = False

        for attempt in range(1, self._max_retries + 1):
            try:
                if progress_callback:
                    mode_info = " (direct)" if use_direct else ""
                    progress_callback(f"Downloading {name}{mode_info} (attempt {attempt}/{self._max_retries})...")

                logger.info(f"Downloading {url} (attempt {attempt}, direct={use_direct})")
                session = self._create_session(direct=use_direct)

                response = session.get(
                    url,
                    stream=True,
                    timeout=(self._connect_timeout, self._read_timeout),
                )
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                if total_size and total_size < self._min_file_size:
                    logger.error(f"Content-Length too small: {total_size} bytes")
                    continue

                downloaded = 0
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=self._chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size:
                                pct = int(downloaded * 100 / total_size)
                                progress_callback(f"Downloading... {pct}%")

                if not os.path.exists(dest_path) or os.path.getsize(dest_path) < self._min_file_size:
                    logger.error(f"Downloaded file too small or missing (attempt {attempt})")
                    continue

                logger.info(f"Download complete: {os.path.getsize(dest_path)} bytes")
                return dest_path

            except (requests.exceptions.ProxyError, requests.exceptions.SSLError) as e:
                logger.warning(f"Proxy/SSL error on attempt {attempt}: {e}. Switching to direct connection...")
                use_direct = True
                if progress_callback:
                    progress_callback("Proxy error, retrying with direct connection...")

            except requests.exceptions.Timeout:
                logger.warning(f"Download timed out (attempt {attempt}/{self._max_retries})")
                if progress_callback:
                    progress_callback(f"Timeout, retrying... ({attempt}/{self._max_retries})")
                # On timeout, try direct if we were using a proxy
                if not use_direct:
                    use_direct = True

            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error (attempt {attempt}): {e}")
                if progress_callback:
                    progress_callback(f"Connection error, retrying... ({attempt}/{self._max_retries})")
                if not use_direct:
                    use_direct = True

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error: {e}")
                if progress_callback:
                    progress_callback(f"HTTP error: {e.response.status_code}")
                # Don't retry on 4xx client errors
                if e.response is not None and e.response.status_code < 500:
                    return None

            except (OSError, IOError) as e:
                logger.error(f"File I/O error (attempt {attempt}): {e}")

            # Clean up partial file before retry
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
            except OSError:
                pass

        logger.error(f"All {self._max_retries} download attempts failed")
        if progress_callback:
            progress_callback("Download failed after all retries.")
        return None

    # ---- SHA-256 verification (Xray / sing-box .dgst sidecar) --------------

    @staticmethod
    def _verify_sha256(file_path: str, download_url: str) -> bool:
        """Verify file SHA-256 against the .dgst sidecar published on GitHub releases.

        The .dgst URL is derived from *download_url* by appending ``.dgst``.
        If the sidecar is missing (404), verification is **skipped** and the
        file is accepted — this keeps the flow backward-compatible with
        releases that don't publish checksums.
        """
        dgst_url = download_url + ".dgst"
        expected = FileDownloader._fetch_expected_sha256(dgst_url)
        if expected is None:
            logger.info(f"[FileDownloader] No .dgst sidecar at {dgst_url} — skipping SHA-256 check")
            return True

        actual = FileDownloader._sha256_hex(file_path)
        if actual is None:
            logger.warning("[FileDownloader] Could not compute SHA-256 of downloaded file")
            return False

        if actual != expected:
            logger.error(
                f"[FileDownloader] SHA-256 MISMATCH — expected {expected}, got {actual}. Discarding downloaded file."
            )
            try:
                os.remove(file_path)
            except OSError:
                pass
            return False

        logger.info(f"[FileDownloader] SHA-256 verified: {actual[:16]}…")
        return True

    @staticmethod
    def _sha256_hex(path: str) -> Optional[str]:
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 16), b""):
                    h.update(chunk)
            return h.hexdigest()
        except OSError as e:
            logger.warning(f"[FileDownloader] SHA-256 read error: {e}")
            return None

    @staticmethod
    def _fetch_expected_sha256(dgst_url: str) -> Optional[str]:
        """Fetch the .dgst sidecar and extract the ``SHA2-256=`` value."""
        try:
            resp = requests.get(dgst_url, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            for line in resp.text.splitlines():
                if line.startswith("SHA2-256="):
                    return line.split("=", 1)[1].strip().lower()
        except Exception as e:
            logger.warning(f"[FileDownloader] Could not fetch .dgst via default route: {e}. Trying direct...")
            try:
                session = FileDownloader._create_session(direct=True)
                resp = session.get(dgst_url, timeout=15)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                for line in resp.text.splitlines():
                    if line.startswith("SHA2-256="):
                        return line.split("=", 1)[1].strip().lower()
            except Exception as e2:
                logger.warning(f"[FileDownloader] Direct .dgst fetch also failed: {e2}")
        return None

    @staticmethod
    def temp_dest(filename: str) -> str:
        """Absolute temp path for a downloaded archive in staging directory."""
        staging_root = os.path.join(tempfile.gettempdir(), "xenray_staging")
        os.makedirs(staging_root, exist_ok=True)
        return os.path.join(staging_root, filename)

    def download_xray_core(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
        target_version: Optional[str] = None,
    ) -> Optional[str]:
        """Download the Xray-core release archive for the current platform."""
        from src.core.constants import XRAY_VERSION
        from src.platform import get_core_asset_adapter

        version = (target_version or XRAY_VERSION).lstrip("v")
        asset = get_core_asset_adapter().get_xray_asset_info(version)

        dest = self.download(
            asset.download_url,
            self.temp_dest(f"xray_update{asset.archive_extension}"),
            progress_callback=progress_callback,
            label=asset.filename,
        )
        if dest and not self._verify_sha256(dest, asset.download_url):
            return None
        return dest

    def download_singbox_core(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
        target_version: Optional[str] = None,
    ) -> Optional[str]:
        """Download the sing-box release archive for the current platform."""
        from src.core.constants import SINGBOX_VERSION
        from src.platform import get_core_asset_adapter

        version = (target_version or SINGBOX_VERSION).lstrip("v")
        asset = get_core_asset_adapter().get_singbox_asset_info(version)

        dest = self.download(
            asset.download_url,
            self.temp_dest(f"singbox_update{asset.archive_extension}"),
            progress_callback=progress_callback,
            label=asset.filename,
        )
        if dest and not self._verify_sha256(dest, asset.download_url):
            return None
        return dest


__all__ = ["FileDownloader"]
