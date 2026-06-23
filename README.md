# osm-capk — Cluster API + KubeVirt (CAPK) integration for OSM

Provision CAPK clusters as OSM-owned clusters via `osm cluster-create`. Cluster API runs on
the OSM management cluster and creates nodes as KubeVirt VMs.

Each subdirectory is a fork; the exact diff vs upstream is in [`CHANGES/`](CHANGES):
`LCM` & `NBI` vs `v19.0`, `osm-krm-functions` vs `master`, `sw-catalogs-osm` vs its pre-CAPK base.

## Prerequisites

Management cluster (k3s tested) + **OSM 19** with Flux + Argo Workflows, plus:
Cluster API + CAPK (`clusterctl init --infrastructure kubevirt`), KubeVirt, MetalLB.

## Steps to replicate

**1. Management-cluster prerequisites**
```bash
# Dedicated MetalLB pool for control-plane LoadBalancers
kubectl apply -f sw-catalogs-osm/infra-configs/metallb/capi-lb-pool.yaml
# RBAC for the argo kubeconfig-copy step
kubectl apply -f sw-catalogs-osm/infra-configs/osm-workflows/templates/capk-kubeconfig-copy-rbac.yaml
# Disable k3s servicelb so MetalLB serves all LB services (prevents svclb capturing port 6443):
# add 'servicelb' to k3s --disable, then restart k3s.
```

**2. Host the catalog + KRM functions**
```bash
# Push sw-catalogs-osm to the git repo Flux/Argo read (the kubevirt-kubeadm catalog must be served).
# Inject the KRM functions over the :19 image (no rebuild):
kubectl create configmap osm-krm-functions-capk-scripts \
  --from-file=krm-functions.rc=osm-krm-functions/scripts/library/krm-functions.rc \
  -n osm-workflows --dry-run=client -o yaml | kubectl apply -f -
```

**3. Inject the LCM/NBI changes — version-match to the DEPLOYED image**
The running `lcm`/`nbi` image is usually newer than the git tag, so base the edits on the pods:
```bash
# extract the live files
kubectl exec -n osm <lcm-pod> -c lcm -- cat /usr/lib/python3/dist-packages/osm_lcm/odu_libs/cluster_mgmt.py > cluster_mgmt.py
kubectl exec -n osm <nbi-pod> -c nbi -- cat /usr/lib/python3/dist-packages/osm_nbi/k8s_topics.py > k8s_topics.py
# re-apply the CAPK changes from CHANGES/ (cluster_mgmt.py + 2 launcher .j2 for LCM; k8s_topics.py for NBI)
```
Then create ConfigMaps from the patched files + the two `launcher-*.j2`, and subPath-mount them
over the in-pod paths (`.../osm_lcm/odu_libs/cluster_mgmt.py`, `.../odu_libs/templates/<launcher>.j2`,
`.../osm_nbi/k8s_topics.py`) by patching the `lcm`/`nbi` Deployments; roll out.

**4. Create a connector-less kubevirt VIM**
```bash
osm vim-create --name capk-vim --account_type kubevirt \
  --auth_url http://dummy --user dummy --password dummy --tenant osm
# VIM lands ERROR (no RO connector) — expected; cluster-create still works.
```

**5. Create a cluster**
```bash
osm cluster-create capk-01 --vim-account capk-vim --node-count 1 --version 1.30.1
# -> record "Created by OSM: YES" -> LCM submits the CAPK workflow -> Flux -> KubeVirt VMs
```

**6. Finish provisioning (current manual steps, until automated)**
```bash
# a) copy the kubeconfig secret to managed-resources (CNI/post-install need it)
kubectl get secret capk-01-kubeconfig -n default -o jsonpath='{.data.value}' | base64 -d \
  | kubectl create secret generic capk-01-kubeconfig -n managed-resources \
    --from-file=value=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
# b) if KCP stays WaitingForKubeadmInit: create the kube-proxy ConfigMap on the workload
#    cluster, then run the skipped phases on the control-plane VM:
#    kubeadm init phase {upload-config all, mark-control-plane, bootstrap-token,
#    kubelet-finalize all, addon coredns}
```

> Do **not** `osm cluster-register` / `cluster-deregister` these clusters — it rewrites the
> Flux Kustomization to empty with `prune: true` and destroys the cluster. Use create/delete only.
