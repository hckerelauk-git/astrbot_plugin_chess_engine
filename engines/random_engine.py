import random

from engines.base import ChessEngine, EngineResult


class RandomEngine(ChessEngine):
    """随机引擎 - 从合法走法中随机选择，用于测试"""

    def get_name(self) -> str:
        return "random"

    def get_version(self) -> str:
        return "1.0.0"

    def is_installed(self) -> bool:
        return True

    async def install(self) -> bool:
        return True

    async def uninstall(self) -> bool:
        return True

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4, timeout_ms: int | None = None) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")
        move = random.choice(legal_moves)
        return EngineResult(best_move=move, depth=depth)
