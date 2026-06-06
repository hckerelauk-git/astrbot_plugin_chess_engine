import asyncio
import importlib
import logging
import shutil
import sys
import time
from pathlib import Path

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # noqa: BLE001 - 兼容子包加载阶段 astrbot.api 尚未就绪
    logger = logging.getLogger("astrbot_plugin_chess_engine.elephantfish")

from engines.base import ChessEngine, EngineResult
from engines.download import (
    ensure_elephantfish_repo,
    get_elephantfish_dir,
    get_elephantfish_module_path,
)


_ELEPHANTFISH_REPO = "bupticybee/elephantfish"
_ELEPHANTFISH_REPO_URL = f"https://github.com/{_ELEPHANTFISH_REPO}.git"


def _to_legal_moves_set(legal_moves) -> set[str]:
    return {str(m).strip().lower() for m in (legal_moves or []) if str(m).strip()}


class ElephantfishEngine(ChessEngine):
    """elephantfish 引擎 - 124行纯Python中国象棋引擎 (bupticybee/elephantfish)"""

    DEFAULT_THINK_TIME = 5.0
    MAX_THINK_TIME = 30.0
    DEFAULT_MAX_DEPTH = 6

    def __init__(self, options: dict | None = None):
        self._options = options or {}
        self._module = None
        self._last_install_state: bool = False

    def set_options(self, options: dict) -> None:
        self._options = options

    def get_options(self) -> dict:
        return dict(self._options)

    def _bin_dir(self) -> Path:
        return get_elephantfish_dir()

    def _module_path(self) -> Path:
        return get_elephantfish_module_path()

    def _load_module(self) -> None:
        if self._module is not None:
            sys.modules["elephantfish"] = self._module
            return
        path = self._module_path()
        if not path.exists():
            raise RuntimeError(
                f"elephantfish 模块不存在: {path}，请先运行 安装象棋引擎 elephantfish"
            )
        module_dir = str(path.parent)
        if module_dir in sys.path:
            sys.path.remove(module_dir)
        sys.path.insert(0, module_dir)
        stale = sys.modules.get("elephantfish")
        stale_file = getattr(stale, "__file__", "") if stale is not None else ""
        if stale is not None and Path(stale_file).resolve() != path.resolve():
            sys.modules.pop("elephantfish", None)
        module = importlib.import_module("elephantfish")
        self._module = module

    def get_name(self) -> str:
        return "elephantfish"

    def get_version(self) -> str:
        if self._module_path().exists():
            return "installed"
        return "not installed"

    def is_installed(self) -> bool:
        return self._module_path().exists()

    async def install(self) -> bool:
        try:
            await asyncio.to_thread(ensure_elephantfish_repo)
            return self.is_installed()
        except Exception as exc:
            logger.warning("[ChessEngine] elephantfish 安装失败: %s", exc)
            return False

    async def uninstall(self) -> bool:
        try:
            shutil.rmtree(self._bin_dir(), ignore_errors=True)
            self._module = None
            return True
        except Exception as exc:
            logger.warning("[ChessEngine] elephantfish 卸载失败: %s", exc)
            return False

    def _think_time_seconds(self) -> float:
        movetime_ms = int(self._options.get("movetime", int(self.DEFAULT_THINK_TIME * 1000)))
        if movetime_ms <= 0:
            movetime_ms = int(self.DEFAULT_THINK_TIME * 1000)
        seconds = movetime_ms / 1000.0
        return max(0.5, min(self.MAX_THINK_TIME, seconds))

    def _max_depth(self) -> int:
        return max(1, min(20, int(self._options.get("max_depth", self.DEFAULT_MAX_DEPTH))))

    def _skill_level(self) -> int:
        return max(1, min(10, int(self._options.get("skill_level", 5))))

    def _use_book(self) -> bool:
        return bool(self._options.get("use_opening_book", False))

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4, timeout_ms: int | None = None) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")
        if not self.is_installed():
            raise RuntimeError("elephantfish 未安装，请先运行: 安装象棋引擎 elephantfish")
        try:
            return await asyncio.to_thread(self._analyze_sync, fen, legal_moves, timeout_ms)
        except Exception as exc:
            raise RuntimeError(f"elephantfish 分析失败: {exc}")

    def _analyze_sync(self, fen: str, legal_moves: list[str], timeout_ms: int | None = None) -> EngineResult:
        self._load_module()
        tools_path = self._bin_dir() / "tools.py"
        if not tools_path.exists():
            raise RuntimeError(f"elephantfish tools.py 缺失: {tools_path}")
        module_dir = str(tools_path.parent)
        if module_dir in sys.path:
            sys.path.remove(module_dir)
        sys.path.insert(0, module_dir)
        if self._module is not None:
            sys.modules["elephantfish"] = self._module
        stale_tools = sys.modules.get("tools")
        stale_file = getattr(stale_tools, "__file__", "") if stale_tools is not None else ""
        if stale_tools is not None and Path(stale_file).resolve() != tools_path.resolve():
            sys.modules.pop("tools", None)
        tools = importlib.import_module("tools")

        think_seconds = self._think_time_seconds()
        if timeout_ms is not None:
            think_seconds = min(think_seconds, max(0.5, timeout_ms / 1000.0 - 0.5))
        max_depth = self._max_depth()
        legal_set = _to_legal_moves_set(legal_moves)

        start = time.perf_counter()
        try:
            pos = tools.parseFEN(fen)
        except Exception as exc:
            raise RuntimeError(f"elephantfish 解析 FEN 失败: {exc}")
        searcher = self._module.Searcher()
        history = (pos,)
        try:
            best_move, _score, reached_depth = tools.search(searcher, pos, think_seconds, history)
        except Exception as exc:
            raise RuntimeError(f"elephantfish 搜索失败: {exc}")
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        if not best_move:
            raise RuntimeError("elephantfish 未返回任何走法")

        try:
            uci = tools.mrender(pos, best_move)
        except Exception:
            uci = ""

        if uci and uci.lower() in legal_set:
            return EngineResult(best_move=uci.lower(), depth=reached_depth, time_ms=elapsed_ms)

        try:
            raw_a = self._module.render(best_move[0])
            raw_b = self._module.render(best_move[1])
            uci_raw = (raw_a + raw_b).lower()
        except Exception:
            uci_raw = ""

        if uci_raw and uci_raw in legal_set:
            return EngineResult(best_move=uci_raw, depth=reached_depth, time_ms=elapsed_ms)

        if reached_depth > max_depth:
            pass
        for candidate in (uci.lower(), uci_raw):
            if candidate and candidate in legal_set:
                return EngineResult(best_move=candidate, depth=reached_depth, time_ms=elapsed_ms)

        raise RuntimeError(
            f"elephantfish 返回的走法不在合法列表: {uci!r}/{uci_raw!r} legal_moves={list(legal_set)[:8]}"
        )
