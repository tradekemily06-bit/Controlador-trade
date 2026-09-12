Tenant-scoped audit is a contract boundary only.

The application must not infer tenant identity from IP address, headers, query parameters, or request bodies. A trusted deployment identity layer must provide the tenant identifier. Until that boundary exists, production SaaS audit access remains fail-closed.
