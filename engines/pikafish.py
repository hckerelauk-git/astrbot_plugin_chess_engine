import asyncio
import os
import platform
import shutil
from pathlib import Path

from engines.base import ChessEngine, EngineResult
from engines.download import find_pikafish_binary, download_pikafish, get_pikafish_dir


class PikafishEngine(ChessEngine):
    """Pikafish 引擎 - 最强开源象棋引擎，基于 Stockfish"""

    def __init__(self, custom_path: str = "", uci_options: dict | None = None):
        self._custom_path = custom_path
        self._uci_options = uci_options or {}

    def set_custom_path(self, path: str):
        self._custom_path = path

    def set_uci_options(self, options: dict):
        self._uci_options = options

    def _get_binary_path(self) -> Path | None:
        if self._custom_path:
            p = Path(self._custom_path)
            if p.exists() and p.is_file():
                return p
        return find_pikafish_binary()

    def _build_setoption_lines(self) -> list[str]:
        lines = []
        opts = self._uci_options
        threads = max(1, min(1024, int(opts.get("threads", 2))))
        lines.append(f"setoption name Threads value {threads}")

        hash_mb = max(1, min(33554432, int(opts.get("hash", 256))))
        lines.append(f"setoption name Hash value {hash_mb}")

        overhead = max(0, min(5000, int(opts.get("move_overhead", 30))))
        lines.append(f"setoption name Move Overhead value {overhead}")

        ponder = bool(opts.get("ponder", False))
        lines.append(f"setoption name Ponder value {str(ponder).lower()}")

        multipv = max(1, min(500, int(opts.get("multipv", 1))))
        lines.append(f"setoption name MultiPV value {multipv}")

        return lines

    def get_name(self) -> str:
        return "pikafish"

    def get_version(self) -> str:
        binary = self._get_binary_path()
        if binary:
            return binary.name or "installed"
        return "not installed"

    def is_installed(self) -> bool:
        return self._get_binary_path() is not None

    async def install(self) -> bool:
        if self.is_installed():
            return True
        try:
            await download_pikafish()
            return self.is_installed()
        except Exception:
            return False

    async def uninstall(self) -> bool:
        try:
            shutil.rmtree(get_pikafish_dir(), ignore_errors=True)
            self._custom_path = ""
            return True
        except Exception:
            return False

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")

        binary = self._get_binary_path()
        if not binary:
            raise RuntimeError("Pikafish 未安装，请先运行: 安装象棋引擎 pikafish")

        try:
            return await self._run_engine(binary, fen, legal_moves, depth)
        except asyncio.TimeoutError:
            raise RuntimeError("Pikafish 分析超时")
        except Exception as e:
            raise RuntimeError(f"Pikafish 分析失败: {e}")

    async def _run_engine(
        self, binary: Path, fen: str, legal_moves: list[str], depth: int
    ) -> EngineResult:
        setoption_lines = self._build_setoption_lines()
        movetime = int(self._uci_options.get("movetime", 0))
        if movetime > 0:
            go_cmd = f"go movetime {movetime}"
            proc_timeout = (movetime / 1000) + 30
        else:
            go_cmd = f"go depth {depth}"
            proc_timeout = 120

        uci_commands = ["uci", "ucinewgame", "isready"] + setoption_lines + [
            "isready",
            f"position fen {fen}",
            go_cmd,
            "quit",
        ]
        input_data = "\n".join(uci_commands) + "\n"

        proc = await asyncio.create_subprocess_exec(
            str(binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=input_data.encode()),
                timeout=proc_timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
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
