# Discovery memory

Discovery memory records observations, evidence, validation state, and operational admission state for newly discovered market relationships.

It is deliberately separate from execution authority. A record may be validated and operationally admitted while `execution_authorized` remains false. Any trading decision must still pass the ecosystem decision, risk, and execution gates.

The memory is open-ended: it does not require a fixed registry of market patterns and can retain relationships that were not part of the original methodology vocabulary.
