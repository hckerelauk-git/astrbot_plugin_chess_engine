import asyncio
from pathlib import Path

from engines.base import ChessEngine, EngineResult
from engines.download import find_pikafish_binary, download_pikafish, get_pikafish_dir


class PikafishEngine(ChessEngine):
    """Pikafish 引擎 - 最强开源象棋引擎，基于 Stockfish"""

    def __init__(self, custom_path: str = ""):
        self._custom_path = custom_path

    def _get_binary_path(self) -> Path | None:
        if self._custom_path:
            p = Path(self._custom_path)
            if p.exists():
                return p
        return find_pikafish_binary()

    def get_name(self) -> str:
        return "pikafish"

    def get_version(self) -> str:
        binary = self._get_binary_path()
        if binary:
            return binary.parent.name or "installed"
        return "not installed"

    def is_installed(self) -> bool:
        return self._get_binary_path() is not None

    async def install(self) -> bool:
        if self.is_installed():
            return True
        try:
            await download_pikafish()
            return True
        except Exception:
            return False

    async def uninstall(self) -> bool:
        binary = self._get_binary_path()
        if binary and binary.exists():
            try:
                binary.unlink()
                return True
            except Exception:
                return False
        return True

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")

        binary = self._get_binary_path()
        if not binary:
            raise RuntimeError("Pikafish 未安装，请先运行: 安装象棋引擎 pikafish")

        try:
            result = await self._run_engine(binary, fen, legal_moves, depth)
            return result
        except asyncio.TimeoutError:
            raise RuntimeError("Pikafish 分析超时")
        except Exception as e:
            raise RuntimeError(f"Pikafish 分析失败: {e}")

    async def _run_engine(
        self, binary: Path, fen: str, legal_moves: list[str], depth: int
    ) -> EngineResult:
        uci_commands = [
            "uci",
            f"position fen {fen}",
            f"go depth {depth}",
        ]
        input_data = "\n".join(uci_commands) + "\nquit\n"

        proc = await asyncio.create_subprocess_exec(
            str(binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=input_data.encode()),
                timeout=300,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise

        output = stdout.decode("utf-8", errors="replace")
        best_move = self._parse_uci_output(output, legal_moves)

        if not best_move:
            best_move = legal_moves[0]

        return EngineResult(best_move=best_move, depth=depth)

    def _parse_uci_output(self, output: str, legal_moves: list[str]) -> str | None:
        for line in reversed(output.splitlines()):
            line = line.strip()
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) >= 2:
                    move = parts[1]
                    if move in legal_moves:
                        return move

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("info") and " pv " in line:
                parts = line.split()
                try:
                    pv_idx = parts.index("pv")
                    if pv_idx + 1 < len(parts):
                        move = parts[pv_idx + 1]
                        if move in legal_moves:
                            return move
                except ValueError:
                    pass

        return None
