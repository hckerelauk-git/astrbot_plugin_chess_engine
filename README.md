# AstrBot 象棋引擎插件

AstrBot 象棋引擎插件 - 支持多种引擎自动安装和切换，提供对外接口供其他插件调用。

## 功能特性

- **多引擎支持**：xqwlight、Pikafish、elephantfish、random
- **一键安装**：聊天命令即可安装引擎
- **轻松切换**：随时切换不同引擎
- **对外接口**：其他插件可通过接口调用引擎能力

## 支持的引擎

| 引擎 | 安装方式 | 说明 |
|------|---------|------|
| **xqwlight** | 平台 API（无需安装） | 默认引擎，零本地消耗 |
| **pikafish** | 下载预编译二进制 | 最强开源引擎，基于 Stockfish |
| **elephantfish** | pip install | 轻量级 Python 引擎 |
| **random** | 无需安装 | 测试用 |

## 安装

1. 将本仓库放到 AstrBot 的 `data/plugins/astrbot_plugin_chess_engine/` 目录
2. 安装依赖：`pip install aiohttp>=3.8`
3. 重启 AstrBot

## 聊天命令

| 命令 | 说明 |
|------|------|
| `安装象棋引擎 <名称>` | 下载安装引擎 |
| `卸载象棋引擎 <名称>` | 卸载引擎 |
| `切换象棋引擎 <名称>` | 切换当前引擎 |
| `象棋引擎状态` | 查看当前引擎状态 |
| `象棋引擎列表` | 列出所有支持的引擎 |

## 对外接口

其他插件可通过以下接口调用本插件：

```python
# 获取插件实例
chess_engine = self.context.get_plugin("astrbot_plugin_chess_engine")

# 分析局面，返回最佳走法
best_move = await chess_engine.analyze_position(
    fen="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w",
    legal_moves=["a0a1", "b2b3", ...],
    depth=6
)

# 获取详细分析结果
result = await chess_engine.analyze_position_detail(fen, legal_moves, depth)
# result.best_move, result.score, result.depth, result.time_ms

# 获取当前引擎信息
info = chess_engine.get_engine_info()
# {"name": "pikafish", "version": "2026-01-02", "installed": True, "depth": 4}

# 列出所有引擎状态
engines = chess_engine.list_engines()
```

## 引擎基类

其他插件可继承 `ChessEngine` 基类实现自定义引擎：

```python
from engines.base import ChessEngine, EngineResult

class MyEngine(ChessEngine):
    def get_name(self) -> str:
        return "my_engine"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def is_installed(self) -> bool:
        return True
    
    async def install(self) -> bool:
        return True
    
    async def uninstall(self) -> bool:
        return True
    
    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        # 实现你的引擎逻辑
        return EngineResult(best_move=legal_moves[0], depth=depth)
```

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `engine_select` | select | xqwlight | 选择引擎 |
| `engine_depth` | number | 4 | 搜索深度（1-10） |
| `pikafish_path` | string | 空 | Pikafish 路径（留空自动检测） |

## 许可证

MIT License
