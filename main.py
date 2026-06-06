from __future__ import annotations

import asyncio
import random
import sys
import time
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from aiohttp import web

try:
    from astrbot.api import logger
except Exception:  # noqa: BLE001
    import logging

    logger = logging.getLogger("astrbot_plugin_chess_engine")

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from engines.base import EngineResult
from engines.manager import EngineManager


def _as_int(value: Any, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if min_value is not None:
        result = max(min_value, result)
    if max_value is not None:
        result = min(max_value, result)
    return result


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "是", "开"}:
        return True
    if text in {"0", "false", "no", "off", "否", "关"}:
        return False
    return default


def _as_optional_seed(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


class ChessEnginePlugin(Star):
    """AstrBot 象棋引擎插件。"""

    PROTOCOL_NAME = "xiangqi-engine-v1"

    ENGINE_OPTION_ALIASES = {
        "elephantfish": {
            "maxdepth": "max_depth",
            "max-depth": "max_depth",
            "skilllevel": "skill_level",
            "skill-level": "skill_level",
            "useopeningbook": "use_opening_book",
            "use-opening-book": "use_opening_book",
            "move_time": "movetime",
            "move-time": "movetime",
        },
        "pikafish": {
            "moveoverhead": "move_overhead",
            "move-overhead": "move_overhead",
            "move_time": "movetime",
            "move-time": "movetime",
        },
        "xqwlight": {
            "http_timeout": "timeout",
            "http-timeout": "timeout",
        },
    }

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._arena_base = str(self.config.get("arena_base") or "http://101.43.22.174:8787").rstrip("/")
        self._token = str(self.config.get("token") or "").strip()
        self._engine_depth = _as_int(self.config.get("engine_depth"), 4, 1, 20)
        self._engine_select = str(self.config.get("engine_select") or "xqwlight").strip().lower()
        self._pikafish_path = str(self.config.get("pikafish_path") or "").strip()
        self._http_port = _as_int(self.config.get("http_port"), 0, 0, 65535)

        engine_options = self._build_engine_options()
        self._manager = EngineManager(
            self._arena_base,
            self._token,
            self._pikafish_path,
            engine_options=engine_options,
        )
        if not self._manager.set_current(self._engine_select):
            logger.warning("[ChessEngine] 未知默认引擎 %s，已回退 xqwlight", self._engine_select)
            self._engine_select = "xqwlight"
            self._manager.set_current(self._engine_select)

        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._http_url = ""
        try:
            self._startup_task = asyncio.get_running_loop().create_task(self._startup())
        except RuntimeError:
            self._startup_task = None
            logger.warning("[ChessEngine] 当前没有运行中的事件循环，HTTP 服务不会自动启动")

    def _normalize_engine_option_key(self, engine_name: str, key: str) -> str:
        normalized = str(key).strip().lower().replace(" ", "_")
        aliases = self.ENGINE_OPTION_ALIASES.get(engine_name, {})
        return aliases.get(normalized, normalized)

    def _normalize_engine_options(self, engine_name: str, options: dict) -> dict:
        return {
            self._normalize_engine_option_key(engine_name, str(key)): value
            for key, value in dict(options or {}).items()
        }

    def _build_engine_options(self) -> dict[str, dict]:
        engine_options = {
            "pikafish": {
                "threads": _as_int(self.config.get("pikafish_threads"), 2, 1, 1024),
                "hash": _as_int(self.config.get("pikafish_hash"), 256, 1, 33554432),
                "movetime": _as_int(self.config.get("pikafish_movetime"), 8000, 0, 60000),
                "multipv": _as_int(self.config.get("pikafish_multipv"), 1, 1, 500),
                "ponder": _as_bool(self.config.get("pikafish_ponder"), False),
                "move_overhead": _as_int(self.config.get("pikafish_move_overhead"), 30, 0, 5000),
            },
            "xqwlight": {
                "timeout": _as_int(self.config.get("xqwlight_timeout"), 30, 1, 120),
            },
            "elephantfish": {
                "movetime": _as_int(self.config.get("elephantfish_movetime"), 5000, 500, 30000),
                "max_depth": _as_int(self.config.get("elephantfish_max_depth"), 6, 1, 20),
                "skill_level": _as_int(self.config.get("elephantfish_skill_level"), 5, 1, 10),
                "use_opening_book": _as_bool(self.config.get("elephantfish_use_opening_book"), False),
            },
            "random": {
                "seed": _as_optional_seed(self.config.get("random_seed")),
            },
        }
        runtime = self.config.get("engine_options_runtime") or {}
        if isinstance(runtime, dict):
            for name, options in runtime.items():
                if isinstance(options, dict):
                    engine_name = str(name).strip().lower()
                    engine_options.setdefault(engine_name, {}).update(
                        self._normalize_engine_options(engine_name, options)
                    )
        return engine_options

    def _save_config(self) -> None:
        save = getattr(self.config, "save_config", None)
        if callable(save):
            save()

    def _fallback_result(self, legal_moves: list[str], depth: int, started_at: float, warning: str) -> dict:
        move = random.choice(legal_moves)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.warning("[ChessEngine] 回退随机走法: %s", move)
        return {
            "protocol": self.PROTOCOL_NAME,
            "engine": "random-fallback",
            "engine_version": "1.0.0",
            "best_move": move,
            "move": move,
            "depth": depth,
            "score": None,
            "elapsed_ms": elapsed_ms,
            "warning": warning,
        }

    async def _startup(self) -> None:
        if self._http_port <= 0:
            return
        app = web.Application()
        app.router.add_post("/analyze", self._handle_analyze)
        app.router.add_post("/choose-move", self._handle_analyze)
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/info", self._handle_info)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._http_port)
        await self._site.start()
        self._http_url = f"http://127.0.0.1:{self._http_port}"
        logger.info("[ChessEngine] HTTP 引擎服务已启动: %s", self._http_url)

    async def _handle_analyze(self, request: web.Request) -> web.Response:
        started_at = time.perf_counter()
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        request_id = str(data.get("request_id") or "").strip() or None
        fen = str(data.get("fen") or "").strip()
        legal_moves = data.get("legal_moves") or data.get("legalMoves") or []
        legal_moves = [str(move).strip() for move in legal_moves if str(move).strip()]
        depth = _as_int(data.get("depth"), self._engine_depth, 1, 20)
        timeout_ms = _as_int(data.get("timeout_ms"), 8000, 500, 120000)
        if not fen:
            return web.json_response({"error": "missing fen"}, status=400)
        if not legal_moves:
            return web.json_response({"error": "missing legal_moves"}, status=400)
        try:
            engine_info = self._manager.get_current_info()
            logger.info(
                "[ChessEngine] analyze request request_id=%s engine=%s depth=%s timeout_ms=%s legal_moves=%s",
                request_id,
                engine_info.get("name"),
                depth,
                timeout_ms,
                len(legal_moves),
            )
            result = await asyncio.wait_for(
                self._manager.get_current().analyze(fen, legal_moves, depth, timeout_ms=timeout_ms),
                timeout=(timeout_ms / 1000) + 2,
            )
            if result.best_move not in legal_moves:
                raise RuntimeError(f"引擎返回非法走法: {result.best_move}")
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info("[ChessEngine] analyze result request_id=%s move=%s elapsed_ms=%s", request_id, result.best_move, elapsed_ms)
            return web.json_response({
                "protocol": self.PROTOCOL_NAME,
                "request_id": request_id,
                "engine": engine_info.get("name"),
                "engine_version": engine_info.get("version"),
                "best_move": result.best_move,
                "move": result.best_move,
                "depth": result.depth,
                "score": result.score,
                "elapsed_ms": elapsed_ms,
            })
        except Exception as exc:
            logger.warning("[ChessEngine] 分析失败: %s", exc)
            payload = self._fallback_result(legal_moves, depth, started_at, str(exc))
            payload["request_id"] = request_id
            return web.json_response(payload)

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "protocol": self.PROTOCOL_NAME})

    async def _handle_info(self, request: web.Request) -> web.Response:
        return web.json_response({"engine": self.get_engine_info(), "http_url": self._http_url})

    async def analyze_position(self, fen: str, legal_moves: list[str], depth: int | None = None) -> str:
        result = await self.analyze_position_detail(fen, legal_moves, depth)
        return result.best_move

    async def analyze_position_detail(self, fen: str, legal_moves: list[str], depth: int | None = None) -> EngineResult:
        use_depth = depth or self._engine_depth
        return await self._manager.get_current().analyze(fen, legal_moves, use_depth)

    def get_engine_info(self) -> dict:
        return {**self._manager.get_current_info(), "depth": self._engine_depth}

    def list_engines(self) -> list[dict]:
        return self._manager.list_all()

    @filter.command("安装象棋引擎")
    async def install_engine(self, event: AstrMessageEvent, engine_name: str = ""):
        engine_name = engine_name.strip().lower()
        if not engine_name:
            yield event.plain_result("用法：安装象棋引擎 <名称>\n支持：pikafish、elephantfish")
            return
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}\n支持：xqwlight、pikafish、elephantfish、random")
            return
        if engine.is_installed():
            if engine_name == "pikafish":
                yield event.plain_result(self._format_pikafish_bins(f"{engine_name} 已安装，可选版本:"))
            else:
                yield event.plain_result(f"{engine_name} 已安装")
            return
        yield event.plain_result(f"正在安装 {engine_name}，请稍候...")
        try:
            success = await asyncio.wait_for(engine.install(), timeout=300)
            if not success:
                yield event.plain_result(f"{engine_name} 安装失败")
                return
            if engine_name == "pikafish":
                yield event.plain_result(self._format_pikafish_bins(f"{engine_name} 安装成功，可选版本:"))
            else:
                yield event.plain_result(f"{engine_name} 安装成功")
        except asyncio.TimeoutError:
            yield event.plain_result(f"{engine_name} 安装超时")
        except Exception as exc:
            yield event.plain_result(f"{engine_name} 安装异常: {exc}")

    @filter.command("卸载象棋引擎")
    async def uninstall_engine(self, event: AstrMessageEvent, engine_name: str = ""):
        engine_name = engine_name.strip().lower()
        if not engine_name:
            yield event.plain_result("用法：卸载象棋引擎 <名称>")
            return
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}")
            return
        if not engine.is_installed():
            yield event.plain_result(f"{engine_name} 未安装")
            return
        try:
            success = await engine.uninstall()
            yield event.plain_result(f"{engine_name} 已卸载" if success else f"{engine_name} 卸载失败")
        except Exception as exc:
            yield event.plain_result(f"{engine_name} 卸载异常: {exc}")

    @filter.command("重装象棋引擎")
    async def reinstall_engine(self, event: AstrMessageEvent, engine_name: str = ""):
        engine_name = engine_name.strip().lower()
        if not engine_name:
            yield event.plain_result("用法：重装象棋引擎 <名称>")
            return
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}")
            return
        try:
            await engine.uninstall()
            success = await asyncio.wait_for(engine.install(), timeout=300)
            yield event.plain_result(f"{engine_name} 重装{'成功' if success else '失败'}")
        except Exception as exc:
            yield event.plain_result(f"{engine_name} 重装异常: {exc}")

    @filter.command("设置引擎选项")
    async def set_engine_option(self, event: AstrMessageEvent, rest: str = ""):
        parts = rest.split(None, 2)
        if len(parts) < 3:
            yield event.plain_result("用法：设置引擎选项 <引擎> <key> <value>")
            return
        engine_name = parts[0].strip().lower()
        key = self._normalize_engine_option_key(engine_name, parts[1])
        raw_value = parts[2]
        if not self._manager.get_engine(engine_name):
            yield event.plain_result(f"未知引擎: {engine_name}")
            return
        current = dict(self._manager.get_engine_options(engine_name))
        parsed = self._parse_option_value(current.get(key), raw_value)
        current[key] = parsed
        if not self._manager.set_engine_options(engine_name, current):
            yield event.plain_result(f"未知引擎: {engine_name}")
            return
        self.config.setdefault("engine_options_runtime", {})[engine_name] = current
        self._save_config()
        yield event.plain_result(f"{engine_name}.{key} = {parsed}（运行时生效，已记忆）")

    def _parse_option_value(self, current_value: Any, raw_value: str) -> Any:
        text = raw_value.strip()
        if isinstance(current_value, bool) or text.lower() in {"true", "false", "yes", "no", "on", "off"}:
            return _as_bool(text)
        if isinstance(current_value, int):
            return int(text)
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return text

    @filter.command("查看引擎选项")
    async def view_engine_options(self, event: AstrMessageEvent, engine_name: str = ""):
        engine_name = engine_name.strip().lower()
        if not engine_name:
            yield event.plain_result("用法：查看引擎选项 <引擎>")
            return
        if not self._manager.get_engine(engine_name):
            yield event.plain_result(f"未知引擎: {engine_name}")
            return
        options = self._manager.get_engine_options(engine_name)
        lines = [f"{engine_name} 当前选项:"]
        lines.extend(f"  {key} = {value}" for key, value in options.items())
        yield event.plain_result("\n".join(lines))

    @filter.command("设置象棋引擎路径")
    async def set_engine_path(self, event: AstrMessageEvent, path: str = ""):
        path = path.strip()
        if not path:
            yield event.plain_result("用法：设置象棋引擎路径 <完整路径>")
            return
        if not Path(path).exists():
            yield event.plain_result(f"路径不存在: {path}")
            return
        self._manager.set_pikafish_path(path)
        self._pikafish_path = path
        self.config["pikafish_path"] = path
        self._save_config()
        yield event.plain_result(f"已设置 pikafish 路径: {path}")

    def _format_pikafish_bins(self, header: str) -> str:
        bins = self._manager.list_pikafish_binaries()
        if not bins:
            return "还没找到 pikafish 二进制，请先安装象棋引擎 pikafish"
        lines = [header]
        for idx, item in enumerate(bins, 1):
            lines.append(f"{idx}. {item}")
        lines.append("用 选择象棋引擎版本 <编号> 选当前系统对应的")
        return "\n".join(lines)

    @filter.command("列出象棋引擎二进制")
    async def list_engine_bins(self, event: AstrMessageEvent):
        yield event.plain_result(self._format_pikafish_bins("可选的 pikafish 二进制:"))

    @filter.command("选择象棋引擎版本")
    async def choose_engine_bin(self, event: AstrMessageEvent, index: str = ""):
        try:
            idx = int(index.strip())
        except ValueError:
            yield event.plain_result("用法：选择象棋引擎版本 <编号>")
            return
        engine = self._manager.get_engine("pikafish")
        binary = engine.pick_binary(idx) if engine and hasattr(engine, "pick_binary") else None
        if not binary:
            yield event.plain_result("编号无效，请先用 列出象棋引擎二进制 查看")
            return
        engine.set_custom_path(str(binary))
        self._manager.set_pikafish_path(str(binary))
        self._manager.set_current("pikafish")
        self._pikafish_path = str(binary)
        self._engine_select = "pikafish"
        self.config["pikafish_path"] = str(binary)
        self.config["engine_select"] = "pikafish"
        self._save_config()
        yield event.plain_result(f"已选择: {binary}\n已切换到 pikafish 引擎")

    @filter.command("切换象棋引擎")
    async def switch_engine(self, event: AstrMessageEvent, engine_name: str = ""):
        engine_name = engine_name.strip().lower()
        if not engine_name:
            yield event.plain_result("用法：切换象棋引擎 <名称>")
            return
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}\n支持：xqwlight、pikafish、elephantfish、random")
            return
        if not engine.is_installed():
            yield event.plain_result(f"{engine_name} 未安装，请先运行: 安装象棋引擎 {engine_name}")
            return
        self._manager.set_current(engine_name)
        self._engine_select = engine_name
        self.config["engine_select"] = engine_name
        self._save_config()
        yield event.plain_result(f"已切换到引擎: {engine_name}")

    @filter.command("象棋引擎状态")
    async def engine_status(self, event: AstrMessageEvent):
        info = self.get_engine_info()
        lines = [
            f"当前引擎: {info['name']}",
            f"版本: {info['version']}",
            f"搜索深度: {info['depth']}",
            f"已安装: {'是' if info['installed'] else '否'}",
        ]
        options = self._manager.get_engine_options(info["name"])
        if options:
            lines.append("选项:")
            lines.extend(f"  {key} = {value}" for key, value in options.items())
        if self._http_url:
            lines.append(f"HTTP 端点: {self._http_url}/analyze")
            lines.append(f"chess_arena 配置: custom_engine_http_url = {self._http_url}/analyze")
        yield event.plain_result("\n".join(lines))

    @filter.command("象棋引擎列表")
    async def engine_list(self, event: AstrMessageEvent):
        lines = ["支持的引擎:"]
        for item in self.list_engines():
            status = "已安装" if item["installed"] else "未安装"
            current = " [当前]" if item["current"] else ""
            lines.append(f"  {item['name']} - {status}{current}")
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        if self._runner:
            await self._runner.cleanup()
        if self._startup_task and not self._startup_task.done():
            self._startup_task.cancel()
        logger.info("[ChessEngine] 插件已卸载")
