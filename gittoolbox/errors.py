class ToolboxError(Exception):
    """An error the user can fix (bad path, unreadable list, unknown branch...)."""


class GitNotFound(ToolboxError):
    pass
