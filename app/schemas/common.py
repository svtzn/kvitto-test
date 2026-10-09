from pydantic import BeforeValidator


def blank_to_none(value: object) -> object:
    """Пустая или пробельная строка считается отсутствием значения."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


BlankToNone = BeforeValidator(blank_to_none)
