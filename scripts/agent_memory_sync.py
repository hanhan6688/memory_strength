#!/usr/bin/env python3
"""
Agent 记忆实时同步服务
- 监控每个 Agent 的记忆文件
- 自动同步到 Weaviate (按 agent_id 隔离)
- 支持 MEMORY.md 和 memory/*.md
- 集成到 OpenClaw cron
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/memory-system"))

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
MEMORY_DIR = WORKSPACE / "memory"
SYNC_STATE_FILE = WORKSPACE / "memory-system" / ".agent-sync-state.json"

# 禁用代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'


class AgentMemorySync:
    """Agent 记忆同步器"""
    
    def __init__(self):
        self.state = self._load_state()
        self.weaviate_url = os.environ.get("WEAVIATE_URL", "http://localhost:8080")
    
    def _load_state(self) -> dict:
        """加载同步状态"""
        if SYNC_STATE_FILE.exists():
            try:
                return json.loads(SYNC_STATE_FILE.read_text())
            except:
                pass
        return {
            "agents": {},  # {agent_id: {files: {filename: hash}}}
            "last_sync": ""
        }
    
    def _save_state(self):
        """保存同步状态"""
        self.state["last_sync"] = datetime.now().isoformat()
        SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNC_STATE_FILE.write_text(json.dumps(self.state, indent=2))
    
    def _get_file_hash(self, file_path: Path) -> str:
        """计算文件哈希"""
        if not file_path.exists():
            return ""
        content = file_path.read_bytes()
        return hashlib.md5(content).hexdigest()
    
    def _store_memory(self, content: str, agent_id: str, memory_type: str = "context",
                      importance: float = 0.5, date: str = None) -> bool:
        """存储记忆到 Weaviate"""
        import requests
        
        obj = {
            "class": "Memory",
            "properties": {
                "content": content,
                "date": date or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "type": memory_type,
                "importance": importance,
                "agent_id": agent_id,
                "source": "auto_sync"
            }
        }
        
        try:
            resp = requests.post(
                f"{self.weaviate_url}/v1/objects",
                json=obj,
                proxies={"http": None, "https": None},
                timeout=10
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"存储失败: {e}")
            return False
    
    def _extract_memories_from_md(self, content: str, file_type: str = "daily") -> List[Dict]:
        """从 Markdown 提取记忆"""
        memories = []
        lines = content.split('\n')
        current_section = ""
        
        for line in lines:
            # 检测标题
            if line.startswith('## '):
                current_section = line[3:].strip()
            elif line.startswith('### '):
                current_section = line[4:].strip()
            
            # 提取列表项
            elif line.startswith('- ') or line.startswith('* '):
                text = line[2:].strip()
                
                # 判断类型
                mem_type = "context"
                if '决策' in current_section or '决定' in text:
                    mem_type = "decision"
                elif '事件' in current_section or '完成' in text:
                    mem_type = "event"
                elif '学习' in current_section:
                    mem_type = "learning"
                
                # 判断重要性
                importance = 0.5
                if '✅' in line or '重要' in text:
                    importance = 0.8
                elif '⚠️' in line:
                    importance = 0.7
                
                if len(text) > 5:
                    memories.append({
                        "content": text,
                        "type": mem_type,
                        "importance": importance
                    })
        
        return memories
    
    def sync_agent(self, agent_id: str) -> int:
        """同步单个 Agent 的记忆"""
        import requests
        
        print(f"\n🔄 同步 Agent: {agent_id}")
        
        # Agent 记忆文件路径
        agent_memory_file = MEMORY_DIR / f"agent-{agent_id}.md"
        
        # 如果没有专门的 agent 文件，则从 MEMORY.md 或 memory/*.md 提取
        count = 0
        
        # 检查是否有专属记忆文件
        if agent_memory_file.exists():
            count = self._sync_file(agent_memory_file, agent_id)
        else:
            # 从共享记忆文件同步（根据 agent_id 过滤相关内容）
            count = self._sync_shared_memories(agent_id)
        
        return count
    
    def _sync_file(self, file_path: Path, agent_id: str) -> int:
        """同步单个文件"""
        current_hash = self._get_file_hash(file_path)
        
        # 初始化 agent 状态
        if agent_id not in self.state["agents"]:
            self.state["agents"][agent_id] = {"files": {}}
        
        old_hash = self.state["agents"][agent_id]["files"].get(file_path.name, "")
        
        if current_hash == old_hash:
            print(f"  ⏭️ {file_path.name} 无变化")
            return 0
        
        print(f"  📝 {file_path.name} 有变化，正在同步...")
        
        # 提取并存储记忆
        content = file_path.read_text(encoding='utf-8')
        memories = self._extract_memories_from_md(content)
        
        count = 0
        for mem in memories:
            if self._store_memory(
                content=mem["content"],
                agent_id=agent_id,
                memory_type=mem["type"],
                importance=mem["importance"]
            ):
                count += 1
        
        # 更新状态
        self.state["agents"][agent_id]["files"][file_path.name] = current_hash
        self._save_state()
        
        print(f"  ✅ 同步 {count} 条记忆")
        return count
    
    def _sync_shared_memories(self, agent_id: str) -> int:
        """从共享记忆文件同步"""
        # 这里可以根据 agent_id 的关键词过滤相关记忆
        # 目前简化为不同步
        print(f"  ℹ️ Agent {agent_id} 暂无专属记忆文件")
        return 0
    
    def sync_all_agents(self) -> Dict:
        """同步所有 Agent"""
        print("🚀 开始同步所有 Agent 记忆...")
        
        # 发现所有 Agent
        agents = self._discover_agents()
        print(f"📋 发现 {len(agents)} 个 Agent: {', '.join(agents)}")
        
        results = {}
        total_count = 0
        
        for agent_id in agents:
            count = self.sync_agent(agent_id)
            results[agent_id] = count
            total_count += count
        
        print(f"\n✅ 同步完成:")
        for agent_id, count in results.items():
            print(f"   {agent_id}: {count} 条")
        print(f"   总计: {total_count} 条")
        
        return {
            "agents": results,
            "total": total_count
        }
    
    def _discover_agents(self) -> List[str]:
        """发现所有 Agent"""
        agents = set()
        
        # 1. 从 Weaviate 查询已有的 agent_id
        import requests
        try:
            query = {
                "query": """{
                    Get {
                        Memory(limit: 500) {
                            agent_id
                        }
                    }
                }"""
            }
            
            resp = requests.post(
                f"{self.weaviate_url}/v1/graphql",
                json=query,
                proxies={"http": None, "https": None},
                timeout=10
            )
            
            memories = resp.json().get("data", {}).get("Get", {}).get("Memory") or []
            for m in memories:
                agent_id = m.get("agent_id")
                if agent_id:
                    agents.add(agent_id)
        except:
            pass
        
        # 2. 从文件系统发现
        if MEMORY_DIR.exists():
            for f in MEMORY_DIR.glob("agent-*.md"):
                agent_id = f.stem.replace("agent-", "")
                agents.add(agent_id)
        
        # 3. 添加默认 agent
        agents.add("main")
        
        return sorted(agents)
    
    def create_agent_memory_file(self, agent_id: str) -> Path:
        """创建 Agent 记忆文件"""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        file_path = MEMORY_DIR / f"agent-{agent_id}.md"
        
        if not file_path.exists():
            content = f"""# {agent_id} Agent 记忆日志

## 📅 {datetime.now().strftime('%Y-%m-%d')}

### 🚀 工作记录
- 

### 💡 学习内容
- 

### 🎯 决策
- 
"""
            file_path.write_text(content, encoding='utf-8')
            print(f"✅ 创建 Agent 记忆文件: {file_path}")
        
        return file_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent 记忆同步")
    parser.add_argument("--sync", action="store_true", help="同步所有 Agent")
    parser.add_argument("--agent", help="同步指定 Agent")
    parser.add_argument("--create", help="创建 Agent 记忆文件")
    parser.add_argument("--discover", action="store_true", help="发现所有 Agent")
    parser.add_argument("--status", action="store_true", help="显示同步状态")
    
    args = parser.parse_args()
    
    syncer = AgentMemorySync()
    
    if args.create:
        syncer.create_agent_memory_file(args.create)
    
    elif args.agent:
        syncer.sync_agent(args.agent)
    
    elif args.discover:
        agents = syncer._discover_agents()
        print(f"📋 发现 Agent: {', '.join(agents)}")
    
    elif args.status:
        print(json.dumps(syncer.state, indent=2, ensure_ascii=False))
    
    else:
        # 默认：同步所有
        syncer.sync_all_agents()


if __name__ == "__main__":
    main()