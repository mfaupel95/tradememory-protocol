# REST single-tenant safety guard

The REST application uses shared global journal/state objects. Authentication
maps keys to identities, but does not scope every database read/write by tenant.
It is therefore unsafe to configure independent tenants against one instance.

Until full isolation is implemented, BearerAuthMiddleware and require_auth reject
protected requests with HTTP 503 when TRADEMEMORY_API_KEYS maps keys to more than
one distinct tenant. Rejection happens before invoking the route handler, even
for a valid token. Configuration is checked on every request. Health, docs and
existing static path exemptions remain reachable through the middleware.

Multiple keys for one tenant remain supported; they share the same data by design.
Unset/empty configuration retains the existing anonymous localhost behavior.
This guard is NOT row-level isolation, does not migrate data and does not protect
against separate processes deliberately sharing a database. Use separate processes,
databases, state paths and OS permissions per trust boundary. MCP/non-REST access
and malformed configuration hardening are outside this change. Do not treat token
authentication as a complete multi-tenant security model.

## Offline regression

From the repository root, using an already provisioned environment:

    PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_auth_tenant_guard_unittest.py -v

The regression builds a minimal FastAPI app, imports only the package initializer
and auth module, uses synthetic environment keys, and calls TestClient's in-process
ASGI transport. It does not import the production server, create a database,
connect to a broker, start a listener or manage existing processes.

The normal pytest test_auth.py expectation for different tenants is updated to
503. Run that suite in a provisioned test environment before accepting the change:

    PYTHONPATH=src python -m pytest tests/test_auth.py tests/test_auth_tenant_guard_unittest.py -q

No installation, deployment or restart is part of this change.
