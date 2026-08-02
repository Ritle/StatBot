"""Expected channel setup failures safe to show to administrators."""


class SetupError(Exception):
    """A channel/discussion pair cannot be configured safely."""


class SetupPermissionError(SetupError):
    """The requesting user is not allowed to administer the channel."""
