from ._client import ConnectionState


class CasambiBtError(RuntimeError):
    pass


class NetworkNotFoundError(CasambiBtError):
    pass


class ConnectionStateError(CasambiBtError):
    def __init__(
        self, expected: ConnectionState, got: ConnectionState, expl: str | None = None
    ) -> None:
        self.expected = expected
        self.got = got

        msg = f"Expected state {expected.name}. Current state {got.name}."
        if expl:
            msg += " " + expl

        super().__init__(msg)


class BluetoothError(CasambiBtError):
    def __init__(self, key: str, msg: str, *args: object) -> None:
        self.key = key
        self.msg = msg
        super().__init__(*args)


class BluetoothNotReadyError(BluetoothError):
    pass


class ProtocolError(CasambiBtError):
    pass


class AuthenticationError(CasambiBtError):
    pass
