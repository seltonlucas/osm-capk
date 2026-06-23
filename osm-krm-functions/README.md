# osm-krm-functions

`osm-krm-functions` is a bash/Alpine-based container used by the OSM declarative workflow.

ArgoWorkflow steps call into this container to perform low-level Kubernetes resource management operations: cluster bootstrap, git operations, secret encryption (via `sops`/`age`), and resource lifecycle management using `kubectl`, `kustomize`, `flux`, `kpt`, and `yq`.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
