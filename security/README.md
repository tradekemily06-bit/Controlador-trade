# Security boundaries

`tenant_audit.py` provides a provider-neutral tenant-scoped audit contract.

It does not authenticate users or resolve tenant identity. Production callers must
obtain a trusted tenant identity from the deployment identity boundary before using
this contract. The in-memory sink is for tests/demo only; durable multi-instance
storage remains a deployment concern.
