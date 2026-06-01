import os
import sys
import zipfile
import platform
from pathlib import Path

import aiohttp

# Pikafish GitHub Releases 地址
PIKAFISH_REPO = "official-pikafish/Pikafish"
PIKAFISH_LATEST_URL = f"https://api.github.com/repos/{PIKAFISH_REPO}/releases/latest"


def get_platform_info() -> tuple[str, str]:
    """获取当前系统平台信息，返回 (系统名, 文件后缀)"""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        return "windows", ".exe"
    elif system == "linux":
        return "linux", ""
    elif system == "darwin":
        return "macos", ""
    else:
        return system, ""


def get_arch_tag() -> str:
    """获取 CPU 架构标签"""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86-64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    else:
        return "x86-64"


def get_pikafish_filename() -> str:
    """获取 Pikafish 可执行文件名"""
    system, ext = get_platform_info()
    return f"pikafish{ext}"


def get_pikafish_dir() -> Path:
    """获取 Pikafish 存放目录"""
    plugin_dir = Path(__file__).parent.parent
    bin_dir = plugin_dir / "bin" / "pikafish"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir


def find_pikafish_binary() -> Path | None:
    """查找已安装的 Pikafish 二进制文件"""
    bin_dir = get_pikafish_dir()
    filename = get_pikafish_filename()
    binary = bin_dir / filename
    if binary.exists():
        return binary
    return None


async def get_latest_release_info() -> dict:
    """获取 Pikafish 最新版本信息"""
    async with aiohttp.ClientSession() as session:
        async with session.get(PIKAFISH_LATEST_URL) as resp:
            if resp.status != 200:
                raise RuntimeError(f"获取版本信息失败: HTTP {resp.status}")
            return await resp.json()


def get_download_url(release_info: dict) -> str:
    """根据当前平台获取下载地址"""
    system, _ = get_platform_info()
    arch = get_arch_tag()
    tag = release_info.get("tag_name", "")

    assets = release_info.get("assets", [])
    for asset in assets:
        name = asset.get("name", "").lower()
        if system in name and arch.replace("-", "") in name.replace("-", ""):
            return asset.get("browser_download_url", "")

    raise RuntimeError(f"未找到适配 {system}/{arch} 的下载包")


def get_asset_filename(url: str) -> str:
    """从下载 URL 提取文件名"""
    return url.split("/")[-1]


async def download_pikafish(progress_callback=None) -> Path:
    """下载并解压 Pikafish，返回可执行文件路径"""
    bin_dir = get_pikafish_dir()
    filename = get_pikafish_filename()
    target_binary = bin_dir / filename

    if target_binary.exists():
        return target_binary

    release_info = await get_latest_release_info()
    download_url = get_download_url(release_info)
    asset_filename = get_asset_filename(download_url)

    zip_path = bin_dir / asset_filename

    async with aiohttp.ClientSession() as session:
        async with session.get(download_url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"下载失败: HTTP {resp.status}")
            with open(zip_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)

    if zip_path.suffix == ".zip":
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member.endswith(filename) or member.endswith("pikafish"):
                    member_path = zf.extract(member, bin_dir)
                    extracted = Path(member_path)
                    if extracted.name != filename:
                        extracted.rename(target_binary)
                    break
            else:
                raise RuntimeError("ZIP 中未找到 Pikafish 可执行文件")
        zip_path.unlink(missing_ok=True)
    else:
        zip_path.chmod(0o755)
        zip_path.rename(target_binary)

    return target_binary
