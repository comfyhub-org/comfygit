"""Real-time log compression for reducing token count in debug logs."""

import re
from datetime import datetime


class LogCompressor:
    """Compresses log records in real-time while preserving semantic content."""

    LOG_PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - '
        r'([^ ]+) - '
        r'(\w+) - '
        r'([^:]+):(\d+) - '
        r'(.+)$'
    )

    def __init__(self, compression_level: str = 'medium'):
        self.compression_level = compression_level
        self.module_dict = {}
        self.session_start = None

    def _get_module_id(self, module: str) -> str:
        """Get or create short ID for module path."""
        if module not in self.module_dict:
            self.module_dict[module] = f"M{len(self.module_dict)}"
        return self.module_dict[module]

    def _format_delta(self, timestamp: datetime) -> str:
        """Format timestamp as delta from session start."""
        if self.session_start is None:
            self.session_start = timestamp
            return "+0.000s"

        delta = (timestamp - self.session_start).total_seconds()
        return f"+{delta:.3f}s"

    def compress_record(self, message: str) -> str:
        """Compress a single log record.

        Args:
            message: Formatted log message from handler

        Returns:
            Compressed version of the message
        """
        # Try to parse structured log line
        match = self.LOG_PATTERN.match(message)
        if not match:
            # Non-standard line (command separator, continuation, etc)
            return message

        ts_str, module, level, function, line_num, msg = match.groups()

        try:
            timestamp = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S,%f')
        except ValueError:
            # Fallback if timestamp parse fails
            return message

        # Always preserve errors and warnings with full module info
        if level in ('ERROR', 'WARNING'):
            delta = self._format_delta(timestamp)
            return f"{delta} [{level}] {module} - {msg}"

        # Command boundaries (separator lines)
        if '====' in msg or '----' in msg:
            return message

        # For aggressive compression, skip some DEBUG details
        if self.compression_level == 'aggressive' and level == 'DEBUG':
            if 'Cache' in function or 'resolve_single_node' in function:
                # Skip verbose cache/resolution internals
                return ''

        # Compress based on level
        delta = self._format_delta(timestamp)

        if self.compression_level == 'light':
            # Light: Just delta + shortened module
            mod_id = self._get_module_id(module)
            return f"{delta} {mod_id}.{function} [{level}] {msg}"

        # Medium/aggressive: more compression
        if level == 'DEBUG':
            mod_id = self._get_module_id(module)
            return f"{delta} [{mod_id}] {msg}"
        elif level == 'INFO':
            return f"{delta} [INFO] {msg}"
        else:
            return f"{delta} [{level}] {msg}"

    def get_dictionary(self) -> str:
        """Get module dictionary for appending to log file."""
        if not self.module_dict:
            return ""

        lines = ["\n# Module Dictionary:"]
        for module, mod_id in sorted(self.module_dict.items(), key=lambda x: x[1]):
            lines.append(f"# {mod_id} = {module}")
        return '\n'.join(lines) + '\n'
