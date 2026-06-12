"""Qucs-S config file management.

Qucs-S stores configuration at ~/.config/qucs/qucs_s.conf in QSettings INI format.
"""

import configparser
import os
import shutil
from typing import Optional


def get_config_path() -> str:
    """Return the path to the Qucs-S config file."""
    return os.path.join(os.path.expanduser("~"), ".config", "qucs", "qucs_s.conf")


def read_config() -> configparser.ConfigParser:
    """Read the Qucs-S INI config file.

    QSettings allows duplicate keys (e.g., ``recentdocs``) which Python's
    configparser rejects in strict mode.  We use ``strict=False`` so those
    files parse without error.

    Returns an empty ConfigParser if the file does not exist.
    """
    config = configparser.ConfigParser(
        strict=False,
        interpolation=None,  # QSettings values may contain % (e.g. mpirun -np %p)
    )
    # Preserve case: QSettings is case-sensitive (NgspiceExecutable ≠ ngspiceexecutable)
    config.optionxform = str
    path = get_config_path()
    if os.path.exists(path):
        config.read(path)
    return config


def write_config(config: configparser.ConfigParser) -> None:
    """Write a ConfigParser back to the Qucs-S config file.

    Creates parent directories if they do not exist.
    """
    path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        config.write(f)


def is_configured_for_pqwave() -> bool:
    """Check if *both* NgspiceExecutable and NgspiceParams are set for pqwave.

    A half-configured state (e.g. executable pointing to pqwave but empty
    params) is NOT considered configured — it will be repaired by Connect.

    Returns False if the config file does not exist or either key is missing.
    """
    path = get_config_path()
    if not os.path.exists(path):
        return False
    config = read_config()
    try:
        exe = config.get("General", "NgspiceExecutable")
        params = config.get("General", "NgspiceParams")
    except (configparser.NoSectionError, configparser.NoOptionError):
        return False
    return "pqwave" in exe.lower() and "--qucs-bridge" in params


def apply_bridge_config(pqwave_exe: str,
                        pqwave_params: str = "--qucs-bridge") -> str:
    """Configure Qucs-S to use pqwave as the waveform viewer.

    Qucs-S runs: ``"<NgspiceExecutable>" <NgspiceParams> <netlist>``, so the
    subcommand MUST go in ``NgspiceParams`` — putting ``--qucs-bridge`` inside
    ``NgspiceExecutable`` would be quoted as one token and fail.

    1. Reads the current config.
    2. Creates a backup at ``<config_path>.pqwave_backup``.
    3. Sets ``General.NgspiceExecutable = pqwave_exe``.
    4. Sets ``General.NgspiceParams = pqwave_params``.
    5. Writes the config.
    6. Returns the backup path.
    """
    config_path = get_config_path()
    backup_path = config_path + ".pqwave_backup"

    # Create backup (copy the file if it exists, otherwise an empty backup)
    if os.path.exists(config_path):
        shutil.copy2(config_path, backup_path)
    else:
        # Ensure directory exists for the backup
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

    config = read_config()
    if not config.has_section("General"):
        config.add_section("General")
    config.set("General", "NgspiceExecutable", pqwave_exe)
    config.set("General", "NgspiceParams", pqwave_params)
    write_config(config)

    return backup_path


def restore_config(backup_path: str) -> bool:
    """Restore the Qucs-S config from a backup file.

    Copies the backup back to the original config path, overwriting the
    current config.

    Returns True on success, False if the backup file does not exist.
    """
    if not os.path.exists(backup_path):
        return False
    config_path = get_config_path()
    shutil.copy2(backup_path, config_path)
    return True


def detect_ngspice() -> Optional[str]:
    """Find the real ngspice executable on the system.

    Checks in order:
    1. Current config's NgspiceExecutable (if it does not already point to pqwave).
    2. ``shutil.which("ngspice")``.
    3. Common paths: ``/usr/bin/ngspice``, ``/usr/local/bin/ngspice``.

    Returns the path as a string, or None if not found.
    """
    # Check current config (only if not already pointing to pqwave)
    config = read_config()
    try:
        existing = config.get("General", "NgspiceExecutable")
        if existing and "pqwave" not in existing.lower():
            if os.path.isfile(existing):
                return existing
            # The value may include arguments (e.g. "/usr/bin/ngspice -b").
            # Extract just the executable path.
            candidate = existing.split()[0]
            if os.path.isfile(candidate):
                return candidate
    except (configparser.NoSectionError, configparser.NoOptionError):
        pass

    # Check PATH
    found = shutil.which("ngspice")
    if found:
        return found

    # Check common paths
    for path in ("/usr/bin/ngspice", "/usr/local/bin/ngspice"):
        if os.path.isfile(path):
            return path

    return None
