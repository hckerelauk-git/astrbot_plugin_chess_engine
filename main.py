from __future__ import annotations

import asyncio

from aiohttp import web

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .engines import EngineManager
from .engines.base import EngineResult


class ChessEnginePlugin(Star):
    """象棋引擎插件 - 只管引擎，不管业务，提供对外接口供其他插件调用"""

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}

        self._arena_base = str(self.config.get("arena_base") or "http://101.43.22.174:8787").rstrip("/")
        self._token = str(self.config.get("token") or "").strip()
        self._engine_depth = int(self.config.get("engine_depth") or 4)
        self._engine_select = str(self.config.get("engine_select") or "xqwlight").strip()
        self._pikafish_path = str(self.config.get("pikafish_path") or "").strip()
        self._http_port = int(self.config.get("http_port") or 0)

        self._manager = EngineManager(self._arena_base, self._token)
        self._manager.set_current(self._engine_select)
        if self._pikafish_path:
            self._manager.set_pikafish_path(self._pikafish_path)

        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._http_url: str = ""

        if self._http_port > 0:
            asyncio.create_task(self._start_http_server())

        logger.info("[ChessEngine] 插件已加载，当前引擎: %s，深度: %d", self._engine_select, self._engine_depth)

    async def _start_http_server(self):
        """启动 HTTP 引擎服务端点"""
        app = web.Application()
        app.router.add_post("/analyze", self._handle_analyze)
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/info", self._handle_info)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._http_port)
        try:
            await self._site.start()
            self._http_url = f"http://127.0.0.1:{self._http_port}"
            logger.info("[ChessEngine] HTTP 引擎服务已启动: %s", self._http_url)
        except Exception as e:
            logger.error("[ChessEngine] HTTP 服务启动失败: %s", e)

    async def _handle_analyze(self, request: web.Request) -> web.Response:
        """处理分析请求 - 兼容 chess_arena v3.1.0 custom_engine_http 接口"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        fen = str(data.get("fen") or "").strip()
        legal_moves = data.get("legal_moves") or []
        depth = int(data.get("depth") or self._engine_depth)
        timeout_ms = int(data.get("timeout_ms") or 8000)

        if not fen or not legal_moves:
            return web.json_response({"error": "missing fen or legal_moves"}, status=400)

        try:
            engine = self._manager.get_current()
            result = await asyncio.wait_for(
                engine.analyze(fen, legal_moves, depth),
                timeout=timeout_ms / 1000,
            )
            return web.json_response({"best_move": result.best_move})
        except asyncio.TimeoutError:
            return web.json_response({"error": "engine timeout"}, status=504)
        except Exception as e:
            logger.warning("[ChessEngine] 分析失败: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_health(self, request: web.Request) -> web.Response:
        """健康检查"""
        return web.json_response({"status": "ok"})

    async def _handle_info(self, request: web.Request) -> web.Response:
        """引擎信息"""
        return web.json_response({
            "engine": self._manager.get_current_info(),
            "depth": self._engine_depth,
            "http_url": self._http_url,
        })

    async def analyze_position(self, fen: str, legal_moves: list[str], depth: int | None = None) -> str:
        """分析局面，返回最佳走法（其他插件调用此接口）"""
        use_depth = depth or self._engine_depth
        engine = self._manager.get_current()
        result = await engine.analyze(fen, legal_moves, use_depth)
        return result.best_move

    async def analyze_position_detail(self, fen: str, legal_moves: list[str], depth: int | None = None) -> EngineResult:
        """分析局面，返回详细结果（其他插件调用此接口）"""
        use_depth = depth or self._engine_depth
        engine = self._manager.get_current()
        return await engine.analyze(fen, legal_moves, use_depth)

    def get_engine_info(self) -> dict:
        """获取当前引擎信息（其他插件调用此接口）"""
        return {
            **self._manager.get_current_info(),
            "depth": self._engine_depth,
        }

    def list_engines(self) -> list[dict]:
        """获取所有引擎状态（其他插件调用此接口）"""
        return self._manager.list_all()

    @filter.command("安装象棋引擎")
    async def install_engine(self, event: AstrMessageEvent, engine_name: str):
        """安装指定的象棋引擎"""
        if not engine_name:
            yield event.plain_result("用法：安装象棋引擎 <名称>\n支持：pikafish、elephantfish")
            return

        engine_name = engine_name.strip().lower()
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}\n支持：xqwlight、pikafish、elephantfish、random")
            return

        if engine.is_installed():
            yield event.plain_result(f"{engine_name} 已安装")
            return

        yield event.plain_result(f"正在安装 {engine_name}，请稍候...")

        try:
            success = await asyncio.wait_for(engine.install(), timeout=300)
            if success:
                yield event.plain_result(f"{engine_name} 安装成功！")
            else:
                yield event.plain_result(f"{engine_name} 安装失败")
        except asyncio.TimeoutError:
            yield event.plain_result(f"{engine_name} 安装超时")
        except Exception as e:
            yield event.plain_result(f"{engine_name} 安装异常: {e}")

    @filter.command("卸载象棋引擎")
    async def uninstall_engine(self, event: AstrMessageEvent, engine_name: str):
        """卸载指定的象棋引擎"""
        if not engine_name:
            yield event.plain_result("用法：卸载象棋引擎 <名称>")
            return

        engine_name = engine_name.strip().lower()
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}")
            return

        if not engine.is_installed():
            yield event.plain_result(f"{engine_name} 未安装")
            return

        try:
            success = await engine.uninstall()
            if success:
                yield event.plain_result(f"{engine_name} 已卸载")
            else:
                yield event.plain_result(f"{engine_name} 卸载失败")
        except Exception as e:
            yield event.plain_result(f"{engine_name} 卸载异常: {e}")

    @filter.command("切换象棋引擎")
    async def switch_engine(self, event: AstrMessageEvent, engine_name: str):
        """切换当前使用的引擎"""
        if not engine_name:
            yield event.plain_result("用法：切换象棋引擎 <名称>")
            return

        engine_name = engine_name.strip().lower()
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

        yield event.plain_result(f"已切换到引擎: {engine_name}")

    @filter.command("象棋引擎状态")
    async def engine_status(self, event: AstrMessageEvent):
        """查看当前引擎状态"""
        info = self.get_engine_info()
        msg = (
            f"当前引擎: {info['name']}\n"
            f"版本: {info['version']}\n"
            f"搜索深度: {info['depth']}\n"
            f"已安装: {'是' if info['installed'] else '否'}"
        )
        if self._http_url:
            msg += f"\nHTTP 端点: {self._http_url}/analyze"
            msg += f"\nchess_arena 配置: custom_engine_http_url = {self._http_url}/analyze"
        yield event.plain_result(msg)

    @filter.command("象棋引擎列表")
    async def engine_list(self, event: AstrMessageEvent):
        """列出所有支持的引擎"""
        engines = self.list_engines()
        lines = ["支持的引擎:"]
        for e in engines:
            status = "✓ 已安装" if e["installed"] else "✗ 未安装"
            current = " [当前]" if e["current"] else ""
            lines.append(f"  {e['name']} - {status}{current}")
        lines.append("\n使用命令安装：安装象棋引擎 <名称>")
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        """插件卸载时清理"""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("[ChessEngine] 插件已卸载")
