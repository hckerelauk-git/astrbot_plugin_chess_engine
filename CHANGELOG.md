# 更新日志

## [1.14] - 2026-06-01

### 新增
- Pikafish 引擎支持 UCI 选项配置：Threads、Hash、Move Overhead、Ponder、MultiPV
- Pikafish 支持 movetime 模式（固定每步思考时间），设为 0 则用 depth 模式
- Pikafish 专用配置字段全部加 `pikafish_` 前缀，不影响其他引擎

### 优化
- Pikafish 改为存放在插件外持久目录，更新插件后无需重新安装
- 启动时自动把旧插件目录里的 Pikafish 文件迁移到新持久目录
- `_bin_dir()` 路径缓存，避免重复创建目录
- UCI 选项值自动校验范围，防止非法参数导致引擎异常
- `analyze()` 超时根据 movetime 动态计算，不再硬编码 120s
- 修复 `uninstall()` 删除后多余重建目录的问题
- MultiPV 上限修正为 500（与 Pikafish 实际一致）
- UCI 交互加入 `ucinewgame` 清除残局信息，避免干扰搜索
- UCI 交互加入 `isready` 同步，确保 setoption 生效后再搜索
- `engines/` 包同步支持 UCI 选项、movetime、手动选版本辅助方法、nnue 复制与 `pikafish-*` 二进制识别
- HTTP 接口兼容 chess_arena 的 `/analyze` 与 `/choose-move` 路径
- HTTP 请求兼容 `legal_moves` 和 `legalMoves` 字段，响应同时返回 `best_move` / `move`
- chess_arena 超时取消请求时会正确结束 Pikafish 子进程，避免残留进程
- Pikafish 调用改为真正的 UCI 交互流程：等待 `uciok` / `readyok` 后再继续，稳定性更高

## [1.0.2] - 2026-06-01

### 变更
- Pikafish 不再自动按平台选二进制，改为安装后手动选择具体系统版本
- 安装 Pikafish 后自动列出所有可选版本，用户直接用 `选择象棋引擎版本 <编号>` 选当前系统版本
- 重复执行 `安装象棋引擎 pikafish` 也可重新查看版本列表并重选
- 新增 `列出象棋引擎二进制` 命令，用于随时查看所有可选的 Pikafish 版本
- 新增 `选择象棋引擎版本 <编号>` 命令，用于按编号指定当前系统对应版本，选完自动切换到 pikafish
- 新增 `设置象棋引擎路径 <完整路径>` 命令，用于直接指定可执行文件

### 修复
- 解压后自动将 `pikafish.nnue` 权重文件复制到每个平台子目录，确保引擎能找到权重文件正常运行
- 之前安装的用户如遇 nnue 缺失，请卸载后重新安装：`卸载象棋引擎 pikafish` → `安装象棋引擎 pikafish`

### 文档
- README 补充 Pikafish 版本选择说明
- README 补充相关聊天命令说明
- metadata.yaml 的帮助信息同步更新

## [1.0.1] - 2026-06-01

### 修复
- **Linux Pikafish 权限问题**：解压后自动 `chmod +x` 添加执行权限，避免 `Permission denied`
- `_fix_nested_binary()` 中两处移动文件后都加上 `os.chmod(target, 0o755)`

### 文档
- README 增加 Linux 权限注意事项
- metadata.yaml 帮助信息增加 Linux 权限说明

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
