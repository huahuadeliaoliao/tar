"""Application configuration loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


CONFIG_ENV_VAR = "APP_CONFIG_FILE"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.toml"


class Config:
    """Application configuration loaded from TOML files.

    The initializer normalizes nested dictionaries and allows environment
    variables to override sensitive values such as secrets and connection
    strings.
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        """Initialise configuration values from parsed TOML data.

        Args:
            data: Nested dictionary representation of the TOML file.
        """
        registration = data.get("registration", {})
        jwt = data.get("jwt", {})
        database = data.get("database", {})
        openai = data.get("openai", {})
        web_search = data.get("web_search", {})
        llm = data.get("llm", {})
        prompts = data.get("prompts", {})
        file_uploads = data.get("file_uploads", {})
        allowed_file_types = file_uploads.get("allowed_file_types", {})
        image_settings = file_uploads.get("image", {})
        libreoffice = data.get("libreoffice", {})
        agent = data.get("agent", {})
        background_tasks = data.get("background_tasks", {})

        self.REGISTRATION_TOKEN: str = os.getenv("REGISTRATION_TOKEN", registration.get("token", ""))

        self.JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", jwt.get("secret_key", ""))
        self.JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", jwt.get("algorithm", "HS256"))
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", jwt.get("access_token_expire_minutes", 30))
        )
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = int(
            os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", jwt.get("refresh_token_expire_days", 7))
        )

        self.DATABASE_URL: str = os.getenv("DATABASE_URL", database.get("url", "sqlite:///./data/app.db"))

        self.OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", openai.get("base_url", ""))
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", openai.get("api_key", ""))
        self.AVAILABLE_MODELS: List[Dict[str, Any]] = [dict(model) for model in openai.get("available_models", [])]

        self.WEB_SEARCH_MODELS: List[str] = list(web_search.get("models", []))
        self.WEB_SEARCH_TIMEOUT: int = int(os.getenv("WEB_SEARCH_TIMEOUT", web_search.get("timeout", 100)))

        self.LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", llm.get("temperature", 0.5)))
        self.LLM_TOP_P: float = float(os.getenv("LLM_TOP_P", llm.get("top_p", 1.0)))
        self.LLM_MAX_TOKENS: Optional[int] = self._parse_optional_int(
            os.getenv("LLM_MAX_TOKENS", self._none_to_empty(llm.get("max_tokens")))
        )
        self.LLM_FREQUENCY_PENALTY: float = float(os.getenv("LLM_FREQUENCY_PENALTY", llm.get("frequency_penalty", 0.0)))
        self.LLM_PRESENCE_PENALTY: float = float(os.getenv("LLM_PRESENCE_PENALTY", llm.get("presence_penalty", 0.0)))

        self.SYSTEM_PROMPT: str = prompts.get("system", "")
        self.TOOL_ERROR_SYSTEM_PROMPT: str = prompts.get("tool_error", "")
        self.MULTIPLE_TOOLS_WARNING: str = prompts.get("multiple_tools_warning", "")

        self.MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", file_uploads.get("max_file_size", 50 * 1024 * 1024)))
        self.ALLOWED_FILE_TYPES: Dict[str, List[str]] = {key: list(value) for key, value in allowed_file_types.items()}

        self.IMAGE_FORMAT: str = image_settings.get("format", "webp")
        self.IMAGE_COMPRESSION_QUALITY: int = int(image_settings.get("compression_quality", 75))
        self.IMAGE_MAX_DIMENSION: int = int(image_settings.get("max_dimension", 2048))

        self.LIBREOFFICE_TIMEOUT: int = int(os.getenv("LIBREOFFICE_TIMEOUT", libreoffice.get("timeout", 120)))
        self.LIBREOFFICE_PATH: str = os.getenv("LIBREOFFICE_PATH", libreoffice.get("path", "/usr/bin/libreoffice"))
        self.PDF_TO_IMAGE_DPI: int = int(libreoffice.get("pdf_to_image_dpi", 150))

        self.MAX_ITERATIONS: int = int(agent.get("max_iterations", 50))
        self.MAX_RETRY_ON_MULTIPLE_TOOLS: int = int(agent.get("max_retry_on_multiple_tools", 3))

        self.BACKGROUND_TASK_MAX_WORKERS: int = int(background_tasks.get("max_workers", 8))

    @staticmethod
    def _none_to_empty(value: Any) -> str:
        """Convert `None` to an empty string.

        Args:
            value: The original value that may be `None`.

        Returns:
            str: An empty string when `value` is `None`; otherwise the string
            representation of `value`.
        """
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _parse_optional_int(value: str | None) -> Optional[int]:
        """Parse an optional integer value from a string.

        Args:
            value: String representation of an integer or a sentinel that
                indicates absence (for example `"None"`).

        Returns:
            Optional[int]: The parsed integer, or `None` when `value` is falsy
            or one of the sentinel strings.

        Raises:
            ValueError: If `value` is not a valid integer representation.
        """
        if value in (None, "", "None", "none", "null", "Null"):
            return None
        return int(value)


def load_config(path: Path | str | None = None) -> Config:
    """Load the application configuration from a TOML file.

    Args:
        path: Optional path to the configuration file. When omitted, the
            function checks the `APP_CONFIG_FILE` environment variable and
            finally falls back to `config.toml`.

    Returns:
        Config: A configuration object populated with the parsed values.

    Raises:
        FileNotFoundError: If the configuration file cannot be located.
        tomllib.TOMLDecodeError: If the TOML content is malformed.
    """
    config_path = _resolve_config_path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    return Config(data)


def _resolve_config_path(path: Path | str | None) -> Path:
    """Resolve the path to the configuration file.

    Args:
        path: Explicit path provided by the caller.

    Returns:
        Path: The resolved configuration path, prioritizing the argument, then
        the `APP_CONFIG_FILE` environment variable, and lastly the default
        location.
    """
    if path:
        return Path(path)

    env_path = os.getenv(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path)

    return CONFIG_PATH


config = load_config()
