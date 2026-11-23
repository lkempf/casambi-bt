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


class CloudUnavailableError(NetworkUpdateError):
    """Exception that is raised when the Casambi cloud can't be used.

    The cloud is unreachable or answers with an error that says nothing about
    the credentials, e.g. maintenance (5xx) or a rate limit (403, 429).
    ``status_code`` is the http status or ``None`` for a network error.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Create a new `CloudUnavailableError`."""
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(CasambiBtError):
    """Exception that is raised when authentication to the network fails.

    ``status_code`` is the http status of the rejected cloud login (usually
    401) or ``None`` if the failure didn't come from the cloud.
    """

    def __init__(self, message: str = "", status_code: int | None = None) -> None:
        """Create a new `AuthenticationError`."""
        self.status_code = status_code
        super().__init__(message)


class OfflineBackupError(CasambiBtError):
    """Exception that is raised when an offline backup is invalid or doesn't match."""

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


class BluetoothDeviceNotFoundError(CasambiBtError):
    """Exception that is raised when the bluetooth device used by the network can't be found."""

    pass


class ProtocolError(CasambiBtError):
    """Exception that is raised when communication with the device doesn't follow the expected protocol."""

    pass


class UnsupportedProtocolVersion(CasambiBtError):
    """Exception that is raised when the network has an unsupported version."""

    pass
