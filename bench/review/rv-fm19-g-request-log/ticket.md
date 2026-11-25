# Log request latency

**Intent.** Log one line per API request through the standard logger: method, route, status and latency.
Replace gin's default logger with it, and keep panic recovery.
