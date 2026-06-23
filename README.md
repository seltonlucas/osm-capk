# osm-capk — Cluster API + KubeVirt (CAPK) integration for OSM

Forks of OSM components wired to provision **Cluster API + KubeVirt (CAPK)** Kubernetes
clusters as first-class, OSM-owned clusters via `osm cluster-create`. CAPK runs Cluster API
on the OSM **management cluster** and creates control-plane/worker nodes as KubeVirt
`VirtualMachineInstance`s — i.e. virtualization, not bare metal (no Metal3/CAPM3).

Validated end-to-end on the reference lab: `osm cluster-create … --vim-account <kubevirt-vim>`
produces a record with `Created by OSM: YES`, LCM renders a CAPK launcher and submits the
Argo workflow, and the cluster comes up as KubeVirt VMs.

## Components

| Directory | Upstream | What changed |
|---|---|---|
| [LCM/](LCM) | osm/LCM | `cluster_mgmt.py` gains a `vim_type == "kubevirt"` branch; new `launcher-create/update-capi-kubevirt-cluster*.j2` |
| [NBI/](NBI) | osm/NBI | `k8s_topics.py` accepts a `kubevirt` VIM type for `cluster-create` |
| [osm-krm-functions/](osm-krm-functions) | osm/osm-krm-functions | `create_/update_capi_kubevirt_cluster` KRM functions |
| [sw-catalogs-osm/](sw-catalogs-osm) | osm sw-catalogs | parameterized CAPI/KubeVirt manifests + Flux templates + fixes |

## Reviewing the changes

Each subdirectory is the full fork; the precise delta vs upstream is in [`CHANGES/`](CHANGES):

- `CHANGES/LCM.patch` — vs `v19.0`
- `CHANGES/NBI.patch` — vs `v19.0`
- `CHANGES/osm-krm-functions.patch` — vs `master`
- `CHANGES/sw-catalogs-osm.patch` — vs the pre-CAPK catalog base

Integration design and rationale: [`docs/integration-design.md`](docs/integration-design.md).

> Note: `fleet-osm` (the GitOps deploy repo) is intentionally **not** included here — it
> holds live cluster secrets (sops/age keys, kubeconfigs).
