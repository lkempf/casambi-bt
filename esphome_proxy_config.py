"""ESPHome Bluetooth Proxy Configuration for Casambi."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ESPHomeProxyConfig:
    """Configuration for connecting through ESPHome Bluetooth proxy.
    
    Attributes:
        host: IP address or hostname of the ESPHome device
        port: Port number for the ESPHome API (default: 6053)
        password: API password if set in ESPHome configuration
        encryption_key: Base64 encoded encryption key for API communication
    """
    host: str
    port: int = 6053
    password: Optional[str] = None
    encryption_key: Optional[str] = None
    
    def to_connection_params(self) -> dict:
        """Convert to parameters for BleakClient connection."""
        params = {
            "address_or_ble_device": f"{self.host}:{self.port}",
        }
        if self.password:
            params["password"] = self.password
        if self.encryption_key:
            params["encryption_key"] = self.encryption_key
        return params