#!/usr/bin/env python3
"""
Enhanced Memory - 统一入口
"""

import sys
import os

# 添加 scripts 目录到路径
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

from unified_memory import get_unified_memory, UnifiedMemorySystem

__all__ = ['get_unified_memory', 'UnifiedMemorySystem']

# 版本
__version__ = '1.0.0'