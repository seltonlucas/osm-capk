# Integrating CAPK (Cluster API + KubeVirt) into OSM cluster lifecycle

Proof-of-concept for making CAPK clusters first-class in `osm cluster-create`.
Branches: `feature/capk-provider` in **LCM**, **NBI**, **sw-catalogs-osm**, **fleet-osm**, **osm-krm-functions**.

## 0. Context: virtualization, not bare metal

The original goals were written assuming **bare metal** (Metal3/CAPM3 — registering
physical `BareMetalHost` machines). This work uses **KubeVirt virtualization (CAPK)**:
Cluster API provisions worker/control-plane nodes as KubeVirt `VirtualMachineInstance`
objects **on the OSM management cluster itself**. There is no external cloud account and
no pool of physical hosts to register — VMs are created on demand and destroyed with the
cluster. So "registration/management of bare-metal resources" has no direct CAPK analog;
the equivalent is the management cluster's capacity + a MetalLB IP pool (already in place).

## 1. The gap we found

`osm cluster-create` → NBI → `LCM/osm_lcm/odu_libs/cluster_mgmt.py::create_cluster()` renders a
Jinja2 "launcher" that submits an Argo Workflow. In v19.0 this is **hardcoded to crossplane**:

```python
workflow_template = "launcher-create-crossplane-cluster-and-bootstrap.j2"
if   vim_type == "azure": cluster_type = "aks"
elif vim_type == "aws":   cluster_type = "eks"
elif vim_type == "gcp":   cluster_type = "gke"
else: raise Exception("Not suitable VIM account to register cluster")
```

There is **zero** `kubevirt`/`capk`/`capi` mention anywhere in LCM. The CAPK
`full-create-capi-kubevirt-cluster-and-bootstrap-wft` workflow exists, but nothing in OSM
can launch it. So the only way to build a CAPK cluster was to run the Argo workflow
**directly** (bypassing OSM), which leaves OSM with no record of it.

## 2. Why "create via workflow, then `osm cluster-register`" is destructive

A CAPK cluster's lifecycle hinges on one Flux Kustomization named after the cluster
(`<name>` in `managed-resources`). The creation workflow points it at the CAPI manifests
(it *manages* the cluster). But `osm cluster-register` treats the cluster as **imported**
and **rewrites that same Kustomization to an empty manifest** with `prune: true` — so Flux
prunes the CAPI Cluster and **all VMs are destroyed**. Observed twice: deregistering
capk-test-01 and registering capk-test-02 each destroyed a healthy cluster within minutes.

**Conclusion: integration must be OSM-driven creation, not create-then-register.**

## 3. Prototype changes

### LCM (`feature/capk-provider`)
- **`osm_lcm/odu_libs/templates/launcher-create-capi-kubevirt-cluster-and-bootstrap.j2`** (new)
  — submits `full-create-capi-kubevirt-cluster-and-bootstrap-wft` with KubeVirt sizing/network
  params (CP/worker cpu/mem/storage, `vm_image`, `pod_cidr`, `service_cidr`, `cluster_cni`,
  `capk_resources_namespace`).
- **`launcher-update-capi-kubevirt-cluster.j2`** (new) — day-2 (scale/upgrade/resize) →
  `full-update-capi-kubevirt-cluster-and-bootstrap-wft`.
- **`osm_lcm/odu_libs/cluster_mgmt.py`** — `create_cluster()` and `update_cluster()` add a
  `vim_type == "kubevirt"` branch selecting the CAPK launcher and CAPK params. CAPK values are
  overridable per-cluster via `--config` (read from `db_cluster`), else WFT defaults apply.
  `vm_image` defaults to `quay.io/capk/ubuntu-2204-container-disk:v<k8s_version>`.
  `delete_cluster()` is provider-agnostic — no change.

### NBI (`feature/capk-provider`)
- **`osm_nbi/osm_nbi/k8s_topics.py`** — `_validate_input_new` accepts `vim_type == "kubevirt"`
  (requires worker `node_count`, like azure/gcp). `vim_type` already accepts any shortname and
  `check_vim` doesn't restrict types, so **no schema/enum change is needed**.

### Already done (GitOps layer, validated end-to-end by building capk-test-02)
- `sw-catalogs-osm`: parameterized `kubevirt.yaml` base + Flux templates; fixes for
  `timeoutForControlPlane` (under `apiServer`), kubelet-api-admin RBAC, the `git-wft`
  absolute-path bug, dedicated MetalLB pool annotation.
- `osm-krm-functions`: `create_/update_capi_kubevirt_cluster` (injected via ConfigMap).
- `fleet-osm`: CAPK management-cluster prerequisites as GitOps.

## 4. End-to-end flow this enables

```
osm vim-create  --name capk-vim --account-type kubevirt ...
osm cluster-create capk-01 --vim-account capk-vim --node-count 1 --version 1.30.1 \
    [--config '{control_plane_cpu_cores: 4, worker_memory: 8Gi, vm_image: ...}']
   → NBI accepts kubevirt VIM, creates cluster record (Created by OSM = yes)
   → LCM renders launcher-create-capi-kubevirt-...j2 → submits the CAPK workflow
   → workflow → Flux → Cluster API → KubeVirt VMs → cluster Ready
   → cluster is tracked by OSM; osm cluster-delete tears it down cleanly
```

No separate register step → no Kustomization collision → no destruction.

## 5. Open design questions for the OSM developers

1. **VIM type / RO connector.** NBI persists a `kubevirt` VIM fine, but the RO has no
   `kubevirt` connector plugin. CAPK provisioning does **not** use the RO VIM connector
   (LCM → Argo → CAPK/Flux do the work), so the VIM is a logical target. Options: (a) a real
   `kubevirt` VIM type marked connector-less (like the existing `dummy` `_system-osm-vim`);
   (b) reuse the system VIM and have LCM treat it as CAPK-capable. Which do you prefer?
2. **Where do CAPK sizing params live?** This POC reads them from `db_cluster` (settable via
   `--config`), with defaults. Should they become first-class `cluster-create` options?
3. **Shipping to a running OSM.** Rebuild the LCM/NBI images, or ConfigMap-subPath-inject the
   `.j2` + patched modules into the pods (as we do for `krm-functions.rc`, version-locked to v19.0)?

## 6. Still-manual gaps (environment, not OSM core)

- **k3s servicelb** creates a `svclb-*` pod that captures host port 6443 for the control-plane
  LoadBalancer, breaking webhooks/VMI updates. The `svccontroller.k3s.cattle.io/nodelabels`
  annotation is **ignored by k3s v1.34.2+k3s1**, so the DaemonSet must be neutralized
  reactively. Needs a real fix (MetalLB `--lb-class`, or disabling k3s servicelb).
- **`wait-and-copy-kubeconfig`** workflow step fails if the CAPI Cluster object doesn't exist
  yet (`kubectl wait` exits 1); needs retry/existence logic. The kubeconfig secret currently
  has to be copied manually before the CNI/postinstall Kustomizations can apply.
