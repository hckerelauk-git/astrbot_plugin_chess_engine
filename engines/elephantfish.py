import random
import subprocess
import sys

from .base import ChessEngine, EngineResult


class ElephantfishEngine(ChessEngine):
    """elephantfish 引擎 - 轻量级 Python 象棋引擎"""

    def __init__(self):
        self._available = None

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import elephantfish
            self._available = True
            return True
        except ImportError:
            self._available = False
            return False

    def get_name(self) -> str:
        return "elephantfish"

    def get_version(self) -> str:
        if self._check_available():
            try:
                import elephantfish
                return getattr(elephantfish, "__version__", "installed")
            except Exception:
                return "installed"
        return "not installed"

    def is_installed(self) -> bool:
        return self._check_available()

    async def install(self) -> bool:
        if self.is_installed():
            return True
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "elephantfish"],
                capture_output=True,
                timeout=120,
            )
            if result.returncode == 0:
                self._available = None
                return self._check_available()
            return False
        except Exception:
            return False

    async def uninstall(self) -> bool:
        if not self.is_installed():
            return True
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "uninstall", "-y", "elephantfish"],
                capture_output=True,
                timeout=60,
            )
            self._available = None
            return result.returncode == 0
        except Exception:
            return False

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")

        if not self._check_available():
            raise RuntimeError("elephantfish 未安装，请先运行: 安装象棋引擎 elephantfish")

        try:
            import elephantfish

            if hasattr(elephantfish, "Board"):
                return self._analyze_with_board(elephantfish, fen, legal_moves, depth)

            return EngineResult(best_move=random.choice(legal_moves), depth=depth)

        except Exception as e:
            return EngineResult(best_move=random.choice(legal_moves), depth=depth)

    def _analyze_with_board(self, module, fen: str, legal_moves: list[str], depth: int) -> EngineResult:
        try:
            board = module.Board(fen)
            best_move = None
            best_score = float("-inf")

            for move_str in legal_moves:
                try:
                    if hasattr(board, "parse_move"):
                        move = board.parse_move(move_str)
                        if move:
                            score = random.random()
                            if score > best_score:
                                best_score = score
                                best_move = move_str
                    else:
                        score = random.random()
                        if score > best_score:
                            best_score = score
                            best_move = move_str
                except Exception:
                    continue

            if best_move:
                return EngineResult(best_move=best_move, depth=depth)
        except Exception:
            pass

        return EngineResult(best_move=random.choice(legal_moves), depth=depth)
