"""Log Parser - Extracts network error signals from log lines."""

import re
from typing import Optional

from src.services.network_stability_observer import (ErrorSeverity,
                                                     ErrorSignal, ErrorType)


class LogParser:
    """Parses log lines to extract network error signals."""

    # Log pattern matching (multiple patterns per error type)
    TIMEOUT_PATTERNS = [
        r"\[Error\].*timeout",
        r"dial tcp.*i/o timeout",
        r"context deadline exceeded",
        r"operation timed out",
    ]

    CONNECTION_RESET_PATTERNS = [
        r"connection reset by peer",
        r"broken pipe",
        r"connection refused",
        r"connection.*(?:dropped|closed|lost)",  # connection dropped/closed/lost
        r"connection.*error",  # generic connection error
        r"failed to process outbound traffic",
        r"failed to find an available destination",
        r"failed to open connection",
        r"failed to dial",
        r"failed to transfer response payload",
    ]

    DNS_FAILURE_PATTERNS = [
        r"dns.*lookup.*timeout",
        r"no such host",
        r"dns.*failure",
        r"process DNS packet.*bad",  # Captures bad question name/rdata
        r"dns.*bad rdata",
        r"dns: buffer size too small",
        r"dns: message size too large",
        r"dns: exchange failed",  # e.g. "dns: exchange failed for ... IN A: EOF"
    ]

    TLS_FAILURE_PATTERNS = [
        r"tls.*handshake.*timeout",
        r"tls.*handshake.*failed",
        r"certificate.*invalid",
        r"tls: bad record MAC",
        r"tls: bad certificate",
        r"XTLS rejected",
    ]

    SUCCESS_PATTERNS = [
        r"connection established",
        r"connected to",
        r"tunnel.*opened",
        r"handshake completed",
    ]

    def __init__(self):
        """Initialize LogParser with compiled regex patterns."""
        # Compile patterns for better performance
        self._timeout_regexes = [
            re.compile(p, re.IGNORECASE) for p in self.TIMEOUT_PATTERNS
        ]
        self._connection_reset_regexes = [
            re.compile(p, re.IGNORECASE) for p in self.CONNECTION_RESET_PATTERNS
        ]
        self._dns_failure_regexes = [
            re.compile(p, re.IGNORECASE) for p in self.DNS_FAILURE_PATTERNS
        ]
        self._tls_failure_regexes = [
            re.compile(p, re.IGNORECASE) for p in self.TLS_FAILURE_PATTERNS
        ]
        self._success_regexes = [
            re.compile(p, re.IGNORECASE) for p in self.SUCCESS_PATTERNS
        ]

    def parse_line(self, line: str) -> Optional[ErrorSignal]:
        """
        Parse a log line and return error signal if found.

        Args:
            line: Log line to parse

        Returns:
            ErrorSignal if error found, None otherwise
        """
        if not line:
            return None

        # Check for timeout errors
        if self._matches_any(line, self._timeout_regexes):
            return ErrorSignal(type=ErrorType.TIMEOUT, severity=ErrorSeverity.MODERATE)

        # Check for connection reset errors
        if self._matches_any(line, self._connection_reset_regexes):
            return ErrorSignal(
                type=ErrorType.CONNECTION_RESET, severity=ErrorSeverity.MODERATE
            )

        # Check for DNS failures
        if self._matches_any(line, self._dns_failure_regexes):
            return ErrorSignal(
                type=ErrorType.DNS_FAILURE, severity=ErrorSeverity.SEVERE
            )

        # Check for TLS failures
        if self._matches_any(line, self._tls_failure_regexes):
            return ErrorSignal(
                type=ErrorType.TLS_FAILURE, severity=ErrorSeverity.SEVERE
            )

        return None

    def is_success(self, line: str) -> bool:
        """
        Check if line indicates successful connection.

        Args:
            line: Log line to check

        Returns:
            True if success pattern found
        """
        return self._matches_any(line, self._success_regexes)

    def _matches_any(self, line: str, patterns: list) -> bool:
        """Check if line matches any of the given patterns."""
        return any(pattern.search(line) for pattern in patterns)
