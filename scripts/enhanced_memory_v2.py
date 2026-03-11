#!/usr/bin/env python3
"""
Enhanced Memory System - Multi-User Architecture

Architecture:
- User-level: Memory Store + Knowledge Graph (shared across agents)
- Agent-level: Working Memory (session-specific)
- Vector Store: Weaviate with user_id partitioning
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path


class UserMemoryStore:
    """
    用户级记忆存储
    - 所有 Agent 共享
    - 按 user_id 隔离
    """
    
    def __init__(self, user_id: str, weaviate_url: str = "http://localhost:8080",
                 ollama_url: str = "http://localhost:11434"):
        self.user_id = user_id
        self.weaviate_url = weaviate_url
        self.ollama_url = ollama_url
        self.embedding_model = "nomic-embed-text"
        
        # 禁用代理
        os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取向量嵌入"""
        resp = requests.post(
            f"{self.ollama_url}/api/embed",
            json={"model": self.embedding_model, "input": text},
            proxies={"http": None, "https": None}
        )
        return resp.json()["embeddings"][0]
    
    def add_memory(self, content: str, memory_type: str = "context",
                   importance: float = 0.5, tags: List[str] = None,
                   source_agent: str = None) -> str:
        """
        添加记忆到用户记忆库
        
        Args:
            content: 记忆内容
            memory_type: 类型 (context/event/decision/learning)
            importance: 重要性 0-1
            tags: 标签
            source_agent: 来源 Agent ID
        """
        obj = {
            "class": "Memory",
            "properties": {
                "content": content,
                "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "type": memory_type,
                "importance": importance,
                "tags": tags or [],
                "user_id": self.user_id,
                "source_agent": source_agent or "unknown"
            }
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/objects",
            json=obj,
            proxies={"http": None, "https": None}
        )
        
        if resp.status_code == 200:
            return resp.json().get("id", "")
        raise Exception(f"添加记忆失败: {resp.text}")
    
    def search_memories(self, query: str, limit: int = 10,
                        memory_type: str = None, days: int = None) -> List[Dict]:
        """
        搜索用户记忆（语义搜索）
        
        只返回当前用户的记忆
        """
        query_vector = self._get_embedding(query)
        
        # 构建过滤器：只查当前用户
        conditions = [{
            "path": ["user_id"],
            "operator": "Equal",
            "valueText": self.user_id
        }]
        
        if memory_type:
            conditions.append({
                "path": ["type"],
                "operator": "Equal",
                "valueText": memory_type
            })
        
        if days:
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
            conditions.append({
                "path": ["date"],
                "operator": "GreaterThanEqual",
                "valueText": cutoff
            })
        
        graphql_query = {
            "query": f'''{{
                Get {{
                    Memory(
                        nearVector: {{vector: {json.dumps(query_vector)}}}
                        where: {{operator: "And", operands: {json.dumps(conditions)}}}
                        limit: {limit}
                    ) {{
                        _additional {{ id certainty }}
                        content date type importance tags source_agent
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        return resp.json().get("data", {}).get("Get", {}).get("Memory", [])
    
    def get_memories_by_date(self, date: str) -> List[Dict]:
        """获取指定日期的记忆"""
        conditions = [
            {"path": ["user_id"], "operator": "Equal", "valueText": self.user_id},
            {"path": ["date"], "operator": "Like", "valueText": f"{date}T*"}
        ]
        
        graphql_query = {
            "query": f'''{{
                Get {{
                    Memory(
                        where: {{operator: "And", operands: {json.dumps(conditions)}}}
                        limit: 100
                    ) {{
                        _additional {{ id }}
                        content date type importance tags source_agent
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        return resp.json().get("data", {}).get("Get", {}).get("Memory", [])
    
    def get_date_list(self) -> Dict[str, int]:
        """获取所有有记忆的日期及数量"""
        conditions = [{
            "path": ["user_id"],
            "operator": "Equal",
            "valueText": self.user_id
        }]
        
        graphql_query = {
            "query": f'''{{
                Get {{
                    Memory(
                        where: {{operator: "And", operands: {json.dumps(conditions)}}}
                        limit: 1000
                    ) {{
                        date
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        memories = resp.json().get("data", {}).get("Get", {}).get("Memory", [])
        
        # 按日期统计
        date_counts = {}
        for m in memories:
            date = (m.get("date", "")[:10])
            date_counts[date] = date_counts.get(date, 0) + 1
        
        return date_counts


class AgentWorkingMemory:
    """
    Agent 工作记忆
    - 每个会话独立
    - 短期存储
    - 任务完成后清理
    """
    
    def __init__(self, agent_id: str, user_id: str):
        self.agent_id = agent_id
        self.user_id = user_id
        self.hot_memories: List[Dict] = []
        self.max_hot = 20
    
    def add(self, content: str, memory_type: str = "context"):
        """添加到工作记忆"""
        self.hot_memories.append({
            "content": content,
            "type": memory_type,
            "timestamp": datetime.now().isoformat(),
            "agent_id": self.agent_id
        })
        
        # 超出限制时移除最旧的
        if len(self.hot_memories) > self.max_hot:
            self.hot_memories.pop(0)
    
    def get_context(self) -> str:
        """获取工作记忆上下文"""
        return "\n".join([m["content"] for m in self.hot_memories])
    
    def clear(self):
        """清理工作记忆"""
        self.hot_memories = []


class UserKnowledgeGraph:
    """
    用户级知识图谱
    - 所有 Agent 共享
    - 按 user_id 隔离
    """
    
    def __init__(self, user_id: str, db_path: str = None):
        self.user_id = user_id
        if db_path is None:
            db_path = os.path.expanduser(f"~/.openclaw/users/{user_id}/knowledge_graph.db")
        
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        import sqlite3
        self.conn = sqlite3.connect(db_path)
        self._init_db()
    
    def _init_db(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT,
                entity_type TEXT,
                mention_count INTEGER DEFAULT 1,
                first_seen TEXT,
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                source_id TEXT,
                target_id TEXT,
                relation_type TEXT,
                weight REAL
            );
        ''')
        self.conn.commit()
    
    def add_entity(self, name: str, entity_type: str):
        """添加实体"""
        import uuid
        from datetime import datetime
        
        now = datetime.now().isoformat()
        
        # 检查是否存在
        cursor = self.conn.execute(
            "SELECT id, mention_count FROM entities WHERE name = ?", (name,)
        )
        row = cursor.fetchone()
        
        if row:
            # 更新提及次数
            self.conn.execute(
                "UPDATE entities SET mention_count = ?, last_seen = ? WHERE id = ?",
                (row[1] + 1, now, row[0])
            )
        else:
            # 创建新实体
            self.conn.execute(
                "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4())[:8], name, entity_type, 1, now, now)
            )
        
        self.conn.commit()
    
    def get_entities(self, limit: int = 100) -> List[Dict]:
        """获取所有实体"""
        entities = []
        for row in self.conn.execute(
            "SELECT * FROM entities ORDER BY mention_count DESC LIMIT ?",
            (limit,)
        ):
            entities.append({
                "id": row[0],
                "name": row[1],
                "entityType": row[2],
                "mentionCount": row[3]
            })
        return entities


class EnhancedMemorySystem:
    """
    增强记忆系统 - 统一入口
    
    Architecture:
    - UserMemoryStore: 用户级长期记忆
    - AgentWorkingMemory: Agent级工作记忆
    - UserKnowledgeGraph: 用户级知识图谱
    """
    
    def __init__(self, user_id: str, agent_id: str = "main"):
        self.user_id = user_id
        self.agent_id = agent_id
        
        # 用户级存储（所有 Agent 共享）
        self.user_memory = UserMemoryStore(user_id)
        self.knowledge_graph = UserKnowledgeGraph(user_id)
        
        # Agent 级工作记忆（独立）
        self.working_memory = AgentWorkingMemory(agent_id, user_id)
    
    def remember(self, content: str, memory_type: str = "context",
                 importance: float = 0.5, tags: List[str] = None) -> str:
        """
        存储记忆
        
        同时存储到：
        1. 用户长期记忆
        2. Agent 工作记忆
        """
        # 存到用户长期记忆
        mem_id = self.user_memory.add_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            source_agent=self.agent_id
        )
        
        # 存到 Agent 工作记忆
        self.working_memory.add(content, memory_type)
        
        # 提取实体到知识图谱
        self._extract_entities(content)
        
        return mem_id
    
    def recall(self, query: str, limit: int = 10) -> List[Dict]:
        """
        检索记忆
        
        优先级：
        1. Agent 工作记忆
        2. 用户长期记忆（语义搜索）
        """
        results = []
        
        # 1. 工作记忆
        for m in self.working_memory.hot_memories:
            if query.lower() in m["content"].lower():
                results.append({
                    "content": m["content"],
                    "type": m["type"],
                    "source": "working_memory",
                    "priority": 1.0
                })
        
        # 2. 用户长期记忆
        long_term = self.user_memory.search_memories(query, limit=limit)
        for m in long_term:
            results.append({
                "content": m.get("content"),
                "type": m.get("type"),
                "date": m.get("date"),
                "source": "user_memory",
                "priority": 0.8,
                "certainty": m.get("_additional", {}).get("certainty", 0)
            })
        
        return results[:limit]
    
    def recall_by_date(self, date: str) -> List[Dict]:
        """按日期检索记忆"""
        return self.user_memory.get_memories_by_date(date)
    
    def get_date_list(self) -> Dict[str, int]:
        """获取日期列表"""
        return self.user_memory.get_date_list()
    
    def _extract_entities(self, text: str):
        """提取实体到知识图谱"""
        import re
        
        # 简单的实体提取规则
        patterns = {
            "tool": r'\b(Docker|Python|Weaviate|Ollama|OpenClaw|Git|GitHub)\b',
            "project": r'(\w+(?:系统|模块|项目|服务))',
            "concept": r'\b(API|LLM|RAG|向量数据库|知识图谱)\b'
        }
        
        for entity_type, pattern in patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            for name in matches:
                if isinstance(name, tuple):
                    name = name[0]
                self.knowledge_graph.add_entity(name, entity_type)
    
    def get_context(self) -> str:
        """获取当前上下文（工作记忆）"""
        return self.working_memory.get_context()
    
    def clear_working_memory(self):
        """清理工作记忆"""
        self.working_memory.clear()


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enhanced Memory System")
    parser.add_argument("--user", default="default", help="User ID")
    parser.add_argument("--agent", default="main", help="Agent ID")
    parser.add_argument("--remember", help="Store memory")
    parser.add_argument("--recall", help="Search memory")
    parser.add_argument("--dates", action="store_true", help="List dates")
    parser.add_argument("--date", help="Get memories by date")
    
    args = parser.parse_args()
    
    memory = EnhancedMemorySystem(user_id=args.user, agent_id=args.agent)
    
    if args.remember:
        mem_id = memory.remember(args.remember)
        print(f"✅ 记忆已存储: {mem_id}")
    
    elif args.recall:
        results = memory.recall(args.recall)
        print(f"🔍 找到 {len(results)} 条记忆:")
        for r in results:
            print(f"  [{r['source']}] {r['content'][:50]}...")
    
    elif args.dates:
        dates = memory.get_date_list()
        print("📅 记忆日期:")
        for date, count in sorted(dates.items(), reverse=True)[:10]:
            print(f"  {date}: {count} 条")
    
    elif args.date:
        memories = memory.recall_by_date(args.date)
        print(f"📝 {args.date} 的记忆 ({len(memories)} 条):")
        for m in memories:
            print(f"  - {m.get('content', '')[:50]}...")
    
    else:
        dates = memory.get_date_list()
        print(f"🧠 用户 {args.user} 的记忆系统")
        print(f"   Agent: {args.agent}")
        print(f"   日期数: {len(dates)}")
        print(f"   总记忆: {sum(dates.values())}")


if __name__ == "__main__":
    main()