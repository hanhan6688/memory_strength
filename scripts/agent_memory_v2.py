#!/usr/bin/env python3
"""
Agent Memory System - 简化版
使用 Weaviate 存储记忆和实体（cross-reference）
不再使用 SQLite
"""

import os
import json
import re
import requests
from datetime import datetime
from typing import List, Dict, Optional
from collections import Counter


class AgentMemorySystem:
    """
    Agent 记忆系统 - 统一使用 Weaviate
    
    存储：
    - Memory: 记忆内容 + 向量嵌入
    - Entity: 实体 + cross-reference 到 Memory
    """
    
    def __init__(self, agent_id: str = "main", user_id: str = "default"):
        self.agent_id = agent_id
        self.user_id = user_id
        self.weaviate_url = os.environ.get("WEAVIATE_URL", "http://localhost:8080")
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        
        # 工作记忆（会话级）
        self.working_memory: List[Dict] = []
        
        # 禁用代理
        os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取向量嵌入"""
        resp = requests.post(
            f"{self.ollama_url}/api/embed",
            json={"model": "nomic-embed-text", "input": text},
            proxies={"http": None, "https": None},
            timeout=30
        )
        return resp.json()["embeddings"][0]
    
    def _extract_entities(self, text: str) -> List[Dict]:
        """提取实体"""
        patterns = {
            "tool": r'\b(Docker|Python|Weaviate|Ollama|OpenClaw|Git|GitHub|Flask|Redis|MySQL|MongoDB)\b',
            "project": r'(\w+(?:系统|模块|项目|服务|应用))',
            "concept": r'\b(API|LLM|RAG|向量数据库|知识图谱|NLP|ML)\b',
            "platform": r'\b(飞书|Feishu|Discord|Telegram|Slack|微信)\b'
        }
        
        entities = []
        for entity_type, pattern in patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            for name in matches:
                if isinstance(name, tuple):
                    name = name[0]
                entities.append({"name": name, "type": entity_type})
        
        return entities
    
    def remember(self, content: str, memory_type: str = "context",
                 importance: float = 0.5) -> Optional[str]:
        """存储记忆（自动提取实体并关联）"""
        # 过滤无用内容
        if self._should_filter(content):
            return None
        
        # 计算重要性
        importance = max(importance, self._get_importance(content))
        if importance < 0.5:
            return None
        
        # 提取实体
        entities = self._extract_entities(content)
        
        # 创建记忆对象
        memory_obj = {
            "class": "Memory",
            "properties": {
                "content": content,
                "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "type": memory_type,
                "importance": importance,
                "agent_id": self.agent_id,
                "user_id": self.user_id,
                "entities": [e["name"] for e in entities]  # 简化：直接存实体名称列表
            }
        }
        
        # 存储到 Weaviate
        resp = requests.post(
            f"{self.weaviate_url}/v1/objects",
            json=memory_obj,
            proxies={"http": None, "https": None},
            timeout=10
        )
        
        if resp.status_code != 200:
            print(f"存储失败: {resp.text}")
            return None
        
        memory_id = resp.json().get("id")
        
        # 存储实体到 Weaviate（用于词云图）
        for entity in entities:
            self._store_entity(entity["name"], entity["type"])
        
        # 同时存到工作记忆
        self.working_memory.append({
            "content": content,
            "type": memory_type,
            "timestamp": datetime.now().isoformat()
        })
        
        return memory_id
    
    def _store_entity(self, name: str, entity_type: str):
        """存储实体到 Weaviate"""
        # 先检查是否存在
        query = {
            "query": f'''{{
                Get {{
                    Entity(where: {{path: ["name"], operator: Equal, valueText: "{name}"}}) {{
                        _additional {{ id }}
                        name mentionCount
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=query,
            proxies={"http": None, "https": None},
            timeout=10
        )
        
        existing = resp.json().get("data", {}).get("Get", {}).get("Entity", [])
        
        if existing:
            # 更新提及次数
            entity = existing[0]
            new_count = (entity.get("mentionCount") or 1) + 1
            entity_id = entity["_additional"]["id"]
            
            requests.put(
                f"{self.weaviate_url}/v1/objects/Entity/{entity_id}",
                json={"properties": {"mentionCount": new_count}},
                proxies={"http": None, "https": None},
                timeout=10
            )
        else:
            # 创建新实体
            requests.post(
                f"{self.weaviate_url}/v1/objects",
                json={
                    "class": "Entity",
                    "properties": {
                        "name": name,
                        "entityType": entity_type,
                        "mentionCount": 1
                    }
                },
                proxies={"http": None, "https": None},
                timeout=10
            )
    
    def recall(self, query: str, limit: int = 10) -> List[Dict]:
        """检索记忆"""
        results = []
        
        # 1. 工作记忆
        for m in self.working_memory:
            if query.lower() in m["content"].lower():
                results.append({
                    "content": m["content"],
                    "type": m["type"],
                    "source": "working",
                    "priority": 1.0
                })
        
        # 2. Weaviate 语义搜索
        try:
            query_vector = self._get_embedding(query)
            
            graphql_query = {
                "query": f'''{{
                    Get {{
                        Memory(
                            nearVector: {{vector: {json.dumps(query_vector)}}}
                            where: {{path: ["agent_id"], operator: Equal, valueText: "{self.agent_id}"}}
                            limit: {limit}
                        ) {{
                            _additional {{ id certainty }}
                            content date type importance entities
                        }}
                    }}
                }}'''
            }
            
            resp = requests.post(
                f"{self.weaviate_url}/v1/graphql",
                json=graphql_query,
                proxies={"http": None, "https": None},
                timeout=15
            )
            
            memories = resp.json().get("data", {}).get("Get", {}).get("Memory", [])
            
            for m in memories:
                results.append({
                    "content": m.get("content"),
                    "type": m.get("type"),
                    "date": m.get("date"),
                    "source": "weaviate",
                    "priority": 0.8,
                    "entities": m.get("entities", []),
                    "certainty": m.get("_additional", {}).get("certainty", 0)
                })
        
        except Exception as e:
            print(f"检索失败: {e}")
        
        return results[:limit]
    
    def recall_by_date(self, date: str) -> List[Dict]:
        """按日期检索"""
        query = {
            "query": f'''{{
                Get {{
                    Memory(
                        where: {{
                            operator: "And",
                            operands: [
                                {{path: ["agent_id"], operator: Equal, valueText: "{self.agent_id}"}},
                                {{path: ["date"], operator: Like, valueText: "{date}T*"}}
                            ]
                        }}
                        limit: 100
                    ) {{
                        content date type importance entities
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=query,
            proxies={"http": None, "https": None},
            timeout=10
        )
        
        return resp.json().get("data", {}).get("Get", {}).get("Memory", [])
    
    def get_date_list(self) -> Dict[str, int]:
        """获取日期列表"""
        query = {
            "query": f'''{{
                Get {{
                    Memory(
                        where: {{path: ["agent_id"], operator: Equal, valueText: "{self.agent_id}"}}
                        limit: 1000
                    ) {{
                        date
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=query,
            proxies={"http": None, "https": None},
            timeout=10
        )
        
        memories = resp.json().get("data", {}).get("Get", {}).get("Memory", [])
        
        date_counts = {}
        for m in memories:
            date = (m.get("date", "")[:10])
            if date:
                date_counts[date] = date_counts.get(date, 0) + 1
        
        return date_counts
    
    def get_entities(self) -> List[Dict]:
        """获取所有实体（用于词云图）"""
        query = {
            "query": '''{
                Get {
                    Entity(limit: 100) {
                        _additional { id }
                        name entityType mentionCount
                    }
                }
            }'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=query,
            proxies={"http": None, "https": None},
            timeout=10
        )
        
        entities = resp.json().get("data", {}).get("Get", {}).get("Entity", [])
        
        return [{"name": e.get("name"), 
                 "entityType": e.get("entityType"),
                 "mentionCount": e.get("mentionCount", 1)} 
                for e in entities]
    
    def get_stats(self) -> Dict:
        """获取统计"""
        dates = self.get_date_list()
        entities = self.get_entities()
        
        return {
            "agent_id": self.agent_id,
            "total_memories": sum(dates.values()),
            "total_dates": len(dates),
            "total_entities": len(entities),
            "working_memory": len(self.working_memory)
        }
    
    def clear_working_memory(self):
        """清理工作记忆"""
        self.working_memory = []
    
    def _should_filter(self, text: str) -> bool:
        """判断是否应该过滤"""
        patterns = [
            r'^(你好|嗨|hello|hi|hey)[！!。.]*$',
            r'^(好的|明白了|收到|OK|ok|嗯|哦)[！!。.]*$',
            r'^(谢谢|感谢|多谢)[！!。.]*$',
            r'^(让我想想|嗯\.\.\.)',
        ]
        
        for p in patterns:
            if re.match(p, text.strip().lower()):
                return True
        return False
    
    def _get_importance(self, text: str) -> float:
        """计算重要性"""
        score = 0.5
        
        keywords = ['决定', '完成', '创建', '配置', '记住', '偏好', '密码', '问题']
        for kw in keywords:
            if kw in text:
                score += 0.1
        
        if re.search(r'[/~]\w+', text):
            score += 0.1
        if re.search(r'https?://', text):
            score += 0.1
        
        return min(1.0, score)


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent Memory System")
    parser.add_argument("--agent", default="main")
    parser.add_argument("--user", default="default")
    parser.add_argument("--remember", help="存储记忆")
    parser.add_argument("--recall", help="检索记忆")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--entities", action="store_true")
    
    args = parser.parse_args()
    
    memory = AgentMemorySystem(agent_id=args.agent, user_id=args.user)
    
    if args.remember:
        mem_id = memory.remember(args.remember)
        print(f"✅ 存储成功: {mem_id}" if mem_id else "⚠️ 已过滤")
    
    elif args.recall:
        results = memory.recall(args.recall)
        print(f"🔍 找到 {len(results)} 条")
        for r in results[:5]:
            print(f"  [{r['source']}] {r['content'][:40]}...")
    
    elif args.stats:
        print(json.dumps(memory.get_stats(), indent=2, ensure_ascii=False))
    
    elif args.entities:
        entities = memory.get_entities()
        print(f"📊 实体数量: {len(entities)}")
        for e in entities[:10]:
            print(f"  {e['name']} ({e['entityType']}) - {e['mentionCount']}次")
    
    else:
        stats = memory.get_stats()
        print(f"🧠 Agent: {args.agent}")
        print(f"   记忆: {stats['total_memories']}")
        print(f"   实体: {stats['total_entities']}")


if __name__ == "__main__":
    main()