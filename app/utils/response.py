def success(data=None, message: str = "success", code: int = 0):
    return {
        "code": code,
        "message": message,
        "data": data,
    }


def fail(message: str = "fail", code: int = -1, data=None):
    return {
        "code": code,
        "message": message,
        "data": data,
    }











