import os
import platform
import shutil
import subprocess
from pathlib import Path

import aiohttp

PIKAFISH_REPO = "official-pikafish/Pikafish"
PIKAFISH_LATEST_URL = f"https://api.github.com/repos/{PIKAFISH_REPO}/releases/latest"


def get_platform_info() -> tuple[str, str]:
    system = platform.system().lower()
    if system == "windows":
        return "windows", ".exe"
    elif system == "linux":
        return "linux", ""
    elif system == "darwin":
        return "mac", ""
    return system, ""


def get_pikafish_filename() -> str:
    system, ext = get_platform_info()
    return f"pikafish{ext}"


def get_pikafish_dir() -> Path:
    plugin_dir = Path(__file__).parent.parent
    bin_dir = plugin_dir / "bin" / "pikafish"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir


def find_pikafish_binary() -> Path | None:
    """查找已安装的 Pikafish 二进制，支持 pikafish 和 pikafish-* 名字"""
    bin_dir = get_pikafish_dir()
    _, ext = get_platform_info()

    direct = bin_dir / f"pikafish{ext}"
    if direct.exists() and direct.is_file():
        return direct

    for f in bin_dir.rglob(f"pikafish*{ext}"):
        if f.is_file():
            return f

    return None


async def get_latest_release_info() -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(PIKAFISH_LATEST_URL) as resp:
            if resp.status != 200:
                raise RuntimeError(f"获取版本信息失败: HTTP {resp.status}")
            return await resp.json()


def get_asset_info(release_info: dict) -> tuple[str, str]:
    assets = release_info.get("assets", [])
    if not assets:
        raise RuntimeError("发布页无可用下载包")
    asset = assets[0]
    return asset.get("browser_download_url", ""), asset.get("name", "")


async def download_pikafish() -> Path:
    bin_dir = get_pikafish_dir()

    existing = find_pikafish_binary()
    if existing:
        return existing

    release_info = await get_latest_release_info()
    download_url, asset_name = get_asset_info(release_info)
    archive_path = bin_dir / asset_name

    async with aiohttp.ClientSession() as session:
        async with session.get(download_url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"下载失败: HTTP {resp.status}")
            with open(archive_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(65536):
                    f.write(chunk)

    _extract_archive(archive_path, bin_dir)
    archive_path.unlink(missing_ok=True)
    _copy_nnue_to_subdirs(bin_dir)

    if platform.system().lower() != "windows":
        for binary in _list_all_pikafish(bin_dir):
            os.chmod(str(binary), 0o755)

    result = find_pikafish_binary()
    if result:
        return result

    raise RuntimeError("解压后未找到 pikafish 二进制，请检查包内结构并手动指定 pikafish_path")


def _list_all_pikafish(bin_dir: Path) -> list[Path]:
    _, ext = get_platform_info()
    candidates = []
    for f in bin_dir.rglob(f"pikafish*{ext}"):
        if f.is_file():
            candidates.append(f)
    return candidates


def _copy_nnue_to_subdirs(bin_dir: Path) -> None:
    """将 pikafish.nnue 从根目录复制到每个平台子目录"""
    nnue_root = bin_dir / "pikafish.nnue"
    if not nnue_root.exists():
        return
    for child in bin_dir.iterdir():
        if child.is_dir() and child.name.lower() not in {"wiki", "__pycache__"}:
            target = child / "pikafish.nnue"
            if not target.exists():
                shutil.copy2(str(nnue_root), str(target))


def _extract_archive(archive_path: Path, dest_dir: Path):
    suffix = archive_path.suffix.lower()
    if suffix == ".7z":
        _extract_7z(archive_path, dest_dir)
    elif suffix == ".zip":
        _extract_zip(archive_path, dest_dir)
    else:
        raise RuntimeError(f"不支持的压缩格式: {suffix}")


def _extract_7z(archive_path: Path, dest_dir: Path):
    seven_zip = shutil.which("7z") or shutil.which("7z.exe") or shutil.which("7za")

    if seven_zip:
        result = subprocess.run(
            [seven_zip, "x", str(archive_path), f"-o{str(dest_dir)}", "-y"],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"7z 解压失败: {result.stderr.decode('utf-8', 'ignore')[:200]}")
        return

    try:
        import py7zr
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=dest_dir)
        return
    except ImportError:
        pass

    if platform.system().lower() == "windows":
        result = subprocess.run(
            [
                "powershell", "-Command",
                f"Expand-7Zip -ArchivePath '{archive_path}' -DestinationPath '{dest_dir}' -Force"
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0:
            return

    raise RuntimeError(
        "需要 7z 解压工具，请安装:\n"
        "  Windows: winget install 7zip.7zip\n"
        "  Linux: apt install p7zip-full\n"
        "  或 pip install py7zr"
    )


def _extract_zip(archive_path: Path, dest_dir: Path):
    import zipfile
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(dest_dir)
