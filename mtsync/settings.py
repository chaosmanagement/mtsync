import os
from typing import Dict, Generator, Optional


class Settings:
    fields = (
        "hostname",
        "username",
        "password",
        "ignore_certificate_errors",
    )

    def __init__(self) -> None:
        self.hostname: Optional[str] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.ignore_certificate_errors: bool = False

    def apply_environment_variables(self) -> None:
        for field_name in self.fields:
            if field_name in os.environ:
                setattr(self, field_name, os.environ[field_name])

            if field_name.upper() in os.environ:
                setattr(self, field_name, os.environ[field_name.upper()])

    def apply_arguments(
        self,
        hostname: Optional[str],
        username: Optional[str],
        password: Optional[str],
        ignore_certificate_errors: Optional[bool],
    ) -> None:
        self.hostname = hostname if hostname is not None else self.hostname
        self.username = username if username is not None else self.username
        self.password = password if password is not None else self.password
        self.ignore_certificate_errors = (
            True if ignore_certificate_errors else self.ignore_certificate_errors
        )

    def apply_metadata(
        self,
        metdata: Dict[str, str],
    ) -> None:
        for field_name in self.fields:
            if field_name in metdata and metdata[field_name] is not None:
                setattr(self, field_name, metdata[field_name])

    def valid(self) -> bool:
        return bool(self.hostname) and bool(self.username)

    def __rich_repr__(self) -> Generator:
        yield "hostname", self.hostname
        yield "username", self.username
        yield "password", self.password
        yield "ignore_certificate_errors", self.ignore_certificate_errors
