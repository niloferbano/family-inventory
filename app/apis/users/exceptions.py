class InvalidCredentials(Exception):
    pass


class UserAlreadyExists(Exception):
    pass


class UserAlreadyActive(Exception):
    pass


class UserNameAlreadyExists(Exception):
    pass


class InvalidResetToken(Exception):
    pass


class InvalidActivationToken(Exception):
    pass


class UserNotActive(Exception):
    pass
