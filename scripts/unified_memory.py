#!/usr/bin/env python3
"""
统一记忆检索接口
整合所有记忆系统：
- 神经记忆图谱 (扩散激活)
- 分层系统 (HOT/WARM/COLD)
- 向量数据库 (Weaviate)
- 本地文件 (MEMORY.md)
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/memory-system"))

# 导入各模块
from scripts.neural_memory_v2 import NeuralMemoryGraph
from scripts.memory_tiering import MemoryTier
from scripts.time_range_query import TimeRangeMemoryQuery

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))

class UnifiedMemorySystem:
    """统一记忆系统"""
    
    def __init__(self):
        self.neural_graph = NeuralMemoryGraph()
        self.tier_system = MemoryTier()
        self.time_query = TimeRangeMemoryQuery(use_llm=True)
        
        # 记忆源优先级
        self.source_priority = {
            'hot': 1.0,      # 最高优先级
            'neural': 0.9,   # 神经记忆
            'warm': 0.7,     # 稳定配置
            'cold': 0.5,     # 历史归档
            'vector': 0.4    # 向量搜索
        }
    
    def remember(self, content: str, memory_type: str = "fact",
                 importance: float = 0.5, tags: List[str] = None) -> Dict:
        """存储记忆到所有系统"""
        results = {}
        
        # 1. 判断应该存储到哪一层
        tier = self.tier_system.classify_memory(content, memory_type)
        results['tier'] = tier
        
        # 2. 存储到神经图谱
        neuron_id = self.neural_graph.remember(content, memory_type, importance, tags)
        results['neuron_id'] = neuron_id
        
        # 3. 存储到分层系统
        if tier in ['hot', 'warm']:
            self.tier_system.add_to_tier(content, tier)
            results['tier_stored'] = tier
        
        return results
    
    def recall(self, query: str, depth: int = 2, max_results: int = 15) -> List[Dict]:
        """统一检索：整合所有记忆源"""
        all_memories = []
        seen_content = set()
        
        # 1. 从 HOT 记忆检索（最高优先级）
        hot_memories = self.tier_system.get_hot_memories()
        for mem in hot_memories:
            if any(kw in mem.lower() for kw in query.lower().split()):
                if mem not in seen_content:
                    all_memories.append({
                        'content': mem,
                        'source': 'hot',
                        'priority': self.source_priority['hot'],
                        'type': 'active_context'
                    })
                    seen_content.add(mem)
        
        # 2. 神经记忆扩散激活检索
        neural_results = self.neural_graph.recall(query, depth=depth, max_results=10)
        for r in neural_results:
            content = r['content']
            if content not in seen_content:
                all_memories.append({
                    'content': content,
                    'source': 'neural',
                    'priority': self.source_priority['neural'] * r['activation'],
                    'type': r['type'],
                    'activation': r['activation'],
                    'access_count': r.get('access_count', 0)
                })
                seen_content.add(content)
        
        # 3. 从 WARM 记忆检索
        warm_memories = self.tier_system.get_warm_memories()
        for mem in warm_memories:
            if any(kw in mem.lower() for kw in query.lower().split()):
                if mem not in seen_content:
                    all_memories.append({
                        'content': mem,
                        'source': 'warm',
                        'priority': self.source_priority['warm'],
                        'type': 'config'
                    })
                    seen_content.add(mem)
        
        # 4. 从 COLD 记忆检索
        cold_memories = self.tier_system.get_cold_memories()
        for mem in cold_memories:
            if any(kw in mem.lower() for kw in query.lower().split()):
                if mem not in seen_content:
                    all_memories.append({
                        'content': mem,
                        'source': 'cold',
                        'priority': self.source_priority['cold'],
                        'type': 'archive'
                    })
                    seen_content.add(mem)
        
        # 5. 按优先级排序
        all_memories.sort(key=lambda x: x['priority'], reverse=True)
        
        return all_memories[:max_results]
    
    def get_context(self) -> Dict:
        """获取当前上下文（会话开始时调用）"""
        return {
            'hot': self.tier_system.get_hot_memories(),
            'warm_summary': self.tier_system.get_warm_memories()[:10],
            'stats': {
                'neural_neurons': len(self.neural_graph.neurons),
                'neural_synapses': sum(len(s) for s in self.neural_graph.synapses.values()),
                'tier_stats': self.tier_system.get_tier_stats()
            }
        }
    
    def recall_by_time(self, time_expression: str, 
                       keywords: List[str] = None,
                       max_results: int = 20) -> Dict:
        """按时间范围查询记忆
        
        Args:
            time_expression: 时间表达式
                - "上个月" / "昨天" / "上周"
                - "最近7天" / "过去3天"
                - "2026-02-01~2026-02-28"
            keywords: 可选关键词过滤
            max_results: 最大返回数量
        
        Returns:
            {
                'time_range': '2026-02-01 ~ 2026-03-01',
                'memories': [...],
                'total_count': N
            }
        
        Example:
            >>> memory.recall_by_time("上个月")
            >>> memory.recall_by_time("昨天", keywords=["Docker"])
            >>> memory.recall_by_time("最近3天", keywords=["Weaviate"])
        """
        return self.time_query.query_by_time(time_expression, keywords, max_results)
    
    def recall_interactive(self, user_input: str) -> Dict:
        """智能查询：从自然语言中提取时间和关键词
        
        Example:
            >>> memory.recall_interactive("就像我上个月说的那样")
            >>> memory.recall_interactive("上周做的 Docker 配置")
            >>> memory.recall_interactive("昨天下午讨论的 Weaviate 问题")
        """
        return self.time_query.interactive_query(user_input)
    
    def detect_contradictions(self) -> List[Dict]:
        """检测记忆矛盾"""
        return self.neural_graph.detect_contradictions()
    
    def trace_causal_chain(self, query: str) -> List[Dict]:
        """追溯因果链"""
        return self.neural_graph.trace_causal_chain(query)
    
    def cleanup_after_task(self):
        """任务完成后清理"""
        self.tier_system.prune_hot()
    
    def reorganize_memories(self):
        """重组记忆层级"""
        self.tier_system.reorganize()
    
    def get_stats(self) -> Dict:
        """获取系统统计"""
        neural_stats = self.neural_graph.get_stats()
        tier_stats = self.tier_system.get_tier_stats()
        
        return {
            'neural': neural_stats,
            'tiers': tier_stats,
            'total_memories': (
                tier_stats['hot']['count'] + 
                tier_stats['warm']['count'] + 
                tier_stats['cold']['count'] +
                neural_stats['total_neurons']
            )
        }


# 全局实例
_unified_memory = None

def get_unified_memory():
    """获取统一记忆系统实例"""
    global _unified_memory
    if _unified_memory is None:
        _unified_memory = UnifiedMemorySystem()
    return _unified_memory


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="统一记忆系统")
    parser.add_argument("--remember", help="存储记忆")
    parser.add_argument("--recall", help="检索记忆")
    parser.add_argument("--by-time", "-t", help="按时间范围检索（上个月/昨天/最近7天）")
    parser.add_argument("--interactive", "-i", help="智能查询（自然语言输入）")
    parser.add_argument("--keywords", "-k", nargs='+', help="关键词过滤")
    parser.add_argument("--context", action="store_true", help="获取上下文")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    parser.add_argument("--contradictions", action="store_true", help="检测矛盾")
    parser.add_argument("--cleanup", action="store_true", help="任务后清理")
    parser.add_argument("--depth", type=int, default=2, help="扩散深度")
    
    args = parser.parse_args()
    
    memory = get_unified_memory()
    
    if args.remember:
        result = memory.remember(args.remember)
        print(f"✅ 记忆已存储")
        print(f"   层级: {result['tier']}")
        print(f"   神经元: {result['neuron_id'][:8]}...")
    
    elif args.by_time:
        result = memory.recall_by_time(args.by_time, args.keywords)
        
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"📅 时间范围: {result['time_range']}")
            print(f"📊 找到 {result['total_count']} 条记忆\n")
            
            for mem in result['daily_memories'][:10]:
                print(f"📄 [{mem['date']}] {mem['content'][:60]}...")
            
            for mem in result['neural_memories'][:10]:
                print(f"🧠 [{mem['date']}] {mem['content'][:60]}...")
    
    elif args.interactive:
        result = memory.recall_interactive(args.interactive)
        
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"📅 时间范围: {result['time_range']}")
            print(f"📊 找到 {result['total_count']} 条记忆\n")
            
            for mem in result['daily_memories'][:10]:
                print(f"📄 [{mem['date']}] {mem['content'][:60]}...")
            
            for mem in result['neural_memories'][:10]:
                print(f"🧠 [{mem['date']}] {mem['content'][:60]}...")
    
    elif args.recall:
        results = memory.recall(args.recall, depth=args.depth)
        print(f"🔍 找到 {len(results)} 条相关记忆:\n")
        for i, r in enumerate(results, 1):
            source_emoji = {'hot': '🔥', 'neural': '🧠', 'warm': '🌡️', 'cold': '❄️'}
            print(f"{i}. {source_emoji.get(r['source'], '📄')} [{r['priority']:.2f}] {r['content'][:60]}...")
    
    elif args.context:
        ctx = memory.get_context()
        print("📋 当前上下文:")
        print(f"\n🔥 HOT ({len(ctx['hot'])} 条):")
        for h in ctx['hot'][:5]:
            print(f"   - {h[:50]}...")
    
    elif args.stats:
        stats = memory.get_stats()
        print("📊 记忆系统统计:")
        print(f"\n🧠 神经记忆:")
        print(f"   神经元: {stats['neural']['total_neurons']}")
        print(f"   突触: {stats['neural']['total_synapses']}")
        print(f"\n📦 分层存储:")
        print(f"   🔥 HOT: {stats['tiers']['hot']['count']}")
        print(f"   🌡️ WARM: {stats['tiers']['warm']['count']}")
        print(f"   ❄️ COLD: {stats['tiers']['cold']['count']}")
        print(f"\n   总计: {stats['total_memories']} 条记忆")
    
    elif args.contradictions:
        contradictions = memory.detect_contradictions()
        print(f"⚠️ 发现 {len(contradictions)} 组矛盾记忆")
        for c in contradictions[:5]:
            print(f"\n  记忆1: {c['memory1'][:40]}...")
            print(f"  记忆2: {c['memory2'][:40]}...")
    
    elif args.cleanup:
        memory.cleanup_after_task()
        print("✅ 任务后清理完成")
    
    else:
        stats = memory.get_stats()
        print("🧠 统一记忆系统")
        print(f"   总记忆: {stats['total_memories']} 条")
        print(f"   神经元: {stats['neural']['total_neurons']}")
        print(f"   突触: {stats['neural']['total_synapses']}")


if __name__ == "__main__":
    main()