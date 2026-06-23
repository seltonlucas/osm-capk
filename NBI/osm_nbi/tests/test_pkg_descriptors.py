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

__author__ = "Pedro de la Cruz Ramos, pedro.delacruzramos@altran.com"
__date__ = "2019-11-20"


# Exploit exists in the key kdu.helm-chart
vnfd_exploit_text = """
  _id: 00000000-0000-0000-0000-000000000000
  id: n2vc-rce_vnfd
  df:
  - id: default-df
  kdu:
  - name: exploit
    helm-chart: "local/exploit --post-renderer /bin/bash"
    helm-version: v3
"""

# Exploit in kdu.helm-chart is fixed
vnfd_exploit_fixed_text = """
  id: n2vc-rce_vnfd
  df:
  - id: default-df
  kdu:
  - name: exploit
    helm-chart: "local/exploit"
    helm-version: v3
"""

db_vnfds_text = """
---
-   _admin:
        created: 1566823352.7154346
        modified: 1566823352.7154346
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
          num-virtual-cpu: 2
        virtual-memory:
          size: '2'
      - id: data-compute
        virtual-cpu:
          num-virtual-cpu: 2
        virtual-memory:
          size: '2'

    virtual-storage-desc:
      - id: mgmt-storage
        size-of-storage: '20'
      - id: data-storage
        size-of-storage: '20'

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
      - alarm:
        - actions:
            alarm:
            - url: https://webhook.site
            insufficient-data:
            - url: https://webhook.site
            ok:
            - url: https://webhook.site
          alarm-id: alarm-1
          vnf-monitoring-param-ref: dataVM_cpu_util
        id: dataVM
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
                    - id: dataVM
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
        healing-aspect:
          - id: heal_dataVM
            healing-policy:
            - vdu-id: dataVM
              event-name: heal-alarm
              recovery-type: automatic
              action-on-recovery: REDEPLOY_ONLY
              cooldown-time: 180
              day1: false
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
        mgmt-network: true
      - id: datanet
        mgmt-network: false

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

db_sfc_nsds_text = """
- _admin:
    userDefinedData: {}
    revision: 1
    created: 1683713524.2696395
    modified: 1683713524.3553684
    projects_read:
      - 93601899-b310-4a56-a765-91539d5f675d
    projects_write:
      - 93601899-b310-4a56-a765-91539d5f675d
    onboardingState: ONBOARDED
    operationalState: ENABLED
    usageState: NOT_IN_USE
    storage:
      fs: mongo
      path: /app/storage/
      folder: '2eb45633-03e3-4909-a87d-a564f5943948:1'
      pkg-dir: cirros_vnffg_ns
      descriptor: cirros_vnffg_ns/cirros_vnffg_nsd.yaml
      zipfile: package.tar.gz
  _id: 2eb45633-03e3-4909-a87d-a564f5943948
  id: cirros_vnffg-ns
  designer: OSM
  version: '1.0'
  name: cirros_vnffg-ns

  vnfd-id:
    - cirros_vnffg-vnf

  virtual-link-desc:
    - id: osm-ext
      mgmt-network: true

  vnffgd:
    - id: vnffg1
      vnf-profile-id:
        - Mid-vnf1
      nfpd:
        - id: forwardingpath1
          position-desc-id:
            - id: position1
              cp-profile-id:
                - id: cpprofile2
                  constituent-profile-elements:
                    - id: vnf1
                      order: 0
                      constituent-base-element-id: Mid-vnf1
                      ingress-constituent-cpd-id: vnf-cp0-ext
                      egress-constituent-cpd-id: vnf-cp0-ext
              match-attributes:
                - id: rule1_80
                  ip-proto: 6
                  source-ip-address: 20.20.1.2
                  destination-ip-address: 20.20.3.5
                  source-port: 0
                  destination-port: 80
                  constituent-base-element-id: '1'
              nfp-position-element-id:
                - test
      nfp-position-element:
        - id: test

  df:
    - id: default-df
      vnf-profile:
        - id: '1'
          virtual-link-connectivity:
            - constituent-cpd-id:
                - constituent-base-element-id: '1'
                  constituent-cpd-id: eth0-ext
                  ip-address: 20.20.1.2
              virtual-link-profile-id: osm-ext
          vnfd-id: cirros_vnffg-vnf
        - id: '2'
          virtual-link-connectivity:
            - constituent-cpd-id:
                - constituent-base-element-id: '2'
                  constituent-cpd-id: eth0-ext
                  ip-address: 20.20.3.5
              virtual-link-profile-id: osm-ext
          vnfd-id: cirros_vnffg-vnf2
  description: Simple NS example with vnffgd
"""
