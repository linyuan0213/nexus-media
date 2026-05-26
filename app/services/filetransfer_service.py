"""FileTransferService compatibility shim.

Re-export from app.services.transfer package for backward compatibility.
"""

from app.services.transfer import FileTransferService

__all__ = ["FileTransferService"]
