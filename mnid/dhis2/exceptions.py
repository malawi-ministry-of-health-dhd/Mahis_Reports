"""Explicit errors raised by the MNID DHIS2 integration."""


class DHIS2Error(Exception):
    """Base class for all MNID DHIS2 failures."""


class DHIS2ConfigurationError(DHIS2Error):
    """Configuration is missing or invalid."""


class DHIS2AuthenticationError(DHIS2Error):
    """DHIS2 rejected the supplied identity."""


class DHIS2AuthorizationError(DHIS2Error):
    """The authenticated identity lacks required permissions."""


class DHIS2ConnectionError(DHIS2Error):
    """A network connection could not be established."""


class DHIS2TimeoutError(DHIS2Error):
    """A DHIS2 request exceeded its configured timeout."""


class DHIS2RateLimitError(DHIS2Error):
    """DHIS2 rate-limited the client after bounded retries."""


class DHIS2RequestError(DHIS2Error):
    """DHIS2 rejected a request or returned a permanent HTTP failure."""


class DHIS2ResponseError(DHIS2Error):
    """DHIS2 returned malformed or unsupported content."""


class DHIS2MappingError(DHIS2Error):
    """Indicator or organisation-unit mappings are invalid."""


class DHIS2ValidationError(DHIS2Error):
    """Retrieved or calculated data failed validation."""


class DHIS2StorageError(DHIS2Error):
    """Local audit or last-known-good storage failed."""


class DHIS2SyncError(DHIS2Error):
    """The overall synchronization did not complete successfully."""
