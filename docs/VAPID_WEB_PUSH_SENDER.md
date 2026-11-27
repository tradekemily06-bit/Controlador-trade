# VAPID-backed Web Push sender

`integration.pywebpush_sender.PyWebPushSender` adapts the tenant-scoped sink to the maintained `pywebpush` API.

- The VAPID private key is obtained from an injected host secret provider on each send; no key is committed, read from an arbitrary path, or logged.
- The VAPID subject must be an operational `mailto:` contact. The audience is derived by pywebpush from each push endpoint and the expiry is refreshed by the library.
- Delivery uses the RFC 8188 `aes128gcm` default, a bounded TTL, and a bounded network timeout.
- The sender is optional and lazily imports `pywebpush`, so importing the application does not require the dependency until the sender is actually used.

This is a transport adapter, not a configured production deployment. A real host must provide a managed VAPID private key and contact address, inject a durable encrypted subscription store, wire the sender into the outbox worker, and verify delivery with a browser subscription. Do not set the runtime to push-enabled until those steps and end-to-end delivery tests pass.