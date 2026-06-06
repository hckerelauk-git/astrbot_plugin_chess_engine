# astrbot_plugin_chess_engine

> AstrBot 象棋引擎插件 - 支持多种引擎安装和切换，提供对外接口供其他插件调用。

| 信息 | 内容 |
|------|------|
| **插件名** | astrbot_plugin_chess_engine |
| **版本** | 1.48 |
| **作者** | 九喵 |
| **许可证** | MIT License |
| **AstrBot 最低版本** | 4.10.0 |
| **依赖** | aiohttp >= 3.8, py7zr >= 0.22.0 |
| **仓库** | https://github.com/hckerelauk-git/astrbot_plugin_chess_engine |

> **Pikafish 版本选择注意**：解压后会保留多个系统版本，请使用 `列出象棋引擎二进制` 查看，再用 `选择象棋引擎版本 <编号>` 手动选当前系统对应版本，避免 Linux 误选到 macOS 版本。

> **更新保留说明**：Pikafish 现在默认存放到插件外的持久目录。更新插件代码后不会再因为覆盖插件目录而丢失引擎文件；旧版本如果已经装过，会在下次启动时自动迁移。

> **更新后重启说明**：如果更新了本插件的 Python 文件，请重启 AstrBot。仅重载插件可能仍使用旧模块缓存，尤其是 elephantfish 这类动态加载引擎。

---

## 功能

- 支持 4 种象棋引擎：xqwlight、pikafish、elephantfish、random
- 通过聊天命令安装/卸载/切换引擎
- Pikafish 支持自动下载预编译二进制，并允许手动选择具体系统版本
- 当前引擎异常时 HTTP 接口会回退随机合法走法，避免 chess_arena 棋局中断
- 主入口仅负责 AstrBot 命令与 HTTP 接口，引擎逻辑统一由 `engines/` 子包管理
- 提供简洁的对外接口供其他插件调用

---

## 安装

1. 将本仓库放到 AstrBot 的 `data/plugins/astrbot_plugin_chess_engine/` 目录
2. 安装依赖：`pip install aiohttp>=3.8`
3. 重启 AstrBot
4. 在 WebUI 插件配置页面选择引擎

---

## 支持的引擎

| 引擎 | 安装方式 | 说明 |
|------|---------|------|
| **xqwlight** | 无需安装（平台 API） | 默认引擎，调用楚河平台 API，零本地消耗 |
| **pikafish** | 下载预编译二进制 | 最强开源引擎，已兼容 chess_arena 的 H/E/G 棋子别名 FEN |
| **elephantfish** | GitHub 自动下载 | 124行纯Python中国象棋引擎，已兼容 chess_arena 的棋子别名 FEN 与红黑视角走法坐标 |
| **random** | 无需安装 | 随机走法，用于测试 |

> 如果只是测试 chess_arena 对接，建议先选 `random`。确认能走棋后，再切换到 `xqwlight`、`elephantfish` 或 `pikafish`。

---

## 聊天命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `安装象棋引擎 <名称>` | 下载安装指定引擎，Pikafish 安装后自动列出可选版本 | `安装象棋引擎 pikafish` |
| `卸载象棋引擎 <名称>` | 卸载指定引擎 | `卸载象棋引擎 pikafish` |
| `切换象棋引擎 <名称>` | 切换当前引擎 | `切换象棋引擎 pikafish` |
| `象棋引擎状态` | 查看当前引擎信息 | `象棋引擎状态` |
| `象棋引擎列表` | 列出所有支持的引擎 | `象棋引擎列表` |
| `列出象棋引擎二进制` | 列出 Pikafish 可选二进制 | `列出象棋引擎二进制` |
| `选择象棋引擎版本 <编号>` | 按编号选择具体二进制 | `选择象棋引擎版本 1` |
| `重装象棋引擎 <名称>` | 卸载后立刻重装引擎 | `重装象棋引擎 elephantfish` |
| `设置引擎选项 <引擎> <key> <value>` | 运行时调整任意引擎选项 | `设置引擎选项 pikafish movetime 12000` |
| `查看引擎选项 <引擎>` | 查看引擎当前生效选项 | `查看引擎选项 elephantfish` |

> 运行时设置会自动规范化别名。例如 `设置引擎选项 elephantfish maxdepth 10` 会保存为 `max_depth = 10`，`skilllevel` 会保存为 `skill_level`，`useopeningbook` 会保存为 `use_opening_book`。

> `random_seed` 为空时是真随机；填写后会按 FEN、depth 与合法走法数量生成可复现结果，不会所有局面固定同一步。

---

## 配置项

### engine_select

选择当前使用的象棋引擎。

| 属性 | 值 |
|------|-----|
| 类型 | string |
| 默认值 | xqwlight |
| 可选值 | xqwlight, pikafish, elephantfish, random |
| 说明 | xqwlight 平台 API 零消耗；pikafish 最强本地引擎；elephantfish 轻量 Python 引擎；random 随机走法 |

### engine_depth

引擎搜索深度。

| 属性 | 值 |
|------|-----|
| 类型 | int |
| 默认值 | 4 |
| 范围 | 1-10 |
| 说明 | 越大棋力越强但越慢。推荐 4-6 |

### pikafish_path

Pikafish 可执行文件路径。

| 属性 | 值 |
|------|-----|
| 类型 | string |
| 默认值 | 空 |
| 说明 | 留空则不自动选择，安装后请用 `选择象棋引擎版本 <编号>` 指定当前系统版本，或用 `设置象棋引擎路径 <完整路径>` 直接指定 |

### Pikafish UCI 选项（仅对 Pikafish 有效）

| 配置项 | 类型 | 默认值 | 范围 | 说明 |
|--------|------|--------|------|------|
| `pikafish_threads` | int | 2 | 1-1024 | 线程数，推荐等于 CPU 核心数 |
| `pikafish_hash` | int | 256 | 1-33554432 | 哈希内存 (MB)，推荐 128-512 |
| `pikafish_movetime` | int | 8000 | 0-60000 | 每步思考时间 (ms)，设 0 则用 `engine_depth` 控制 |
| `pikafish_multipv` | int | 1 | 1-500 | 多 PV 数，设 1 性能最佳 |
| `pikafish_ponder` | bool | false | - | 后台思考 |
| `pikafish_move_overhead` | int | 30 | 0-5000 | 补偿通信延迟 (ms) |

> **movetime vs depth**：`pikafish_movetime > 0` 时使用固定时间模式（`go movetime`），不受 chess_arena 传来的 `depth` 参数影响。设为 0 则切换为固定深度模式（`go depth`）。

### http_port

HTTP 引擎服务端口。

| 属性 | 值 |
|------|-----|
| 类型 | int |
| 默认值 | 0（禁用） |
| 范围 | 0-65535 |
| 说明 | 设为 0 禁用。启用后其他插件可通过 HTTP 调用本插件引擎。推荐 18080 |

---

## 兼容 chess_arena v3.1.0

本插件可与 [astrbot_plugin_chess_arena](https://github.com/zxx624/astrbot_plugin_chess_arena) v3.1.0 配合使用，为 chess_arena 提供自定义引擎能力。

### 配置步骤

1. **本插件配置**：设置 `http_port = 18080`，先选择 `random` 测试连通性
2. **状态检查**：发送 `象棋引擎状态`，确认显示 `HTTP 端点: http://127.0.0.1:18080/analyze`
3. **Pikafish 版本选择**：如果要使用 Pikafish，安装后先执行 `列出象棋引擎二进制`，再用 `选择象棋引擎版本 <编号>` 选当前系统版本

4. **chess_arena 配置**：
   - `engine_mode` 选择 `custom_http`
   - `custom_engine_http_url` 填 `http://127.0.0.1:18080/analyze`
   - 也兼容 `http://127.0.0.1:18080/choose-move`

### 故障回退

如果当前引擎分析失败，HTTP 接口会返回一个随机合法走法，并在响应中附带 `warning` 字段。这样 chess_arena 不会因为某个引擎异常而中断棋局。日志里看到 `回退随机走法` 时，说明对接仍然可用，但当前选择的引擎需要单独排查。

### 接口协议

**请求格式**（chess_arena POST 到本插件）：

```json
{
    "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w",
    "legal_moves": ["a0a1", "b2b3", "c4c5"],
    "side": "red",
    "depth": 4,
    "timeout_ms": 8000,
    "bot_name": "MyBot",
    "chess_style": "random"
}
```

**响应格式**（本插件返回给 chess_arena）：

```json
{
    "best_move": "h2e2",
    "move": "h2e2",
    "warning": "仅在当前引擎异常并回退时出现"
}
```

### HTTP 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/analyze` | POST | 分析局面，返回最佳走法 |
| `/health` | GET | 健康检查 |
| `/info` | GET | 引擎信息 |

---

## 对外接口

其他插件可通过以下接口调用本插件的引擎能力。

### 获取插件实例

```python
chess_engine = self.context.get_plugin("astrbot_plugin_chess_engine")
```

### analyze_position

分析局面，返回最佳走法。

```python
async def analyze_position(self, fen: str, legal_moves: list[str], depth: int = 4) -> str
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| fen | str | 是 | 局面的 FEN 字符串 |
| legal_moves | list[str] | 是 | 合法走法列表 |
| depth | int | 否 | 搜索深度，默认使用配置值 |

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

---

## 其他插件使用示例

### 示例 1：调用引擎分析

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
        
        # 提交走法到平台
        await self.submit_move(best_move)
        
        yield event.plain_result(f"走棋: {best_move}")
```

### 示例 2：获取引擎信息

```python
chess_engine = self.context.get_plugin("astrbot_plugin_chess_engine")

# 获取当前引擎信息
info = chess_engine.get_engine_info()
print(f"当前引擎: {info['name']}")
print(f"搜索深度: {info['depth']}")
print(f"已安装: {info['installed']}")

# 获取所有引擎状态
engines = chess_engine.list_engines()
for engine in engines:
    status = "已安装" if engine["installed"] else "未安装"
    current = " [当前]" if engine["current"] else ""
    print(f"  {engine['name']} - {status}{current}")
```

### 示例 3：获取详细结果

```python
chess_engine = self.context.get_plugin("astrbot_plugin_chess_engine")

result = await chess_engine.analyze_position_detail(
    fen="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w",
    legal_moves=["a0a1", "b2b3", "c4c5"],
    depth=8
)

print(f"最佳走法: {result.best_move}")
print(f"评分: {result.score}")
print(f"搜索深度: {result.depth}")
print(f"耗时: {result.time_ms}ms")
```

---

## 引擎基类

其他插件可继承 `ChessEngine` 基类实现自定义引擎：

```python
from engines.base import ChessEngine, EngineResult


class MyCustomEngine(ChessEngine):
    """自定义象棋引擎"""
    
    def get_name(self) -> str:
        """引擎名称"""
        return "my_engine"
    
    def get_version(self) -> str:
        """引擎版本"""
        return "1.0.0"
    
    def is_installed(self) -> bool:
        """检查引擎是否已安装"""
        return True
    
    async def install(self) -> bool:
        """安装引擎，返回是否成功"""
        return True
    
    async def uninstall(self) -> bool:
        """卸载引擎，返回是否成功"""
        return True
    
    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        """分析局面，从 legal_moves 中选择最佳走法"""
        # 实现你的引擎逻辑
        return EngineResult(best_move=legal_moves[0], depth=depth)
```

---

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
└── bin/                 # Pikafish 二进制存放（解压后保留多系统版本）
    └── .gitkeep
```

---

## 许可证

MIT License
