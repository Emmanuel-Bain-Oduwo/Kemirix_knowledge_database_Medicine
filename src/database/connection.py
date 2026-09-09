"""PostgreSQL connection for the Kemirix database domain.

Credentials come only from explicit parameters, a URL, or PG* environment
variables — never from Git, config or logs. TLS is required by default:
only secure libpq sslmodes are accepted, with one loudly-named escape
(allow_insecure) that exists solely for the isolated hosted CI service.
Password-bearing DSNs are never printed or embedded in errors.
"""

from urllib.parse import urlsplit

from .exceptions import DatabaseConnectionError

SECURE_SSLMODES = ("require", "verify-ca", "verify-full")
DEFAULT_SSLMODE = "require"
DEFAULT_CONNECT_TIMEOUT = 8
SUPPORTED_MAJOR = 17


def connect(
    *,
    host,
    port,
    dbname,
    user,
    password,
    sslmode=DEFAULT_SSLMODE,
    connect_timeout=DEFAULT_CONNECT_TIMEOUT,
    application_name="kemirix",
    allow_insecure=False,
):
    """Open one PostgreSQL connection with explicit transaction control.

    The connection is created with autocommit enabled so the small
    transaction helper owns BEGIN/COMMIT/ROLLBACK boundaries explicitly.
    """
    if sslmode not in SECURE_SSLMODES and not allow_insecure:
        raise DatabaseConnectionError(
            f"sslmode {sslmode!r} is not secure; require/verify-ca/verify-full "
            "or the CI-only allow_insecure escape"
        )
    import psycopg

    try:
        return psycopg.connect(
            host=host,
            port=int(port),
            dbname=dbname,
            user=user,
            password=password,
            sslmode=sslmode,
            connect_timeout=int(connect_timeout),
            application_name=application_name,
            autocommit=True,
        )
    except psycopg.Error as error:
        # Never include the DSN or any parameter value in the message.
        raise DatabaseConnectionError(f"connection failed ({type(error).__name__})") from None


def connect_from_url(url, *, allow_insecure=False):
    """Connect using a postgres:// or postgresql:// URL parsed in-process."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql") or not parts.hostname:
        raise DatabaseConnectionError("a postgres:// URL is required")
    if parts.query:
        from urllib.parse import parse_qs

        parameters = parse_qs(parts.query)
        sslmode = parameters.get("sslmode", [DEFAULT_SSLMODE])[-1]
    else:
        sslmode = DEFAULT_SSLMODE
    return connect(
        host=parts.hostname,
        port=parts.port or 5432,
        dbname=parts.path.lstrip("/"),
        user=parts.username,
        password=parts.password,
        sslmode=sslmode,
        allow_insecure=allow_insecure,
    )


def connect_from_pg_env(env, *, allow_insecure=False):
    """Connect using PG* environment variables (the operator-provided surface)."""
    required = ("PGHOST", "PGDATABASE", "PGUSER")
    missing = [name for name in required if not env.get(name)]
    if missing or not env.get("PGPASSWORD"):
        raise DatabaseConnectionError(
            "PG* environment incomplete; provide at least " + ", ".join(required + ("PGPASSWORD",))
        )
    return connect(
        host=env["PGHOST"],
        port=env.get("PGPORT", "5432"),
        dbname=env["PGDATABASE"],
        user=env["PGUSER"],
        password=env["PGPASSWORD"],
        sslmode=env.get("PGSSLMODE", DEFAULT_SSLMODE),
        allow_insecure=allow_insecure,
    )


def server_version(connection):
    """Integer server_version_num of the connected PostgreSQL."""
    return int(connection.execute("SHOW server_version_num").fetchone()[0])


def healthcheck(connection, *, major=SUPPORTED_MAJOR):
    """True when the server answers and runs the supported major version."""
    try:
        version = server_version(connection)
    except Exception as error:
        raise DatabaseConnectionError(f"healthcheck failed ({type(error).__name__})") from None
    if not major * 10000 <= version < (major + 1) * 10000:
        raise DatabaseConnectionError(f"unsupported PostgreSQL major version {version // 10000}")
    return True


def close(connection):
    """Close the connection quietly."""
    try:
        connection.close()
    except Exception as error:  # pragma: no cover - defensive
        raise DatabaseConnectionError(f"close failed ({type(error).__name__})") from None
