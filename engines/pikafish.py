import asyncio
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

    def list_binaries(self) -> list[Path]:
        bin_dir = get_pikafish_dir()
        candidates: list[Path] = []
        for f in bin_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() in {".7z", ".zip", ".txt", ".md", ".log", ".nnue"}:
                continue
            name = f.name.lower()
            if "pikafish" not in name and "pikafish" not in "".join(part.lower() for part in f.parts):
                continue
            candidates.append(f)
        candidates.sort(key=lambda p: len(p.relative_to(bin_dir).parts))
        return candidates

    def pick_binary(self, index: int) -> Path | None:
        candidates = self.list_binaries()
        if index < 1 or index > len(candidates):
            return None
        return candidates[index - 1]

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
        binaries = self.list_binaries()
        if binaries:
            return f"candidates:{len(binaries)}"
        return "not installed"

    def is_installed(self) -> bool:
        return bool(self.list_binaries())

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

        proc = await asyncio.create_subprocess_exec(
            str(binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            assert proc.stdin is not None
            assert proc.stdout is not None
            await self._write_line(proc, "uci")
            await self._wait_for_token(proc, "uciok", timeout=10)
            for line in setoption_lines:
                await self._write_line(proc, line)
            await self._write_line(proc, "isready")
            await self._wait_for_token(proc, "readyok", timeout=10)
            await self._write_line(proc, "ucinewgame")
            await self._write_line(proc, "isready")
            await self._wait_for_token(proc, "readyok", timeout=10)
            await self._write_line(proc, f"position fen {fen}")
            await self._write_line(proc, go_cmd)
            best_move = await self._wait_for_bestmove(proc, legal_moves, timeout=proc_timeout)
            await self._write_line(proc, "quit")
            await proc.communicate()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise
        except asyncio.CancelledError:
            proc.kill()
            await proc.communicate()
            raise

        return EngineResult(best_move=best_move, depth=depth)

    async def _write_line(self, proc: asyncio.subprocess.Process, line: str) -> None:
        assert proc.stdin is not None
        proc.stdin.write((line + "\n").encode("utf-8"))
        await proc.stdin.drain()

    async def _wait_for_token(self, proc: asyncio.subprocess.Process, token: str, timeout: float) -> None:
        assert proc.stdout is not None

        async def _reader() -> None:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    raise RuntimeError(f"Pikafish 未返回 {token}")
                if line.decode("utf-8", errors="replace").strip() == token:
                    return

        await asyncio.wait_for(_reader(), timeout=timeout)

    async def _wait_for_bestmove(self, proc: asyncio.subprocess.Process, legal_moves: list[str], timeout: float) -> str:
        assert proc.stdout is not None

        async def _reader() -> str:
            fallback_move = ""
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text.startswith("info") and " pv " in text and not fallback_move:
                    parts = text.split()
                    try:
                        pv_idx = parts.index("pv")
                        if pv_idx + 1 < len(parts) and parts[pv_idx + 1] in legal_moves:
                            fallback_move = parts[pv_idx + 1]
                    except ValueError:
                        pass
                if text.startswith("bestmove"):
                    parts = text.split()
                    if len(parts) >= 2 and parts[1] in legal_moves:
                        return parts[1]
                    break
            if fallback_move:
                return fallback_move
            return legal_moves[0]

        return await asyncio.wait_for(_reader(), timeout=timeout)
