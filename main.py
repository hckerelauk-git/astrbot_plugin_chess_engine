from __future__ import annotations

import asyncio
import os
import platform
import random
import shutil
import subprocess
import sys
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


@dataclass
class EngineResult:
    best_move: str
    score: int | None = None
    depth: int | None = None
    time_ms: int | None = None


class ChessEngine(ABC):
    @abstractmethod
    def get_name(self) -> str: ...

    @abstractmethod
    def get_version(self) -> str: ...

    @abstractmethod
    def is_installed(self) -> bool: ...

    @abstractmethod
    async def install(self) -> bool: ...

    @abstractmethod
    async def uninstall(self) -> bool: ...

    @abstractmethod
    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult: ...


class RandomEngine(ChessEngine):
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

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")
        return EngineResult(best_move=random.choice(legal_moves), depth=depth)


class XqwlightEngine(ChessEngine):
    def __init__(self, arena_base: str, token: str = ""):
        self._arena_base = arena_base.rstrip("/")
        self._token = token

    def set_arena(self, arena_base: str, token: str = ""):
        self._arena_base = arena_base.rstrip("/")
        self._token = token

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

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")
        headers = {}
        if self._token:
            headers["X-Bot-Token"] = self._token
            headers["Authorization"] = f"Bearer {self._token}"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._arena_base}/api/analyze",
                json={"fen": fen, "depth": depth},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"xqwlight 分析失败: HTTP {resp.status} {text[:200]}")
                data = await resp.json()
        best = str(data.get("best_move") or data.get("move") or "").strip()
        if best and best in legal_moves:
            return EngineResult(best_move=best, depth=depth)
        return EngineResult(best_move=random.choice(legal_moves), depth=depth)


class PikafishEngine(ChessEngine):
    PIKAFISH_REPO = "official-pikafish/Pikafish"

    def __init__(self, custom_path: str = ""):
        self._custom_path = custom_path.strip()

    def set_custom_path(self, path: str):
        self._custom_path = path.strip()

    def _bin_dir(self) -> Path:
        path = Path(__file__).resolve().parent / "bin" / "pikafish"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_binaries(self) -> list[Path]:
        """列出解压后所有可能的 Pikafish 二进制，由用户手动选择。"""
        bin_dir = self._bin_dir()
        candidates: list[Path] = []
        if not bin_dir.exists():
            return candidates
        for f in bin_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() in {".7z", ".zip", ".txt", ".md", ".log"}:
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

        direct = self._bin_dir() / ("pikafish.exe" if platform.system().lower() == "windows" else "pikafish")
        if direct.exists() and direct.is_file():
            return direct

        return None

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
            await self._download_and_extract()
            return self.is_installed()
        except Exception as exc:
            logger.warning("[ChessEngine] Pikafish 安装失败: %s", exc)
            return False

    async def uninstall(self) -> bool:
        try:
            shutil.rmtree(self._bin_dir(), ignore_errors=True)
            self._bin_dir()
            self._custom_path = ""
            return True
        except Exception:
            return False

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")
        binary = self._get_binary_path()
        if not binary:
            candidates = self.list_binaries()
            if candidates:
                lines = ["Pikafish 已解压，但还没选具体二进制。"]
                for i, item in enumerate(candidates, 1):
                    lines.append(f"{i}. {item.relative_to(self._bin_dir())}")
                lines.append("用 设置象棋引擎路径 <完整路径> 选择一个")
                raise RuntimeError("\n".join(lines))
            raise RuntimeError("Pikafish 未安装，请先运行: 安装象棋引擎 pikafish")
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=(f"uci\nposition fen {fen}\ngo depth {depth}\nquit\n").encode("utf-8")),
                timeout=60,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError("Pikafish 分析超时")
        output = stdout.decode("utf-8", errors="replace")
        for line in reversed(output.splitlines()):
            line = line.strip()
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) >= 2 and parts[1] in legal_moves:
                    return EngineResult(best_move=parts[1], depth=depth)
        return EngineResult(best_move=random.choice(legal_moves), depth=depth)

    async def _download_and_extract(self) -> None:
        release = await self._latest_release()
        url, name = self._asset_info(release)
        archive_path = self._bin_dir() / name
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"下载失败: HTTP {resp.status}")
                with open(archive_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
        suffix = archive_path.suffix.lower()
        if suffix == ".7z":
            await self._extract_7z(archive_path)
        elif suffix == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(self._bin_dir())
        else:
            raise RuntimeError(f"不支持的压缩格式: {suffix}")
        archive_path.unlink(missing_ok=True)
        if platform.system().lower() != "windows":
            for binary in self.list_binaries():
                os.chmod(str(binary), 0o755)

    async def _latest_release(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.github.com/repos/{self.PIKAFISH_REPO}/releases/latest") as resp:
                if resp.status != 200:
                    raise RuntimeError(f"获取版本信息失败: HTTP {resp.status}")
                return await resp.json()

    def _asset_info(self, release: dict) -> tuple[str, str]:
        assets = release.get("assets", [])
        if not assets:
            raise RuntimeError("发布页无可用下载包")
        asset = assets[0]
        return asset.get("browser_download_url", ""), asset.get("name", "Pikafish.7z")

    async def _extract_7z(self, archive_path: Path) -> None:
        try:
            import py7zr
        except ImportError as exc:
            raise RuntimeError("缺少 py7zr 依赖，无法解压 Pikafish 的 7z 包") from exc
        with py7zr.SevenZipFile(archive_path, mode="r") as zf:
            zf.extractall(path=self._bin_dir())
        # 不做自动整理，保留原始目录结构，交给用户手动选择


class ElephantfishEngine(ChessEngine):
    def __init__(self):
        self._available = None

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import elephantfish  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def get_name(self) -> str:
        return "elephantfish"

    def get_version(self) -> str:
        return "installed" if self._check_available() else "not installed"

    def is_installed(self) -> bool:
        return self._check_available()

    async def install(self) -> bool:
        if self.is_installed():
            return True
        result = subprocess.run([sys.executable, "-m", "pip", "install", "elephantfish"], capture_output=True, timeout=120)
        self._available = None
        return result.returncode == 0 and self._check_available()

    async def uninstall(self) -> bool:
        if not self.is_installed():
            return True
        result = subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "elephantfish"], capture_output=True, timeout=60)
        self._available = None
        return result.returncode == 0

    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4) -> EngineResult:
        if not legal_moves:
            raise RuntimeError("无合法走法可选")
        return EngineResult(best_move=random.choice(legal_moves), depth=depth)


class EngineManager:
    def __init__(self, arena_base: str = "", token: str = "", pikafish_path: str = ""):
        self._engines: dict[str, ChessEngine] = {
            "xqwlight": XqwlightEngine(arena_base, token),
            "pikafish": PikafishEngine(pikafish_path),
            "elephantfish": ElephantfishEngine(),
            "random": RandomEngine(),
        }
        self._current_name = "xqwlight"

    def set_arena(self, arena_base: str, token: str = ""):
        self._engines["xqwlight"].set_arena(arena_base, token)

    def set_pikafish_path(self, path: str):
        self._engines["pikafish"]._custom_path = path

    def list_pikafish_binaries(self) -> list[str]:
        engine = self._engines["pikafish"]
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


class ChessEnginePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._arena_base = str(self.config.get("arena_base") or "http://101.43.22.174:8787").rstrip("/")
        self._token = str(self.config.get("token") or "").strip()
        self._engine_depth = int(self.config.get("engine_depth") or 4)
        self._engine_select = str(self.config.get("engine_select") or "xqwlight").strip()
        self._pikafish_path = str(self.config.get("pikafish_path") or "").strip()
        self._http_port = int(self.config.get("http_port") or 0)

        self._manager = EngineManager(self._arena_base, self._token, self._pikafish_path)
        self._manager.set_current(self._engine_select)

        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._http_url: str = ""
        try:
            self._startup_task = asyncio.get_running_loop().create_task(self._startup())
        except RuntimeError:
            self._startup_task = None
            logger.warning("[ChessEngine] 当前没有运行中的事件循环，HTTP 服务稍后不会自动启动")

    async def _startup(self):
        if self._http_port > 0:
            app = web.Application()
            app.router.add_post("/analyze", self._handle_analyze)
            app.router.add_get("/health", self._handle_health)
            app.router.add_get("/info", self._handle_info)
            self._runner = web.AppRunner(app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, "0.0.0.0", self._http_port)
            await self._site.start()
            self._http_url = f"http://127.0.0.1:{self._http_port}"
            logger.info("[ChessEngine] HTTP 引擎服务已启动: %s", self._http_url)

    async def _handle_analyze(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        fen = str(data.get("fen") or "").strip()
        legal_moves = data.get("legal_moves") or []
        depth = int(data.get("depth") or self._engine_depth)
        timeout_ms = int(data.get("timeout_ms") or 8000)
        if not fen or not legal_moves:
            return web.json_response({"error": "missing fen or legal_moves"}, status=400)
        try:
            result = await asyncio.wait_for(self._manager.get_current().analyze(fen, legal_moves, depth), timeout=timeout_ms / 1000)
            return web.json_response({"best_move": result.best_move})
        except asyncio.TimeoutError:
            return web.json_response({"error": "engine timeout"}, status=504)
        except Exception as exc:
            logger.warning("[ChessEngine] 分析失败: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _handle_info(self, request: web.Request) -> web.Response:
        return web.json_response({"engine": self._manager.get_current_info(), "depth": self._engine_depth, "http_url": self._http_url})

    async def analyze_position(self, fen: str, legal_moves: list[str], depth: int | None = None) -> str:
        use_depth = depth or self._engine_depth
        result = await self._manager.get_current().analyze(fen, legal_moves, use_depth)
        return result.best_move

    async def analyze_position_detail(self, fen: str, legal_moves: list[str], depth: int | None = None) -> EngineResult:
        use_depth = depth or self._engine_depth
        return await self._manager.get_current().analyze(fen, legal_moves, use_depth)

    def get_engine_info(self) -> dict:
        return {**self._manager.get_current_info(), "depth": self._engine_depth}

    def list_engines(self) -> list[dict]:
        return self._manager.list_all()

    @filter.command("安装象棋引擎")
    async def install_engine(self, event: AstrMessageEvent, engine_name: str):
        if not engine_name:
            yield event.plain_result("用法：安装象棋引擎 <名称>\n支持：pikafish、elephantfish")
            return
        engine_name = engine_name.strip().lower()
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}\n支持：xqwlight、pikafish、elephantfish、random")
            return
        if engine.is_installed():
            if engine_name == "pikafish":
                bins = self._manager.list_pikafish_binaries()
                if bins:
                    lines = [f"{engine_name} 已安装，可选版本:"]
                    for idx, item in enumerate(bins, 1):
                        lines.append(f"{idx}. {item}")
                    lines.append("用 选择象棋引擎版本 <编号> 选当前系统对应的")
                    yield event.plain_result("\n".join(lines))
                else:
                    yield event.plain_result(f"{engine_name} 已安装")
            else:
                yield event.plain_result(f"{engine_name} 已安装")
            return
        yield event.plain_result(f"正在安装 {engine_name}，请稍候...")
        try:
            success = await asyncio.wait_for(engine.install(), timeout=300)
            if not success:
                yield event.plain_result(f"{engine_name} 安装失败")
                return
            if engine_name == "pikafish":
                bins = self._manager.list_pikafish_binaries()
                if bins:
                    lines = [f"{engine_name} 安装成功，可选版本:"]
                    for idx, item in enumerate(bins, 1):
                        lines.append(f"{idx}. {item}")
                    lines.append("用 选择象棋引擎版本 <编号> 选当前系统对应的")
                    yield event.plain_result("\n".join(lines))
                else:
                    yield event.plain_result(f"{engine_name} 安装成功，但未找到二进制文件")
            else:
                yield event.plain_result(f"{engine_name} 安装成功")
        except asyncio.TimeoutError:
            yield event.plain_result(f"{engine_name} 安装超时")
        except Exception as exc:
            yield event.plain_result(f"{engine_name} 安装异常: {exc}")

    @filter.command("卸载象棋引擎")
    async def uninstall_engine(self, event: AstrMessageEvent, engine_name: str):
        if not engine_name:
            yield event.plain_result("用法：卸载象棋引擎 <名称>")
            return
        engine_name = engine_name.strip().lower()
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}")
            return
        if not engine.is_installed():
            yield event.plain_result(f"{engine_name} 未安装")
            return
        try:
            success = await engine.uninstall()
            yield event.plain_result(f"{engine_name} 已卸载" if success else f"{engine_name} 卸载失败")
        except Exception as exc:
            yield event.plain_result(f"{engine_name} 卸载异常: {exc}")

    @filter.command("设置象棋引擎路径")
    async def set_engine_path(self, event: AstrMessageEvent, path: str):
        if not path:
            yield event.plain_result("用法：设置象棋引擎路径 <完整路径>")
            return
        path = path.strip()
        if not Path(path).exists():
            yield event.plain_result(f"路径不存在: {path}")
            return
        self._manager.set_pikafish_path(path)
        self._pikafish_path = path
        self.config["pikafish_path"] = path
        yield event.plain_result(f"已设置 pikafish 路径: {path}")

    @filter.command("列出象棋引擎二进制")
    async def list_engine_bins(self, event: AstrMessageEvent):
        bins = self._manager.list_pikafish_binaries()
        if not bins:
            yield event.plain_result("还没找到 pikafish 二进制，请先安装象棋引擎 pikafish")
            return
        lines = ["可选的 pikafish 二进制:"]
        for idx, item in enumerate(bins, 1):
            lines.append(f"{idx}. {item}")
        lines.append("用 选择象棋引擎版本 <编号> 直接选当前系统对应的那个")
        yield event.plain_result("\n".join(lines))

    @filter.command("选择象棋引擎版本")
    async def choose_engine_bin(self, event: AstrMessageEvent, index: str):
        if not index:
            yield event.plain_result("用法：选择象棋引擎版本 <编号>")
            return
        try:
            idx = int(index.strip())
        except ValueError:
            yield event.plain_result("编号必须是数字")
            return
        engine = self._manager.get_engine("pikafish")
        if not engine:
            yield event.plain_result("pikafish 引擎不可用")
            return
        binary = engine.pick_binary(idx)
        if not binary:
            yield event.plain_result("编号无效，请先用 列出象棋引擎二进制 查看")
            return
        engine.set_custom_path(str(binary))
        self._pikafish_path = str(binary)
        self.config["pikafish_path"] = str(binary)
        yield event.plain_result(f"已选择: {binary}")

    @filter.command("切换象棋引擎")
    async def switch_engine(self, event: AstrMessageEvent, engine_name: str):
        if not engine_name:
            yield event.plain_result("用法：切换象棋引擎 <名称>")
            return
        engine_name = engine_name.strip().lower()
        engine = self._manager.get_engine(engine_name)
        if not engine:
            yield event.plain_result(f"未知引擎: {engine_name}\n支持：xqwlight、pikafish、elephantfish、random")
            return
        if not engine.is_installed():
            yield event.plain_result(f"{engine_name} 未安装，请先运行: 安装象棋引擎 {engine_name}")
            return
        self._manager.set_current(engine_name)
        self._engine_select = engine_name
        self.config["engine_select"] = engine_name
        yield event.plain_result(f"已切换到引擎: {engine_name}")

    @filter.command("象棋引擎状态")
    async def engine_status(self, event: AstrMessageEvent):
        info = self.get_engine_info()
        msg = (
            f"当前引擎: {info['name']}\n"
            f"版本: {info['version']}\n"
            f"搜索深度: {info['depth']}\n"
            f"已安装: {'是' if info['installed'] else '否'}"
        )
        if self._http_url:
            msg += f"\nHTTP 端点: {self._http_url}/analyze"
            msg += f"\nchess_arena 配置: custom_engine_http_url = {self._http_url}/analyze"
        yield event.plain_result(msg)

    @filter.command("象棋引擎列表")
    async def engine_list(self, event: AstrMessageEvent):
        engines = self.list_engines()
        lines = ["支持的引擎:"]
        for e in engines:
            status = "✓ 已安装" if e["installed"] else "✗ 未安装"
            current = " [当前]" if e["current"] else ""
            lines.append(f"  {e['name']} - {status}{current}")
        lines.append("\n使用命令安装：安装象棋引擎 <名称>")
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        if self._runner:
            await self._runner.cleanup()
        if self._startup_task and not self._startup_task.done():
            self._startup_task.cancel()
        logger.info("[ChessEngine] 插件已卸载")
