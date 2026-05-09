class RocoBaseError(Exception):
    pass

class GameWindowNotFoundError(RocoBaseError):
    pass

class ImageNotFoundError(RocoBaseError):
    pass

class BattleTimeoutError(RocoBaseError):
    pass

class PvpAbortError(RocoBaseError):
    """PVP 自动战斗严重失败（如连续多次未识别到任何技能），需要终止整个脚本。"""
    pass
