#!/usr/bin/env python3
"""
测试调度器功能

测试 APScheduler 配置和邮件通知
"""
import sys
from pathlib import Path
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils import load_config, load_env, setup_logging
from src.notifier import EmailNotifier, send_test_email


def test_scheduler_config():
    """测试调度器配置"""
    print("\n" + "=" * 60)
    print("🧪 测试调度器配置")
    print("=" * 60)
    
    load_env()
    config = load_config()
    
    scheduler_config = config.get('scheduler', {})
    
    # 测试 1: 检查配置项
    print("\n测试 1: 检查配置项")
    required_keys = ['enabled', 'run_time', 'timezone']
    
    all_present = True
    for key in required_keys:
        if key in scheduler_config:
            print(f"  ✅ {key}: {scheduler_config[key]}")
        else:
            print(f"  ❌ {key}: 未配置")
            all_present = False
    
    if not all_present:
        print("\n❌ 配置不完整")
        return False
    
    # 测试 2: 验证时间格式
    print("\n测试 2: 验证时间格式")
    run_time = scheduler_config.get('run_time', '')
    try:
        hour, minute = map(int, run_time.split(':'))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            print(f"  ✅ 时间格式正确: {run_time}")
        else:
            print(f"  ❌ 时间值超出范围: {run_time}")
            return False
    except:
        print(f"  ❌ 时间格式错误: {run_time}")
        print("  应为 HH:MM 格式，例如: 09:00")
        return False
    
    # 测试 3: 验证时区
    print("\n测试 3: 验证时区")
    timezone = scheduler_config.get('timezone', '')
    try:
        import pytz
        tz = pytz.timezone(timezone)
        print(f"  ✅ 时区有效: {timezone}")
    except:
        print(f"  ❌ 时区无效: {timezone}")
        print("  常用时区: Asia/Shanghai, UTC, America/New_York")
        return False
    
    # 测试 4: 检查邮件通知配置
    print("\n测试 4: 检查邮件通知配置")
    notification_config = scheduler_config.get('notification', {})
    if notification_config.get('enabled', False):
        print("  ✅ 邮件通知已启用")
        email_config = notification_config.get('email', {})
        
        required_email_keys = ['smtp_server', 'smtp_port', 'sender', 'recipients']
        email_config_ok = True
        
        for key in required_email_keys:
            if key in email_config and email_config[key]:
                if key == 'recipients':
                    print(f"    ✅ {key}: {len(email_config[key])} 个收件人")
                else:
                    print(f"    ✅ {key}: {email_config[key]}")
            else:
                print(f"    ❌ {key}: 未配置")
                email_config_ok = False
        
        if not email_config_ok:
            print("  ⚠️  邮件配置不完整，通知功能可能无法使用")
    else:
        print("  ℹ️  邮件通知未启用")
    
    print("\n✅ 调度器配置测试通过")
    return True


def test_email_notification():
    """测试邮件通知"""
    print("\n" + "=" * 60)
    print("📧 测试邮件通知")
    print("=" * 60)
    
    load_env()
    config = load_config()
    
    notification_config = config.get('scheduler', {}).get('notification', {})
    
    if not notification_config.get('enabled', False):
        print("\n⚠️  邮件通知未启用")
        print("在 config/config.yaml 中设置:")
        print("  scheduler:")
        print("    notification:")
        print("      enabled: true")
        return False
    
    email_config = notification_config.get('email', {})
    
    # 创建邮件通知器
    notifier = EmailNotifier(email_config)
    
    # 发送测试邮件
    print("\n发送测试邮件...")
    print(f"收件人: {', '.join(email_config.get('recipients', []))}")
    
    test_stats = {
        'papers_count': 20,
        'summaries_count': 20,
        'categories_count': 2,
        'keywords_count': 50
    }
    
    success = notifier.send_notification(
        success=True,
        stats=test_stats,
        duration=125.5
    )
    
    if success:
        print("\n✅ 测试邮件发送成功！")
        print("请检查收件箱（可能在垃圾邮件中）")
        return True
    else:
        print("\n❌ 测试邮件发送失败！")
        print("\n常见问题:")
        print("1. 检查 SMTP 服务器和端口")
        print("2. 确认邮箱密码正确（Gmail 需要应用专用密码）")
        print("3. 检查防火墙设置")
        print("4. 查看日志获取详细错误信息")
        return False


def test_scheduler_import():
    """测试调度器导入"""
    print("\n" + "=" * 60)
    print("📦 测试依赖导入")
    print("=" * 60)
    
    try:
        print("\n检查 APScheduler...")
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        print("  ✅ APScheduler 已安装")
    except ImportError:
        print("  ❌ APScheduler 未安装")
        print("  安装: pip install apscheduler")
        return False
    
    try:
        print("\n检查 pytz...")
        import pytz
        print("  ✅ pytz 已安装")
    except ImportError:
        print("  ❌ pytz 未安装")
        print("  安装: pip install pytz")
        return False
    
    try:
        print("\n检查邮件模块...")
        import smtplib
        from email.mime.text import MIMEText
        print("  ✅ 邮件模块可用")
    except ImportError:
        print("  ❌ 邮件模块不可用")
        return False
    
    print("\n✅ 所有依赖已就绪")
    return True


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🧪 Daily arXiv 调度器测试")
    print("=" * 60)
    
    tests = []
    
    # 测试 1: 依赖导入
    tests.append(("依赖导入", test_scheduler_import()))
    
    # 测试 2: 配置检查
    tests.append(("调度器配置", test_scheduler_config()))
    
    # 测试 3: 邮件通知
    print("\n是否测试邮件通知？(这会发送一封测试邮件)")
    choice = input("输入 'y' 测试，其他键跳过: ").strip().lower()
    
    if choice == 'y':
        tests.append(("邮件通知", test_email_notification()))
    else:
        print("\n⏭️  跳过邮件通知测试")
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    for name, result in tests:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    print(f"\n通过: {passed}/{total}")
    print(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n✅ 所有测试通过！")
        print("\n下一步:")
        print("  1. 启动调度器: python scheduler.py")
        print("  2. 或使用启动脚本: ./deploy/start.sh")
        return True
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        print("请检查配置和依赖")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
