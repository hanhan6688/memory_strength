#!/usr/bin/env python3
"""
神经记忆系统 v2.0
借鉴 neural-memory 的核心思想：
- 扩散激活检索
- 记忆关联图谱
- Hebbian 学习
- 矛盾检测
- 因果推理
"""

import os
import sys
import json
import re
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

# 突触类型（借鉴 neural-memory）
class SynapseType(Enum):
    # 时间关系
    BEFORE = "before"         # A 在 B 之前
    AFTER = "after"           # A 在 B 之后
    DURING = "during"         # A 与 B 同时发生
    
    # 因果关系
    CAUSED_BY = "caused_by"   # A 导致 B
    LEADS_TO = "leads_to"     # A 导致 B
    ENABLES = "enables"       # A 使 B 成为可能
    
    # 语义关系
    IS_A = "is_a"             # A 是 B 的一种
    HAS_PROPERTY = "has_property"  # A 有属性 B
    PART_OF = "part_of"       # A 是 B 的一部分
    RELATED_TO = "related_to" # A 与 B 相关
    
    # 情感关系
    FELT = "felt"             # A 感到 B
    EVOKES = "evokes"         # A 唤起 B
    
    # 冲突关系
    CONTRADICTS = "contradicts"  # A 与 B 矛盾
    REPLACES = "replaces"     # A 替换 B
    
    # 依赖关系
    DEPENDS_ON = "depends_on" # A 依赖 B
    USES = "uses"             # A 使用 B


@dataclass
class Neuron:
    """记忆神经元"""
    id: str
    content: str
    memory_type: str  # fact, decision, event, preference, error, insight
    importance: float = 0.5
    created_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    decay_rate: float = 0.01  # Ebbinghaus 遗忘曲线
    tags: List[str] = field(default_factory=list)
    
    def get_strength(self) -> float:
        """计算记忆强度（考虑衰减和访问频率）"""
        # Hebbian 学习：访问越多越强
        frequency_boost = min(1.0, self.access_count * 0.1)
        
        # Ebbinghaus 衰减
        if self.created_at:
            try:
                created = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
                days_old = (datetime.now(created.tzinfo) - created).days
                decay = 2.71 ** (-self.decay_rate * days_old)
            except:
                decay = 0.5
        else:
            decay = 0.5
        
        return min(1.0, self.importance * decay + frequency_boost)


@dataclass
class Synapse:
    """突触连接"""
    source_id: str
    target_id: str
    synapse_type: SynapseType
    weight: float = 0.5  # 连接强度
    created_at: str = ""


class NeuralMemoryGraph:
    """神经记忆图谱"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.openclaw/workspace/memory-system/neural_memory.db")
        
        self.db_path = db_path
        self.conn = None
        self.neurons: Dict[str, Neuron] = {}
        self.synapses: Dict[str, List[Synapse]] = defaultdict(list)  # neuron_id -> synapses
        
        self._init_db()
        self._load_from_db()
    
    def _init_db(self):
        """初始化数据库"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS neurons (
                id TEXT PRIMARY KEY,
                content TEXT,
                memory_type TEXT,
                importance REAL,
                created_at TEXT,
                last_accessed TEXT,
                access_count INTEGER,
                decay_rate REAL,
                tags TEXT
            );
            
            CREATE TABLE IF NOT EXISTS synapses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT,
                target_id TEXT,
                synapse_type TEXT,
                weight REAL,
                created_at TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_synapse_source ON synapses(source_id);
            CREATE INDEX IF NOT EXISTS idx_synapse_target ON synapses(target_id);
        ''')
        self.conn.commit()
    
    def _load_from_db(self):
        """从数据库加载"""
        # 加载神经元
        for row in self.conn.execute('SELECT * FROM neurons'):
            self.neurons[row[0]] = Neuron(
                id=row[0],
                content=row[1],
                memory_type=row[2],
                importance=row[3],
                created_at=row[4],
                last_accessed=row[5],
                access_count=row[6],
                decay_rate=row[7],
                tags=json.loads(row[8]) if row[8] else []
            )
        
        # 加载突触
        for row in self.conn.execute('SELECT * FROM synapses'):
            synapse = Synapse(
                source_id=row[1],
                target_id=row[2],
                synapse_type=SynapseType(row[3]),
                weight=row[4],
                created_at=row[5]
            )
            self.synapses[synapse.source_id].append(synapse)
    
    def remember(self, content: str, memory_type: str = "fact",
                 importance: float = 0.5, tags: List[str] = None) -> str:
        """存储记忆"""
        import uuid
        neuron_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        neuron = Neuron(
            id=neuron_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            created_at=now,
            last_accessed=now,
            access_count=1,
            tags=tags or []
        )
        
        self.neurons[neuron_id] = neuron
        
        # 存入数据库
        self.conn.execute('''
            INSERT INTO neurons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (neuron_id, content, memory_type, importance, now, now, 1, 0.01, json.dumps(tags or [])))
        self.conn.commit()
        
        # 自动创建关联
        self._auto_create_synapses(neuron_id, content)
        
        return neuron_id
    
    def _auto_create_synapses(self, neuron_id: str, content: str):
        """自动创建突触连接"""
        # 提取实体和关键词
        entities = self._extract_entities(content)
        
        # 查找相关神经元并创建连接
        for other_id, other in self.neurons.items():
            if other_id == neuron_id:
                continue
            
            other_entities = self._extract_entities(other.content)
            
            # 实体重叠 -> RELATED_TO
            if entities & other_entities:
                self.create_synapse(neuron_id, other_id, SynapseType.RELATED_TO)
            
            # 时间关系
            if self.neurons[neuron_id].created_at and other.created_at:
                try:
                    t1 = datetime.fromisoformat(self.neurons[neuron_id].created_at.replace('Z', '+00:00'))
                    t2 = datetime.fromisoformat(other.created_at.replace('Z', '+00:00'))
                    
                    if t1 < t2:
                        self.create_synapse(neuron_id, other_id, SynapseType.BEFORE)
                    elif t1 > t2:
                        self.create_synapse(other_id, neuron_id, SynapseType.BEFORE)
                except:
                    pass
    
    def _extract_entities(self, text: str) -> Set[str]:
        """提取实体"""
        entities = set()
        
        # 技术工具
        tools = re.findall(r'(OpenClaw|Weaviate|Ollama|Docker|ClawHub|飞书|Python|Flask)', text, re.IGNORECASE)
        entities.update(t.lower() for t in tools)
        
        # 项目名称
        projects = re.findall(r'(\w+(?:系统|模块|项目|服务))', text)
        entities.update(projects)
        
        # 关键概念
        concepts = re.findall(r'(\w+(?:配置|安装|部署|修复|完成))', text)
        entities.update(concepts)
        
        return entities
    
    def create_synapse(self, source_id: str, target_id: str, 
                       synapse_type: SynapseType, weight: float = 0.5):
        """创建突触连接"""
        now = datetime.now().isoformat()
        
        synapse = Synapse(
            source_id=source_id,
            target_id=target_id,
            synapse_type=synapse_type,
            weight=weight,
            created_at=now
        )
        
        self.synapses[source_id].append(synapse)
        
        self.conn.execute('''
            INSERT INTO synapses (source_id, target_id, synapse_type, weight, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (source_id, target_id, synapse_type.value, weight, now))
        self.conn.commit()
    
    def recall(self, query: str, depth: int = 1, max_results: int = 10) -> List[Dict]:
        """扩散激活回忆"""
        # 1. 找到与查询相关的起始神经元
        query_entities = self._extract_entities(query)
        
        activated: Dict[str, float] = {}  # neuron_id -> activation_level
        
        # 初始激活
        for neuron_id, neuron in self.neurons.items():
            neuron_entities = self._extract_entities(neuron.content)
            
            # 实体重叠
            overlap = len(query_entities & neuron_entities)
            if overlap > 0:
                strength = neuron.get_strength()
                activated[neuron_id] = overlap * 0.3 + strength * 0.7
        
        # 关键词匹配
        query_lower = query.lower()
        for neuron_id, neuron in self.neurons.items():
            if any(kw in neuron.content.lower() for kw in query_lower.split()):
                activated[neuron_id] = activated.get(neuron_id, 0) + 0.3
        
        # 2. 扩散激活
        for _ in range(depth):
            new_activated = activated.copy()
            
            for neuron_id, activation in activated.items():
                # 沿着突触扩散
                for synapse in self.synapses.get(neuron_id, []):
                    target_id = synapse.target_id
                    
                    # 扩散激活 = 源激活 * 突触权重 * 衰减因子
                    spread = activation * synapse.weight * 0.7
                    
                    if target_id in new_activated:
                        new_activated[target_id] = max(new_activated[target_id], spread)
                    else:
                        new_activated[target_id] = spread
            
            activated = new_activated
        
        # 3. 按激活强度排序
        sorted_neurons = sorted(activated.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for neuron_id, activation in sorted_neurons[:max_results]:
            neuron = self.neurons.get(neuron_id)
            if neuron:
                # 更新访问计数（Hebbian 学习）
                neuron.access_count += 1
                neuron.last_accessed = datetime.now().isoformat()
                
                results.append({
                    'id': neuron_id,
                    'content': neuron.content,
                    'type': neuron.memory_type,
                    'activation': activation,
                    'strength': neuron.get_strength(),
                    'access_count': neuron.access_count
                })
        
        # 更新数据库
        for neuron_id, activation in sorted_neurons[:max_results]:
            self.conn.execute('''
                UPDATE neurons SET access_count = access_count + 1, last_accessed = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), neuron_id))
        self.conn.commit()
        
        return results
    
    def detect_contradictions(self) -> List[Dict]:
        """检测矛盾记忆"""
        contradictions = []
        
        # 检查已标记的矛盾
        for neuron_id, synapses in self.synapses.items():
            for synapse in synapses:
                if synapse.synapse_type == SynapseType.CONTRADICTS:
                    contradictions.append({
                        'memory1': self.neurons.get(neuron_id, {}).content if neuron_id in self.neurons else '',
                        'memory2': self.neurons.get(synapse.target_id, {}).content if synapse.target_id in self.neurons else '',
                        'type': 'explicit'
                    })
        
        # 自动检测矛盾（简单的否定词检测）
        negation_patterns = ['不', '没有', '不是', '无法', '不能']
        
        for id1, n1 in self.neurons.items():
            for id2, n2 in self.neurons.items():
                if id1 >= id2:
                    continue
                
                # 检测相似但有一个包含否定
                similarity = self._text_similarity(n1.content, n2.content)
                if similarity > 0.6:
                    n1_neg = any(neg in n1.content for neg in negation_patterns)
                    n2_neg = any(neg in n2.content for neg in negation_patterns)
                    
                    if n1_neg != n2_neg:  # 一个有否定，一个没有
                        contradictions.append({
                            'memory1': n1.content,
                            'memory2': n2.content,
                            'type': 'auto_detected',
                            'confidence': similarity
                        })
        
        return contradictions
    
    def trace_causal_chain(self, query: str) -> List[Dict]:
        """追溯因果链"""
        # 找到起始记忆
        results = self.recall(query, depth=0, max_results=1)
        if not results:
            return []
        
        start_id = results[0]['id']
        chain = []
        visited = set()
        
        def trace_back(neuron_id: str, depth: int = 0):
            if neuron_id in visited or depth > 5:
                return
            visited.add(neuron_id)
            
            # 找 CAUSED_BY 关系
            for synapse in self.synapses.get(neuron_id, []):
                if synapse.synapse_type == SynapseType.CAUSED_BY:
                    target = self.neurons.get(synapse.target_id)
                    if target:
                        chain.append({
                            'content': target.content,
                            'relation': 'caused_by',
                            'depth': depth
                        })
                        trace_back(synapse.target_id, depth + 1)
        
        trace_back(start_id)
        return chain
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """文本相似度"""
        if not text1 or not text2:
            return 0.0
        words1 = set(text1.lower())
        words2 = set(text2.lower())
        return len(words1 & words2) / len(words1 | words2) if (words1 | words2) else 0
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            'total_neurons': len(self.neurons),
            'total_synapses': sum(len(s) for s in self.synapses.values()),
            'by_type': defaultdict(int, {n.memory_type: 0 for n in self.neurons.values()}),
            'avg_strength': sum(n.get_strength() for n in self.neurons.values()) / len(self.neurons) if self.neurons else 0
        }


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="神经记忆系统")
    parser.add_argument("--remember", help="存储记忆")
    parser.add_argument("--recall", help="回忆记忆")
    parser.add_argument("--depth", type=int, default=1, help="扩散深度")
    parser.add_argument("--contradictions", action="store_true", help="检测矛盾")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    
    args = parser.parse_args()
    
    graph = NeuralMemoryGraph()
    
    if args.remember:
        mem_id = graph.remember(args.remember)
        print(f"✅ 记忆已存储: {mem_id}")
    elif args.recall:
        results = graph.recall(args.recall, depth=args.depth)
        print(f"🔍 找到 {len(results)} 条相关记忆:\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['activation']:.2f}激活] {r['content'][:60]}...")
    elif args.contradictions:
        contradictions = graph.detect_contradictions()
        print(f"⚠️ 发现 {len(contradictions)} 组矛盾记忆")
        for c in contradictions:
            print(f"\n  记忆1: {c['memory1'][:50]}...")
            print(f"  记忆2: {c['memory2'][:50]}...")
    elif args.stats:
        stats = graph.get_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        stats = graph.get_stats()
        print(f"📊 神经记忆系统状态:")
        print(f"   神经元: {stats['total_neurons']}")
        print(f"   突触: {stats['total_synapses']}")
        print(f"   平均强度: {stats['avg_strength']:.2f}")


if __name__ == "__main__":
    main()