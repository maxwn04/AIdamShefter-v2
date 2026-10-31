# Linux and WSL relocation

Use one Linux-native development checkout in WSL2 or Codex Cloud. Historical Windows campaign evidence remains immutable and separate from that checkout.

- [Architecture](architecture.md): offline relocation and evidence boundaries.
- [Contracts](application-contracts.md): validation, attestation and failure rules.
- [Development](development.md): setup, checks and local startup.

The relocation command creates a verified offline binding and records the observed Linux runtime. It never changes campaign inputs, approves runtime differences, connects to a database, or resumes generations. Live continuation needs a separately reviewed integration and reconciliation against the original target. Matching retained receipts cannot establish current live state.
