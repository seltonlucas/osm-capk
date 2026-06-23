# Copyright 2022 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

db_nsrs_text = """
---
-   _id: dbfbd751-3de4-4e68-bd40-ec5ae0a53898
    name: k8s-ns
    name-ref: k8s-ns
    short-name: k8s-ns
    admin-status: ENABLED
    nsState: READY
    currentOperation: IDLE
    currentOperationID: null
    errorDescription: null
    errorDetail: null
    deploymentStatus: null
    configurationStatus:
      - elementType: VNF
        elementUnderConfiguration: 1b6a4eb3-4fbf-415e-985c-4aeb3161eec0
        status: READY
      - elementType: VNF
        elementUnderConfiguration: 17892d73-aa19-4b87-9a00-1d094f07a6b3
        status: READY
    vcaStatus: null
    nsd:
      _id: 12f320b5-2a57-40f4-82b5-020a6b1171d7
      id: k8s_proxy_charm-ns
      version: '1.0'
      name: k8s_proxy_charm-ns
      vnfd-id:
        - k8s_proxy_charm-vnf
      virtual-link-desc:
        - id: mgmtnet
          mgmt-network: true
        - id: datanet
      df:
        - id: default-df
          vnf-profile:
            - id: vnf1
              virtual-link-connectivity:
                - constituent-cpd-id:
                    - constituent-base-element-id: vnf1
                      constituent-cpd-id: vnf-mgmt-ext
                  virtual-link-profile-id: mgmtnet
                - constituent-cpd-id:
                    - constituent-base-element-id: vnf1
                      constituent-cpd-id: vnf-data-ext
                  virtual-link-profile-id: datanet
              vnfd-id: k8s_proxy_charm-vnf
            - id: vnf2
              virtual-link-connectivity:
                - constituent-cpd-id:
                    - constituent-base-element-id: vnf2
                      constituent-cpd-id: vnf-mgmt-ext
                  virtual-link-profile-id: mgmtnet
                - constituent-cpd-id:
                    - constituent-base-element-id: vnf2
                      constituent-cpd-id: vnf-data-ext
                  virtual-link-profile-id: datanet
              vnfd-id: k8s_proxy_charm-vnf
      description: NS with 2 VNFs with cloudinit connected by datanet and mgmtnet VLs
      _admin:
        userDefinedData: {}
        revision: 1
        created: 1658990740.88281
        modified: 1658990741.09266
        projects_read:
          - 51e0e80fe533469d98766caa16552a3e
        projects_write:
          - 51e0e80fe533469d98766caa16552a3e
        onboardingState: ONBOARDED
        operationalState: ENABLED
        usageState: NOT_IN_USE
        storage:
          fs: mongo
          path: /app/storage/
          folder: '12f320b5-2a57-40f4-82b5-020a6b1171d7:1'
          pkg-dir: k8s_proxy_charm_ns
          descriptor: k8s_proxy_charm_ns/k8s_proxy_charm_nsd.yaml
          zipfile: k8s_proxy_charm_ns.tar.gz
    datacenter: bad7338b-ae46-43d4-a434-c3337a8054ac
    resource-orchestrator: osmopenmano
    description: default description
    constituent-vnfr-ref:
      - 1b6a4eb3-4fbf-415e-985c-4aeb3161eec0
      - 17892d73-aa19-4b87-9a00-1d094f07a6b3
    operational-status: running
    config-status: configured
    detailed-status: Done
    orchestration-progress: {}
    create-time: 1658998097.57611
    nsd-name-ref: k8s_proxy_charm-ns
    operational-events: []
    nsd-ref: k8s_proxy_charm-ns
    nsd-id: 12f320b5-2a57-40f4-82b5-020a6b1171d7
    vnfd-id:
      - 6d9e1ca1-f387-4d01-9876-066fc7311e0f
    instantiate_params:
      nsdId: 12f320b5-2a57-40f4-82b5-020a6b1171d7
      nsName: k8s-ns
      nsDescription: default description
      vimAccountId: bad7338b-ae46-43d4-a434-c3337a8054ac
      vld:
        - name: mgmtnet
          vim-network-name: osm-ext
    additionalParamsForNs: null
    ns-instance-config-ref: dbfbd751-3de4-4e68-bd40-ec5ae0a53898
    id: dbfbd751-3de4-4e68-bd40-ec5ae0a53898
    ssh-authorized-key: null
    flavor:
      - id: '0'
        memory-mb: 1024
        name: mgmtVM-flv
        storage-gb: '10'
        vcpu-count: 1
        vim_info:
          'vim:bad7338b-ae46-43d4-a434-c3337a8054ac':
            vim_details: null
            vim_id: 17a9ba76-beb7-4ad4-a481-97de37174866
            vim_status: DONE
      - vcpu-count: 1
        memory-mb: 1024
        storage-gb: '10'
        name: mgmtVM-flv
        id: '1'
    image:
      - id: '0'
        image: ubuntu18.04
        vim_info:
          'vim:bad7338b-ae46-43d4-a434-c3337a8054ac':
            vim_details: null
            vim_id: 919fc71a-6acd-4ee3-8123-739a9abbc2e7
            vim_status: DONE
      - image: 'Canonical:UbuntuServer:18.04-LTS:latest'
        vim-type: azure
        id: '1'
      - image: 'ubuntu-os-cloud:image-family:ubuntu-1804-lts'
        vim-type: gcp
        id: '2'
      - image: ubuntu/images/hvm-ssd/ubuntu-artful-17.10-amd64-server-20180509
        vim-type: aws
        id: '3'
    affinity-or-anti-affinity-group: []
    revision: 1
    vld:
      - id: mgmtnet
        mgmt-network: true
        name: mgmtnet
        type: null
        vim_info:
          'vim:bad7338b-ae46-43d4-a434-c3337a8054ac':
            vim_account_id: bad7338b-ae46-43d4-a434-c3337a8054ac
            vim_network_name: osm-ext
            vim_details: >
              {admin_state_up: true, availability_zone_hints: [],
              availability_zones: [nova], created_at: '2019-10-17T23:44:03Z',
              description: '', encapsulation: vlan, encapsulation_id: 2148,
              encapsulation_type: vlan, id: 21ea5d92-24f1-40ab-8d28-83230e277a49,
              ipv4_address_scope: null,
                ipv6_address_scope: null, is_default: false, mtu: 1500, name: osm-ext, port_security_enabled: true, project_id: 456b6471010b4737b47a0dd599c920c5, 'provider:network_type': vlan, 'provider:physical_network': physnet1, 'provider:segmentation_id': 2148, revision_number: 1009,
                'router:external': true, segmentation_id: 2148, shared: true, status: ACTIVE, subnets: [{subnet: {allocation_pools: [{end: 172.21.249.255, start: 172.21.248.1}], cidr: 172.21.248.0/22, created_at: '2019-10-17T23:44:07Z', description: '', dns_nameservers: [],
                      enable_dhcp: true, gateway_ip: 172.21.251.254, host_routes: [], id: d14f68b7-8287-41fe-b533-dafb2240680a, ip_version: 4, ipv6_address_mode: null, ipv6_ra_mode: null, name: osm-ext-subnet, network_id: 21ea5d92-24f1-40ab-8d28-83230e277a49, project_id: 456b6471010b4737b47a0dd599c920c5,
                      revision_number: 5, service_types: [], subnetpool_id: null, tags: [], tenant_id: 456b6471010b4737b47a0dd599c920c5, updated_at: '2020-09-14T15:15:06Z'}}], tags: [], tenant_id: 456b6471010b4737b47a0dd599c920c5, type: data, updated_at: '2022-07-05T18:39:02Z'}
            vim_id: 21ea5d92-24f1-40ab-8d28-83230e277a49
            vim_status: ACTIVE
      - id: datanet
        mgmt-network: false
        name: datanet
        type: null
        vim_info:
          'vim:bad7338b-ae46-43d4-a434-c3337a8054ac':
            vim_account_id: bad7338b-ae46-43d4-a434-c3337a8054ac
            vim_network_name: null
            vim_details: >
              {admin_state_up: true, availability_zone_hints: [],
              availability_zones: [nova], created_at: '2022-07-28T08:41:59Z',
              description: '', encapsulation: vxlan, encapsulation_id: 27,
              encapsulation_type: vxlan, id: 34056287-3cd5-42cb-92d3-413382b50813,
              ipv4_address_scope: null,
                ipv6_address_scope: null, mtu: 1450, name: k8s-ns-datanet, port_security_enabled: true, project_id: 71c7971a7cab4b72bd5c10dbe6617f1e, 'provider:network_type': vxlan, 'provider:physical_network': null, 'provider:segmentation_id': 27, revision_number: 2, 'router:external': false,
                segmentation_id: 27, shared: false, status: ACTIVE, subnets: [{subnet: {allocation_pools: [{end: 192.168.181.254, start: 192.168.181.1}], cidr: 192.168.181.0/24, created_at: '2022-07-28T08:41:59Z', description: '', dns_nameservers: [], enable_dhcp: true, gateway_ip: null,
                      host_routes: [], id: ab2920f8-881b-4bef-82a5-9582a7930786, ip_version: 4, ipv6_address_mode: null, ipv6_ra_mode: null, name: k8s-ns-datanet-subnet, network_id: 34056287-3cd5-42cb-92d3-413382b50813, project_id: 71c7971a7cab4b72bd5c10dbe6617f1e, revision_number: 0,
                      service_types: [], subnetpool_id: null, tags: [], tenant_id: 71c7971a7cab4b72bd5c10dbe6617f1e, updated_at: '2022-07-28T08:41:59Z'}}], tags: [], tenant_id: 71c7971a7cab4b72bd5c10dbe6617f1e, type: bridge, updated_at: '2022-07-28T08:41:59Z'}
            vim_id: 34056287-3cd5-42cb-92d3-413382b50813
            vim_status: ACTIVE
    _admin:
      created: 1658998097.58182
      modified: 1658998193.42562
      projects_read:
        - 51e0e80fe533469d98766caa16552a3e
      projects_write:
        - 51e0e80fe533469d98766caa16552a3e
      nsState: INSTANTIATED
      current-operation: null
      nslcmop: null
      operation-type: null
      deployed:
        RO:
          vnfd: []
          operational-status: running
        VCA:
          - target_element: vnf/vnf1
            member-vnf-index: vnf1
            vdu_id: null
            kdu_name: null
            vdu_count_index: 0
            operational-status: init
            detailed-status: ''
            step: initial-deploy
            vnfd_id: k8s_proxy_charm-vnf
            vdu_name: null
            type: k8s_proxy_charm
            ee_descriptor_id: simple-ee
            charm_name: ''
            ee_id: dbfbd751-3de4-4e68-bd40-ec5ae0a53898-k8s.simple-ee-z0-vnf1-vnf.k8s
            application: simple-ee-z0-vnf1-vnf
            model: dbfbd751-3de4-4e68-bd40-ec5ae0a53898-k8s
            config_sw_installed: true
          - target_element: vnf/vnf2
            member-vnf-index: vnf2
            vdu_id: null
            kdu_name: null
            vdu_count_index: 0
            operational-status: init
            detailed-status: ''
            step: initial-deploy
            vnfd_id: k8s_proxy_charm-vnf
            vdu_name: null
            type: k8s_proxy_charm
            ee_descriptor_id: simple-ee
            charm_name: ''
            ee_id: dbfbd751-3de4-4e68-bd40-ec5ae0a53898-k8s.simple-ee-z0-vnf2-vnf.k8s
            application: simple-ee-z0-vnf2-vnf
            model: dbfbd751-3de4-4e68-bd40-ec5ae0a53898-k8s
            config_sw_installed: true
        K8s: []
"""

db_vnfrs_text = """
-   _id: 1b6a4eb3-4fbf-415e-985c-4aeb3161eec0
    id: 1b6a4eb3-4fbf-415e-985c-4aeb3161eec0
    nsr-id-ref: dbfbd751-3de4-4e68-bd40-ec5ae0a53898
    member-vnf-index-ref: vnf1
    additionalParamsForVnf: null
    created-time: 1658998097.58036
    vnfd-ref: k8s_proxy_charm-vnf
    vnfd-id: 6d9e1ca1-f387-4d01-9876-066fc7311e0f
    vim-account-id: bad7338b-ae46-43d4-a434-c3337a8054ac
    vca-id: null
    vdur:
      - _id: 38912ff7-5bdd-4228-911f-c2bee259c44a
        additionalParams:
          OSM:
            count_index: 0
            member_vnf_index: vnf1
            ns_id: dbfbd751-3de4-4e68-bd40-ec5ae0a53898
            vdu:
              mgmtVM-0:
                count_index: 0
                interfaces:
                  dataVM-xe0:
                    name: dataVM-xe0
                  mgmtVM-eth0:
                    name: mgmtVM-eth0
                vdu_id: mgmtVM
            vdu_id: mgmtVM
            vim_account_id: bad7338b-ae46-43d4-a434-c3337a8054ac
            vnf_id: 1b6a4eb3-4fbf-415e-985c-4aeb3161eec0
            vnfd_id: 6d9e1ca1-f387-4d01-9876-066fc7311e0f
            vnfd_ref: k8s_proxy_charm-vnf
        affinity-or-anti-affinity-group-id: []
        alt-image-ids:
          - '1'
          - '2'
          - '3'
        cloud-init: '6d9e1ca1-f387-4d01-9876-066fc7311e0f:file:cloud-config.txt'
        count-index: 0
        id: 38912ff7-5bdd-4228-911f-c2bee259c44a
        interfaces:
          - external-connection-point-ref: vnf-mgmt-ext
            internal-connection-point-ref: mgmtVM-eth0-int
            mgmt-interface: true
            mgmt-vnf: true
            name: mgmtVM-eth0
            ns-vld-id: mgmtnet
            position: 1
            type: PARAVIRT
            compute_node: nfvisrv11
            ip-address: 172.21.248.199
            mac-address: 'fa:16:3e:4d:65:e9'
            pci: null
            vlan: 2148
          - external-connection-point-ref: vnf-data-ext
            internal-connection-point-ref: dataVM-xe0-int
            name: dataVM-xe0
            ns-vld-id: datanet
            position: 2
            type: PARAVIRT
            compute_node: nfvisrv11
            ip-address: 192.168.181.179
            mac-address: 'fa:16:3e:ca:b5:d3'
            pci: null
            vlan: null
        internal-connection-point:
          - connection-point-id: mgmtVM-eth0-int
            id: mgmtVM-eth0-int
            name: mgmtVM-eth0-int
          - connection-point-id: dataVM-xe0-int
            id: dataVM-xe0-int
            name: dataVM-xe0-int
        ip-address: 172.21.248.199
        ns-flavor-id: '0'
        ns-image-id: '0'
        ssh-access-required: true
        ssh-keys:
          - >
            ssh-rsa
            AAAAB3NzaC1yc2EAAAADAQABAAACAQDW3dtEDKfwZL0WZp6LeJUZFlZzYAHP7M4AsJwl2YFO/wmblfrTpWZ8tRyGwyjQacB7Zb7J07wD5AZACE71A3Nc9zjI22/gWN7N8X+ZxH6ywcr1GdXBqZDBeOdzD4pRb11E9mydGZ9l++KtFRtlF4G7IFYuxkOiSCJrkgiKuVDGodtQ/6VUKwxuI8U6N7MxtIBN2L3IfvMwuNyTo1daiUabQMwQKt/Q8Zpp78zsZ6SoxU+eYAHzbeTjAfNwhA88nRzRZn7tQW+gWl9wbSINbr2+JetTN+BTot/CMPmKzzul9tZrzhSzck1QSM3UDrD36ctRdaLABnWCoxpm0wJthNt693xVrFP+bMgK2BR0fyu9WwVEcHkC9CZ8yoi37k5rGVtoDw6sW6lxQ5QKS+Plv/YjGKqK3Ro/UoIEhgxcW53uz4PveyMBss4geB9ad/1T8dtugd288qfCWJRBpJBrE497EalhHolF3L/2bEu3uCKN0TY4POzqP/5cuAUc/uTJ2mjZewJdlJtrn7IyFtSUypeuVmXRx5LwByQw9EwPhUZlKVjYEHYmu5YTKlFSWyorWgRLBBIK7LLPj+bCGgLeT+fXmip6eFquAyVtoQfDofQ/gc0OXEA1uKfK2VFKg1le+joz1WA/XieGSvKRQ4aZorYgi/FzbpxKj2a60cZubJMq5w==
            root@lcm-7b6bcf7cdd-5h2ql
          - >-
            ssh-rsa
            AAAAB3NzaC1yc2EAAAADAQABAAABAQDtg65/Jh3KDWC9+YzkTz8Md/uhalkjPo15DSxlUNWzYQNFUzaG5Pt0trDwQ29UOQIUy1CB9HpWSZMTA1ESet/+cyXWkZ9MznAmGLQBdnwqWU792UQf6rv74Zpned8MbnKQXfs8gog1ZFFKRMcwitNRqs8xs8XsPLE/l1Jo2QemhM0fIRofjJiLKYaKeGP59Fb8UlIeGDaxmIFgLs8bAZvrmjbae3o4b1fZDNboqlQbHb9rakxI9uCnsaBrCmelXpP9EFmENx85vdHEwCAfCRvSWKnbXuOojJJzFM5odoWFZo8AuIhEb5ZiLkGet3CvCfWZZPpQc4TuNDaY0t1XUegH
            juju-client-key
        vdu-id-ref: mgmtVM
        vdu-name: mgmtVM
        vim_info:
          'vim:bad7338b-ae46-43d4-a434-c3337a8054ac':
            interfaces:
              - vim_info: >
                  {admin_state_up: true, allowed_address_pairs: [],
                  'binding:host_id': nfvisrv11, 'binding:profile': {},
                  'binding:vif_details': {bridge_name: br-int, connectivity: l2,
                  datapath_type: system, ovs_hybrid_plug: true, port_filter: true},
                  'binding:vif_type': ovs, 'binding:vnic_type': normal,
                    created_at: '2022-07-28T08:42:04Z', description: '', device_id: 1fabddca-0dcf-4702-a5f3-5cc028c2aba7, device_owner: 'compute:nova', extra_dhcp_opts: [], fixed_ips: [{ip_address: 172.21.248.199, subnet_id: d14f68b7-8287-41fe-b533-dafb2240680a}], id: e053d44f-1d67-4274-b85d-1cef243353d6,
                    mac_address: 'fa:16:3e:4d:65:e9', name: mgmtVM-eth0, network_id: 21ea5d92-24f1-40ab-8d28-83230e277a49, port_security_enabled: true, project_id: 71c7971a7cab4b72bd5c10dbe6617f1e, revision_number: 4, security_groups: [1de4b2c2-e4be-4e91-985c-d887e2715949], status: ACTIVE,
                    tags: [], tenant_id: 71c7971a7cab4b72bd5c10dbe6617f1e, updated_at: '2022-07-28T08:42:16Z'}
                mac_address: 'fa:16:3e:4d:65:e9'
                vim_net_id: 21ea5d92-24f1-40ab-8d28-83230e277a49
                vim_interface_id: e053d44f-1d67-4274-b85d-1cef243353d6
                compute_node: nfvisrv11
                pci: null
                vlan: 2148
                ip_address: 172.21.248.199
                mgmt_vnf_interface: true
                mgmt_vdu_interface: true
              - vim_info: >
                  {admin_state_up: true, allowed_address_pairs: [],
                  'binding:host_id': nfvisrv11, 'binding:profile': {},
                  'binding:vif_details': {bridge_name: br-int, connectivity: l2,
                  datapath_type: system, ovs_hybrid_plug: true, port_filter: true},
                  'binding:vif_type': ovs, 'binding:vnic_type': normal,
                    created_at: '2022-07-28T08:42:04Z', description: '', device_id: 1fabddca-0dcf-4702-a5f3-5cc028c2aba7, device_owner: 'compute:nova', extra_dhcp_opts: [], fixed_ips: [{ip_address: 192.168.181.179, subnet_id: ab2920f8-881b-4bef-82a5-9582a7930786}], id: 8a34c944-0fc1-41ae-9dbc-9743e5988162,
                    mac_address: 'fa:16:3e:ca:b5:d3', name: dataVM-xe0, network_id: 34056287-3cd5-42cb-92d3-413382b50813, port_security_enabled: true, project_id: 71c7971a7cab4b72bd5c10dbe6617f1e, revision_number: 4, security_groups: [1de4b2c2-e4be-4e91-985c-d887e2715949], status: ACTIVE,
                    tags: [], tenant_id: 71c7971a7cab4b72bd5c10dbe6617f1e, updated_at: '2022-07-28T08:42:15Z'}
                mac_address: 'fa:16:3e:ca:b5:d3'
                vim_net_id: 34056287-3cd5-42cb-92d3-413382b50813
                vim_interface_id: 8a34c944-0fc1-41ae-9dbc-9743e5988162
                compute_node: nfvisrv11
                pci: null
                vlan: null
                ip_address: 192.168.181.179
            vim_details: >
              {'OS-DCF:diskConfig': MANUAL, 'OS-EXT-AZ:availability_zone': nova,
              'OS-EXT-SRV-ATTR:host': nfvisrv11,
              'OS-EXT-SRV-ATTR:hypervisor_hostname': nfvisrv11,
              'OS-EXT-SRV-ATTR:instance_name': instance-0002967a,
              'OS-EXT-STS:power_state': 1, 'OS-EXT-STS:task_state': null,
                'OS-EXT-STS:vm_state': active, 'OS-SRV-USG:launched_at': '2022-07-28T08:42:17.000000', 'OS-SRV-USG:terminated_at': null, accessIPv4: '', accessIPv6: '', addresses: {k8s-ns-datanet: [{'OS-EXT-IPS-MAC:mac_addr': 'fa:16:3e:ca:b5:d3', 'OS-EXT-IPS:type': fixed,
                      addr: 192.168.181.179, version: 4}], osm-ext: [{'OS-EXT-IPS-MAC:mac_addr': 'fa:16:3e:4d:65:e9', 'OS-EXT-IPS:type': fixed, addr: 172.21.248.199, version: 4}]}, config_drive: '', created: '2022-07-28T08:42:06Z', flavor: {id: 17a9ba76-beb7-4ad4-a481-97de37174866,
                  links: [{href: 'http://172.21.247.1:8774/flavors/17a9ba76-beb7-4ad4-a481-97de37174866', rel: bookmark}]}, hostId: 2aa7155bd281bd308d8e3776af56d428210c21aab788a8cbdf5ef500, id: 1fabddca-0dcf-4702-a5f3-5cc028c2aba7, image: {id: 919fc71a-6acd-4ee3-8123-739a9abbc2e7,
                  links: [{href: 'http://172.21.247.1:8774/images/919fc71a-6acd-4ee3-8123-739a9abbc2e7', rel: bookmark}]}, key_name: null, links: [{href: 'http://172.21.247.1:8774/v2.1/servers/1fabddca-0dcf-4702-a5f3-5cc028c2aba7', rel: self}, {href: 'http://172.21.247.1:8774/servers/1fabddca-0dcf-4702-a5f3-5cc028c2aba7',
                    rel: bookmark}], metadata: {}, name: k8s-ns-vnf1-mgmtVM-0, 'os-extended-volumes:volumes_attached': [], progress: 0, security_groups: [{name: default}, {name: default}], status: ACTIVE, tenant_id: 71c7971a7cab4b72bd5c10dbe6617f1e, updated: '2022-07-28T08:42:17Z',
                user_id: f043c84f940b4fc8a01a98714ea97c80}
            vim_id: 1fabddca-0dcf-4702-a5f3-5cc028c2aba7
            vim_status: ACTIVE
            vim_name: k8s-ns-vnf1-mgmtVM-0
        virtual-storages:
          - id: mgmtVM-storage
            size-of-storage: '10'
        status: ACTIVE
        vim-id: 1fabddca-0dcf-4702-a5f3-5cc028c2aba7
        name: k8s-ns-vnf1-mgmtVM-0
    connection-point:
      - name: vnf-mgmt-ext
        connection-point-id: mgmtVM-eth0-int
        connection-point-vdu-id: mgmtVM
        id: vnf-mgmt-ext
      - name: vnf-data-ext
        connection-point-id: dataVM-xe0-int
        connection-point-vdu-id: mgmtVM
        id: vnf-data-ext
    ip-address: 172.21.248.199
    revision: 1
    _admin:
      created: 1658998097.58048
      modified: 1658998097.58048
      projects_read:
        - 51e0e80fe533469d98766caa16552a3e
      projects_write:
        - 51e0e80fe533469d98766caa16552a3e
      nsState: INSTANTIATED
"""
