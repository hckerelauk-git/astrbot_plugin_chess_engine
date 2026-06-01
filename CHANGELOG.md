# 更新日志

## [1.0.0] - 2026-06-01

### 新增
- 初始版本发布
- 支持 4 种象棋引擎：xqwlight、pikafish、elephantfish、random
- 引擎安装/卸载/切换功能，通过聊天命令管理
- Pikafish 引擎支持自动下载预编译二进制（GitHub Releases）
- HTTP 引擎服务端点，兼容 chess_arena v3.1.0 的 `custom_engine_http` 接口
  - `POST /analyze` - 分析局面返回最佳走法
  - `GET /health` - 健康检查
  - `GET /info` - 引擎信息
- 对外接口供其他插件调用：
  - `analyze_position()` - 分析局面
  - `analyze_position_detail()` - 分析局面（详细结果）
  - `get_engine_info()` - 获取当前引擎信息
  - `list_engines()` - 获取所有引擎状态
- 引擎基类 `ChessEngine`，其他插件可继承实现自定义引擎

### 聊天命令
- `安装象棋引擎 <名称>` - 下载安装指定引擎
- `卸载象棋引擎 <名称>` - 卸载指定引擎
- `切换象棋引擎 <名称>` - 切换当前引擎
- `象棋引擎状态` - 查看当前引擎信息
- `象棋引擎列表` - 列出所有支持的引擎

### 修复
- 修复 `main.py` 使用绝对导入导致的加载失败，改为相对导入
- 修复 `_conf_schema.json` 使用不支持的 `select` 类型，改为 `string` + `options`
- 修复 `_conf_schema.json` 使用不支持的 `number` 类型，改为 `int`
- 修复 `elephantfish` 引擎 API 兼容性问题
- 清理未使用的导入

### 已知限制
- Pikafish 下载依赖 GitHub API（可能受速率限制影响）
- elephantfish 的 `pip install` 需要 Python 环境和网络连接
- HTTP 引擎服务需要手动配置 `http_port` 启用