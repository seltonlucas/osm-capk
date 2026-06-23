#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# For those usages not covered by the Apache License, Version 2.0 please
# contact: esousa@whitestack.com or alfonso.tiernosepulveda@telefonica.com
##

"""Contains database content needed for tests"""


db_vim_accounts_text = """
---
-   _admin:
        created: 1566818150.3024442
        current_operation: 0
        deployed:
            RO: dc51ce6c-c7f2-11e9-b9c0-02420aff0004
            RO-account: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
        detailed-status: Done
        modified: 1566818150.3024442
        operationalState: ENABLED
        operations:
        -   detailed-status: Done
            lcmOperationType: create
            operationParams: null
            operationState: COMPLETED
            startTime: 1566818150.3025382
            statusEnteredTime: 1566818150.3025382
            worker: 86434c2948e2
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    description: Openstack site 2, based on Mirantis, also called DSS9000-1, with
        tenant tid
    name: ost2-mrt-tid
    schema_version: '1.1'
    vim_password: 5g0yGX86qIhprX86YTMcpg==
    vim_tenant_name: osm
    vim_type: openstack
    vim_url: http://10.95.87.162:5000/v2.0
    vim_user: osm
"""

db_vnfds_text = """
---
-   _admin:
        created: 1566823352.7154346
        modified: 1566823353.9295402
        onboardingState: ONBOARDED
        operationalState: ENABLED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        storage:
            descriptor: hackfest_3charmed_vnfd/hackfest_3charmed_vnfd.yaml
            folder: 7637bcf8-cf14-42dc-ad70-c66fcf1e6e77
            fs: local
            path: /app/storage/
            pkg-dir: hackfest_3charmed_vnfd
            zipfile: package.tar.gz
        type: vnfd
        usageState: NOT_IN_USE
        userDefinedData: {}
    _id: 7637bcf8-cf14-42dc-ad70-c66fcf1e6e77
    id: hackfest3charmed-vnf
    description: >-
      A VNF consisting of 2 VDUs connected to an internal VL, and one VDU with
      cloud-init
    product-name: hackfest3charmed-vnf
    version: '1.0'
    mgmt-cp: vnf-mgmt-ext
  
    virtual-compute-desc:
      - id: mgmt-compute
        virtual-cpu:
          num-virtual-cpu: 1
        virtual-memory:
          size: 1
      - id: data-compute
        virtual-cpu:
          num-virtual-cpu: 1
        virtual-memory:
          size: 1
  
    virtual-storage-desc:
      - id: mgmt-storage
        size-of-storage: 10
      - id: data-storage
        size-of-storage: 10
  
    sw-image-desc:
      - id: hackfest3-mgmt
        name: hackfest3-mgmt
  
    vdu:
      - id: mgmtVM
        name: mgmtVM
        cloud-init-file: cloud-config.txt
        sw-image-desc: hackfest3-mgmt
        virtual-compute-desc: mgmt-compute
        virtual-storage-desc:
          - mgmt-storage
        int-cpd:
          - id: vnf-mgmt
            virtual-network-interface-requirement:
              - name: mgmtVM-eth0
                position: 1
                virtual-interface:
                  type: VIRTIO
          - id: mgmtVM-internal
            int-virtual-link-desc: internal
            virtual-network-interface-requirement:
              - name: mgmtVM-eth1
                position: 2
                virtual-interface:
                  type: VIRTIO
      - id: dataVM
        name: dataVM
        sw-image-desc: hackfest3-mgmt
        virtual-compute-desc: data-compute
        virtual-storage-desc:
          - data-storage
        int-cpd:
          - id: dataVM-internal
            int-virtual-link-desc: internal
            virtual-network-interface-requirement:
              - name: dataVM-eth1
                position: 1
                virtual-interface:
                  type: VIRTIO
          - id: vnf-data
            virtual-network-interface-requirement:
              - name: dataVM-eth0
                position: 2
                virtual-interface:
                  type: VIRTIO
        monitoring-parameter:
          - id: dataVM_cpu_util
            name: dataVM_cpu_util
            performance-metric: cpu_utilization
  
    int-virtual-link-desc:
      - id: internal
  
    ext-cpd:
      - id: vnf-mgmt-ext
        int-cpd: # Connection to int-cpd
          vdu-id: mgmtVM
          cpd: vnf-mgmt
      - id: vnf-data-ext
        int-cpd: # Connection to int-cpd
          vdu-id: dataVM
          cpd: vnf-data
  
    df:
      - id: hackfest_default
        vdu-profile:
          - id: mgmtVM
            min-number-of-instances: 1
          - id: dataVM
            min-number-of-instances: 1
            max-number-of-instances: 10
        instantiation-level:
          - id: default
            vdu-level:
              - vdu-id: mgmtVM
                number-of-instances: 1
              - vdu-id: dataVM
                number-of-instances: 1
        scaling-aspect:
          - id: scale_dataVM
            name: scale_dataVM
            max-scale-level: 10
            aspect-delta-details:
              deltas:
                - id: delta1
                  vdu-delta:
                    - id: vdudelta1
                      number-of-instances: 1
            scaling-policy:
              - name: auto_cpu_util_above_threshold
                scaling-type: automatic
                enabled: true
                threshold-time: 0
                cooldown-time: 60
                scaling-criteria:
                  - name: cpu_util_above_threshold
                    scale-in-relational-operation: LE
                    scale-in-threshold: '15.0000000000'
                    scale-out-relational-operation: GE
                    scale-out-threshold: '60.0000000000'
                    vnf-monitoring-param-ref: dataVM_cpu_util
            scaling-config-action:
              - trigger: post-scale-out
                vnf-config-primitive-name-ref: touch
              - trigger: pre-scale-in
                vnf-config-primitive-name-ref: touch
        lcm-operations-configuration:
          operate-vnf-op-config:
            day1-2:
            - id: hackfest3charmed-vnf
              execution-environment-list:
                - id: simple-ee
                  juju:
                    charm: simple
              initial-config-primitive:
                - seq: "1"
                  execution-environment-ref: simple-ee
                  name: config
                  parameter:
                    - name: ssh-hostname
                      value: <rw_mgmt_ip>
                    - name: ssh-username
                      value: ubuntu
                    - name: ssh-password
                      value: osm4u
                - seq: "2"
                  execution-environment-ref: simple-ee
                  name: touch
                  parameter:
                    - name: filename
                      value: <touch_filename>
              config-primitive:
                - name: touch
                  execution-environment-ref: simple-ee
                  parameter:
                    - data-type: STRING
                      default-value: <touch_filename2>
                      name: filename
"""

db_nsds_text = """
---
-   _admin:
        created: 1566823353.971486
        modified: 1566823353.971486
        onboardingState: ONBOARDED
        operationalState: ENABLED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        storage:
            descriptor: hackfest_3charmed_nsd/hackfest_3charmed_nsd.yaml
            folder: 8c2f8b95-bb1b-47ee-8001-36dc090678da
            fs: local
            path: /app/storage/
            pkg-dir: hackfest_3charmed_nsd
            zipfile: package.tar.gz
        usageState: NOT_IN_USE
        userDefinedData: {}
    _id: 8c2f8b95-bb1b-47ee-8001-36dc090678da
    id: hackfest3charmed-ns
    name: hackfest3charmed-ns
    description: NS with 2 VNFs hackfest3charmed-vnf connected by datanet and mgmtnet VLs
    designer: OSM
    version: '1.0'

    vnfd-id:
      - hackfest3charmed-vnf

    virtual-link-desc:
      - id: mgmt
        mgmt-network: "true"
      - id: datanet
        mgmt-network: "false"

    df:
      - id: hackfest_charmed_DF
        vnf-profile:
          - id: hackfest_vnf1 # member-vnf-index-ref: 1
            vnfd-id: hackfest3charmed-vnf
            virtual-link-connectivity:
              - virtual-link-profile-id: mgmt
                constituent-cpd-id:
                  - constituent-base-element-id: hackfest_vnf1
                    constituent-cpd-id: vnf-mgmt-ext
              - virtual-link-profile-id: datanet
                constituent-cpd-id:
                  - constituent-base-element-id: hackfest_vnf1
                    constituent-cpd-id: vnf-data-ext
          - id: hackfest_vnf2 # member-vnf-index-ref: 2
            vnfd-id: hackfest3charmed-vnf
            virtual-link-connectivity:
              - virtual-link-profile-id: mgmt
                constituent-cpd-id:
                  - constituent-base-element-id: hackfest_vnf2
                    constituent-cpd-id: vnf-mgmt-ext
              - virtual-link-profile-id: datanet
                constituent-cpd-id:
                  - constituent-base-element-id: hackfest_vnf2
                    constituent-cpd-id: vnf-data-ext
"""

db_nsrs_text = """
---
-   _admin:
        created: 1566823354.3716335
        modified: 1566823354.3716335
        nsState: NOT_INSTANTIATED
        nslcmop: null
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: f48163a6-c807-47bc-9682-f72caef5af85
    additionalParamsForNs: null
    admin-status: ENABLED
    config-status: init
    constituent-vnfr-ref:
    - 88d90b0c-faff-4b9f-bccd-017f33985984
    - 1ca3bb1a-b29b-49fe-bed6-5f3076d77434
    create-time: 1566823354.36234
    datacenter: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    description: default description
    detailed-status: 'ERROR executing proxy charm initial primitives for member_vnf_index=1
        vdu_id=None: charm error executing primitive verify-ssh-credentials for member_vnf_index=1
        vdu_id=None: ''timeout after 600 seconds'''
    id: f48163a6-c807-47bc-9682-f72caef5af85
    instantiate_params:
        nsDescription: default description
        nsName: ALF
        nsdId: 8c2f8b95-bb1b-47ee-8001-36dc090678da
        vimAccountId: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    name: ALF
    name-ref: ALF
    ns-instance-config-ref: f48163a6-c807-47bc-9682-f72caef5af85
    nsd:
        _admin:
            created: 1566823353.971486
            modified: 1566823353.971486
            onboardingState: ONBOARDED
            operationalState: ENABLED
            projects_read:
            - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
            projects_write:
            - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
            storage:
                descriptor: hackfest_3charmed_nsd/hackfest_3charmed_nsd.yaml
                folder: 8c2f8b95-bb1b-47ee-8001-36dc090678da
                fs: local
                path: /app/storage/
                pkg-dir: hackfest_3charmed_nsd
                zipfile: package.tar.gz
            usageState: NOT_IN_USE
            userDefinedData: {}
        _id: 8c2f8b95-bb1b-47ee-8001-36dc090678da
        id: hackfest3charmed-ns
        name: hackfest3charmed-ns
        description: NS with 2 VNFs hackfest3charmed-vnf connected by datanet and mgmtnet VLs
        designer: OSM
        version: '1.0'

        vnfd-id:
          - hackfest3charmed-vnf

        virtual-link-desc:
          - id: mgmt
            mgmt-network: "true"
          - id: datanet
            mgmt-network: "false"

        df:
          - id: hackfest_charmed_DF
            vnf-profile:
              - id: hackfest_vnf1 # member-vnf-index-ref: 1
                vnfd-id: hackfest3charmed-vnf
                virtual-link-connectivity:
                  - virtual-link-profile-id: mgmt
                    constituent-cpd-id:
                      - constituent-base-element-id: hackfest_vnf1
                        constituent-cpd-id: vnf-mgmt-ext
                  - virtual-link-profile-id: datanet
                    constituent-cpd-id:
                      - constituent-base-element-id: hackfest_vnf1
                        constituent-cpd-id: vnf-data-ext
              - id: hackfest_vnf2 # member-vnf-index-ref: 2
                vnfd-id: hackfest3charmed-vnf
                virtual-link-connectivity:
                  - virtual-link-profile-id: mgmt
                    constituent-cpd-id:
                      - constituent-base-element-id: hackfest_vnf2
                        constituent-cpd-id: vnf-mgmt-ext
                  - virtual-link-profile-id: datanet
                    constituent-cpd-id:
                      - constituent-base-element-id: hackfest_vnf2
                        constituent-cpd-id: vnf-data-ext
    nsd-id: 8c2f8b95-bb1b-47ee-8001-36dc090678da
    nsd-name-ref: hackfest3charmed-ns
    nsd-ref: hackfest3charmed-ns
    operational-events: []
    operational-status: failed
    orchestration-progress: {}
    resource-orchestrator: osmopenmano
    short-name: ALF
    ssh-authorized-key: null
    vld:
    -   id: mgmt
        name: null
        status: ACTIVE
        status-detailed: null
        vim-id: f99ae780-0e2f-4985-af41-574eae6919c0
        vim-network-name: mgmt
    -   id: datanet
        name: ALF-datanet
        status: ACTIVE
        status-detailed: null
        vim-id: c31364ba-f573-4ab6-bf1a-fed30ede39a8
    vnfd-id:
    - 7637bcf8-cf14-42dc-ad70-c66fcf1e6e77
"""

db_nslcmops_text = """
---
-   _admin:
        created: 1566823354.4148262
        modified: 1566823354.4148262
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        worker: 86434c2948e2
    _id: a639fac7-e0bb-4225-8ecb-c1f8efcc125e
    detailed-status: 'FAILED executing proxy charm initial primitives for member_vnf_index=1
        vdu_id=None: charm error executing primitive verify-ssh-credentials for member_vnf_index=1
        vdu_id=None: ''timeout after 600 seconds'''
    id: a639fac7-e0bb-4225-8ecb-c1f8efcc125e
    isAutomaticInvocation: false
    isCancelPending: false
    lcmOperationType: instantiate
    links:
        nsInstance: /osm/nslcm/v1/ns_instances/f48163a6-c807-47bc-9682-f72caef5af85
        self: /osm/nslcm/v1/ns_lcm_op_occs/a639fac7-e0bb-4225-8ecb-c1f8efcc125e
    nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
    operationParams:
        additionalParamsForVnf:
        -   additionalParams:
                touch_filename: /home/ubuntu/first-touch-1
                touch_filename2: /home/ubuntu/second-touch-1
            member-vnf-index: '1'
        -   additionalParams:
                touch_filename: /home/ubuntu/first-touch-2
                touch_filename2: /home/ubuntu/second-touch-2
            member-vnf-index: '2'
        lcmOperationType: instantiate
        nsDescription: default description
        nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
        nsName: ALF
        nsdId: 8c2f8b95-bb1b-47ee-8001-36dc090678da
        vimAccountId: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    operationState: FAILED
    startTime: 1566823354.414689
    statusEnteredTime: 1566824534.5112448
"""

db_vnfrs_text = """
---
-   _admin:
        created: 1566823354.3668208
        modified: 1566823354.3668208
        nsState: NOT_INSTANTIATED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 88d90b0c-faff-4b9f-bccd-017f33985984
    additionalParamsForVnf:
        touch_filename: /home/ubuntu/first-touch-1
        touch_filename2: /home/ubuntu/second-touch-1
    connection-point:
    -   connection-point-id: vnf-mgmt
        id: vnf-mgmt
        name: vnf-mgmt
    -   connection-point-id: vnf-data
        id: vnf-data
        name: vnf-data
    created-time: 1566823354.36234
    id: 88d90b0c-faff-4b9f-bccd-017f33985984
    ip-address: 10.205.1.46
    member-vnf-index-ref: '1'
    nsr-id-ref: f48163a6-c807-47bc-9682-f72caef5af85
    vdur:
    -   _id: f0e7d7ce-2443-4dcb-ad0b-5ab9f3b13d37
        count-index: 0
        interfaces:
        -   ip-address: 10.205.1.46
            mac-address: fa:16:3e:b4:3e:b1
            mgmt-vnf: true
            name: mgmtVM-eth0
            ns-vld-id: mgmt
            position: 1
        -   ip-address: 192.168.54.2
            mac-address: fa:16:3e:6e:7e:78
            name: mgmtVM-eth1
            vnf-vld-id: internal
            position: 2
        internal-connection-point:
        -   connection-point-id: mgmtVM-internal
            id: mgmtVM-internal
            name: mgmtVM-internal
        ip-address: 10.205.1.46
        name: ALF-1-mgmtVM-1
        status: ACTIVE
        status-detailed: null
        vdu-id-ref: mgmtVM
        vim-id: c2538499-4c30-41c0-acd5-80cb92f48061
    -   _id: ab453219-2d9a-45c2-864d-2c0788385028
        count-index: 0
        interfaces:
        -   ip-address: 192.168.54.3
            mac-address: fa:16:3e:d9:7a:5d
            name: dataVM-eth0
            vnf-vld-id: internal
        -   ip-address: 192.168.24.3
            mac-address: fa:16:3e:d1:6c:0d
            name: dataVM-xe0
            ns-vld-id: datanet
        internal-connection-point:
        -   connection-point-id: dataVM-internal
            id: dataVM-internal
            name: dataVM-internal
        ip-address: null
        name: ALF-1-dataVM-1
        status: ACTIVE
        status-detailed: null
        vdu-id-ref: dataVM
        vim-id: 87973c3f-365d-4227-95c2-7a8abc74349c
    vim-account-id: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    vld:
    -   id: internal
        name: ALF-internal
        status: ACTIVE
        status-detailed: null
        vim-id: ff181e6d-2597-4244-b40b-bb0174bdfeb6
    vnfd-id: 7637bcf8-cf14-42dc-ad70-c66fcf1e6e77
    vnfd-ref: hackfest3charmed-vnf
-   _admin:
        created: 1566823354.3703845
        modified: 1566823354.3703845
        nsState: NOT_INSTANTIATED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 1ca3bb1a-b29b-49fe-bed6-5f3076d77434
    additionalParamsForVnf:
        touch_filename: /home/ubuntu/first-touch-2
        touch_filename2: /home/ubuntu/second-touch-2
    connection-point:
    -   connection-point-id: vnf-mgmt
        id: vnf-mgmt
        name: vnf-mgmt
    -   connection-point-id: vnf-data
        id: vnf-data
        name: vnf-data
    created-time: 1566823354.36234
    id: 1ca3bb1a-b29b-49fe-bed6-5f3076d77434
    ip-address: 10.205.1.47
    member-vnf-index-ref: '2'
    nsr-id-ref: f48163a6-c807-47bc-9682-f72caef5af85
    vdur:
    -   _id: 190b4a2c-4f85-4cfe-9406-4cef7ffb1e67
        count-index: 0
        interfaces:
        -   ip-address: 10.205.1.47
            mac-address: fa:16:3e:cb:9f:c7
            mgmt-vnf: true
            name: mgmtVM-eth0
            ns-vld-id: mgmt
        -   ip-address: 192.168.231.1
            mac-address: fa:16:3e:1a:89:24
            name: mgmtVM-eth1
            vnf-vld-id: internal
        internal-connection-point:
        -   connection-point-id: mgmtVM-internal
            id: mgmtVM-internal
            name: mgmtVM-internal
        ip-address: 10.205.1.47
        name: ALF-2-mgmtVM-1
        status: ACTIVE
        status-detailed: null
        vdu-id-ref: mgmtVM
        vim-id: 248077b2-e3b8-4a37-8b72-575abb8ed912
    -   _id: 889b874d-e1c3-4e75-aa45-53a9b0ddabd9
        count-index: 0
        interfaces:
        -   ip-address: 192.168.231.3
            mac-address: fa:16:3e:7e:ba:8c
            name: dataVM-eth0
            vnf-vld-id: internal
        -   ip-address: 192.168.24.4
            mac-address: fa:16:3e:d2:e1:f5
            name: dataVM-xe0
            ns-vld-id: datanet
        internal-connection-point:
        -   connection-point-id: dataVM-internal
            id: dataVM-internal
            name: dataVM-internal
        ip-address: null
        name: ALF-2-dataVM-1
        status: ACTIVE
        status-detailed: null
        vdu-id-ref: dataVM
        vim-id: a4ce4372-e0ad-4ae3-8f9f-1c969f32e77b
    vim-account-id: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    vld:
    -   id: internal
        name: ALF-internal
        status: ACTIVE
        status-detailed: null
        vim-id: ff181e6d-2597-4244-b40b-bb0174bdfeb6
    vnfd-id: 7637bcf8-cf14-42dc-ad70-c66fcf1e6e77
    vnfd-ref: hackfest3charmed-vnf
"""

db_vnfm_vnfd_text = """
---
-   _admin:
        created: 1647529096.3635302
        modified: 1650456936.518325
        onboardingState: ONBOARDED
        operationalState: ENABLED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        storage:
            descriptor: hackfest_basic_metrics_vnf/hackfest_basic_metrics_vnfd.yaml
            folder: 70b47595-fafa-4f63-904b-fc3ada60eebb
            fs: mongo
            path: /app/storage/
            pkg-dir: hackfest_basic_metrics_vnf
            zipfile: package.tar.gz
        type: vnfd
        usageState: NOT_IN_USE
        userDefinedData: {}
    _id: 70b47595-fafa-4f63-904b-fc3ada60eebb
    _links:
        packageContent:
            href: /vnfpkgm/v1/vnf_packages/70b47595-fafa-4f63-904b-fc3ada60eebb/package_content
        self:
            href: /vnfpkgm/v1/vnf_packages/70b47595-fafa-4f63-904b-fc3ada60eebb
        vnfd:
            href: /vnfpkgm/v1/vnf_packages/70b47595-fafa-4f63-904b-fc3ada60eebb/vnfd
    description: A basic VNF descriptor with one VDU and VIM metrics
    df:
    -   id: default-df
        instantiation-level:
        -   id: default-instantiation-level
            vdu-level:
            -   number-of-instances: 1
                vdu-id: hackfest_basic_metrics-VM
        scaling-aspect:
        -   aspect-delta-details:
                deltas:
                -   id: vdu_autoscale-delta
                    vdu-delta:
                    -   id: hackfest_basic_metrics-VM
                        number-of-instances: 1
            id: vdu_autoscale
            max-scale-level: 1
            name: vdu_autoscale
            scaling-policy:
            -   cooldown-time: 120
                name: cpu_util_above_threshold
                scaling-criteria:
                -   name: cpu_util_above_threshold
                    scale-in-relational-operation: LT
                    scale-in-threshold: '10.0000000000'
                    scale-out-relational-operation: GT
                    scale-out-threshold: '60.0000000000'
                    vnf-monitoring-param-ref: vnf_cpu_util
                scaling-type: automatic
                threshold-time: 10
        vdu-profile:
        -   id: hackfest_basic_metrics-VM
            max-number-of-instances: 2
            min-number-of-instances: 1
    ext-cpd:
    -   id: vnf-cp0-ext
        int-cpd:
            cpd: vdu-eth0-int
            vdu-id: hackfest_basic_metrics-VM
    id: hackfest_basic_metrics-vnf
    mgmt-cp: vnf-cp0-ext
    onboardingState: ONBOARDED
    operationalState: ENABLED
    product-name: hackfest_basic_metrics-vnf
    sw-image-desc:
    -   id: bionic
        image: bionic
        name: bionic
    -   id: ubuntu18.04-aws
        image: ubuntu/images/hvm-ssd/ubuntu-artful-17.10-amd64-server-20180509
        name: ubuntu18.04-aws
        vim-type: aws
    -   id: ubuntu18.04-azure
        image: Canonical:UbuntuServer:18.04-LTS:latest
        name: ubuntu18.04-azure
        vim-type: azure
    -   id: ubuntu18.04-gcp
        image: ubuntu-os-cloud:image-family:ubuntu-1804-lts
        name: ubuntu18.04-gcp
        vim-type: gcp
    usageState: NOT_IN_USE
    vdu:
    -   alarm:
        -   actions:
                alarm:
                -   url: https://webhook.site/b79f9bf9-4c19-429d-81ed-19be26a3d5d8
                insufficient-data:
                -   url: https://webhook.site/b79f9bf9-4c19-429d-81ed-19be26a3d5d8
                ok:
                -   url: https://webhook.site/b79f9bf9-4c19-429d-81ed-19be26a3d5d8
            alarm-id: alarm-1
            operation: LT
            value: '20.0000'
            vnf-monitoring-param-ref: vnf_cpu_util
        alternative-sw-image-desc:
        - ubuntu18.04-aws
        - ubuntu18.04-azure
        - ubuntu18.04-gcp
        cloud-init-file: cloud-config
        id: hackfest_basic_metrics-VM
        int-cpd:
        -   id: vdu-eth0-int
            virtual-network-interface-requirement:
            -   name: vdu-eth0
                virtual-interface:
                    type: PARAVIRT
        monitoring-parameter:
        -   id: vnf_cpu_util
            name: vnf_cpu_util
            performance-metric: cpu_utilization
        -   id: vnf_memory_util
            name: vnf_memory_util
            performance-metric: average_memory_utilization
        -   id: vnf_packets_sent
            name: vnf_packets_sent
            performance-metric: packets_sent
        -   id: vnf_packets_received
            name: vnf_packets_received
            performance-metric: packets_received
        name: hackfest_basic_metrics-VM
        sw-image-desc: bionic
        virtual-compute-desc: hackfest_basic_metrics-VM-compute
        virtual-storage-desc:
        - hackfest_basic_metrics-VM-storage
    version: '1.0'
    virtual-compute-desc:
    -   id: hackfest_basic_metrics-VM-compute
        virtual-cpu:
            num-virtual-cpu: 1
        virtual-memory:
            size: 1.0
    virtual-storage-desc:
    -   id: hackfest_basic_metrics-VM-storage
        size-of-storage: '10'
"""
