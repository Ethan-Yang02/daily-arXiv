# 定时调度使用指南

## 概述

本项目提供三种定时调度方式：

1. **APScheduler** - Python 调度器（推荐）
2. **Cron** - Linux 系统 cron 任务
3. **Systemd** - Linux 系统服务

## 方式 1: APScheduler（推荐）

### 优点

- ✅ 跨平台（Linux、macOS、Windows）
- ✅ Python 原生支持
- ✅ 实时日志输出
- ✅ 易于调试
- ✅ 支持多种触发器
- ✅ 集成邮件通知

### 配置

编辑 `config/config.yaml`:

```yaml
scheduler:
  enabled: true
  run_time: "09:00"  # 每天 9:00 运行
  timezone: "Asia/Shanghai"
  run_on_start: false  # 启动时是否立即运行
  
  notification:
    enabled: true  # 启用邮件通知
    email:
      smtp_server: "smtp.gmail.com"
      smtp_port: 587
      sender: "your-email@gmail.com"
      password: ""  # 在 .env 中设置 EMAIL_PASSWORD
      recipients:
        - "recipient@example.com"
      on_success: true
      on_failure: true
```

### 启动方式

#### 方式 A: 使用启动脚本（推荐）

```bash
./deploy/start.sh
```

选择选项：
1. 前台运行（查看实时日志）
2. 后台运行（守护进程）
3. 运行一次任务（测试）
4. 测试邮件通知
5. 查看调度器状态
6. 停止调度器

#### 方式 B: 直接运行

```bash
# 前台运行
python scheduler.py

# 后台运行
nohup python scheduler.py > logs/scheduler.log 2>&1 &

# 保存 PID
echo $! > logs/scheduler.pid

# 查看日志
tail -f logs/scheduler.log

# 停止
kill $(cat logs/scheduler.pid)
```

### 邮件通知配置

1. **Gmail 配置**

如果使用 Gmail，需要：
- 启用"两步验证"
- 生成"应用专用密码"
- 在 `.env` 文件中设置：

```bash
EMAIL_PASSWORD=your-app-specific-password
```

2. **其他邮箱**

根据邮箱提供商设置 SMTP 服务器：

```yaml
# QQ 邮箱
smtp_server: "smtp.qq.com"
smtp_port: 587

# 163 邮箱
smtp_server: "smtp.163.com"
smtp_port: 25

# Outlook
smtp_server: "smtp.office365.com"
smtp_port: 587
```

3. **测试邮件**

```bash
./deploy/start.sh
# 选择选项 4: 测试邮件通知
```

或者：

```bash
python -c "
from src.utils import load_config, load_env
from src.notifier import send_test_email

load_env()
config = load_config()
email_config = config['scheduler']['notification']['email']
send_test_email(email_config)
"
```

## 方式 2: Linux Cron

### 优点

- ✅ 系统级调度
- ✅ 无需额外进程
- ✅ 可靠稳定

### 缺点

- ❌ 仅限 Linux/macOS
- ❌ 调试不便
- ❌ 需要手动配置日志

### 配置步骤

1. **编辑 crontab**

```bash
crontab -e
```

2. **添加任务**

```bash
# 每天上午 9:00 执行
0 9 * * * cd /path/to/daily-arxiv && /path/to/python/bin/python main.py >> logs/cron.log 2>&1
```

3. **查看已配置的任务**

```bash
crontab -l
```

4. **查看日志**

```bash
tail -f logs/cron.log
```

### Cron 时间格式

```
* * * * * command
┬ ┬ ┬ ┬ ┬
│ │ │ │ └─ 星期 (0-7)
│ │ │ └─── 月份 (1-12)
│ │ └───── 日期 (1-31)
│ └─────── 小时 (0-23)
└───────── 分钟 (0-59)
```

**示例**：

```bash
# 每天 9:00
0 9 * * *

# 每周一 9:00
0 9 * * 1

# 每天 9:00 和 18:00
0 9,18 * * *

# 每小时
0 * * * *

# 每 30 分钟
*/30 * * * *
```

## 方式 3: Systemd 服务

### 优点

- ✅ 系统级管理
- ✅ 自动启动
- ✅ 日志集成
- ✅ 故障重启

### 缺点

- ❌ 仅限 Linux
- ❌ 需要 root 权限

### 配置步骤

推荐使用一键部署脚本：

```bash
bash deploy/deploy_services.sh
```

脚本会自动：选择 Conda/venv 环境、安装依赖、生成适配本机的 systemd service 文件、启用并启动服务。

如需手动部署，模板文件位于 `deploy/daily-arxiv-scheduler.service` 。

3. **管理服务**

```bash
# 查看状态
sudo systemctl status daily-arxiv

# 查看日志
sudo journalctl -u daily-arxiv -f

# 停止服务
sudo systemctl stop daily-arxiv

# 重启服务
sudo systemctl restart daily-arxiv

# 禁用服务
sudo systemctl disable daily-arxiv
```

4. **创建日志目录**

```bash
sudo mkdir -p /var/log/daily-arxiv
sudo chown YOUR_USERNAME:YOUR_USERNAME /var/log/daily-arxiv
```

## 调度策略建议

### 1. 开发/测试环境

使用 **APScheduler** 前台运行：

```bash
python scheduler.py
```

优点：
- 实时查看日志
- 方便调试
- 快速测试

### 2. 个人服务器

使用 **APScheduler** 后台运行：

```bash
./deploy/start.sh
# 选择选项 2: 后台运行
```

或使用 **Cron**：

```bash
crontab -e
# 添加定时任务
```

### 3. 生产环境

使用 **Systemd 服务**：

```bash
sudo systemctl enable daily-arxiv-scheduler
sudo systemctl start daily-arxiv-scheduler
```

优点：
- 系统级管理
- 自动启动
- 故障恢复
- 日志集成

## 监控和维护

### 1. 查看执行日志

```bash
# APScheduler 日志
tail -f logs/scheduler.log

# Cron 日志
tail -f logs/cron.log

# Systemd 日志
sudo journalctl -u daily-arxiv -f
```

### 2. 检查数据更新

```bash
# 查看最新数据
ls -lh data/papers/latest.json
ls -lh data/summaries/latest.json
ls -lh data/analysis/latest.json

# 查看数据时间戳
stat data/papers/latest.json
```

### 3. 测试单次运行

```bash
# 运行一次完整任务
python main.py

# 或使用启动脚本
./deploy/start.sh
# 选择选项 3
```

### 4. 邮件通知测试

```bash
./deploy/start.sh
# 选择选项 4: 测试邮件通知
```

### 5. 日志轮转

添加日志轮转配置（可选）：

```bash
# 创建配置文件
sudo nano /etc/logrotate.d/daily-arxiv
```

添加内容：

```
/path/to/daily-arxiv/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}
```

## 故障排查

### 问题 1: 调度器未启动

**检查**：
```bash
# 查看配置
cat config/config.yaml | grep -A 5 scheduler

# 检查 enabled 是否为 true
```

**解决**：
```yaml
scheduler:
  enabled: true  # 确保为 true
```

### 问题 2: 任务未执行

**检查**：
```bash
# 查看日志
tail -f logs/scheduler.log

# 检查时间配置
cat config/config.yaml | grep run_time
```

**解决**：
- 确认时区设置正确
- 确认时间格式为 "HH:MM"
- 检查系统时间: `date`

### 问题 3: 邮件发送失败

**检查**：
```bash
# 查看环境变量
cat .env | grep EMAIL

# 测试邮件
./deploy/start.sh  # 选项 4
```

**常见原因**：
- SMTP 密码错误
- 未启用应用专用密码（Gmail）
- SMTP 服务器/端口错误
- 防火墙拦截

### 问题 4: 权限错误

**解决**：
```bash
# 确保脚本有执行权限
chmod +x deploy/start.sh

# 确保数据目录可写
chmod -R 755 data logs
```

### 问题 5: Python 环境问题

**检查**：
```bash
# 确认 Python 环境
which python
python --version

# 确认依赖安装
pip list | grep apscheduler
```

**解决**：
```bash
# 激活 conda 环境
conda activate daily-arxiv

# 安装依赖
pip install -r requirements.txt
```

## 性能优化

### 1. 调整运行时间

避开服务器高峰期：

```yaml
# 凌晨运行（服务器负载低）
run_time: "02:00"

# 工作时间前运行
run_time: "07:00"
```

### 2. 控制资源占用

```yaml
# 减少论文数量
arxiv:
  max_results: 10  # 默认 20

# 使用更快的 LLM
llm:
  provider: "gemini"  # 或 "deepseek"
```

### 3. 并行处理

修改 `main.py` 支持并行总结（可选）。

## 下一步

- [ ] 集成 Telegram Bot
- [ ] 添加数据库存储
- [ ] 实现增量更新
- [ ] 添加性能监控

## 参考资料

- [APScheduler 文档](https://apscheduler.readthedocs.io/)
- [Cron 表达式](https://crontab.guru/)
- [Systemd 服务管理](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
