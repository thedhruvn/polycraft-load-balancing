from main.MCServerMain import CommandSet


class LBFormattedMsg:

    def __init__(self, cmd: CommandSet, msg=None):
        self.msg = self.__format_msg_to_minecraft(cmd, msg)

    @staticmethod
    def __format_msg_to_minecraft(cmd: CommandSet, msg: str = ""):
        """
        The MC API Running each node doesn't need json. Rather, it just needs a simple
        message prefix [space] message parameters
        :param cmd: Message prefix to send
        :param msg: parameters (they can be none)
        :return: a formatted string that is designed to be parsed by @main.MCServerMain#run()
        """
        if msg is None:
            msg = ""

        if cmd is None:
            cmd = CommandSet.HELLO

        # return f'{{"cmd":"{cmd.value}", "arg":"{msg}"}}'
        return f'{cmd.value} {msg}'