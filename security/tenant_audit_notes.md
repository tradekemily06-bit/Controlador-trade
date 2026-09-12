Security assumptions:
- tenant_id must come from a trusted identity boundary;
- untrusted HTTP headers, query strings, IP addresses, and bodies are not tenant identity;
- the demo sink is not a production persistence provider;
- multi-instance durable storage remains a deployment boundary;
- missing tenant scope fails closed.
