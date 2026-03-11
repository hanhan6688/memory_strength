---
name: enhanced-memory
description: Enhanced memory system with knowledge graph, learning capabilities, and intelligent memory management for AI agents.
version: 1.0.0
author: hanhan6688
homepage: https://github.com/hanhan6688/enhanced-memory
metadata:
  clawdbot:
    emoji: 🧠
    requires:
      bins: ["python3", "ollama"]
      env: []
    capabilities:
      - knowledge_graph
      - time_range_query
      - memory_deduplication
      - neural_memory
---

# Enhanced Memory System

增强版 AI 代理记忆系统，支持知识图谱、时间范围查询、智能学习和记忆去重。

## ✨ 核心功能

### 1. 🕸️ 知识图谱
- 自动实体识别（人名、项目、工具、概念）
- 关系抽取（因果关系、时间关系、语义关系）
- 图谱可视化（Web UI）
- 路径查询（A 和 B 有什么关系？）

### 2. ⏰ 时间范围查询
- 自然语言时间表达式解析
- 支持"上个月"、"昨天"、"最近7天"等
- 小模型辅助解析复杂表达式

### 3. 🧠 神经记忆
- 扩散激活检索
- Hebbian 学习（访问越多越强）
- Ebbinghaus 遗忘曲线
- 矛盾检测

### 4. 🔄 智能去重
- 语义相似度检测
- 自动合并相似记忆
- 冲突识别与解决

### 5. 📚 学习能力
- 从交互中自动学习
- 模式识别与归纳
- 偏好提取

## 🚀 快速开始

```bash
# 查看系统状态
python3 scripts/unified_memory.py --stats

# 按时间查询
python3 scripts/unified_memory.py -t "上个月"

# 智能查询
python3 scripts/unified_memory.py -i "就像我上个月说的那样"

# 知识图谱
python3 scripts/knowledge_graph.py --build
python3 scripts/knowledge_graph.py --query "OpenClaw 和 Weaviate 的关系"

# 记忆去重
python3 scripts/memory_optimizer.py --dedupe
```

## 📖 API

```python
from scripts.unified_memory import get_unified_memory

memory = get_unified_memory()

# 存储记忆
memory.remember("今天完成了 Docker 配置", "event", importance=0.8)

# 检索记忆
results = memory.recall("Docker")

# 时间范围查询
result = memory.recall_by_time("上个月", keywords=["Docker"])

# 智能查询
result = memory.recall_interactive("就像我上周说的那样")

# 知识图谱
graph = memory.get_knowledge_graph()
paths = memory.find_relation_path("OpenClaw", "Weaviate")

# 学习
memory.learn_from_interaction("用户偏好使用 Docker 进行部署")

# 去重
memory.deduplicate()
```

## 🔧 依赖

- Python 3.8+
- Ollama (nomic-embed-text, qwen2.5:0.5b)
- SQLite (内置)

## 📁 目录结构

```
enhanced-memory/
├── SKILL.md
├── scripts/
│   ├── unified_memory.py      # 统一接口
│   ├── neural_memory_v2.py    # 神经记忆
│   ├── time_range_query.py    # 时间查询
│   ├── knowledge_graph.py     # 知识图谱
│   ├── memory_optimizer.py    # 去重优化
│   ├── memory_learner.py      # 学习模块
│   └── memory_tiering.py      # 分层存储
├── api/
│   └── web_server.py          # Web API
└── ui/
    └── index.html             # 可视化界面
```

## 🌐 Web UI

启动 Web 服务器后访问 http://localhost:5001

- 记忆浏览器（按日期导航）
- 知识图谱可视化
- 时间范围搜索
- 记忆统计仪表盘

## 📝 更新日志

### v1.0.0 (2026-03-11)
- 初始版本
- 知识图谱支持
- 时间范围查询
- 神经记忆系统
- 智能去重