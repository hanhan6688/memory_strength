#!/usr/bin/env python3
"""
时间范围查询模块
支持自然语言时间表达式解析 + 时间范围记忆检索

示例：
- "上个月说的"
- "上周做的决策"
- "昨天下午的讨论"
- "3天前"
- "2026-02-01~2026-02-28"
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import subprocess

sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/memory-system"))

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
MEMORY_DIR = WORKSPACE / "memory"


class TimeExpressionParser:
    """时间表达式解析器"""
    
    def __init__(self, use_llm: bool = True, model: str = "qwen2.5:0.5b"):
        self.use_llm = use_llm
        self.model = model
        
        # 预定义规则（不依赖 LLM 的快速解析）
        self.rules = [
            # 今天/昨天/前天
            (r'今天', lambda m: self._get_day_range(0)),
            (r'昨天', lambda m: self._get_day_range(-1)),
            (r'前天', lambda m: self._get_day_range(-2)),
            (r'大前天', lambda m: self._get_day_range(-3)),
            
            # 本周/上周
            (r'本周', lambda m: self._get_week_range(0)),
            (r'这周', lambda m: self._get_week_range(0)),
            (r'上周', lambda m: self._get_week_range(-1)),
            (r'上上周', lambda m: self._get_week_range(-2)),
            
            # 本月/上个月
            (r'本月', lambda m: self._get_month_range(0)),
            (r'这个月', lambda m: self._get_month_range(0)),
            (r'上个月', lambda m: self._get_month_range(-1)),
            (r'上上个月', lambda m: self._get_month_range(-2)),
            
            # N天前/N周前/N月前
            (r'(\d+)天前', lambda m: self._get_day_range(-int(m.group(1)))),
            (r'(\d+)周前', lambda m: self._get_week_range(-int(m.group(1)))),
            (r'(\d+)个月前', lambda m: self._get_month_range(-int(m.group(1)))),
            (r'(\d+)年前', lambda m: self._get_year_range(-int(m.group(1)))),
            
            # 最近N天
            (r'最近(\d+)天', lambda m: self._get_recent_days(int(m.group(1)))),
            (r'过去(\d+)天', lambda m: self._get_recent_days(int(m.group(1)))),
            
            # 日期范围
            (r'(\d{4}-\d{2}-\d{2})\s*[至到~]\s*(\d{4}-\d{2}-\d{2})', 
             lambda m: self._parse_date_range(m.group(1), m.group(2))),
            
            # 单个日期
            (r'(\d{4}-\d{2}-\d{2})', lambda m: self._parse_single_date(m.group(1))),
        ]
    
    def _get_day_range(self, offset_days: int) -> Tuple[datetime, datetime]:
        """获取某一天的范围"""
        target = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset_days)
        return target, target + timedelta(days=1)
    
    def _get_week_range(self, offset_weeks: int) -> Tuple[datetime, datetime]:
        """获取某一周的范围（周一到周日）"""
        now = datetime.now()
        # 计算本周一
        monday = now - timedelta(days=now.weekday())
        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        # 加上偏移
        start = monday + timedelta(weeks=offset_weeks)
        end = start + timedelta(days=7)
        return start, end
    
    def _get_month_range(self, offset_months: int) -> Tuple[datetime, datetime]:
        """获取某个月的范围"""
        now = datetime.now()
        year = now.year
        month = now.month + offset_months
        
        # 处理跨年
        while month <= 0:
            year -= 1
            month += 12
        while month > 12:
            year += 1
            month -= 12
        
        start = datetime(year, month, 1)
        # 下个月第一天
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        
        return start, end
    
    def _get_year_range(self, offset_years: int) -> Tuple[datetime, datetime]:
        """获取某一年的范围"""
        year = datetime.now().year + offset_years
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        return start, end
    
    def _get_recent_days(self, days: int) -> Tuple[datetime, datetime]:
        """获取最近N天的范围"""
        end = datetime.now()
        start = end - timedelta(days=days)
        return start, end
    
    def _parse_date_range(self, start_str: str, end_str: str) -> Tuple[datetime, datetime]:
        """解析日期范围字符串"""
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)
        return start, end
    
    def _parse_single_date(self, date_str: str) -> Tuple[datetime, datetime]:
        """解析单个日期"""
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = start + timedelta(days=1)
        return start, end
    
    def parse(self, expression: str) -> Optional[Tuple[datetime, datetime]]:
        """解析时间表达式，返回 (start, end)"""
        expression = expression.strip()
        
        # 1. 尝试规则匹配
        for pattern, handler in self.rules:
            match = re.search(pattern, expression)
            if match:
                try:
                    return handler(match)
                except:
                    continue
        
        # 2. 规则匹配失败，尝试 LLM 解析
        if self.use_llm:
            return self._llm_parse(expression)
        
        return None
    
    def _llm_parse(self, expression: str) -> Optional[Tuple[datetime, datetime]]:
        """使用小模型解析复杂时间表达式"""
        now = datetime.now()
        
        prompt = f"""你是一个时间表达式解析器。当前时间是 {now.strftime("%Y-%m-%d %H:%M")}。

用户输入："{expression}"

请返回 JSON 格式：
{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}

注意：
- end 是结束日期（不包含当天）
- 只返回 JSON，不要其他内容

示例：
输入："上个月说的" → {{"start": "{(now.replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d')}", "end": "{now.replace(day=1).strftime('%Y-%m-%d')}"}}
"""
        
        try:
            result = subprocess.run(
                ['ollama', 'run', self.model, prompt],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = result.stdout.strip()
            
            # 提取 JSON
            json_match = re.search(r'\{[^}]+\}', output)
            if json_match:
                data = json.loads(json_match.group())
                start = datetime.strptime(data['start'], "%Y-%m-%d")
                end = datetime.strptime(data['end'], "%Y-%m-%d")
                return start, end
        except Exception as e:
            print(f"LLM 解析失败: {e}")
        
        return None
    
    def format_range(self, start: datetime, end: datetime) -> str:
        """格式化时间范围显示"""
        if (end - start).days == 1:
            return f"{start.strftime('%Y-%m-%d')}（{(datetime.now() - start).days}天前）"
        else:
            return f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"


class TimeRangeMemoryQuery:
    """时间范围记忆查询"""
    
    def __init__(self, use_llm: bool = True):
        self.time_parser = TimeExpressionParser(use_llm=use_llm)
        self.memory_dir = MEMORY_DIR
        
    def query_by_time(self, time_expression: str, 
                      keywords: List[str] = None,
                      max_results: int = 20) -> Dict:
        """按时间范围查询记忆
        
        Args:
            time_expression: 时间表达式，如 "上个月"、"昨天"、"最近7天"
            keywords: 可选的关键词过滤
            max_results: 最大返回数量
        
        Returns:
            {
                'time_range': (start, end),
                'memories': [...],
                'daily_files': [...],
                'neural_memories': [...]
            }
        """
        # 1. 解析时间表达式
        time_range = self.time_parser.parse(time_expression)
        
        if not time_range:
            return {
                'error': f'无法解析时间表达式: {time_expression}',
                'memories': []
            }
        
        start, end = time_range
        
        results = {
            'time_expression': time_expression,
            'time_range': self.time_parser.format_range(start, end),
            'start': start.isoformat(),
            'end': end.isoformat(),
            'daily_memories': [],
            'neural_memories': [],
            'total_count': 0
        }
        
        # 2. 查询每日记忆文件
        results['daily_memories'] = self._query_daily_files(start, end, keywords)
        
        # 3. 查询神经记忆图谱
        results['neural_memories'] = self._query_neural_graph(start, end, keywords)
        
        results['total_count'] = len(results['daily_memories']) + len(results['neural_memories'])
        
        return results
    
    def _query_daily_files(self, start: datetime, end: datetime, 
                           keywords: List[str] = None) -> List[Dict]:
        """查询每日记忆文件"""
        memories = []
        current = start
        
        while current < end:
            date_str = current.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            
            if file_path.exists():
                content = file_path.read_text(encoding='utf-8')
                
                # 关键词过滤
                if keywords:
                    if not any(kw.lower() in content.lower() for kw in keywords):
                        current += timedelta(days=1)
                        continue
                
                # 解析记忆条目
                entries = self._parse_markdown_entries(content, date_str)
                memories.extend(entries)
            
            current += timedelta(days=1)
        
        return memories
    
    def _parse_markdown_entries(self, content: str, date: str) -> List[Dict]:
        """解析 Markdown 文件中的记忆条目"""
        entries = []
        lines = content.split('\n')
        current_section = ""
        current_entry = ""
        
        for line in lines:
            # 标题作为分隔
            if line.startswith('## '):
                if current_entry.strip():
                    entries.append({
                        'date': date,
                        'section': current_section,
                        'content': current_entry.strip(),
                        'source': 'daily_file'
                    })
                current_section = line[3:].strip()
                current_entry = ""
            elif line.startswith('### '):
                if current_entry.strip():
                    entries.append({
                        'date': date,
                        'section': current_section,
                        'content': current_entry.strip(),
                        'source': 'daily_file'
                    })
                current_section = current_section + " > " + line[4:].strip()
                current_entry = ""
            elif line.startswith('- ') or line.startswith('* '):
                # 列表项作为独立记忆
                entries.append({
                    'date': date,
                    'section': current_section,
                    'content': line[2:].strip(),
                    'source': 'daily_file'
                })
            else:
                current_entry += line + "\n"
        
        # 最后一个条目
        if current_entry.strip():
            entries.append({
                'date': date,
                'section': current_section,
                'content': current_entry.strip(),
                'source': 'daily_file'
            })
        
        return entries
    
    def _query_neural_graph(self, start: datetime, end: datetime,
                            keywords: List[str] = None) -> List[Dict]:
        """查询神经记忆图谱中指定时间范围的记忆"""
        from scripts.neural_memory_v2 import NeuralMemoryGraph
        
        graph = NeuralMemoryGraph()
        memories = []
        
        for neuron_id, neuron in graph.neurons.items():
            # 解析创建时间
            if not neuron.created_at:
                continue
            
            try:
                created = datetime.fromisoformat(neuron.created_at.replace('Z', '+00:00'))
                if created.tzinfo:
                    created = created.replace(tzinfo=None)
            except:
                continue
            
            # 时间范围过滤
            if not (start <= created < end):
                continue
            
            # 关键词过滤
            if keywords:
                if not any(kw.lower() in neuron.content.lower() for kw in keywords):
                    continue
            
            memories.append({
                'date': created.strftime('%Y-%m-%d'),
                'time': created.strftime('%H:%M:%S'),
                'content': neuron.content,
                'type': neuron.memory_type,
                'importance': neuron.importance,
                'access_count': neuron.access_count,
                'source': 'neural_graph'
            })
        
        # 按重要性排序
        memories.sort(key=lambda x: x['importance'], reverse=True)
        
        return memories
    
    def interactive_query(self, user_input: str) -> Dict:
        """智能查询：从用户输入中提取时间表达式和关键词
        
        示例：
        "就像我上个月说的那样" -> 时间:上个月, 关键词:无
        "上周做的 Docker 配置" -> 时间:上周, 关键词:Docker
        """
        # 尝试提取时间表达式
        time_patterns = [
            r'(上个月|这个月|本月|上周|这周|本周|昨天|今天|前天|\d+天前|\d+周前|\d+个月前|最近\d+天)'
        ]
        
        time_expression = None
        keywords = []
        
        # 提取时间表达式
        for pattern in time_patterns:
            match = re.search(pattern, user_input)
            if match:
                time_expression = match.group(1)
                # 从原句中移除时间表达式，剩下的作为关键词
                remaining = re.sub(pattern, '', user_input)
                keywords = [w for w in remaining.split() if len(w) > 1 and w not in ['的', '了', '说', '做']]
                break
        
        if not time_expression:
            # 尝试 LLM 提取
            time_expression = self._extract_time_with_llm(user_input)
        
        if time_expression:
            return self.query_by_time(time_expression, keywords if keywords else None)
        
        return {
            'error': '无法从输入中提取时间表达式',
            'user_input': user_input,
            'memories': []
        }
    
    def _extract_time_with_llm(self, user_input: str) -> Optional[str]:
        """使用 LLM 从复杂句子中提取时间表达式"""
        prompt = f"""从以下句子中提取时间表达式，如果没有则返回 "无"。

句子："{user_input}"

只返回时间表达式（如：上个月、昨天、3天前），不要其他内容。
"""
        
        try:
            result = subprocess.run(
                ['ollama', 'run', self.model, prompt],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            output = result.stdout.strip()
            
            if output != "无" and len(output) < 20:
                return output
        except:
            pass
        
        return None


# CLI
def main():
    import argparse
    parser = argparse.ArgumentParser(description="时间范围记忆查询")
    parser.add_argument("--time", "-t", help="时间表达式（上个月、昨天、最近7天等）")
    parser.add_argument("--keywords", "-k", nargs='+', help="关键词过滤")
    parser.add_argument("--interactive", "-i", help="交互式查询（自然语言输入）")
    parser.add_argument("--parse", "-p", help="仅解析时间表达式")
    
    args = parser.parse_args()
    
    query = TimeRangeMemoryQuery(use_llm=True)
    
    if args.parse:
        result = query.time_parser.parse(args.parse)
        if result:
            start, end = result
            print(f"✅ 解析结果: {query.time_parser.format_range(start, end)}")
        else:
            print("❌ 无法解析")
    
    elif args.interactive:
        print(f"📝 查询: {args.interactive}\n")
        result = query.interactive_query(args.interactive)
        
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"📅 时间范围: {result['time_range']}")
            print(f"📊 找到 {result['total_count']} 条记忆\n")
            
            for mem in result['daily_memories'][:10]:
                print(f"📄 [{mem['date']}] {mem['content'][:60]}...")
            
            for mem in result['neural_memories'][:10]:
                print(f"🧠 [{mem['date']} {mem['time']}] {mem['content'][:60]}...")
    
    elif args.time:
        result = query.query_by_time(args.time, args.keywords)
        
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"📅 时间范围: {result['time_range']}")
            print(f"📊 找到 {result['total_count']} 条记忆\n")
            
            if result['daily_memories']:
                print("📄 每日记忆:")
                for mem in result['daily_memories'][:10]:
                    print(f"   [{mem['date']}] {mem['content'][:50]}...")
            
            if result['neural_memories']:
                print("\n🧠 神经记忆:")
                for mem in result['neural_memories'][:10]:
                    print(f"   [{mem['date']}] {mem['content'][:50]}...")
    
    else:
        # 演示
        print("🕐 时间范围查询演示\n")
        
        tests = ["上个月", "昨天", "最近3天", "上周"]
        for t in tests:
            result = query.time_parser.parse(t)
            if result:
                start, end = result
                print(f"  {t}: {query.time_parser.format_range(start, end)}")


if __name__ == "__main__":
    main()