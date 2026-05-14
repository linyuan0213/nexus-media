from dataclasses import dataclass


@dataclass
class ManualTransferResultDTO:
    """手工转移结果"""
    success: bool = False
    message: str = ""


@dataclass
class ReIdentifyResultDTO:
    """重新识别结果"""
    success: bool = False
    message: str = ""


@dataclass
class SimpleResultDTO:
    """通用操作结果"""
    success: bool = False
    message: str = ""
