class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def not_found():
    return AppError(404, "NOT_FOUND", "资源不存在。")
