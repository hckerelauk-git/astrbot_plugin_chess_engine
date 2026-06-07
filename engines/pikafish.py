import asyncio
import logging
import platform
import shutil
from pathlib import Path

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # noqa: BLE001 - 在包加载阶段 astrbot.api 可能尚未就绪
    logger = logging.getLogger("astrbot_plugin_chess_engine.pikafish")

from engines.base import ChessEngine, EngineResult
from engines.download import download_pikafish, get_pikafish_dir


_FEN_BOARD_TRANSLATION = str.maketrans({
    "H": "N",  # horse -> knight
    "h": "n",
    "E": "B",  # elephant -> bishop
    "e": "b",
    "G": "A",  # guard -> advisor
    "g": "a",
})

_FEN_SIDE_ALIASES = {
    "r": "w",
    "red": "w",
    "w": "w",
    "b": "b",
    "black": "b",
}


class PikafishEngine(ChessEngine):
    """Pikafish 引擎 - 最强开源象棋引擎，基于 Stockfish"""

    def __init__(self, custom_path: str = "", uci_options: dict | None = None):
        self._custom_path = custom_path
        self._uci_options = uci_options or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._proc_options_hash: int = 0
        self._proc_binary: Path | None = None
        self._lock = asyncio.Lock()

    @property
    def _options_hash(self) -> int:
        return hash(frozenset(self._uci_options.items()))

    def set_custom_path(self, path: str):
        self._custom_path = path

    def set_uci_options(self, options: dict):
        self._uci_options = options

    def set_options(self, options: dict) -> None:
        self.set_uci_options(options or {})

    def get_options(self) -> dict:
        return dict(self._uci_options)

    def list_binaries(self) -> list[Path]:
        bin_dir = get_pikafish_dir()
        candidates: list[Path] = []
        for f in bin_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() in {".7z", ".zip", ".txt", ".md", ".log", ".nnue"}:
                continue
            name = f.name.lower()
            if not name.startswith("pikafish"):
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
        ext = ".exe" if platform.system().lower() == "windows" else ""
        direct = get_pikafish_dir() / f"pikafish{ext}"
        if direct.exists() and direct.is_file():
            return direct
        return None

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

    def _normalize_fen(self, fen: str) -> str:
        parts = str(fen or "").strip().split()
        if not parts:
            return fen
        parts[0] = parts[0].translate(_FEN_BOARD_TRANSLATION)
        if len(parts) >= 2:
            parts[1] = _FEN_SIDE_ALIASES.get(parts[1].lower(), parts[1])
        return " ".join(parts)

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

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4, timeout_ms: int | None = None) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")

        binary = self._get_binary_path()
        if not binary:
            candidates = self.list_binaries()
            if candidates:
                lines = ["Pikafish 已解压，但还没选具体二进制。"]
                for i, item in enumerate(candidates, 1):
                    lines.append(f"{i}. {item.relative_to(get_pikafish_dir())}")
                lines.append("用 选择象棋引擎版本 <编号> 选当前系统对应的")
                raise RuntimeError("\n".join(lines))
            raise RuntimeError("Pikafish 未安装，请先运行: 安装象棋引擎 pikafish")

        fen = self._normalize_fen(fen)

        async with self._lock:
            try:
                return await self._run_engine(binary, fen, legal_moves, depth, timeout_ms)
            except asyncio.TimeoutError:
                raise RuntimeError("Pikafish 分析超时")
            except Exception as e:
                raise RuntimeError(f"Pikafish 分析失败: {e}")

    async def shutdown(self) -> None:
        async with self._lock:
            proc = self._proc
            self._proc = None
            self._proc_options_hash = 0
            self._proc_binary = None
            if proc is not None:
                await self._shutdown_proc(proc)

    async def _start_process(self, binary: Path) -> asyncio.subprocess.Process:
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        try:
            await self._write_line(proc, "uci")
            await self._wait_for_token(proc, "uciok", timeout=10)
            for line in self._build_setoption_lines():
                await self._write_line(proc, line)
            await self._write_line(proc, "isready")
            await self._wait_for_token(proc, "readyok", timeout=10)
        except Exception:
            try:
                proc.kill()
                await proc.communicate()
            except Exception:
                pass
            raise
        self._proc = proc
        self._proc_options_hash = self._options_hash
        self._proc_binary = binary
        return proc

    async def _ensure_process(self, binary: Path) -> asyncio.subprocess.Process:
        if self._proc is not None and self._proc.returncode is None:
            if self._proc_binary == binary and self._options_hash == self._proc_options_hash:
                return self._proc
            await self._shutdown_proc(self._proc)
            self._proc = None
            self._proc_binary = None
        return await self._start_process(binary)

    async def _run_engine(
        self, binary: Path, fen: str, legal_moves: list[str], depth: int, timeout_ms: int | None = None
    ) -> EngineResult:
        proc = await self._ensure_process(binary)
        configured_movetime = int(self._uci_options.get("movetime", 0))
        configured_overhead = int(self._uci_options.get("move_overhead", 30))
        effective_timeout_ms = max(1000, int(timeout_ms)) if timeout_ms is not None else None
        if configured_movetime > 0 or effective_timeout_ms is not None:
            if effective_timeout_ms is not None:
                reserve_ms = max(800, configured_overhead + 800)
                arena_movetime = max(200, effective_timeout_ms - reserve_ms)
            else:
                arena_movetime = configured_movetime
            if configured_movetime > 0:
                movetime = min(configured_movetime, arena_movetime)
            else:
                movetime = arena_movetime
            go_cmd = f"go movetime {movetime}"
            proc_timeout = max(2.0, (movetime / 1000) + 2.0)
        else:
            go_cmd = f"go depth {depth}"
            proc_timeout = 120.0

        best_move = ""

        try:
            assert proc.stdin is not None
            assert proc.stdout is not None
            await self._write_line(proc, "ucinewgame")
            await self._write_line(proc, "isready")
            await self._wait_for_token(proc, "readyok", timeout=10)
            await self._write_line(proc, f"position fen {fen}")
            await self._write_line(proc, go_cmd)
            best_move = await self._wait_for_bestmove(proc, legal_moves, timeout=proc_timeout)
        except asyncio.TimeoutError:
            await self._shutdown_proc(proc)
            self._proc = None
            self._proc_options_hash = 0
            self._proc_binary = None
            raise
        except asyncio.CancelledError:
            await self._shutdown_proc(proc)
            self._proc = None
            self._proc_options_hash = 0
            self._proc_binary = None
            raise
        except Exception:
            await self._shutdown_proc(proc)
            self._proc = None
            self._proc_options_hash = 0
            self._proc_binary = None
            raise

        return EngineResult(best_move=best_move, depth=depth)

    async def _shutdown_proc(self, proc: asyncio.subprocess.Process) -> None:
        try:
            if proc.returncode is None:
                try:
                    await self._write_line(proc, "quit")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=2)
                except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    proc.kill()
                    await proc.communicate()
        except ProcessLookupError:
            pass

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
                    logger.warning("[ChessEngine] Pikafish returned invalid bestmove: %s legal_moves=%s", text, legal_moves[:20])
                    break
            if fallback_move:
                logger.warning("[ChessEngine] Pikafish fallback to PV move: %s", fallback_move)
                return fallback_move
            logger.warning("[ChessEngine] Pikafish returned no valid move, fallback first legal move")
            return legal_moves[0]

        return await asyncio.wait_for(_reader(), timeout=timeout)
