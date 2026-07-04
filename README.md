# AI Recorder — 自动工作轨迹记录与日报生成器

一个 Python 工具，自动记录你在电脑上做了什么，用 AI 生成结构化日报。

## 功能

- **自动记录**：后台运行，记录你打开的应用和窗口
- **时间黑洞检测**：发现碎片化工作、无意识摸鱼、会议陷阱
- **AI 日报**：每天自动生成工作日报，包含时间线、统计、建议
- **隐私保护**：数据本地存储，不上传原始日志

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动（系统托盘模式）
python main.py start

# 生成昨天的日报
python main.py report --date 2026-07-03

# 查看今天的统计
python main.py stats

# 停止后台程序
python main.py stop

# 清除所有数据
python main.py clear
```

## 配置

编辑 `config/settings.yaml`：

```yaml
recorder:
  sample_interval: 5        # 采样间隔(秒)
  privacy_mode: true        # 隐私模式

ai:
  api_base: "http://localhost:xxxx"   # Agnes API 地址
  api_key: "your-key"
  model: "agnes-xxx"
```

## 项目结构

```
ai-recorder/
├── core/              # 核心模块
│   ├── recorder.py    # 数据采集器
│   ├── analyzer.py    # 本地分析引擎
│   └── reporter.py    # AI 日报生成器
├── storage/
│   └── database.py    # SQLite 数据库
├── output/
│   ├── markdown.py    # Markdown 日报输出
│   └── html.py        # HTML 仪表盘
├── config/
│   └── settings.py    # 配置管理
├── main.py            # 主程序入口
├── tray.py            # 系统托盘
└── requirements.txt   # 依赖
```

## 隐私说明

- 只记录窗口名称和时间，不录屏、不截屏
- 原始数据存在本地，不上传
- 只向 AI 发送脱敏后的统计摘要
- 代码开源，可随时审查
