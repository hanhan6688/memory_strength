#!/usr/bin/env python3
"""
记忆后端优化模块
- 去重机制
- 质量评分
- 自动标签
- 搜索排序
- 关联推荐
"""

import os
import sys
import re
import json
from datetime import datetime, timedelta
from collections import Counter
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/memory-system"))
from api.memory_api import get_memory_system

class MemoryOptimizer:
    """记忆优化器"""
    
    def __init__(self):
        self.ms = get_memory_system()
        
        # 重要关键词权重
        self.importance_keywords = {
            'critical': ['重要', '关键', '必须', '紧急', '核心', '决定'],
            'high': ['完成', '成功', '解决', '配置', '安装', '部署'],
            'medium': ['学习', '发现', '理解', '知道', '尝试'],
            'low': ['可能', '也许', '大概', '应该']
        }
        
        # 自动标签规则
        self.tag_rules = {
            '技术工具': ['docker', 'weaviate', 'ollama', 'python', 'flask', 'openclaw', 'clawhub'],
            '配置': ['配置', '设置', '安装', '部署', '初始化'],
            '安全': ['密码', '密钥', '凭证', 'token', '安全'],
            '项目': ['项目', '系统', '模块', '功能', '开发'],
            '问题': ['错误', '失败', '问题', 'bug', '修复'],
            '学习': ['学到', '发现', '理解', '知道', '经验']
        }
    
    # ========== 1. 去重机制 ==========
    
    def find_duplicates(self, threshold: float = 0.85) -> List[Dict]:
        """查找重复记忆"""
        memories = self.ms.get_all_memories(500)
        duplicates = []
        checked = set()
        
        for i, mem1 in enumerate(memories):
            id1 = mem1.get('_additional', {}).get('id', str(i))
            if id1 in checked:
                continue
            
            content1 = mem1.get('content', '')
            similar = [mem1]
            
            for j, mem2 in enumerate(memories[i+1:], i+1):
                id2 = mem2.get('_additional', {}).get('id', str(j))
                if id2 in checked:
                    continue
                
                content2 = mem2.get('content', '')
                similarity = self._text_similarity(content1, content2)
                
                if similarity >= threshold:
                    similar.append(mem2)
                    checked.add(id2)
            
            if len(similar) > 1:
                duplicates.append({
                    'group': similar,
                    'count': len(similar),
                    'representative': similar[0]
                })
                checked.add(id1)
        
        return duplicates
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（Jaccard + 编辑距离混合）"""
        if not text1 or not text2:
            return 0.0
        
        # Jaccard 相似度
        words1 = set(text1.lower())
        words2 = set(text2.lower())
        jaccard = len(words1 & words2) / len(words1 | words2) if (words1 | words2) else 0
        
        # 长度相似度
        len_ratio = min(len(text1), len(text2)) / max(len(text1), len(text2))
        
        # 包含关系
        containment = 0
        if text1 in text2 or text2 in text1:
            containment = 0.3
        
        return jaccard * 0.5 + len_ratio * 0.3 + containment
    
    def deduplicate(self, dry_run: bool = True) -> Dict:
        """执行去重"""
        duplicates = self.find_duplicates()
        
        result = {
            'total_groups': len(duplicates),
            'total_duplicates': sum(d['count'] - 1 for d in duplicates),
            'removed': 0,
            'groups': []
        }
        
        for group in duplicates:
            # 保留最重要的记忆（importance 最高，或最新的）
            sorted_memories = sorted(
                group['group'],
                key=lambda m: (m.get('importance', 0), m.get('date', '')),
                reverse=True
            )
            
            keep = sorted_memories[0]
            to_remove = sorted_memories[1:]
            
            group_info = {
                'keep': keep.get('content', '')[:50],
                'remove_count': len(to_remove)
            }
            result['groups'].append(group_info)
            
            if not dry_run:
                for mem in to_remove:
                    mem_id = mem.get('_additional', {}).get('id')
                    if mem_id:
                        try:
                            self.ms.delete_memory(mem_id)
                            result['removed'] += 1
                        except:
                            pass
        
        return result
    
    # ========== 2. 质量评分 ==========
    
    def calculate_quality_score(self, memory: Dict) -> float:
        """计算记忆质量分数 (0-100)"""
        content = memory.get('content', '')
        score = 50  # 基础分
        
        # 内容长度评分 (10分)
        length = len(content)
        if 20 <= length <= 100:
            score += 10
        elif 100 < length <= 200:
            score += 8
        elif length > 200:
            score += 5
        
        # 关键词评分 (20分)
        content_lower = content.lower()
        for level, keywords in self.importance_keywords.items():
            for kw in keywords:
                if kw in content_lower:
                    if level == 'critical':
                        score += 20
                    elif level == 'high':
                        score += 15
                    elif level == 'medium':
                        score += 10
                    else:
                        score += 5
                    break
        
        # 信息密度评分 (10分)
        # 包含数字、路径、URL 等
        if re.search(r'\d+', content):
            score += 3
        if re.search(r'/[\w/]+', content):
            score += 3
        if re.search(r'http|@|:', content):
            score += 4
        
        # 时间新鲜度评分 (10分)
        date_str = memory.get('date', '')
        if date_str:
            try:
                mem_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                days_old = (datetime.now(mem_date.tzinfo) - mem_date).days
                if days_old <= 1:
                    score += 10
                elif days_old <= 7:
                    score += 7
                elif days_old <= 30:
                    score += 4
            except:
                pass
        
        return min(100, score)
    
    def update_quality_scores(self) -> Dict:
        """更新所有记忆的质量分数"""
        memories = self.ms.get_all_memories(500)
        updated = 0
        
        for mem in memories:
            score = self.calculate_quality_score(mem)
            mem_id = mem.get('_additional', {}).get('id')
            
            # 注意：Weaviate 需要删除重建来更新，这里只计算
            mem['_quality_score'] = score
            updated += 1
        
        return {
            'total': len(memories),
            'updated': updated
        }
    
    # ========== 3. 自动标签提取 ==========
    
    def extract_tags(self, content: str) -> List[str]:
        """从内容中提取标签"""
        tags = []
        content_lower = content.lower()
        
        for tag, keywords in self.tag_rules.items():
            for kw in keywords:
                if kw.lower() in content_lower:
                    tags.append(tag)
                    break
        
        # 提取技术名词
        tech_patterns = [
            r'(\w+(?:系统|模块|服务|工具))',
            r'([A-Z][a-z]+(?:[A-Z][a-z]+)+)',  # CamelCase
        ]
        
        for pattern in tech_patterns:
            matches = re.findall(pattern, content)
            tags.extend(matches[:2])
        
        return list(set(tags))[:5]
    
    # ========== 4. 搜索排序优化 ==========
    
    def enhanced_search(self, query: str, limit: int = 10) -> List[Dict]:
        """增强版搜索（向量 + 质量分数 + 时间衰减）"""
        # 向量搜索
        memories = self.ms.search_memories(query=query, limit=limit * 2)
        
        # 重排序
        for mem in memories:
            # 向量相似度
            vector_score = mem.get('_additional', {}).get('certainty', 0.5) * 50
            
            # 质量分数
            quality_score = self.calculate_quality_score(mem) * 0.3
            
            # 时间衰减
            date_str = mem.get('date', '')
            time_score = 0
            if date_str:
                try:
                    mem_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    days_old = (datetime.now(mem_date.tzinfo) - mem_date).days
                    time_score = max(0, 20 - days_old * 0.5)
                except:
                    pass
            
            # 综合分数
            mem['_combined_score'] = vector_score + quality_score + time_score
        
        # 按综合分数排序
        memories.sort(key=lambda m: m.get('_combined_score', 0), reverse=True)
        
        return memories[:limit]
    
    # ========== 5. 关联推荐 ==========
    
    def find_related(self, memory_id: str, limit: int = 5) -> List[Dict]:
        """查找相关记忆"""
        # 获取目标记忆
        memories = self.ms.get_all_memories(500)
        target = None
        
        for mem in memories:
            if mem.get('_additional', {}).get('id') == memory_id:
                target = mem
                break
        
        if not target:
            return []
        
        target_content = target.get('content', '')
        target_date = target.get('date', '')
        
        # 提取目标记忆的特征
        target_tags = set(self.extract_tags(target_content))
        target_entities = self._extract_entities(target_content)
        
        related = []
        for mem in memories:
            if mem.get('_additional', {}).get('id') == memory_id:
                continue
            
            score = 0
            content = mem.get('content', '')
            date = mem.get('date', '')
            
            # 标签重叠
            mem_tags = set(self.extract_tags(content))
            tag_overlap = len(target_tags & mem_tags)
            score += tag_overlap * 15
            
            # 实体重叠
            mem_entities = self._extract_entities(content)
            entity_overlap = len(target_entities & mem_entities)
            score += entity_overlap * 20
            
            # 时间接近
            if target_date and date:
                try:
                    d1 = datetime.fromisoformat(target_date.replace('Z', '+00:00'))
                    d2 = datetime.fromisoformat(date.replace('Z', '+00:00'))
                    days_diff = abs((d1 - d2).days)
                    if days_diff <= 1:
                        score += 10
                    elif days_diff <= 7:
                        score += 5
                except:
                    pass
            
            if score > 0:
                mem['_relation_score'] = score
                related.append(mem)
        
        # 按关联分数排序
        related.sort(key=lambda m: m.get('_relation_score', 0), reverse=True)
        return related[:limit]
    
    def _extract_entities(self, text: str) -> set:
        """提取实体"""
        entities = set()
        
        # 技术工具
        tools = re.findall(r'(OpenClaw|Weaviate|Ollama|Docker|ClawHub|飞书|Python|Flask)', text, re.IGNORECASE)
        entities.update(t.capitalize() for t in tools)
        
        # 项目名称
        projects = re.findall(r'(\w+(?:系统|模块|项目))', text)
        entities.update(projects)
        
        return entities
    
    # ========== 综合优化 ==========
    
    def optimize_all(self, dry_run: bool = True) -> Dict:
        """执行全部优化"""
        print("🔧 开始记忆优化...")
        
        # 1. 去重
        print("\n1️⃣ 检查重复记忆...")
        dedup_result = self.deduplicate(dry_run)
        print(f"   发现 {dedup_result['total_groups']} 组重复，共 {dedup_result['total_duplicates']} 条")
        
        # 2. 质量评分
        print("\n2️⃣ 计算质量分数...")
        quality_result = self.update_quality_scores()
        print(f"   已评估 {quality_result['total']} 条记忆")
        
        # 3. 统计
        print("\n3️⃣ 统计信息...")
        memories = self.ms.get_all_memories(500)
        stats = {
            'total': len(memories),
            'by_type': Counter(m.get('type', 'unknown') for m in memories),
            'avg_quality': sum(self.calculate_quality_score(m) for m in memories) / len(memories) if memories else 0
        }
        print(f"   总记忆: {stats['total']}")
        print(f"   平均质量: {stats['avg_quality']:.1f}")
        
        return {
            'dedup': dedup_result,
            'quality': quality_result,
            'stats': stats
        }


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="记忆优化")
    parser.add_argument("--dedup", action="store_true", help="执行去重")
    parser.add_argument("--quality", action="store_true", help="计算质量分数")
    parser.add_argument("--search", help="增强搜索")
    parser.add_argument("--related", help="查找相关记忆 (需要 memory_id)")
    parser.add_argument("--optimize", action="store_true", help="执行全部优化")
    parser.add_argument("--dry-run", action="store_true", help="预览模式")
    
    args = parser.parse_args()
    
    optimizer = MemoryOptimizer()
    
    if args.dedup:
        result = optimizer.deduplicate(dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.quality:
        result = optimizer.update_quality_scores()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.search:
        results = optimizer.enhanced_search(args.search)
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.get('_combined_score', 0):.1f}分] {r.get('content', '')[:50]}...")
    elif args.related:
        results = optimizer.find_related(args.related)
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.get('_relation_score', 0)}分] {r.get('content', '')[:50]}...")
    elif args.optimize:
        optimizer.optimize_all(dry_run=args.dry_run)
    else:
        optimizer.optimize_all(dry_run=True)


if __name__ == "__main__":
    main()