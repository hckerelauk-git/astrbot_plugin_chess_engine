import logging

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # noqa: BLE001 - 兼容子包加载阶段 astrbot.api 尚未就绪
    logger = logging.getLogger("astrbot_plugin_chess_engine.manager")

from engines.base import ChessEngine
from engines.elephantfish import ElephantfishEngine
from engines.pikafish import PikafishEngine
from engines.random_engine import RandomEngine
from engines.xqwlight import XqwlightEngine


class EngineManager:
    """引擎管理器 - 管理所有可用引擎，支持每个引擎独立功能库。"""

    def __init__(self, arena_base: str = "", token: str = "", engine_options: dict | None = None):
        self._engines: dict[str, ChessEngine] = {}
        self._current_name: str = "xqwlight"
        self._arena_base = arena_base
        self._token = token
        self._engine_options: dict[str, dict] = dict(engine_options or {})

        self._init_engines()

    def _init_engines(self) -> None:
        self._engines["xqwlight"] = XqwlightEngine(
            self._arena_base,
            self._token,
            options=self._engine_options.get("xqwlight", {}),
        )
        self._engines["pikafish"] = PikafishEngine(
            "",
            uci_options=self._engine_options.get("pikafish", {}),
        )
        self._engines["elephantfish"] = ElephantfishEngine(
            options=self._engine_options.get("elephantfish", {}),
        )
        self._engines["random"] = RandomEngine(
            options=self._engine_options.get("random", {}),
        )

    def set_arena(self, arena_base: str, token: str = "") -> None:
        self._arena_base = arena_base
        self._token = token
        engine = self._engines.get("xqwlight")
        if engine and hasattr(engine, "set_arena"):
            engine.set_arena(arena_base, token)

    def set_pikafish_path(self, path: str) -> None:
        engine = self._engines.get("pikafish")
        if engine and hasattr(engine, "set_custom_path"):
            engine.set_custom_path(path)

    def set_pikafish_uci_options(self, options: dict) -> None:
        engine = self._engines.get("pikafish")
        if engine and hasattr(engine, "set_uci_options"):
            engine.set_uci_options(options)
        self._engine_options.setdefault("pikafish", {}).update(options or {})

    def set_engine_options(self, name: str, options: dict) -> None:
        if not name or name not in self._engines:
            return
        self._engine_options.setdefault(name, {}).update(options or {})
        engine = self._engines.get(name)
        if engine is None:
            return
        if name == "pikafish" and hasattr(engine, "set_uci_options"):
            engine.set_uci_options(options or {})
        elif hasattr(engine, "set_options"):
            engine.set_options(options or {})

    def get_engine_options(self, name: str) -> dict:
        return dict(self._engine_options.get(name, {}))

    def list_pikafish_binaries(self) -> list[str]:
        engine = self._engines.get("pikafish")
        if not engine or not hasattr(engine, "list_binaries"):
            return []
        return [str(p) for p in engine.list_binaries()]

    def set_current(self, name: str) -> bool:
        if name in self._engines:
            self._current_name = name
            return True
        return False

    def get_current(self) -> ChessEngine:
        return self._engines.get(self._current_name, self._engines["random"])

    def get_engine(self, name: str) -> ChessEngine | None:
        return self._engines.get(name)

    def get_current_name(self) -> str:
        return self._current_name

    def list_all(self) -> list[dict]:
        result: list[dict] = []
        for name, engine in self._engines.items():
            result.append({
                "name": name,
                "version": engine.get_version(),
                "installed": engine.is_installed(),
                "current": name == self._current_name,
                "options": self._engine_options.get(name, {}),
            })
        return result

    def get_current_info(self) -> dict:
        engine = self.get_current()
        return {
            "name": engine.get_name(),
            "version": engine.get_version(),
            "installed": engine.is_installed(),
            "current": True,
            "options": self._engine_options.get(engine.get_name(), {}),
        }
