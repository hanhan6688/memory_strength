#!/usr/bin/env python3
"""
记忆学习模块
从交互中自动学习：用户偏好、行为模式、常用词汇
"""

import os
import json
import re
from datetime import datetime
from typing import List, Dict
from collections import Counter
from pathlib import Path

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
LEARNING_FILE = WORKSPACE / "memory" / "learned_patterns.json"


class MemoryLearner:
    def __init__(self):
        self.patterns = self._load_patterns()
        self.preference_patterns = [
            (r'我喜欢(.+)', 'preference', 0.9),
            (r'我偏好(.+)', 'preference', 0.9),
            (r'不要(.+)', 'avoid', 0.9),
            (r'记住(.+)', 'important', 1.0),
            (r'下次(.+)', 'instruction', 0.8),
        ]
    
    def _load_patterns(self) -> Dict:
        if LEARNING_FILE.exists():
            return json.loads(LEARNING_FILE.read_text(encoding='utf-8'))
        return {
            'preferences': [], 'avoidances': [], 'important_facts': [],
            'instructions': [], 'tools_used': Counter(), 'topics': Counter()
        }
    
    def _save_patterns(self):
        data = {}
        for k, v in self.patterns.items():
            data[k] = dict(v.most_common(100)) if isinstance(v, Counter) else v
        LEARNING_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEARNING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    
    def learn(self, message: str) -> List[Dict]:
        learned = []
        for pattern, ptype, importance in self.preference_patterns:
            matches = re.findall(pattern, message)
            for m in matches:
                learning = {'type': ptype, 'content': m.strip(), 'importance': importance,
                            'learned_at': datetime.now().isoformat()}
                self.patterns[ptype + 's' if ptype != 'important' else 'important_facts'].append(learning)
                learned.append(learning)
        
        # 提取技术话题
        tools = re.findall(r'\b(Docker|Python|Weaviate|Ollama|OpenClaw)\b', message, re.I)
        for t in tools:
            self.patterns['tools_used'][t] += 1
        
        if learned:
            self._save_patterns()
        return learned
    
    def get_profile(self) -> Dict:
        return {
            'preferences': self.patterns['preferences'][-10:],
            'avoidances': self.patterns['avoidances'][-5:],
            'tools': self.patterns['tools_used'].most_common(10)
        }
    
    def get_context(self) -> str:
        lines = []
        if self.patterns['preferences']:
            lines.append(f"偏好: {', '.join(p['content'] for p in self.patterns['preferences'][-5:])}")
        if self.patterns['avoidances']:
            lines.append(f"避免: {', '.join(a['content'] for a in self.patterns['avoidances'][-3:])}")
        return '\n'.join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--learn", help="从消息学习")
    args = parser.parse_args()
    
    learner = MemoryLearner()
    if args.learn:
        learned = learner.learn(args.learn)
        print(f"✅ 学习了 {len(learned)} 条")
    elif args.profile:
        print(json.dumps(learner.get_profile(), ensure_ascii=False, indent=2))