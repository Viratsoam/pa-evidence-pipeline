type LogLevel = 'info' | 'error' | 'warn' | 'debug';

function log(level: LogLevel, message: string, meta: Record<string, unknown> = {}) {
  const payload = {
    level,
    message,
    timestamp: new Date().toISOString(),
    ...meta,
  };
  // Avoid logging PHI payloads
  console.log(JSON.stringify(payload));
}

export const logger = {
  info: (message: string, meta?: Record<string, unknown>) => log('info', message, meta),
  error: (message: string, meta?: Record<string, unknown>) => log('error', message, meta),
  warn: (message: string, meta?: Record<string, unknown>) => log('warn', message, meta),
  debug: (message: string, meta?: Record<string, unknown>) => log('debug', message, meta),
};
