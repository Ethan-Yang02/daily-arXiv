"""
通知模块初始化
"""
from .email_notifier import EmailNotifier, send_test_email

__all__ = ['EmailNotifier', 'send_test_email']
