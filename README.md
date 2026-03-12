# Enhanced Memory System

🧠 增强版 AI 代理记忆系统，支持知识图谱、时间范围查询、智能学习和记忆去重。

## ✨ 核心功能

### 🕸️ 知识图谱
- 自动实体识别（人名、项目、工具、概念）
- 关系抽取（因果关系、时间关系、语义关系）
- 路径查询（A 和 B 有什么关系？）

### ⏰ 时间范围查询
- 自然语言时间表达式解析
- 支持"上个月"、"昨天"、"最近7天"等
- 小模型辅助解析复杂表达式

### 🧠 神经记忆
- 扩散激活检索
- Hebbian 学习（访问越多越强）
- Ebbinghaus 遗忘曲线
- 矛盾检测

### 🔄 智能去重
- 语义相似度检测
- 自动合并相似记忆

### 📚 学习能力
- 从交互中自动学习
- 用户偏好提取

## 🚀 快速开始

```python
from scripts import get_unified_memory

memory = get_unified_memory()

# 存储记忆
memory.remember("今天完成了 Docker 配置", "event", importance=0.8)

# 检索记忆
results = memory.recall("Docker")

# 时间范围查询
result = memory.recall_by_time("上个月")

# 智能查询
result = memory.recall_interactive("就像我上个月说的那样")
```

## 📦 安装

```bash
# 克隆仓库
git clone https://github.com/hanhan6688/enhanced-memory.git
cd enhanced-memory

# 安装依赖
pip install -r requirements.txt

# 下载 Ollama 模型
ollama pull nomic-embed-text
ollama pull Llama3.2:1B
```

## 🔧 CLI 使用

```bash
# 查看系统状态
python3 scripts/unified_memory.py --stats

# 按时间查询
python3 scripts/unified_memory.py -t "上个月"

# 智能查询
python3 scripts/unified_memory.py -i "就像我上个月说的那样"

# 知识图谱
python3 scripts/knowledge_graph_enhanced.py --build
python3 scripts/knowledge_graph_enhanced.py --path OpenClaw Weaviate

# 学习
python3 scripts/memory_learner.py --profile
```

## 📁 目录结构

```
enhanced-memory/
├── SKILL.md                    # Skill 定义
├── README.md                   # 本文档
├── requirements.txt            # Python 依赖
├── scripts/
│   ├── __init__.py
│   ├── unified_memory.py       # 统一接口
│   ├── neural_memory_v2.py     # 神经记忆
│   ├── time_range_query.py     # 时间查询
│   ├── knowledge_graph_enhanced.py  # 知识图谱
│   ├── memory_learner.py       # 学习模块
│   ├── memory_optimizer.py     # 去重优化
│   └── memory_tiering.py       # 分层存储
```

## 🔌 作为 OpenClaw Skill 使用

将此目录放到 `~/.openclaw/workspace/skills/enhanced-memory/` 即可自动加载。

## 📝 许可证

MIT License
