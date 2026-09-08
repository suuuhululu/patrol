"""STOP/CANCEL common safe action while their final distinction is TBD."""


def interrupt_navigation(navigation) -> None:
    """Request cancellation and leave any restart to a later command."""
    navigation.cancel()
