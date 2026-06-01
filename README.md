# astrbot_plugin_chess_engine

> AstrBot 象棋引擎插件 - 支持多种引擎自动安装和切换，提供对外接口供其他插件调用。

| 信息 | 内容 |
|------|------|
| **插件名** | astrbot_plugin_chess_engine |
| **版本** | 1.0.0 |
| **作者** | 九喵 |
| **许可证** | MIT License |
| **AstrBot 最低版本** | 4.10.0 |
| **依赖** | aiohttp >= 3.8 |
| **仓库** | https://github.com/hckerelauk-git/astrbot_plugin_chess_engine |

## 功能

- 支持 4 种象棋引擎：xqwlight、pikafish、elephantfish、random
- 通过聊天命令安装/卸载/切换引擎
- Pikafish 支持自动下载预编译二进制
- 提供简洁的对外接口供其他插件调用

## 安装

1. 将本仓库放到 AstrBot 的 `data/plugins/astrbot_plugin_chess_engine/` 目录
2. 安装依赖：`pip install aiohttp>=3.8`
3. 重启 AstrBot

## 支持的引擎

| 引擎 | 安装方式 | 说明 |
|------|---------|------|
| xqwlight | 无需安装（平台 API） | 默认引擎，调用楚河平台 API，零本地消耗 |
| pikafish | 下载预编译二进制 | 最强开源引擎，基于 Stockfish |
| elephantfish | pip install | 轻量 Python 引擎 |
| random | 无需安装 | 随机走法，用于测试 |

## 聊天命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `安装象棋引擎 <名称>` | 下载安装指定引擎 | `安装象棋引擎 pikafish` |
| `卸载象棋引擎 <名称>` | 卸载指定引擎 | `卸载象棋引擎 pikafish` |
| `切换象棋引擎 <名称>` | 切换当前引擎 | `切换象棋引擎 pikafish` |
| `象棋引擎状态` | 查看当前引擎信息 | `象棋引擎状态` |
| `象棋引擎列表` | 列出所有支持的引擎 | `象棋引擎列表` |

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `engine_select` | select | xqwlight | 选择引擎 |
| `engine_depth` | number | 4 | 搜索深度（1-10） |
| `pikafish_path` | string | 空 | Pikafish 可执行文件路径（留空自动检测） |

## 对外接口

其他插件可通过以下接口调用本插件的引擎能力：

### 获取插件实例

```python
# 在其他插件中
chess_engine = self.context.get_plugin("astrbot_plugin_chess_engine")
```

### analyze_position

分析局面，返回最佳走法。

```python
async def analyze_position(self, fen: str, legal_moves: list[str], depth: int = 4) -> str
```

**参数：**
- `fen` (str): 局面的 FEN 字符串
- `legal_moves` (list[str]): 合法走法列表
- `depth` (int, 可选): 搜索深度，默认使用配置值

**返回：** str - 最佳走法

**示例：**

```python
best_move = await chess_engine.analyze_position(
    fen="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w",
    legal_moves=["a0a1", "b2b3", "c4c5"],
    depth=6
)
print(f"最佳走法: {best_move}")
```

### analyze_position_detail

分析局面，返回详细结果。

```python
async def analyze_position_detail(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult
```

**参数：** 同 `analyze_position`

**返回：** EngineResult 对象

```python
@dataclass
class EngineResult:
    best_move: str        # 最佳走法
    score: int | None     # 评分（可选）
    depth: int | None     # 实际搜索深度（可选）
    time_ms: int | None   # 耗时毫秒（可选）
```

**示例：**

```python
result = await chess_engine.analyze_position_detail(
    fen="...",
    legal_moves=["a0a1", "b2b3"],
    depth=6
)
print(f"最佳走法: {result.best_move}")
print(f"评分: {result.score}")
```

### get_engine_info

获取当前引擎信息。

```python
def get_engine_info(self) -> dict
```

**返回：**

```python
{
    "name": "pikafish",        # 引擎名称
    "version": "installed",    # 版本
    "installed": True,         # 是否已安装
    "current": True,           # 是否为当前引擎
    "depth": 4                 # 搜索深度
}
```

### list_engines

获取所有引擎状态。

```python
def list_engines(self) -> list[dict]
```

**返回：**

```python
[
    {"name": "xqwlight", "version": "platform", "installed": True, "current": True},
    {"name": "pikafish", "version": "not installed", "installed": False, "current": False},
    {"name": "elephantfish", "version": "not installed", "installed": False, "current": False},
    {"name": "random", "version": "1.0.0", "installed": True, "current": False},
]
```

## 其他插件使用示例

```python
from astrbot.api.star import Context, Star
from astrbot.api.event import AstrMessageEvent


class MyChessPlugin(Star):
    """象棋对战插件 - 使用象棋引擎插件"""
    
    async def on_your_turn(self, event: AstrMessageEvent, fen: str, legal_moves: list[str]):
        # 获取象棋引擎插件
        chess_engine = self.context.get_plugin("astrbot_plugin_chess_engine")
        
        if not chess_engine:
            yield event.plain_result("象棋引擎插件未加载")
            return
        
        # 调用引擎分析
        best_move = await chess_engine.analyze_position(
            fen=fen,
            legal_moves=legal_moves,
            depth=6
        )
        
        # 提交走法（这里只是示例，实际需要调用平台 API）
        await self.submit_move(best_move)
        
        yield event.plain_result(f"走棋: {best_move}")
```

## 引擎基类

其他插件可继承 `ChessEngine` 基类实现自定义引擎：

```python
from engines.base import ChessEngine, EngineResult


class MyCustomEngine(ChessEngine):
    """自定义象棋引擎"""
    
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

## 目录结构

```
astrbot_plugin_chess_engine/
├── main.py              # 主插件（暴露接口）
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # WebUI 配置项
├── requirements.txt     # Python 依赖
├── README.md            # 本文档
├── engines/
│   ├── __init__.py
│   ├── base.py          # 引擎基类（其他插件可继承）
│   ├── manager.py       # 引擎管理器
│   ├── pikafish.py      # Pikafish 引擎
│   ├── xqwlight.py      # xqwlight 引擎
│   ├── elephantfish.py  # elephantfish 引擎
│   ├── random_engine.py # 随机引擎
│   └── download.py      # Pikafish 下载工具
└── bin/                 # Pikafish 二进制存放（用户自行安装）
    └── .gitkeep
```

## 许可证

MIT License
