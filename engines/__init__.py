"""象棋引擎子包。

此文件故意保持为空，避免子包加载时 eager import 各子模块。
当 AstrBot 加载插件时如果从子模块顶上 import 第三方包（例如 astrbot.api）失败，
eager import 会把整个 engines 包加载炸掉，进而报 No module named 'engines'。
这里把 eager import 拆掉，让调用方按需 import：
    from engines.pikafish import PikafishEngine
    from engines.elephantfish import ElephantfishEngine
    from engines.random_engine import RandomEngine
    from engines.xqwlight import XqwlightEngine
    from engines.manager import EngineManager
    from engines.base import ChessEngine, EngineResult
"""
