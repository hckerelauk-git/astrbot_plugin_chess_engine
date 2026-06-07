from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EngineResult:
    """引擎分析结果"""
    best_move: str
    score: int | None = None
    depth: int | None = None
    time_ms: int | None = None


class ChessEngine(ABC):
    """象棋引擎基类 - 其他插件可继承此类实现自定义引擎"""

    @abstractmethod
    def get_name(self) -> str:
        """引擎名称"""
        pass

    @abstractmethod
    def get_version(self) -> str:
        """引擎版本"""
        pass

    @abstractmethod
    def is_installed(self) -> bool:
        """检查引擎是否已安装"""
        pass

    @abstractmethod
    async def install(self) -> bool:
        """安装引擎，返回是否成功"""
        pass

    @abstractmethod
    async def uninstall(self) -> bool:
        """卸载引擎，返回是否成功"""
        pass

    @abstractmethod
    async def analyze(self, fen: str, legal_moves: list[str], depth: int = 4, timeout_ms: int | None = None) -> EngineResult:
        """分析局面，从 legal_moves 中选择最佳走法"""
        pass

    async def shutdown(self) -> None:
        """释放资源，关闭子进程。默认空实现，子类按需覆盖。"""
        pass
