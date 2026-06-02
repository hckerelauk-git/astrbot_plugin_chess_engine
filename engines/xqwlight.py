import random
import aiohttp

from engines.base import ChessEngine, EngineResult


class XqwlightEngine(ChessEngine):
    """xqwlight 引擎 - 通过楚河平台 API 调用，零本地消耗"""

    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        arena_base: str = "http://101.43.22.174:8787",
        token: str = "",
        options: dict | None = None,
    ):
        self._arena_base = arena_base.rstrip("/")
        self._token = token
        self._options = options or {}

    def set_arena(self, arena_base: str, token: str = "") -> None:
        self._arena_base = arena_base.rstrip("/")
        self._token = token

    def set_options(self, options: dict) -> None:
        self._options = options or {}

    def get_options(self) -> dict:
        return dict(self._options)

    def get_name(self) -> str:
        return "xqwlight"

    def get_version(self) -> str:
        return "platform"

    def is_installed(self) -> bool:
        return True

    async def install(self) -> bool:
        return True

    async def uninstall(self) -> bool:
        return True

    def _timeout(self) -> float:
        try:
            value = float(self._options.get("timeout", self.DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            value = self.DEFAULT_TIMEOUT
        return max(1.0, min(120.0, value))

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4, timeout_ms: int | None = None) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")

        headers = {}
        if self._token:
            headers["X-Bot-Token"] = self._token
            headers["Authorization"] = f"Bearer {self._token}"

        payload = {"fen": fen, "depth": depth}

        timeout = self._timeout()
        if timeout_ms is not None:
            timeout = min(timeout, max(1.0, timeout_ms / 1000.0))

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._arena_base}/api/analyze",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"xqwlight 分析失败: HTTP {resp.status} {text[:200]}")
                data = await resp.json()

        best = str(data.get("best_move") or "").strip()
        if best and best in legal_moves:
            return EngineResult(best_move=best, depth=depth)

        return EngineResult(best_move=random.choice(legal_moves), depth=depth)
