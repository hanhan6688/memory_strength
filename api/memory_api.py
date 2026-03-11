#!/usr/bin/env python3
"""
记忆系统核心 API
- 向量存储与检索
- 知识图谱管理
- RAG 检索
"""

import requests
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import re

class MemorySystem:
    def __init__(self, weaviate_url: str = "http://localhost:8080", 
                 ollama_url: str = "http://localhost:11434",
                 dashscope_api_key: str = None):
        self.weaviate_url = weaviate_url
        self.ollama_url = ollama_url
        self.dashscope_api_key = dashscope_api_key
        self.embedding_model = "nomic-embed-text"
        
    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        resp = requests.post(
            f"{self.ollama_url}/api/embed",
            json={"model": self.embedding_model, "input": text},
            proxies={"http": None, "https": None}  # 绕过代理
        )
        data = resp.json()
        return data["embeddings"][0]
    
    def add_memory(self, content: str, memory_type: str = "context",
                   importance: float = 0.5, tags: List[str] = None,
                   source: str = None, date: str = None) -> str:
        """添加一条记忆"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%dT00:00:00Z")
        if tags is None:
            tags = []
        if source is None:
            source = "manual"
            
        # 添加记忆对象
        obj = {
            "class": "Memory",
            "properties": {
                "content": content,
                "date": date,
                "type": memory_type,
                "importance": importance,
                "tags": tags,
                "source": source
            }
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/objects",
            json=obj,
            proxies={"http": None, "https": None}
        )
        
        if resp.status_code == 200:
            result = resp.json()
            return result.get("id", "")
        else:
            raise Exception(f"添加记忆失败: {resp.text}")
    
    def search_memories(self, query: str, limit: int = 10, 
                        days: int = None, memory_type: str = None) -> List[Dict]:
        """搜索记忆（向量相似度）"""
        # 获取查询向量
        query_vector = self._get_embedding(query)
        
        # 构建过滤器
        filters = None
        if days or memory_type:
            conditions = []
            if days:
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
                conditions.append({
                    "path": ["date"],
                    "operator": "GreaterThanEqual",
                    "valueText": cutoff_date
                })
            if memory_type:
                conditions.append({
                    "path": ["type"],
                    "operator": "Equal",
                    "valueText": memory_type
                })
            if len(conditions) == 1:
                filters = conditions[0]
            else:
                filters = {"operator": "And", "operands": conditions}
        
        # 执行向量搜索
        graphql_query = {
            "query": f'''{{
                Get {{
                    Memory(
                        nearVector: {{vector: {json.dumps(query_vector)}}}
                        limit: {limit}
                        {"where: " + json.dumps(filters) if filters else ""}
                    ) {{
                        _additional {{ id certainty }}
                        content date type importance tags source
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        result = resp.json()
        memories = result.get("data", {}).get("Get", {}).get("Memory", [])
        return memories
    
    def hybrid_search(self, query: str, limit: int = 10, 
                      alpha: float = 0.5) -> List[Dict]:
        """混合搜索（向量 + BM25）"""
        graphql_query = {
            "query": f'''{{
                Get {{
                    Memory(
                        hybrid: {{query: "{query}", alpha: {alpha}}}
                        limit: {limit}
                    ) {{
                        _additional {{ id score }}
                        content date type importance tags source
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        result = resp.json()
        return result.get("data", {}).get("Get", {}).get("Memory", [])
    
    def rerank_with_dashscope(self, query: str, documents: List[str], 
                               top_n: int = 5) -> List[Dict]:
        """使用阿里云 DashScope 进行重排序"""
        if not self.dashscope_api_key:
            return [{"text": doc, "score": 0.5} for doc in documents[:top_n]]
        
        resp = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
            headers={
                "Authorization": f"Bearer {self.dashscope_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen3-vl-rerank",
                "input": {
                    "query": {"text": query},
                    "documents": [{"text": doc} for doc in documents]
                },
                "parameters": {
                    "return_documents": True,
                    "top_n": top_n
                }
            }
        )
        
        if resp.status_code == 200:
            result = resp.json()
            return result.get("output", {}).get("results", [])
        else:
            return [{"text": doc, "score": 0.5} for doc in documents[:top_n]]
    
    def get_all_memories(self, limit: int = 100) -> List[Dict]:
        """获取所有记忆"""
        graphql_query = {
            "query": f'''{{
                Get {{
                    Memory(limit: {limit}) {{
                        _additional {{ id }}
                        content date type importance tags source
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        result = resp.json()
        return result.get("data", {}).get("Get", {}).get("Memory", [])
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        resp = requests.delete(
            f"{self.weaviate_url}/v1/objects/Memory/{memory_id}",
            proxies={"http": None, "https": None}
        )
        return resp.status_code == 204
    
    def get_memory_stats(self) -> Dict:
        """获取记忆统计"""
        graphql_query = {
            "query": '''{
                Aggregate {
                    Memory {
                        meta { count }
                    }
                }
            }'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        result = resp.json()
        count = result.get("data", {}).get("Aggregate", {}).get("Memory", [{}])[0].get("meta", {}).get("count", 0)
        
        return {
            "total_memories": count,
            "embedding_model": self.embedding_model,
            "weaviate_url": self.weaviate_url
        }
    
    # ===== 知识图谱实体管理 =====
    
    def add_entity(self, name: str, entity_type: str, description: str = "") -> str:
        """添加知识图谱实体"""
        obj = {
            "class": "Entity",
            "properties": {
                "name": name,
                "entityType": entity_type,
                "description": description,
                "firstSeen": datetime.now().strftime("%Y-%m-%dT00:00:00Z"),
                "lastSeen": datetime.now().strftime("%Y-%m-%dT00:00:00Z"),
                "mentionCount": 1
            }
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/objects",
            json=obj,
            proxies={"http": None, "https": None}
        )
        
        if resp.status_code == 200:
            return resp.json().get("id", "")
        else:
            raise Exception(f"添加实体失败: {resp.text}")
    
    def search_entities(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索实体"""
        query_vector = self._get_embedding(query)
        
        graphql_query = {
            "query": f'''{{
                Get {{
                    Entity(
                        nearVector: {{vector: {json.dumps(query_vector)}}}
                        limit: {limit}
                    ) {{
                        _additional {{ id certainty }}
                        name entityType description mentionCount
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        result = resp.json()
        return result.get("data", {}).get("Get", {}).get("Entity", [])
    
    def get_all_entities(self, limit: int = 100) -> List[Dict]:
        """获取所有实体"""
        graphql_query = {
            "query": f'''{{
                Get {{
                    Entity(limit: {limit}) {{
                        _additional {{ id }}
                        name entityType description firstSeen lastSeen mentionCount
                    }}
                }}
            }}'''
        }
        
        resp = requests.post(
            f"{self.weaviate_url}/v1/graphql",
            json=graphql_query,
            proxies={"http": None, "https": None}
        )
        
        result = resp.json()
        return result.get("data", {}).get("Get", {}).get("Entity", [])


# 全局实例
memory_system = None

def get_memory_system():
    global memory_system
    if memory_system is None:
        # 从环境变量获取配置
        dashscope_key = os.environ.get("DASHSCOPE_API_KEY", "sk-81599a7079a740bab26d523de33483a2")
        memory_system = MemorySystem(dashscope_api_key=dashscope_key)
        # 禁用代理
        os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
        os.environ['no_proxy'] = 'localhost,127.0.0.1'
    return memory_system