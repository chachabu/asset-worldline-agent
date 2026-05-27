from app.core.config import get_settings
from app.services.job_runner import JobRunner


def main() -> None:
    settings = get_settings()
    JobRunner().run_forever(settings.job_poll_seconds)


if __name__ == "__main__":
    main()

