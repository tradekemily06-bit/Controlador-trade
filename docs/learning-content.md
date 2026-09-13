# Learning content and training

The ecosystem has a dedicated educational boundary for videos, articles, documents, images and notes, including material supplied by the user and references to external sources.

## Scope

A learning resource can produce structured observations and study activities. The concept vocabulary is intentionally open-ended: the user's known trading concepts are initial knowledge, not a closed list.

The learning layer supports:

- source metadata and HTTP(S) references;
- extracted statements and concepts;
- evidence and confidence;
- explicit validation state;
- study activities and attempts;
- feedback that can be retained for learning.

## Safety boundary

Learning content is informational. Creating or completing a lesson, quiz, video analysis, or extracted observation does not authorize a market decision or an order.

Remote URLs are metadata at this layer. The model does not fetch arbitrary URLs. Any future retrieval adapter must add its own URL validation, network restrictions, size/time limits and auditability before it is connected.

A newly observed concept is not automatically a validated trading rule. It must remain identifiable as new/uncertain until a separate methodology and validation process establishes its meaning.

## User-provided material

When a user supplies a trading video or document, the application can represent it as a learning resource, extract study observations, and generate exercises. The ingestion/analysis adapter remains separate from this domain model so the ecosystem can support different media providers without redesigning the learning core.
