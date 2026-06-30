# CAPI + KubeVirt Quick Install

## 1. Install clusterctl

```bash
curl -L https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.13.2/clusterctl-linux-amd64 -o clusterctl
chmod +x clusterctl
sudo mv clusterctl /usr/local/bin/clusterctl
```

---

## 2. Install MetalLB (load balancer for bare-metal)

```bash
METALLB_VER=$(curl "https://api.github.com/repos/metallb/metallb/releases/latest" | jq -r ".tag_name")
kubectl apply -f "https://raw.githubusercontent.com/metallb/metallb/${METALLB_VER}/config/manifests/metallb-native.yaml"
kubectl wait pods -n metallb-system -l app=metallb,component=controller --for=condition=Ready --timeout=10m
kubectl wait pods -n metallb-system -l app=metallb,component=speaker --for=condition=Ready --timeout=2m
```

### Configure IP pool

```bash
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: capi-ip-pool
  namespace: metallb-system
spec:
  addresses:
  - <START_IP>-<END_IP>
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: empty
  namespace: metallb-system
EOF
```

---

## 3. Install KubeVirt

```bash
KV_VER=$(curl "https://api.github.com/repos/kubevirt/kubevirt/releases/latest" | jq -r ".tag_name")
kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${KV_VER}/kubevirt-operator.yaml"
kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${KV_VER}/kubevirt-cr.yaml"
kubectl wait -n kubevirt kv kubevirt --for=condition=Available --timeout=10m
```

---

## 4. Install CAPI + CAPK (KubeVirt infrastructure provider)

```bash
clusterctl init --infrastructure kubevirt
```

---

## 5. Generate and apply the workload cluster

### Set required variables

```bash
export NODE_VM_IMAGE_TEMPLATE="quay.io/capk/ubuntu-2404-container-disk:v1.32.1"
export CAPK_GUEST_K8S_VERSION="${NODE_VM_IMAGE_TEMPLATE/*:/}"
export CRI_PATH="unix:///var/run/containerd/containerd.sock"
```

### Generate manifest and apply

```bash
clusterctl generate cluster capi-quickstart \
  --infrastructure="kubevirt" \
  --flavor lb \
  --kubernetes-version ${CAPK_GUEST_K8S_VERSION} \
  --control-plane-machine-count=1 \
  --worker-machine-count=1 \
  > capi-quickstart.yaml

kubectl apply -f capi-quickstart.yaml
```

### Check VMs are running

```bash
kubectl get vm
kubectl get vmi
```

---

## 6. Get workload cluster kubeconfig

```bash
clusterctl get kubeconfig capi-quickstart > capi-quickstart.kubeconfig
```

---

## 7. Install Calico CNI on the workload cluster

```bash
curl https://raw.githubusercontent.com/projectcalico/calico/v3.29.1/manifests/calico.yaml -o calico-workload.yaml

sed -i -E 's|^( +)# (- name: CALICO_IPV4POOL_CIDR)$|\1\2|g;'\
's|^( +)# (  value: )"192.168.0.0/16"|\1\2"10.243.0.0/16"|g;'\
'/- name: CLUSTER_TYPE/{ n; s/( +value: ").+/\1k8s"/g };'\
'/- name: CALICO_IPV4POOL_IPIP/{ n; s/value: "Always"/value: "Never"/ };'\
'/- name: CALICO_IPV4POOL_VXLAN/{ n; s/value: "Never"/value: "Always"/};'\
'/# Set Felix endpoint to host default action to ACCEPT./a\            - name: FELIX_VXLANPORT\n              value: "6789"' \
calico-workload.yaml

kubectl --kubeconfig=./capi-quickstart.kubeconfig create -f calico-workload.yaml
```

### Verify nodes are ready

```bash
kubectl --kubeconfig=./capi-quickstart.kubeconfig get nodes
```
