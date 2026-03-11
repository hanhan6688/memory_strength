#!/usr/bin/env python3
"""
记忆分层系统 (HOT/WARM/COLD)
借鉴 memory-tiering 的思想，按功能和使用频率分层

HOT: 当前会话上下文、活跃任务、临时凭证
WARM: 用户偏好、系统配置、常用信息
COLD: 历史归档、项目总结、经验教训
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter

sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/memory-system"))

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
MEMORY_DIR = WORKSPACE / "memory"
HOT_DIR = MEMORY_DIR / "hot"
WARM_DIR = MEMORY_DIR / "warm"
COLD_FILE = WORKSPACE / "MEMORY.md"

class MemoryTier:
    """记忆分层管理"""
    
    def __init__(self):
        self._ensure_dirs()
        
        # 分层规则
        self.tier_rules = {
            'hot': {
                'description': '当前会话上下文、活跃任务',
                'retention': '2-3 turns',
                'max_items': 20,
                'include': ['active_task', 'temp_credential', 'immediate_goal', 'current_decision']
            },
            'warm': {
                'description': '用户偏好、系统配置、常用信息',
                'retention': '长期',
                'max_items': 100,
                'include': ['user_preference', 'system_config', 'tool_inventory', 'recurring_interest']
            },
            'cold': {
                'description': '历史归档、项目总结、经验教训',
                'retention': '永久',
                'max_items': None,
                'include': ['project_summary', 'lesson_learned', 'milestone', 'archived_task']
            }
        }
    
    def _ensure_dirs(self):
        """确保目录存在"""
        HOT_DIR.mkdir(parents=True, exist_ok=True)
        WARM_DIR.mkdir(parents=True, exist_ok=True)
        
        # 创建默认文件
        if not (HOT_DIR / "HOT_MEMORY.md").exists():
            self._init_hot_memory()
        if not (WARM_DIR / "WARM_MEMORY.md").exists():
            self._init_warm_memory()
    
    def _init_hot_memory(self):
        """初始化 HOT 记忆"""
        content = """# 🔥 HOT Memory - 当前活跃上下文

_此文件存储当前会话的关键信息，在任务完成后清理_

## 🎯 当前任务
<!-- 活跃任务，完成后移除 -->

## 🔑 临时凭证
<!-- 短期有效的凭证，用完即删 -->

## 📋 即时决策
<!-- 近期做出的决策，影响后续行动 -->

## ⚠️ 待处理
<!-- 需要立即关注的事项 -->
"""
        (HOT_DIR / "HOT_MEMORY.md").write_text(content, encoding='utf-8')
    
    def _init_warm_memory(self):
        """初始化 WARM 记忆"""
        content = """# 🌡️ WARM Memory - 稳定配置与偏好

_此文件存储用户偏好、系统配置等稳定信息_

## 👤 用户偏好
<!-- 用户的习惯、偏好、风格 -->

## ⚙️ 系统配置
<!-- 系统设置、环境变量、工具路径 -->

## 🛠️ 工具清单
<!-- 已安装的工具、技能、插件 -->

## 📌 常用信息
<!-- 频繁使用的账号、地址、配置 -->
"""
        (WARM_DIR / "WARM_MEMORY.md").write_text(content, encoding='utf-8')
    
    def classify_memory(self, content: str, memory_type: str) -> str:
        """判断记忆应该属于哪一层"""
        content_lower = content.lower()
        
        # HOT 条件：临时、当前、活跃
        hot_indicators = ['当前', '现在', '正在进行', '待处理', '待办', '临时', '今天']
        if any(ind in content for ind in hot_indicators):
            return 'hot'
        
        # WARM 条件：偏好、配置、稳定
        warm_indicators = ['偏好', '配置', '设置', '习惯', '安装', '账号', '目录']
        if any(ind in content for ind in warm_indicators):
            return 'warm'
        
        # COLD 条件：历史、总结、完成
        cold_indicators = ['完成', '已解决', '历史', '总结', '经验', '教训']
        if any(ind in content for ind in cold_indicators):
            return 'cold'
        
        # 根据类型判断
        type_tier_map = {
            'temp_credential': 'hot',
            'active_task': 'hot',
            'current_decision': 'hot',
            'user_preference': 'warm',
            'system_config': 'warm',
            'tool_inventory': 'warm',
            'project_summary': 'cold',
            'lesson_learned': 'cold',
            'milestone': 'cold'
        }
        
        return type_tier_map.get(memory_type, 'warm')
    
    def add_to_tier(self, content: str, tier: str, section: str = None):
        """添加记忆到指定层"""
        tier_dir = {'hot': HOT_DIR, 'warm': WARM_DIR}[tier]
        tier_file = tier_dir / f"{tier.upper()}_MEMORY.md"
        
        existing = tier_file.read_text(encoding='utf-8')
        
        # 找到合适的章节
        if section:
            # 在指定章节下添加
            pattern = rf'(## {section}\n[^\n]*\n)'
            if re.search(pattern, existing):
                new_content = re.sub(
                    pattern,
                    rf'\1- {content}\n',
                    existing
                )
            else:
                new_content = existing + f"\n## {section}\n- {content}\n"
        else:
            # 添加到文件末尾
            new_content = existing + f"\n- {content}\n"
        
        tier_file.write_text(new_content, encoding='utf-8')
    
    def get_hot_memories(self) -> List[str]:
        """获取 HOT 记忆"""
        hot_file = HOT_DIR / "HOT_MEMORY.md"
        if not hot_file.exists():
            return []
        
        content = hot_file.read_text(encoding='utf-8')
        # 提取列表项
        items = re.findall(r'^[-*]\s+(.+)$', content, re.MULTILINE)
        return items
    
    def get_warm_memories(self) -> List[str]:
        """获取 WARM 记忆"""
        warm_file = WARM_DIR / "WARM_MEMORY.md"
        if not warm_file.exists():
            return []
        
        content = warm_file.read_text(encoding='utf-8')
        items = re.findall(r'^[-*]\s+(.+)$', content, re.MULTILINE)
        return items
    
    def get_cold_memories(self) -> List[str]:
        """获取 COLD 记忆（从 MEMORY.md）"""
        if not COLD_FILE.exists():
            return []
        
        content = COLD_FILE.read_text(encoding='utf-8')
        items = re.findall(r'^[-*]\s+(.+)$', content, re.MULTILINE)
        return items
    
    def promote_to_warm(self, content: str):
        """从 HOT 提升到 WARM"""
        # 从 HOT 删除
        self._remove_from_tier(content, 'hot')
        # 添加到 WARM
        self.add_to_tier(content, 'warm', '常用信息')
    
    def archive_to_cold(self, content: str, summary: str = None):
        """从 WARM 归档到 COLD"""
        # 从 WARM 删除
        self._remove_from_tier(content, 'warm')
        # 添加到 COLD（MEMORY.md）
        if summary:
            self._append_to_memory_md(summary)
    
    def _remove_from_tier(self, content: str, tier: str):
        """从指定层删除记忆"""
        tier_dir = {'hot': HOT_DIR, 'warm': WARM_DIR}[tier]
        tier_file = tier_dir / f"{tier.upper()}_MEMORY.md"
        
        if not tier_file.exists():
            return
        
        existing = tier_file.read_text(encoding='utf-8')
        # 删除匹配的行
        lines = existing.split('\n')
        new_lines = [l for l in lines if content not in l or not l.strip().startswith('-')]
        tier_file.write_text('\n'.join(new_lines), encoding='utf-8')
    
    def _append_to_memory_md(self, content: str):
        """追加到 MEMORY.md"""
        if COLD_FILE.exists():
            existing = COLD_FILE.read_text(encoding='utf-8')
            new_content = existing + f"\n- {content}\n"
            COLD_FILE.write_text(new_content, encoding='utf-8')
    
    def prune_hot(self):
        """清理 HOT 记忆（任务完成后）"""
        hot_file = HOT_DIR / "HOT_MEMORY.md"
        self._init_hot_memory()  # 重置为空模板
        print("✅ HOT 记忆已清理")
    
    def reorganize(self):
        """重新组织记忆层级"""
        print("🔄 重新组织记忆层级...")
        
        # 1. 审计 HOT - 将完成项移到 COLD
        hot_memories = self.get_hot_memories()
        completed = [m for m in hot_memories if '完成' in m or '已解决' in m]
        for item in completed:
            self.archive_to_cold(item)
        
        # 2. 审计 WARM - 将不再活跃的偏好保留
        
        # 3. 验证无信息丢失
        print(f"   HOT: {len(self.get_hot_memories())} 条")
        print(f"   WARM: {len(self.get_warm_memories())} 条")
        print(f"   COLD: {len(self.get_cold_memories())} 条")
        print("✅ 记忆层级重组完成")
    
    def get_tier_stats(self) -> Dict:
        """获取分层统计"""
        return {
            'hot': {
                'count': len(self.get_hot_memories()),
                'description': self.tier_rules['hot']['description']
            },
            'warm': {
                'count': len(self.get_warm_memories()),
                'description': self.tier_rules['warm']['description']
            },
            'cold': {
                'count': len(self.get_cold_memories()),
                'description': self.tier_rules['cold']['description']
            }
        }


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="记忆分层管理")
    parser.add_argument("--stats", action="store_true", help="显示分层统计")
    parser.add_argument("--reorganize", action="store_true", help="重新组织层级")
    parser.add_argument("--prune-hot", action="store_true", help="清理 HOT 记忆")
    parser.add_argument("--add", help="添加记忆")
    parser.add_argument("--tier", choices=['hot', 'warm', 'cold'], help="指定层级")
    
    args = parser.parse_args()
    
    tier = MemoryTier()
    
    if args.stats:
        stats = tier.get_tier_stats()
        print("📊 记忆分层统计:")
        for t, info in stats.items():
            emoji = {'hot': '🔥', 'warm': '🌡️', 'cold': '❄️'}[t]
            print(f"\n{emoji} {t.upper()}: {info['count']} 条")
            print(f"   {info['description']}")
    
    elif args.reorganize:
        tier.reorganize()
    
    elif args.prune_hot:
        tier.prune_hot()
    
    elif args.add:
        target_tier = args.tier or tier.classify_memory(args.add, 'context')
        tier.add_to_tier(args.add, target_tier)
        print(f"✅ 已添加到 {target_tier.upper()}")
    
    else:
        stats = tier.get_tier_stats()
        print("📊 记忆分层系统")
        print(f"   🔥 HOT: {stats['hot']['count']} 条")
        print(f"   🌡️ WARM: {stats['warm']['count']} 条")
        print(f"   ❄️ COLD: {stats['cold']['count']} 条")


if __name__ == "__main__":
    main()