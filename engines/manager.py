from astrbot.api import logger

from .base import ChessEngine
from .pikafish import PikafishEngine
from .xqwlight import XqwlightEngine
from .elephantfish import ElephantfishEngine
from .random_engine import RandomEngine


class EngineManager:
    """引擎管理器 - 管理所有可用引擎"""

    def __init__(self, arena_base: str = "", token: str = ""):
        self._engines: dict[str, ChessEngine] = {}
        self._current_name: str = "xqwlight"
        self._arena_base = arena_base
        self._token = token

        self._init_engines()

    def _init_engines(self):
        self._engines["xqwlight"] = XqwlightEngine(self._arena_base, self._token)
        self._engines["pikafish"] = PikafishEngine()
        self._engines["elephantfish"] = ElephantfishEngine()
        self._engines["random"] = RandomEngine()

    def set_arena(self, arena_base: str, token: str = ""):
        self._arena_base = arena_base
        self._token = token
        if "xqwlight" in self._engines:
            self._engines["xqwlight"].set_arena(arena_base, token)

    def set_pikafish_path(self, path: str):
        if "pikafish" in self._engines:
            self._engines["pikafish"]._custom_path = path

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
        result = []
        for name, engine in self._engines.items():
            result.append({
                "name": name,
                "version": engine.get_version(),
                "installed": engine.is_installed(),
                "current": name == self._current_name,
            })
        return result

    def get_current_info(self) -> dict:
        engine = self.get_current()
        return {
            "name": engine.get_name(),
            "version": engine.get_version(),
            "installed": engine.is_installed(),
            "current": True,
        }
