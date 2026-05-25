from ..config.settings import get_settings
from ..config.logging import setup_logging
from ..adapters.telegram import send_text

def main() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    r = send_text("BUG: prueba de envío al grupo ✅")
    print("OK:", r.get("ok", False))

if __name__ == "__main__":
    main()