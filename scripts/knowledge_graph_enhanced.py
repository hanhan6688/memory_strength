#!/usr/bin/env python3
"""
知识图谱增强模块
功能：
- 自动实体识别
- 关系抽取
- 图谱可视化
- 路径查询
"""

import os
import sys
import json
import re
import sqlite3
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import subprocess

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
DB_PATH = os.path.join(WORKSPACE, "memory-system", "knowledge_graph.db")


class EntityType(Enum):
    PERSON = "person"
    PROJECT = "project"
    TOOL = "tool"
    CONCEPT = "concept"
    LOCATION = "location"
    ORGANIZATION = "org"
    EVENT = "event"
    TECHNOLOGY = "tech"


class RelationType(Enum):
    IS_A = "is_a"
    PART_OF = "part_of"
    USES = "uses"
    DEPENDS_ON = "depends_on"
    CAUSES = "causes"
    BEFORE = "before"
    AFTER = "after"
    CREATED_BY = "created_by"
    RELATED_TO = "related_to"
    SIMILAR_TO = "similar_to"


@dataclass
class Entity:
    id: str
    name: str
    entity_type: EntityType
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    mention_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    
    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'type': self.entity_type.value,
            'description': self.description, 'aliases': self.aliases,
            'mention_count': self.mention_count
        }


@dataclass
class Relation:
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    weight: float = 1.0
    evidence: str = ""
    
    def to_dict(self):
        return {
            'id': self.id, 'source': self.source_id, 'target': self.target_id,
            'type': self.relation_type.value, 'weight': self.weight
        }


class KnowledgeGraph:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self.entity_by_name: Dict[str, str] = {}
        self.relations_by_entity: Dict[str, List[str]] = defaultdict(list)
        self.entity_patterns = self._build_patterns()
        self._init_db()
        self._load_from_db()
    
    def _build_patterns(self):
        return {
            EntityType.TOOL: [
                (r'\b(Python|JavaScript|Docker|Git|GitHub|Ollama|Weaviate|OpenClaw|ClawHub|Flask|Redis|MySQL)\b', 'tool'),
                (r'\b(飞书|Feishu|Discord|Telegram|Slack)\b', 'platform'),
            ],
            EntityType.PROJECT: [
                (r'(\w+(?:系统|模块|项目|服务))', 'project'),
            ],
            EntityType.TECHNOLOGY: [
                (r'\b(API|LLM|RAG|NLP|向量数据库|知识图谱)\b', 'tech'),
            ],
        }
    
    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY, name TEXT UNIQUE, entity_type TEXT,
                description TEXT, aliases TEXT, mention_count INTEGER,
                first_seen TEXT, last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY, source_id TEXT, target_id TEXT,
                relation_type TEXT, weight REAL, evidence TEXT
            );
        ''')
        self.conn.commit()
    
    def _load_from_db(self):
        for row in self.conn.execute('SELECT * FROM entities'):
            self.entities[row[0]] = Entity(
                id=row[0], name=row[1], entity_type=EntityType(row[2]),
                description=row[3] or "", aliases=json.loads(row[4]) if row[4] else [],
                mention_count=row[5] or 0, first_seen=row[6] or "", last_seen=row[7] or ""
            )
            self.entity_by_name[row[1].lower()] = row[0]
        
        for row in self.conn.execute('SELECT * FROM relations'):
            self.relations[row[0]] = Relation(
                id=row[0], source_id=row[1], target_id=row[2],
                relation_type=RelationType(row[3]), weight=row[4] or 1.0, evidence=row[5] or ""
            )
            self.relations_by_entity[row[1]].append(row[0])
            self.relations_by_entity[row[2]].append(row[0])
    
    def extract_entities(self, text: str) -> List[Tuple[str, EntityType]]:
        entities = []
        for entity_type, patterns in self.entity_patterns.items():
            for pattern, _ in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for m in matches:
                    if isinstance(m, tuple): m = m[0]
                    entities.append((m, entity_type))
        return entities
    
    def add_entity(self, name: str, entity_type: EntityType) -> Entity:
        import uuid
        name_lower = name.lower()
        
        if name_lower in self.entity_by_name:
            eid = self.entity_by_name[name_lower]
            self.entities[eid].mention_count += 1
            self.entities[eid].last_seen = datetime.now().isoformat()
            self.conn.execute('UPDATE entities SET mention_count=?, last_seen=? WHERE id=?',
                              (self.entities[eid].mention_count, self.entities[eid].last_seen, eid))
            self.conn.commit()
            return self.entities[eid]
        
        eid = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        entity = Entity(id=eid, name=name, entity_type=entity_type, mention_count=1,
                        first_seen=now, last_seen=now)
        self.entities[eid] = entity
        self.entity_by_name[name_lower] = eid
        
        self.conn.execute('INSERT INTO entities VALUES (?,?,?,?,?,?,?,?)',
                          (eid, name, entity_type.value, "", "[]", 1, now, now))
        self.conn.commit()
        return entity
    
    def add_relation(self, source: str, target: str, rtype: RelationType, evidence: str = ""):
        import uuid
        sid = self.entity_by_name.get(source.lower())
        tid = self.entity_by_name.get(target.lower())
        if not sid or not tid: return None
        
        rid = str(uuid.uuid4())[:8]
        rel = Relation(id=rid, source_id=sid, target_id=tid, relation_type=rtype, evidence=evidence)
        self.relations[rid] = rel
        self.relations_by_entity[sid].append(rid)
        self.relations_by_entity[tid].append(rid)
        
        self.conn.execute('INSERT INTO relations VALUES (?,?,?,?,?,?)',
                          (rid, sid, tid, rtype.value, 1.0, evidence))
        self.conn.commit()
        return rel
    
    def find_path(self, source: str, target: str, max_depth: int = 4) -> List[Dict]:
        from collections import deque
        sid = self.entity_by_name.get(source.lower())
        tid = self.entity_by_name.get(target.lower())
        if not sid or not tid: return []
        
        queue = deque([(sid, [sid])])
        visited = {sid}
        
        while queue:
            curr, path = queue.popleft()
            if len(path) > max_depth: continue
            
            for rid in self.relations_by_entity.get(curr, []):
                rel = self.relations[rid]
                next_id = rel.target_id if rel.source_id == curr else rel.source_id
                
                if next_id == tid:
                    return [{'entity': self.entities[e].to_dict(), 
                             'relation': self._find_rel(path[i], e) if i > 0 else None}
                            for i, e in enumerate(path + [next_id])]
                
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, path + [next_id]))
        return []
    
    def _find_rel(self, s1: str, s2: str) -> Optional[Dict]:
        for rid in self.relations_by_entity.get(s1, []):
            r = self.relations[rid]
            if r.target_id == s2 or r.source_id == s2:
                return r.to_dict()
        return None
    
    def get_stats(self) -> Dict:
        types = defaultdict(int)
        for e in self.entities.values():
            types[e.entity_type.value] += 1
        return {'entities': len(self.entities), 'relations': len(self.relations), 'types': dict(types)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="知识图谱")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--path", nargs=2)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    
    kg = KnowledgeGraph()
    
    if args.build:
        mem_dir = os.path.join(WORKSPACE, "memory")
        for f in os.listdir(mem_dir):
            if f.endswith('.md'):
                content = open(os.path.join(mem_dir, f), encoding='utf-8').read()
                entities = kg.extract_entities(content)
                ids = [kg.add_entity(n, t).id for n, t in entities]
                for i, id1 in enumerate(ids):
                    for id2 in ids[i+1:]:
                        kg.add_relation(kg.entities[id1].name, kg.entities[id2].name, RelationType.RELATED_TO)
        print(f"✅ {len(kg.entities)} entities, {len(kg.relations)} relations")
    
    elif args.path:
        path = kg.find_path(args.path[0], args.path[1])
        for step in path:
            e = step['entity']
            print(f"📍 {e['name']} ({e['type']})")
    
    elif args.stats:
        print(json.dumps(kg.get_stats(), indent=2))
    
    else:
        print(f"🧠 {len(kg.entities)} entities, {len(kg.relations)} relations")


if __name__ == "__main__":
    main()