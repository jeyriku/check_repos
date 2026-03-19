"""check-repos — vérification synchronisation GitLab / GitHub / Nexus."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("check-repos")
except PackageNotFoundError:
    __version__ = "0.0.0"
