from enum import Enum


class MCCommandSet(Enum):
    """
    Commands acceptable by Minecraft. If not passed, the default is SAY
    """
    SAY = "SAY"
    KILL = "KILL"
    DEALLOC = "DEALLOC"

class FormattedMsg:

    def __init__(self, cmd, msg=None):
        self.msg = self.__format_msg_to_minecraft(cmd, msg)

    @staticmethod
    def __format_msg_to_minecraft(cmd: MCCommandSet, msg: str = ""):
        if msg is None:
            msg = "hello"

        if cmd is None:
            cmd = MCCommandSet.SAY

        return f'{{"cmd":"{cmd.value}", "arg":"{msg}"}}'