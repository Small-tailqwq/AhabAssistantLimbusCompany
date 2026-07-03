import logging

# 日志 handler（控制台/文件/UI 面板）由入口构造 module.logger.my_log.Logger() 时挂上。
# 这里只按名取 logger，不构造 Qt 相关对象，避免业务模块导入 log 时顺带加载 GUI。
log = logging.getLogger("AALC")

__all__ = ["log"]
