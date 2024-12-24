"""Error types for CasambiBt."""

from ._constants import ConnectionState


class CasambiBtError(RuntimeError):
    """Base class for all CasambiBt errors."""

    pass


class NetworkNotFoundError(CasambiBtError):
    """Exception that is raised when the network can't be found."""

    pass


class NetworkUpdateError(CasambiBtError):
    """Exception that is raised when the network can't be updated."""

    pass


class NetworkOnlineUpdateNeededError(NetworkUpdateError):
    """Exception that is raised when an online update is needed for the network."""

    pass


class AuthenticationError(CasambiBtError):
    """Excpetion that is raised when authentication to the network fails."""

    pass


class ConnectionStateError(CasambiBtError):
    """Exception that is raised when the connection isn't in the required state."""

    def __init__(
        self,
        expected: ConnectionState,
        got: ConnectionState,
        expl: str | None = None,
    ) -> None:
        """Create a new `ConnectionStateError`."""
        self.expected = expected
        self.got = got

        msg = f"Expected state {expected.name}. Current state {got.name}."
        if expl:
            msg += " " + expl

        super().__init__(msg)


class BluetoothError(CasambiBtError):
    """Exception that is raised when a bluetooth-related error happens."""

    pass


class ProtocolError(CasambiBtError):
    """Exception that is raised when communication with the device doesn't follow the expected protocol."""

    pass


class UnsupportedProtocolVersion(CasambiBtError):
    """Exception that is raised when the network has an unsupported version."""

    pass
