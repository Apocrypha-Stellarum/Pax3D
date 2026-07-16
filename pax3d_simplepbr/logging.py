# Pax3D fork of simplepbr 0.13.1 (Moguri) — adds bloom, ACES tonemapping
from direct.directnotify.DirectNotify import DirectNotify
from direct.directnotify.Notifier import Notifier

LOGGER = None

def get() -> Notifier:
    global LOGGER # pylint: disable=global-statement
    if LOGGER is None:
        LOGGER = DirectNotify().newCategory("pax3d_simplepbr")
    return LOGGER

def info(msg: str) -> None:
    get().info(msg)

def warning(msg: str) -> None:
    get().warning(msg)
