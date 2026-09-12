# Security boundaries

The tenant audit boundary requires an explicit trusted tenant identifier for every audit write and read.

It does not authenticate users or infer tenant identity from HTTP headers, query parameters, IP addresses, or request bodies. Production callers must obtain tenant identity from the deployment identity boundary.

The included in-memory sink is for tests/demo only; durable multi-instance storage remains a deployment concern.
