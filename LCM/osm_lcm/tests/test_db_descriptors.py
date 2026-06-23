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
    constituent-vnfd:
    -   member-vnf-index: '1'
        vnfd-id-ref: hackfest3charmed-vnf
    -   member-vnf-index: '2'
        vnfd-id-ref: hackfest3charmed-vnf
    description: NS with 2 VNFs hackfest3charmed-vnf connected by datanet and mgmtnet VLs
    df:
    - id: default-df
      vnf-profile:
      - id: '1'
        virtual-link-connectivity:
        - constituent-cpd-id:
          - constituent-base-element-id: '1'
            constituent-cpd-id: vnf-mgmt-ext
          virtual-link-profile-id: mgmt
        - constituent-cpd-id:
          - constituent-base-element-id: '1'
            constituent-cpd-id: vnf-data-ext
          virtual-link-profile-id: datanet
        vnfd-id: hackfest3charmed-vnf
      - id: '2'
        virtual-link-connectivity:
        - constituent-cpd-id:
          - constituent-base-element-id: '2'
            constituent-cpd-id: vnf-mgmt-ext
          virtual-link-profile-id: mgmt
        - constituent-cpd-id:
          - constituent-base-element-id: '2'
            constituent-cpd-id: vnf-data-ext
          virtual-link-profile-id: datanet
        vnfd-id: hackfest3charmed-vnf
    id: hackfest3charmed-ns
    name: hackfest3charmed-ns
    version: '1.0'
    virtual-link-desc:
    - id: mgmt
      mgmt-network: true
      vim-network-name: mgmt
    - id: datanet
    vnfd-id:
    - hackfest3charmed-vnf

-   _admin:
        created: 1575031728.9257665
        modified: 1575031728.9257665
        onboardingState: ONBOARDED
        operationalState: ENABLED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        storage:
            descriptor: multikdu_ns/multikdu_nsd.yaml
            folder: d0f63683-9032-4c6f-8928-ffd4674b9f69
            fs: local
            path: /app/storage/
            pkg-dir: multikdu_ns
            zipfile: multikdu_ns.tar.gz
        usageState: NOT_IN_USE
        userDefinedData: {}
    _id: d0f63683-9032-4c6f-8928-ffd4674b9f69
    constituent-vnfd:
    -   member-vnf-index: multikdu
        vnfd-id-ref: multikdu_knf
    description: NS consisting of a single KNF multikdu_knf connected to mgmt network
    id: multikdu_ns
    logo: osm.png
    name: multikdu_ns
    short-name: multikdu_ns
    vendor: OSM
    version: '1.0'
    vld:
    -   id: mgmtnet
        mgmt-network: true
        name: mgmtnet
        type: ELAN
        vim-network-name: mgmt
        vnfd-connection-point-ref:
        -   member-vnf-index-ref: multikdu
            vnfd-connection-point-ref: mgmt
            vnfd-id-ref: multikdu_knf
"""

db_nslcmops_text = """
---
-   _admin:
        created: 1651100375.77829
        modified: 1651100481.36625
        projects_read:
        - 7f563445c74147f78e29b193a6da42bb
        projects_write:
        - 7f563445c74147f78e29b193a6da42bb
        worker: a5adf5972b63
    detailed-status: success
    _id: 6bd4362f-da74-4bd8-a825-fd00e610c644
    id: 6bd4362f-da74-4bd8-a825-fd00e610c644
    operationState: COMPLETED
    queuePosition: 0
    stage: ''
    errorMessage: ''
    detailedStatus:
    statusEnteredTime: 1651100481.36625
    nsInstanceId: 7e3ad9ce-39b8-4636-a661-7870f25bf800
    lcmOperationType: update
    startTime: 1651100375.77823
    isAutomaticInvocation: false
    operationParams:
        updateType: CHANGE_VNFPKG
        changeVnfPackageData:
            vnfInstanceId: 6421c7c9-d865-4fb4-9a13-d4275d243e01
            vnfdId: 7637bcf8-cf14-42dc-ad70-c66fcf1e6e77
        lcmOperationType: update
        nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
    isCancelPending: false
    links:
        self: "/osm/nslcm/v1/ns_lcm_op_occs/6bd4362f-da74-4bd8-a825-fd00e610c644"
        nsInstance: "/osm/nslcm/v1/ns_instances/f48163a6-c807-47bc-9682-f72caef5af85"       
-   _admin:
        created: 1566823354.4148262
        modified: 1566823354.4148262
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        worker: 86434c2948e2
        operations:
        -   member_vnf_index: '1'
            primitive: touch
            primitive_params: /home/ubuntu/last-touch-1
            operationState: COMPLETED
            detailed-status: Done
        -   member_vnf_index: '1'
            primitive: touch
            primitive_params: /home/ubuntu/last-touch-2
            operationState: COMPLETED
            detailed-status: Done
        -   member_vnf_index: '2'
            primitive: touch
            primitive_params: /home/ubuntu/last-touch-3
            operationState: FAILED
            detailed-status: Unknown error
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

-   _admin:
        created: 1600000000.0000000
        modified: 1600000000.0000000
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        worker: 86434c2948e2
    _id: a639fac7-e0bb-4225-ffff-c1f8efcc125e
    detailed-status: None
    lcmOperationType: terminate
    nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
    operationParams: {}
    operationState: PROCESSING
    startTime: 1600000000.0000000
    statusEnteredTime: 1600000000.0000000
    
-   _admin:
        created: 1575034637.044651
        modified: 1575034637.044651
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: cf3aa178-7640-4174-b921-2330e6f2aad6
    detailed-status: done
    id: cf3aa178-7640-4174-b921-2330e6f2aad6
    isAutomaticInvocation: false
    isCancelPending: false
    lcmOperationType: instantiate
    links:
        nsInstance: /osm/nslcm/v1/ns_instances/0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
        self: /osm/nslcm/v1/ns_lcm_op_occs/cf3aa178-7640-4174-b921-2330e6f2aad6
    nsInstanceId: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
    operationParams:
        lcmOperationType: instantiate
        nsDescription: default description
        nsInstanceId: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
        nsName: multikdu
        nsdId: d0f63683-9032-4c6f-8928-ffd4674b9f69
        nsr_id: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
        vimAccountId: 74337dcb-ef54-41e7-bd2d-8c0d7fcd326f
        vld:
        -   name: mgmtnet
            vim-network-name: internal
    operationState: COMPLETED
    startTime: 1575034637.0445576
    statusEnteredTime: 1575034663.8484545

-   _admin:
      created: 1575034637.044651
      modified: 1575034637.044651
      projects_read:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
      projects_write:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 52770491-a765-40ce-97a1-c6e200bba7b3
    detailed-status: done
    id: 52770491-a765-40ce-97a1-c6e200bba7b3
    isAutomaticInvocation: false
    isCancelPending: false
    lcmOperationType: instantiate
    links:
      nsInstance: /osm/nslcm/v1/ns_instances/c54b14cb-69a8-45bc-b011-d6bea187dc0a
      self: /osm/nslcm/v1/ns_lcm_op_occs/52770491-a765-40ce-97a1-c6e200bba7b3
    nsInstanceId: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
    operationParams:
          lcmOperationType: scale
          nsInstanceId: c54b14cb-69a8-45bc-b011-d6bea187dc0a
          scaleVnfData:
            scaleByStepData:
              member-vnf-index: native-kdu
              scaling-group-descriptor: kdu_scaling_group
            scaleVnfType: SCALE_OUT
          scaleType: SCALE_VNF
    operationState: COMPLETED
    startTime: 1575034637.0445576
    statusEnteredTime: 1575034663.8484545

-   _admin:
      created: 1575034637.044651
      modified: 1575034637.044651
      projects_read:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
      projects_write:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 4013bbd2-b151-40ee-bcef-7e24ce5432f6
    detailed-status: done
    id: 4013bbd2-b151-40ee-bcef-7e24ce5432f6
    isAutomaticInvocation: false
    isCancelPending: false
    lcmOperationType: instantiate
    links:
      nsInstance: /osm/nslcm/v1/ns_instances/c54b14cb-69a8-45bc-b011-d6bea187dc0a
      self: /osm/nslcm/v1/ns_lcm_op_occs/4013bbd2-b151-40ee-bcef-7e24ce5432f6
    nsInstanceId: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
    operationParams:
          lcmOperationType: scale
          nsInstanceId: c54b14cb-69a8-45bc-b011-d6bea187dc0a
          scaleVnfData:
            scaleByStepData:
              member-vnf-index: native-kdu
              scaling-group-descriptor: kdu_scaling_group_2
            scaleVnfType: SCALE_OUT
          scaleType: SCALE_VNF
    operationState: COMPLETED
    startTime: 1575034637.0445576
    statusEnteredTime: 1575034663.8484545

-   _admin:
        created: 1566823354.4148262
        modified: 1566823354.4148262
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        worker: 86434c2948e2
        operations:
        -   member_vnf_index: '1'
            primitive: touch
            primitive_params: /home/ubuntu/last-touch-1
            operationState: COMPLETED
            detailed-status: Done
    _id: a639fac7-e0bb-4225-8ecb-c1f8efcc125f
    detailed-status: done
    id: a639fac7-e0bb-4225-8ecb-c1f8efcc125f
    isAutomaticInvocation: false
    isCancelPending: false
    lcmOperationType: update
    links:
        nsInstance: /osm/nslcm/v1/ns_instances/f48163a6-c807-47bc-9682-f72caef5af85
        self: /osm/nslcm/v1/ns_lcm_op_occs/a639fac7-e0bb-4225-8ecb-c1f8efcc125f
    nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
    operationParams:
      lcmOperationType: update
      nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
      removeVnfInstanceId: 88d90b0c-faff-4b9f-bccd-017f33985984
      updateType: REMOVE_VNF
    operationState: FAILED
    startTime: 1566823354.414689
    statusEnteredTime: 1566824534.5112448

-   _id: 1bd4b60a-e15d-49e5-b75e-2b3224f15dda
    id: 1bd4b60a-e15d-49e5-b75e-2b3224f15dda
    operationState: COMPLETED
    queuePosition: 0
    stage: ''
    errorMessage: ''
    detailedStatus:
    statusEnteredTime: 1652349205.9499352
    nsInstanceId: 52f0b3ac-1574-481f-a48f-528fc02912f7
    lcmOperationType: update
    startTime: 1652349205.7415159
    isAutomaticInvocation: false
    operationParams:
      updateType: OPERATE_VNF
      operateVnfData:
        vnfInstanceId: a6df8aa0-1271-4dfc-85a5-e0484fea303f
        changeStateTo: start
        additionalParam:
          run-day1: false
          vdu-id: mgmtVM
          count-index: 0
      lcmOperationType: update
      nsInstanceId: 52f0b3ac-1574-481f-a48f-528fc02912f7
    isCancelPending: false
    links:
      self: "/osm/nslcm/v1/ns_lcm_op_occs/1bd4b60a-e15d-49e5-b75e-2b3224f15dda"
      nsInstance: "/osm/nslcm/v1/ns_instances/52f0b3ac-1574-481f-a48f-528fc02912f7"
    _admin:
      created: 1652349205.7415788
      modified: 1652349205.9499364
      projects_read:
      - e38990e1-6724-4292-ab6f-2ecc109f9af4
      projects_write:
      - e38990e1-6724-4292-ab6f-2ecc109f9af4
      worker: fbf6b5aa99e2
    detailed-status: Done

-   _id: 6eace44b-2ef4-4de5-b15f-63f2e8898bfb
    id: 6eace44b-2ef4-4de5-b15f-63f2e8898bfb
    operationState: Error
    queuePosition: 0
    stage: ''
    errorMessage: ''
    detailedStatus:
    statusEnteredTime: 1652349205.9499352
    nsInstanceId: 52f0b3ac-1574-481f-a48f-528fc02912f7
    lcmOperationType: update
    startTime: 1652349205.7415159
    isAutomaticInvocation: false
    operationParams:
      updateType: OPERATE_VNF
      operateVnfData:
        vnfInstanceId: a6df8aa0-1271-4dfc-85a5-e0484fea303f
        changeStateTo: stop
        additionalParam:
          run-day1: false
          vdu-id: mgmtVM
          count-index: 0
      lcmOperationType: update
      nsInstanceId: 52f0b3ac-1574-481f-a48f-528fc02912f7
    isCancelPending: false
    links:
      self: "/osm/nslcm/v1/ns_lcm_op_occs/1bd4b60a-e15d-49e5-b75e-2b3224f15dda"
      nsInstance: "/osm/nslcm/v1/ns_instances/52f0b3ac-1574-481f-a48f-528fc02912f7"
    _admin:
      created: 1652349205.7415788
      modified: 1652349205.9499364
      projects_read:
      - e38990e1-6724-4292-ab6f-2ecc109f9af4
      projects_write:
      - e38990e1-6724-4292-ab6f-2ecc109f9af4
      worker: fbf6b5aa99e2
    detailed-status: Done

-   _admin:
        created: 1566823354.4148262
        modified: 1566823354.4148262
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        worker: 86434c2948e2
    _id: 8b838aa8-53a3-4955-80bd-fbba6a7957ed
    detailed-status: 'FAILED executing proxy charm initial primitives for member_vnf_index=1
        vdu_id=None: charm error executing primitive verify-ssh-credentials for member_vnf_index=1
        vdu_id=None: ''timeout after 600 seconds'''
    id: 8b838aa8-53a3-4955-80bd-fbba6a7957ed
    isAutomaticInvocation: false
    isCancelPending: false
    lcmOperationType: scale
    links:
        nsInstance: /osm/nslcm/v1/ns_instances/f48163a6-c807-47bc-9682-f72caef5af85
        self: /osm/nslcm/v1/ns_lcm_op_occs/8b838aa8-53a3-4955-80bd-fbba6a7957ed
    nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
    operationParams:
        additionalParamsForVnf:
        -   additionalParams:
                touch_filename: /home/ubuntu/first-touch-1
                touch_filename2: /home/ubuntu/second-touch-1
            member-vnf-index: '1'
        lcmOperationType: instantiate
        nsDescription: default description
        nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
        nsName: ALF
        nsdId: 8c2f8b95-bb1b-47ee-8001-36dc090678da
        vimAccountId: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    operationState: FAILED
    startTime: 1566823354.414689
    statusEnteredTime: 1566824534.5112448

-   _admin:
        created: 1566823354.4148262
        modified: 1566823354.4148262
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        worker: 86434c2948e2
    _id: a21af1d4-7f1a-4f7b-b666-222315113a62
    detailed-status: 'FAILED executing proxy charm initial primitives for member_vnf_index=1
        vdu_id=None: charm error executing primitive verify-ssh-credentials for member_vnf_index=1
        vdu_id=None: ''timeout after 600 seconds'''
    id: a21af1d4-7f1a-4f7b-b666-222315113a62
    isAutomaticInvocation: false
    isCancelPending: false
    lcmOperationType: scale
    links:
        nsInstance: /osm/nslcm/v1/ns_instances/f48163a6-c807-47bc-9682-f72caef5af85
        self: /osm/nslcm/v1/ns_lcm_op_occs/a21af1d4-7f1a-4f7b-b666-222315113a62
    nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
    operationParams:
        additionalParamsForVnf:
        -   additionalParams:
                touch_filename: /home/ubuntu/first-touch-1
                touch_filename2: /home/ubuntu/second-touch-1
            member-vnf-index: '1'
        lcmOperationType: instantiate
        nsDescription: default description
        nsInstanceId: f48163a6-c807-47bc-9682-f72caef5af85
        nsName: ALF
        nsdId: 8c2f8b95-bb1b-47ee-8001-36dc090678da
        vimAccountId: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    operationState: COMPLETED
    startTime: 1566823354.414689
    statusEnteredTime: 1566824534.5112448
"""

db_nsrs_text = """
---
-   _admin:
        created: 1566823354.3716335
        deployed:
            K8s: []
            RO:
                nsd_id: 876573b5-968d-40b9-b52b-91bf5c5844f7
                nsr_id: c9fe9908-3180-430d-b633-fca2f68db008
                nsr_status: ACTIVE
                vnfd:
                -   id: 1ab2a418-9fe3-4358-bf17-411e5155535f
                    member-vnf-index: '1'
                -   id: 0de348e3-c201-4f6a-91cc-7f957e2d5504
                    member-vnf-index: '2'
            VCA:
            -   application: alf-b-aa
                ee_id: f48163a6-c807-47bc-9682-f72caef5af85.alf-b-aa
                needed_terminate: True
                detailed-status: Ready!
                member-vnf-index: '1'
                model: f48163a6-c807-47bc-9682-f72caef5af85
                operational-status: active
                primitive_id: null
                ssh-public-key: ssh-rsa pub-key root@juju-145d3e-0
                step: ssh-public-key-obtained
                vdu_count_index: null
                vdu_id: null
                vdu_name: null
                type: lxc_proxy_charm
                vnfd_id: hackfest3charmed-vnf
            -   application: alf-c-ab
                ee_id: "model_name.application_name.machine_id"
                ee_descriptor_id: f48163a6-c807-47bc-9682-f72caef5af85.alf-c-ab
                needed_terminate: True
                detailed-status: Ready!
                member-vnf-index: hackfest_vnf1
                model: f48163a6-c807-47bc-9682-f72caef5af85
                operational-status: active
                primitive_id: null
                ssh-public-key: ssh-rsa pub-key root@juju-145d3e-0
                step: ssh-public-key-obtained
                vdu_count_index: null
                vdu_id: null
                vdu_name: null
                type: lxc_proxy_charm
                vnfd_id: hackfest3charmed-vnf
                config_sw_installed: true
            VCA-model-name: f48163a6-c807-47bc-9682-f72caef5af85
        modified: 1566823354.3716335
        nsState: INSTANTIATED
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
    vcaStatus:
        8c707f16-2d9b-49d6-af5e-2ce9985b2adf:
            applications:
                app-vnf-1fb8538dfc39:
                    can_upgrade_to: ''
                    charm: 'local:xenial/simple-1'
                    charm_profile: ''
                    charm_version: ''
                    endpoint_bindings: null
                    err: null
                    exposed: false
                    int_: null
                    life: ''
                    meter_statuses: { }
                    provider_id: null
                    public_address: ''
                    relations: { }
                    series: xenial
                    status:
                        data: { }
                        err: null
                        info: Ready!
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:39:54.239185095Z'
                        status: active
                        unknown_fields: { }
                        version: ''
                    subordinate_to: [ ]
                    units:
                        app-vnf-1fb8538dfc39/0:
                            address: null
                            agent_status:
                                data: { }
                                err: null
                                info: ''
                                kind: ''
                                life: ''
                                since: '2021-02-17T08:52:18.077155028Z'
                                status: idle
                                unknown_fields: { }
                                version: 2.8.1
                            charm: ''
                            leader: true
                            machine: '0'
                            opened_ports: null
                            provider_id: null
                            public_address: 10.151.40.53
                            subordinates: { }
                            unknown_fields: { }
                            workload_status:
                                data: { }
                                err: null
                                info: Ready!
                                kind: ''
                                life: ''
                                since: '2021-02-17T08:39:54.239185095Z'
                                status: active
                                unknown_fields: { }
                                version: ''
                            workload_version: ''
                    unknown_fields:
                        charm-verion: ''
                    workload_version: ''
                    actions:
                        generate-ssh-key: >-
                            Generate a new SSH keypair for this unit. This will replace any
                            existing previously generated keypair.
                        get-ssh-public-key: Get the public SSH key for this unit.
                        reboot: Reboot the VNF virtual machine.
                        restart: Stop the service on the VNF.
                        run: Run an arbitrary command
                        start: Stop the service on the VNF.
                        stop: Stop the service on the VNF.
                        touch: Touch a file on the VNF.
                        upgrade: Upgrade the software on the VNF.
                        verify-ssh-credentials: >-
                            Verify that this unit can authenticate with server specified by
                            ssh-hostname and ssh-username.
                    configs:
                        boolean-option:
                            default: false
                            description: A short description of the configuration option
                            source: default
                            type: boolean
                            value: false
                        int-option:
                            default: 9001
                            description: A short description of the configuration option
                            source: default
                            type: int
                            value: 9001
                        ssh-hostname:
                            default: ''
                            description: The hostname or IP address of the machine to
                            source: user
                            type: string
                            value: 192.168.61.90
                        ssh-key-bits:
                            default: 4096
                            description: The number of bits to use for the SSH key.
                            source: default
                            type: int
                            value: 4096
                        ssh-key-type:
                            default: rsa
                            description: The type of encryption to use for the SSH key.
                            source: default
                            type: string
                            value: rsa
                        ssh-password:
                            default: ''
                            description: The password used to authenticate.
                            source: user
                            type: string
                            value: osm4u
                        ssh-private-key:
                            default: ''
                            description: DEPRECATED. The private ssh key to be used to authenticate.
                            source: default
                            type: string
                            value: ''
                        ssh-public-key:
                            default: ''
                            description: The public key of this unit.
                            source: default
                            type: string
                            value: ''
                        ssh-username:
                            default: ''
                            description: The username to login as.
                            source: user
                            type: string
                            value: ubuntu
                        string-option:
                            default: Default Value
                            description: A short description of the configuration option
                            source: default
                            type: string
                            value: Default Value
                app-vnf-943ab4274bb6:
                    can_upgrade_to: ''
                    charm: 'local:xenial/simple-0'
                    charm_profile: ''
                    charm_version: ''
                    endpoint_bindings: null
                    err: null
                    exposed: false
                    int_: null
                    life: ''
                    meter_statuses: { }
                    provider_id: null
                    public_address: ''
                    relations: { }
                    series: xenial
                    status:
                        data: { }
                        err: null
                        info: Ready!
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:39:15.165682713Z'
                        status: active
                        unknown_fields: { }
                        version: ''
                    subordinate_to: [ ]
                    units:
                        app-vnf-943ab4274bb6/0:
                            address: null
                            agent_status:
                                data: { }
                                err: null
                                info: ''
                                kind: ''
                                life: ''
                                since: '2021-02-17T08:46:06.473054303Z'
                                status: idle
                                unknown_fields: { }
                                version: 2.8.1
                            charm: ''
                            leader: true
                            machine: '1'
                            opened_ports: null
                            provider_id: null
                            public_address: 10.151.40.117
                            subordinates: { }
                            unknown_fields: { }
                            workload_status:
                                data: { }
                                err: null
                                info: Ready!
                                kind: ''
                                life: ''
                                since: '2021-02-17T08:39:15.165682713Z'
                                status: active
                                unknown_fields: { }
                                version: ''
                            workload_version: ''
                    unknown_fields:
                        charm-verion: ''
                    workload_version: ''
                    actions:
                        generate-ssh-key: >-
                            Generate a new SSH keypair for this unit. This will replace any
                            existing previously generated keypair.
                        get-ssh-public-key: Get the public SSH key for this unit.
                        reboot: Reboot the VNF virtual machine.
                        restart: Stop the service on the VNF.
                        run: Run an arbitrary command
                        start: Stop the service on the VNF.
                        stop: Stop the service on the VNF.
                        touch: Touch a file on the VNF.
                        upgrade: Upgrade the software on the VNF.
                        verify-ssh-credentials: >-
                            Verify that this unit can authenticate with server specified by
                            ssh-hostname and ssh-username.
                    configs:
                        boolean-option:
                            default: false
                            description: A short description of the configuration option
                            source: default
                            type: boolean
                            value: false
                        int-option:
                            default: 9001
                            description: A short description of the configuration option
                            source: default
                            type: int
                            value: 9001
                        ssh-hostname:
                            default: ''
                            description: The hostname or IP address of the machine to
                            source: user
                            type: string
                            value: 192.168.61.72
                        ssh-key-bits:
                            default: 4096
                            description: The number of bits to use for the SSH key.
                            source: default
                            type: int
                            value: 4096
                        ssh-key-type:
                            default: rsa
                            description: The type of encryption to use for the SSH key.
                            source: default
                            type: string
                            value: rsa
                        ssh-password:
                            default: ''
                            description: The password used to authenticate.
                            source: user
                            type: string
                            value: osm4u
                        ssh-private-key:
                            default: ''
                            description: DEPRECATED. The private ssh key to be used to authenticate.
                            source: default
                            type: string
                            value: ''
                        ssh-public-key:
                            default: ''
                            description: The public key of this unit.
                            source: default
                            type: string
                            value: ''
                        ssh-username:
                            default: ''
                            description: The username to login as.
                            source: user
                            type: string
                            value: ubuntu
                        string-option:
                            default: Default Value
                            description: A short description of the configuration option
                            source: default
                            type: string
                            value: Default Value
            branches: { }
            controller_timestamp: '2021-02-17T09:17:38.006569064Z'
            machines:
                '0':
                    agent_status:
                        data: { }
                        err: null
                        info: ''
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:37:46.637167056Z'
                        status: started
                        unknown_fields: { }
                        version: 2.8.1
                    constraints: ''
                    containers: { }
                    display_name: ''
                    dns_name: 10.151.40.53
                    hardware: arch=amd64 cores=0 mem=0M
                    has_vote: false
                    id_: '0'
                    instance_id: juju-0f027b-0
                    instance_status:
                        data: { }
                        err: null
                        info: Running
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:35:58.435458338Z'
                        status: running
                        unknown_fields: { }
                        version: ''
                    ip_addresses:
                        - 10.151.40.53
                    jobs:
                        - JobHostUnits
                    lxd_profiles: { }
                    modification_status:
                        data: { }
                        err: null
                        info: ''
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:35:34.663795891Z'
                        status: idle
                        unknown_fields: { }
                        version: ''
                    network_interfaces:
                        eth0:
                            dns_nameservers: null
                            gateway: 10.151.40.1
                            ip_addresses:
                                - 10.151.40.53
                            is_up: true
                            mac_address: '00:16:3e:99:bf:c7'
                            space: null
                            unknown_fields: { }
                    primary_controller_machine: null
                    series: xenial
                    unknown_fields: { }

                    wants_vote: false
                '1':
                    agent_status:
                        data: { }
                        err: null
                        info: ''
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:37:00.893313184Z'
                        status: started
                        unknown_fields: { }
                        version: 2.8.1
                    constraints: ''
                    containers: { }
                    display_name: ''
                    dns_name: 10.151.40.117
                    hardware: arch=amd64 cores=0 mem=0M
                    has_vote: false
                    id_: '1'
                    instance_id: juju-0f027b-1
                    instance_status:
                        data: { }
                        err: null
                        info: Running
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:36:23.354547217Z'
                        status: running
                        unknown_fields: { }
                        version: ''
                    ip_addresses:
                        - 10.151.40.117
                    jobs:
                        - JobHostUnits
                    lxd_profiles: { }
                    modification_status:
                        data: { }
                        err: null
                        info: ''
                        kind: ''
                        life: ''
                        since: '2021-02-17T08:35:34.768829507Z'
                        status: idle
                        unknown_fields: { }
                        version: ''
                    network_interfaces:
                        eth0:
                            dns_nameservers: null
                            gateway: 10.151.40.1
                            ip_addresses:
                                - 10.151.40.117
                            is_up: true
                            mac_address: '00:16:3e:99:fe:1c'
                            space: null
                            unknown_fields: { }
                    primary_controller_machine: null
                    series: xenial
                    unknown_fields: { }
                    wants_vote: false
            model:
                available_version: ''
                cloud_tag: cloud-localhost
                migration: null
                name: 7c707f16-2d9b-49d6-af5e-2ce9985b2adf
                region: localhost
                unknown_fields:
                    meter-status:
                        color: ''
                        message: ''
                    model-status:
                        data: { }
                        info: ''
                        kind: ''

                        life: ''
                        since: '2021-02-17T08:35:31.856691457Z'
                        status: available
                        version: ''
                    sla: unsupported
                    type: iaas
                version: 2.8.1
            offers: { }
            relations: [ ]
            remote_applications: { }
            unknown_fields: { }
            executedActions:
                -   id: '6'
                    action: touch
                    status: completed
                    Code: '0'
                    output: ''
                -   id: '4'
                    action: touch
                    status: completed
                    Code: '0'
                    output: ''
                -   id: '2'
                    action: verify-ssh-credentials
                    status: completed
                    Code: '0'
                    output: ALF-1-mgmtvm-1
                    verified: 'True'
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
    operational-status: running
    orchestration-progress: {}
    resource-orchestrator: osmopenmano
    nsState: INSTANTIATED
    short-name: ALF
    ssh-authorized-key: null
    flavor : [{"vcpu-count":1,"memory-mb":1024,"storage-gb":"10","vim_info":[],"name":"mgmtVM-flv","id":"0"}]
    affinity-or-anti-affinity-group : []
    image : [ { "image" : "ubuntu16.04", "vim_info" : [ ], "id" : "0" } ]
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
-   _admin:
        created: 1575034637.011233
        current-operation: null
        deployed:
            K8s:
            -   k8scluster-uuid: 73d96432-d692-40d2-8440-e0c73aee209c
                kdu-instance: stable-mongodb-0086856106
                kdu-model: stable/mongodb
                kdu-name: mongo
                vnfr-id: 5ac34899-a23a-4b3c-918a-cd77acadbea6
            -   k8scluster-uuid: 73d96432-d692-40d2-8440-e0c73aee209c
                kdu-instance: stable-openldap-0092830263
                kdu-model: stable/mongodb
                kdu-name: mongo
                vnfr-id: 5ac34899-a23a-4b3c-918a-cd77acadbea6
            RO:
                detailed-status: Deployed at VIM
                nsd_id: b03a8de8-1898-4142-bc6d-3b0787df567d
                nsr_id: b5ce3e00-8647-415d-afaa-d5a612cf3074
                nsr_status: ACTIVE
                operational-status: running
                vnfd:
                -   id: b9493dae-a4c9-4b96-8965-329581efb0a1
                    member-vnf-index: multikdu
            VCA: []
        modified: 1575034637.011233
        nsState: INSTANTIATED
        nslcmop: null
        operation-type: null
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
    additionalParamsForNs: null
    admin-status: ENABLED
    config-status: configured
    constituent-vnfr-ref:
    - 5ac34899-a23a-4b3c-918a-cd77acadbea6
    create-time: 1575034636.9990137
    datacenter: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    description: default description
    vcaStatus: {}
    detailed-status: done
    id: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
    instantiate_params:
        nsDescription: default description
        nsName: multikdu
        nsdId: d0f63683-9032-4c6f-8928-ffd4674b9f69
        vimAccountId: 74337dcb-ef54-41e7-bd2d-8c0d7fcd326f
    name: multikdu
    name-ref: multikdu
    ns-instance-config-ref: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
    nsd-id: d0f63683-9032-4c6f-8928-ffd4674b9f69
    nsd-name-ref: multikdu_ns
    nsd-ref: multikdu_ns
    operational-events: []
    operational-status: init
    orchestration-progress: {}
    resource-orchestrator: osmopenmano
    short-name: multikdu
    ssh-authorized-key: null
    vld:
    -   id: mgmtnet
        name: null
        status: ACTIVE
        status-detailed: null
        vim-id: 9b6a2ac4-767e-4ec9-9497-8ba63084c77f
        vim-network-name: mgmt
    vnfd-id:
    - 7ab0d10d-8ce2-4c68-aef6-cc5a437a9c62

-   _admin:
      created: 1575034637.011233
      current-operation: null
      deployed:
        K8s:
        - k8scluster-uuid: 73d96432-d692-40d2-8440-e0c73aee209c
          kdu-instance: native-kdu-0
          kdu-model: native-kdu-0
          kdu-name: native-kdu
          member-vnf-index: native-kdu
          vnfr-id: 5ac34899-a23a-4b3c-918a-cd77acadbea6
        RO:
          detailed-status: Deployed at VIM
          nsd_id: b03a8de8-1898-4142-bc6d-3b0787df567d
          nsr_id: b5ce3e00-8647-415d-afaa-d5a612cf3074
          nsr_status: ACTIVE
          operational-status: running
          vnfd:
          - id: b9493dae-a4c9-4b96-8965-329581efb0a1
            member-vnf-index: native-kdu
        VCA: []
      modified: 1575034637.011233
      nsState: INSTANTIATED
      nslcmop: null
      operation-type: null
      projects_read:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
      projects_write:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: c54b14cb-69a8-45bc-b011-d6bea187dc0a
    additionalParamsForNs: null
    admin-status: ENABLED
    config-status: configured
    constituent-vnfr-ref:
    - 5ac34899-a23a-4b3c-918a-cd77acadbea6
    create-time: 1575034636.9990137
    datacenter: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
    description: default description
    detailed-status: done
    id: c54b14cb-69a8-45bc-b011-d6bea187dc0a
    instantiate_params:
      nsDescription: default description
      nsName: native-kdu
      nsdId: d0f63683-9032-4c6f-8928-ffd4674b9f69
      vimAccountId: 74337dcb-ef54-41e7-bd2d-8c0d7fcd326f
    name: native-kdu
    name-ref: native-kdu
    ns-instance-config-ref: c54b14cb-69a8-45bc-b011-d6bea187dc0a
    nsd-id: d0f63683-9032-4c6f-8928-ffd4674b9f69
    nsd-name-ref: native-kdu_ns
    nsd-ref: native-kdu_ns
    operational-events: []
    operational-status: init
    orchestration-progress: {}
    resource-orchestrator: osmopenmano
    short-name: native-kdu
    ssh-authorized-key: null
    vld:
    - id: mgmtnet
      name: null
      status: ACTIVE
      status-detailed: null
      vim-id: 9b6a2ac4-767e-4ec9-9497-8ba63084c77f
      vim-network-name: mgmt
    vnfd-id:
    - d96b1cdf-5ad6-49f7-bf65-907ada989293

-   _id: b63aa1ba-996e-43a7-921a-1aca5ccbc63f
    name: ha_charm-ns2
    name-ref: ha_charm-ns2
    short-name: ha_charm-ns2
    admin-status: ENABLED
    nsState: BROKEN
    currentOperation: IDLE
    currentOperationID:
    errorDescription: 'Operation: INSTANTIATING.8e72f2b5-f466-4382-88a4-4575c9e07eb8,
      Stage 5/5: running Day-1 primitives for NS.'
    deploymentStatus:
    configurationStatus:
    - elementType: VDU
      elementUnderConfiguration: userVM-0
      status: READY
    - elementType: VDU
      elementUnderConfiguration: policyVM-0
      status: READY
    - elementType: NS
      elementUnderConfiguration: b63aa1ba-996e-43a7-921a-1aca5ccbc63f
      status: BROKEN
    vcaStatus:
    nsd:
      _id: a557cb0f-0dc9-494c-a9bd-69e8079767e7
      id: nscharm-ns
      version: '1.0'
      name: nscharm-ns
      vnfd-id:
      - nscharm-user-vnf
      - nscharm-policy-vnf
      virtual-link-desc:
      - id: mgmtnet
        mgmt-network: true
        vim-network-name: osm-ext
      df:
      - id: default-df
        vnf-profile:
        - id: '1'
          virtual-link-connectivity:
          - constituent-cpd-id:
            - constituent-base-element-id: '1'
              constituent-cpd-id: vnf-mgmt-ext
            virtual-link-profile-id: mgmtnet
          vnfd-id: nscharm-user-vnf
        - id: '2'
          virtual-link-connectivity:
          - constituent-cpd-id:
            - constituent-base-element-id: '2'
              constituent-cpd-id: vnf-mgmt-ext
            virtual-link-profile-id: mgmtnet
          vnfd-id: nscharm-policy-vnf
      ns-configuration:
        juju:
          charm: ns_ubuntu-18.04-amd64.charm
        config-primitive:
        - name: add-user
          parameter:
          - name: username
            data-type: STRING
        initial-config-primitive:
        - seq: '1'
          name: config
          parameter:
          - name: juju-username
            value: admin
          - name: juju-password
            value: a5611fc6452349cc6e45705d34c501d4
        - seq: '2'
          name: add-user
          parameter:
          - name: username
            value: root
      description: NS with 2 VNFs
      _admin:
        userDefinedData: {}
        revision: 1
        created: 1658868548.2641
        modified: 1658868548.89253
        projects_read:
        - 51e0e80fe533469d98766caa16552a3e
        projects_write:
        - 51e0e80fe533469d98766caa16552a3e
        onboardingState: ONBOARDED
        operationalState: ENABLED
        usageState: NOT_IN_USE
        storage:
          fs: mongo
          path: "/app/storage/"
          folder: a557cb0f-0dc9-494c-a9bd-69e8079767e7:1
          pkg-dir: nscharm_ns
          descriptor: nscharm_ns/nscharm_nsd.yaml
          zipfile: nscharm_ns.tar.gz
    datacenter: bad7338b-ae46-43d4-a434-c3337a8054ac
    resource-orchestrator: osmopenmano
    description: default description
    constituent-vnfr-ref:
    - 303a6ccd-e6f2-4127-96a4-1e3b97956850
    - 0d0cd621-47db-4eef-a9e8-8edb71a34ea1
    operational-status: running
    config-status: failed
    orchestration-progress: {}
    create-time: 1658868607.27119
    nsd-name-ref: nscharm-ns
    operational-events: []
    nsd-ref: nscharm-ns
    nsd-id: a557cb0f-0dc9-494c-a9bd-69e8079767e7
    vnfd-id:
    - b5068dc9-a3cd-4a1e-b051-e36c3a9f10a4
    - 4aa63021-c816-456b-9998-804c5285a85d
    instantiate_params:
      nsdId: a557cb0f-0dc9-494c-a9bd-69e8079767e7
      nsName: ha_charm-ns2
      nsDescription: default description
      vimAccountId: bad7338b-ae46-43d4-a434-c3337a8054ac
      vld:
      - name: mgmtnet
        vim-network-name: osm-ext
    additionalParamsForNs:
    ns-instance-config-ref: b63aa1ba-996e-43a7-921a-1aca5ccbc63f
    id: b63aa1ba-996e-43a7-921a-1aca5ccbc63f
    ssh-authorized-key:
    flavor:
    - id: '0'
      memory-mb: 1024
      name: userVM-flv
      storage-gb: '10'
      vcpu-count: 1
      vim_info:
        vim:bad7338b-ae46-43d4-a434-c3337a8054ac:
          vim_details:
          vim_id: 17a9ba76-beb7-4ad4-a481-97de37174866
          vim_message:
          vim_status: DONE
    - id: '1'
      memory-mb: 1024
      name: policyVM-flv
      storage-gb: '10'
      vcpu-count: 1
      vim_info:
        vim:bad7338b-ae46-43d4-a434-c3337a8054ac:
          vim_details:
          vim_id: 17a9ba76-beb7-4ad4-a481-97de37174866
          vim_message:
          vim_status: DONE
    image:
    - id: '0'
      image: ubuntu18.04
      vim_info:
        vim:bad7338b-ae46-43d4-a434-c3337a8054ac:
          vim_details:
          vim_id: 919fc71a-6acd-4ee3-8123-739a9abbc2e7
          vim_message:
          vim_status: DONE
    - image: ubuntu/images/hvm-ssd/ubuntu-artful-17.10-amd64-server-20180509
      vim-type: aws
      id: '1'
    - image: Canonical:UbuntuServer:18.04-LTS:latest
      vim-type: azure
      id: '2'
    - image: ubuntu-os-cloud:image-family:ubuntu-1804-lts
      vim-type: gcp
      id: '3'
    affinity-or-anti-affinity-group: []
    revision: 1
    vld:
    - id: mgmtnet
      mgmt-network: true
      name: mgmtnet
      type:
      vim_info:
        vim:bad7338b-ae46-43d4-a434-c3337a8054ac:
          vim_account_id: bad7338b-ae46-43d4-a434-c3337a8054ac
          vim_network_name: osm-ext
          vim_details: |
            {admin_state_up: true, availability_zone_hints: [], availability_zones: [nova], created_at: '2019-10-17T23:44:03Z', description: '', encapsulation: vlan, encapsulation_id: 2148, encapsulation_type: vlan, id: 21ea5d92-24f1-40ab-8d28-83230e277a49, ipv4_address_scope: null,
              ipv6_address_scope: null, is_default: false, mtu: 1500, name: osm-ext, port_security_enabled: true, project_id: 456b6471010b4737b47a0dd599c920c5, 'provider:network_type': vlan, 'provider:physical_network': physnet1, 'provider:segmentation_id': 2148, revision_number: 1009,
              'router:external': true, segmentation_id: 2148, shared: true, status: ACTIVE, subnets: [{subnet: {allocation_pools: [{end: 172.21.249.255, start: 172.21.248.1}], cidr: 172.21.248.0/22, created_at: '2019-10-17T23:44:07Z', description: '', dns_nameservers: [],
                    enable_dhcp: true, gateway_ip: 172.21.251.254, host_routes: [], id: d14f68b7-8287-41fe-b533-dafb2240680a, ip_version: 4, ipv6_address_mode: null, ipv6_ra_mode: null, name: osm-ext-subnet, network_id: 21ea5d92-24f1-40ab-8d28-83230e277a49, project_id: 456b6471010b4737b47a0dd599c920c5,
                    revision_number: 5, service_types: [], subnetpool_id: null, tags: [], tenant_id: 456b6471010b4737b47a0dd599c920c5, updated_at: '2020-09-14T15:15:06Z'}}], tags: [], tenant_id: 456b6471010b4737b47a0dd599c920c5, type: data, updated_at: '2022-07-05T18:39:02Z'}
          vim_id: 21ea5d92-24f1-40ab-8d28-83230e277a49
          vim_message:
          vim_status: ACTIVE
    _admin:
      created: 1658868607.2804
      modified: 1658868966.10105
      projects_read:
      - 51e0e80fe533469d98766caa16552a3e
      projects_write:
      - 51e0e80fe533469d98766caa16552a3e
      nsState: INSTANTIATED
      current-operation:
      nslcmop:
      operation-type:
      deployed:
        RO:
          vnfd: []
          operational-status: running
        VCA:
        - target_element: vnf/1/vdu/userVM/0
          member-vnf-index: '1'
          vdu_id: userVM
          kdu_name:
          vdu_count_index: 0
          operational-status: init
          detailed-status: ''
          step: initial-deploy
          vnfd_id: nscharm-user-vnf
          vdu_name:
          type: lxc_proxy_charm
          ee_descriptor_id: vnf-user-ee
          ee_id: b63aa1ba-996e-43a7-921a-1aca5ccbc63f.app-vnf-3b97956850-z0-vdu-uservm-cnt-z0-eh2hc.2
          application: app-vnf-3b97956850-z0-vdu-uservm-cnt-z0-eh2hc
          model: b63aa1ba-996e-43a7-921a-1aca5ccbc63f
          config_sw_installed: true
        - target_element: vnf/2/vdu/policyVM/0
          member-vnf-index: '2'
          vdu_id: policyVM
          kdu_name:
          vdu_count_index: 0
          operational-status: init
          detailed-status: ''
          step: initial-deploy
          vnfd_id: nscharm-policy-vnf
          vdu_name:
          type: lxc_proxy_charm
          ee_descriptor_id: vnf-policy-ee
          ee_id: b63aa1ba-996e-43a7-921a-1aca5ccbc63f.app-vnf-db71a34ea1-z0-vdu-policyvm-cnt-z0-tr1oc.0
          application: app-vnf-db71a34ea1-z0-vdu-policyvm-cnt-z0-tr1oc
          model: b63aa1ba-996e-43a7-921a-1aca5ccbc63f
          config_sw_installed: true
        - target_element: ns
          member-vnf-index:
          vdu_id:
          kdu_name:
          vdu_count_index: 0
          operational-status: init
          detailed-status: ''
          step: initial-deploy
          vnfd_id:
          vdu_name:
          type: lxc_proxy_charm
          ee_descriptor_id:
          ee_id: b63aa1ba-996e-43a7-921a-1aca5ccbc63f.app-qmfbp.1
          application: app-qmfbp
          model: b63aa1ba-996e-43a7-921a-1aca5ccbc63f
          config_sw_installed: true
        K8s: []
"""

ro_ns_text = """
datacenter_tenant_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
description: null
name: ALF
classifications: []
sdn_nets: []
nets:
-   created: false
    datacenter_id: dc51ce6c-c7f2-11e9-b9c0-02420aff0004
    datacenter_tenant_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
    error_msg: null
    ns_net_osm_id: mgmt
    related: c6bac394-fa27-4c43-bb34-42f621a9d343
    sce_net_id: 8f215bab-c35e-41e6-a035-42bfaa07af9f
    sdn_net_id: null
    status: ACTIVE
    uuid: c6bac394-fa27-4c43-bb34-42f621a9d343
    vim_info: "{vim_info: null}"
    vim_name: null
    vim_net_id: f99ae780-0e2f-4985-af41-574eae6919c0
    vnf_net_id: null
    vnf_net_osm_id: null
-   created: true
    datacenter_id: dc51ce6c-c7f2-11e9-b9c0-02420aff0004
    datacenter_tenant_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
    error_msg: null
    ns_net_osm_id: datanet
    related: 509d576c-120f-493a-99a1-5fea99dfe041
    sce_net_id: 3d766bbc-33a8-41aa-a986-2f35e8d25c16
    sdn_net_id: null
    status: ACTIVE
    uuid: 509d576c-120f-493a-99a1-5fea99dfe041
    vim_info: "{vim_info: null}"
    vim_name: ALF-datanet
    vim_net_id: c31364ba-f573-4ab6-bf1a-fed30ede39a8
    vnf_net_id: null
    vnf_net_osm_id: null
-   created: true
    datacenter_id: dc51ce6c-c7f2-11e9-b9c0-02420aff0004
    datacenter_tenant_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
    error_msg: null
    ns_net_osm_id: null
    related: 277fed09-3220-4bfd-9052-b96b21a32daf
    sce_net_id: null
    sdn_net_id: null
    status: ACTIVE
    uuid: 277fed09-3220-4bfd-9052-b96b21a32daf
    vim_info: "{vim_info: null}"
    vim_name: ALF-internal
    vim_net_id: ff181e6d-2597-4244-b40b-bb0174bdfeb6
    vnf_net_id: 62e62fae-c12b-4ebc-9a9b-30031c6c16fa
    vnf_net_osm_id: internal
-   created: true
    datacenter_id: dc51ce6c-c7f2-11e9-b9c0-02420aff0004
    datacenter_tenant_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
    error_msg: null
    ns_net_osm_id: null
    related: 92534d1a-e697-4372-a84d-aa0aa643b68a
    sce_net_id: null
    sdn_net_id: null
    status: ACTIVE
    uuid: 92534d1a-e697-4372-a84d-aa0aa643b68a
    vim_info: "{vim_info: null}"
    vim_name: ALF-internal
    vim_net_id: 09655387-b639-421a-b5f6-72b26d685fb4
    vnf_net_id: 13c6c77d-86a5-4914-832c-990d4ec7b54e
    vnf_net_osm_id: internal
nsd_osm_id: f48163a6-c807-47bc-9682-f72caef5af85.2.hackfest3charmed-ns
scenario_id: 876573b5-968d-40b9-b52b-91bf5c5844f7
scenario_name: hackfest3charmed-ns
sfis: []
sfps: []
sfs: []
tenant_id: 0ea38bd0-2729-47a9-ae07-c6ce76115eb2
uuid: c9fe9908-3180-430d-b633-fca2f68db008
vnfs:
-   datacenter_id: dc51ce6c-c7f2-11e9-b9c0-02420aff0004
    datacenter_tenant_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
    ip_address: 10.205.1.46
    member_vnf_index: '1'
    mgmt_access: '{interface_id: 61549ee3-cd6c-4930-8b90-eaad97fe345b, required: ''False'',
        vm_id: 6cf4a48f-3b6c-4395-8221-119fa37de24a}

        '
    sce_vnf_id: 83be04a8-c513-42ba-9908-22728f686d31
    uuid: 94724042-7576-4fb0-82ec-6a7ab642741c
    vms:
    -   created_at: '2019-08-26T12:50:38'
        error_msg: null
        interfaces:
        -   external_name: vnf-mgmt
            instance_net_id: c6bac394-fa27-4c43-bb34-42f621a9d343
            internal_name: mgmtVM-eth0
            ip_address: 10.205.1.46
            mac_address: fa:16:3e:b4:3e:b1
            sdn_port_id: null
            type: mgmt
            vim_info: "{vim_info: null}"
            vim_interface_id: 4d3cb8fd-7040-4169-a0ad-2486d2b006a1
        -   external_name: null
            instance_net_id: 277fed09-3220-4bfd-9052-b96b21a32daf
            internal_name: mgmtVM-eth1
            ip_address: 192.168.54.2
            mac_address: fa:16:3e:6e:7e:78
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: 54ed68e2-9802-4dfe-b68a-280b3fc6e02d
        ip_address: 10.205.1.46
        name: mgmtVM
        related: d0b91293-a91d-4f08-b15f-0bf841216dfe
        status: ACTIVE
        uuid: d0b91293-a91d-4f08-b15f-0bf841216dfe
        vdu_osm_id: mgmtVM
        vim_info: "{vim_info: null}"
        vim_name: ALF-1-mgmtVM-1
        vim_vm_id: c2538499-4c30-41c0-acd5-80cb92f48061
    -   created_at: '2019-08-26T12:50:38'
        error_msg: null
        interfaces:
        -   external_name: null
            instance_net_id: 277fed09-3220-4bfd-9052-b96b21a32daf
            internal_name: dataVM-eth0
            ip_address: 192.168.54.3
            mac_address: fa:16:3e:d9:7a:5d
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: 1637f350-8840-4241-8ed0-4616bdcecfcf
        -   external_name: vnf-data
            instance_net_id: 509d576c-120f-493a-99a1-5fea99dfe041
            internal_name: dataVM-xe0
            ip_address: 192.168.24.3
            mac_address: fa:16:3e:d1:6c:0d
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: 54c73e83-7059-41fe-83a9-4c4ae997b481
        name: dataVM
        related: 5c08253d-8a35-474f-b0d3-c5297d174c13
        status: ACTIVE
        uuid: 5c08253d-8a35-474f-b0d3-c5297d174c13
        vdu_osm_id: dataVM
        vim_info: "{vim_info: null}"
        vim_name: ALF-1-dataVM-1
        vim_vm_id: 87973c3f-365d-4227-95c2-7a8abc74349c
    -   created_at: '2019-08-26T13:40:54'
        error_msg: null
        interfaces:
        -   external_name: null
            instance_net_id: 277fed09-3220-4bfd-9052-b96b21a32daf
            internal_name: dataVM-eth0
            ip_address: 192.168.54.5
            mac_address: fa:16:3e:e4:17:45
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: 7e246e40-8710-4c33-9c95-78fc3c02bc5b
        -   external_name: vnf-data
            instance_net_id: 509d576c-120f-493a-99a1-5fea99dfe041
            internal_name: dataVM-xe0
            ip_address: 192.168.24.5
            mac_address: fa:16:3e:29:6f:a6
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: ce81af7a-9adf-494b-950e-6581fd04ecc4
        name: dataVM
        related: 1ae5a0a2-c15a-49a4-a77c-2991d97f6dbe
        status: ACTIVE
        uuid: 1ae5a0a2-c15a-49a4-a77c-2991d97f6dbe
        vdu_osm_id: dataVM
        vim_info: "{vim_info: null}"
        vim_name: ALF-1-dataVM-2
        vim_vm_id: 4916533e-36c6-4861-9fe3-366a8fb0a5f8
    vnf_id: 1ab2a418-9fe3-4358-bf17-411e5155535f
    vnf_name: hackfest3charmed-vnf.1
    vnfd_osm_id: f48163a6-c807-47bc-9682-f72caef5af85.0.1
-   datacenter_id: dc51ce6c-c7f2-11e9-b9c0-02420aff0004
    datacenter_tenant_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
    ip_address: 10.205.1.47
    member_vnf_index: '2'
    mgmt_access: '{interface_id: 538604c3-5c5e-41eb-8f84-c0239c7fabcd, required: ''False'',
        vm_id: dd04d792-05c9-4ecc-bf28-f77384d00311}

        '
    sce_vnf_id: c4f3607a-08ff-4f75-893c-fce507e2f240
    uuid: 00020403-e80f-4ef2-bb7e-b29669643035
    vms:
    -   created_at: '2019-08-26T12:50:38'
        error_msg: null
        interfaces:
        -   external_name: vnf-mgmt
            instance_net_id: c6bac394-fa27-4c43-bb34-42f621a9d343
            internal_name: mgmtVM-eth0
            ip_address: 10.205.1.47
            mac_address: fa:16:3e:cb:9f:c7
            sdn_port_id: null
            type: mgmt
            vim_info: "{vim_info: null}"
            vim_interface_id: dcd6d2de-3c68-481c-883e-e9d38c671dc4
        -   external_name: null
            instance_net_id: 92534d1a-e697-4372-a84d-aa0aa643b68a
            internal_name: mgmtVM-eth1
            ip_address: 192.168.231.1
            mac_address: fa:16:3e:1a:89:24
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: 50e538e3-aba0-4652-93bb-20487f3f28e1
        ip_address: 10.205.1.47
        name: mgmtVM
        related: 4543ab5d-578c-427c-9df2-affd17e21b66
        status: ACTIVE
        uuid: 4543ab5d-578c-427c-9df2-affd17e21b66
        vdu_osm_id: mgmtVM
        vim_info: "{vim_info: null}"
        vim_name: ALF-2-mgmtVM-1
        vim_vm_id: 248077b2-e3b8-4a37-8b72-575abb8ed912
    -   created_at: '2019-08-26T12:50:38'
        error_msg: null
        interfaces:
        -   external_name: null
            instance_net_id: 92534d1a-e697-4372-a84d-aa0aa643b68a
            internal_name: dataVM-eth0
            ip_address: 192.168.231.3
            mac_address: fa:16:3e:7e:ba:8c
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: 15274862-14ea-4527-b405-101cae8bc1a0
        -   external_name: vnf-data
            instance_net_id: 509d576c-120f-493a-99a1-5fea99dfe041
            internal_name: dataVM-xe0
            ip_address: 192.168.24.4
            mac_address: fa:16:3e:d2:e1:f5
            sdn_port_id: null
            type: bridge
            vim_info: "{vim_info: null}"
            vim_interface_id: 253ebe4e-38d5-46be-8777-dbb57510a2ec
        name: dataVM
        related: 6f03f16b-295a-47a1-9a69-2d069d574a33
        status: ACTIVE
        uuid: 6f03f16b-295a-47a1-9a69-2d069d574a33
        vdu_osm_id: dataVM
        vim_info: "{vim_info: null}"
        vim_name: ALF-2-dataVM-1
        vim_vm_id: a4ce4372-e0ad-4ae3-8f9f-1c969f32e77b
    vnf_id: 0de348e3-c201-4f6a-91cc-7f957e2d5504
    vnf_name: hackfest3charmed-vnf.2
    vnfd_osm_id: f48163a6-c807-47bc-9682-f72caef5af85.1.2
"""

ro_delete_action_text = """
actions:
-   created_at: 1580140763.1099188
    description: DELETE
    instance_id: c9fe9908-3180-430d-b633-fca2f68db008
    modified_at: 1580140763.253148
    number_done: 1
    number_failed: 0
    number_tasks: 1
    tenant_id: 0ea38bd0-2729-47a9-ae07-c6ce76115eb2
    uuid: delete
    vim_wim_actions:
    -   action: DELETE
        created_at: 1580140763.1099188
        datacenter_vim_id: dc5c67fa-c7f2-11e9-b9c0-02420aff0004
        error_msg: null
        extra: '{params: [9b6a2ac4-767e-4ec9-9497-8ba63084c77f, null]}'
        instance_action_id: ACTION-1580140763.054037
        item: instance_nets
        item_id: 8cb06b72-c71d-4b58-b419-95025fa651d3
        modified_at: 1580140763.1099188
        related: 8cb06b72-c71d-4b58-b419-95025fa651d3
        status: SUPERSEDED
        task_index: 0
        vim_id: null
        wim_account_id: null
        wim_internal_id: null
        worker: null
"""

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
    description: some description here
    name: vim1
    schema_version: '1.1'
    vim_password: 5g0yGX86qIhprX86YTMcpg==
    vim_tenant_name: osm
    vim_type: openstack
    vim_url: http://10.95.87.162:5000/v2.0
    vim_user: osm
-   _admin:
        created: 1566818150.3024442
        current_operation: 0
        deployed:
            RO: 9ac17c0d-4265-4333-843b-c3cbd1f93f88
            RO-account: 011895dc-ab34-4c9f-b06f-401a8ffb073b
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
    _id: 05357241-1a01-416f-9e02-af20f65f51cd
    description: No description
    name: vim2
    schema_version: '1.1'
    vim_password: 5g0yGX86qIhprX86YTMcpg==
    vim_tenant_name: osm
    vim_type: dumy
    vim_url: http://10.95.88.162:5000/v2.0
    vim_user: osm
"""

db_k8sclusters_text = """
-   _admin:
        created: 1575031378.9268339
        current_operation: 0
        modified: 1575031378.9268339
        operationalState: ENABLED
        operations:
        -   detailed-status: ''
            lcmOperationType: create
            operationParams: null
            operationState: ''
            startTime: 1575031378.926895
            statusEnteredTime: 1575031378.926895
            worker: 36681ccf7f32
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        helm-chart:
            id: 73d96432-d692-40d2-8440-e0c73aee209c
            created: True
        helm-chart-v3:
            id: 73d96432-d692-40d2-8440-e0c73aee209c
            created: True
    _id: e7169dab-f71a-4f1f-b82b-432605e8c4b3
    credentials:
        apiVersion: v1
        users:
        -   name: admin
            user:
                password: qhpdogJXhBLG+JiYyyE0LeNsJXHkCSMy+sGVzlnJqes=
                username: admin
    description: Cluster3
    k8s_version: '1.15'
    name: cluster3
    namespace: kube-system
    nets:
        net1: None
    schema_version: '1.11'
    vim_account: ea958ba5-4e58-4405-bf42-6e3be15d4c3a
"""

db_vnfds_revisions_text = """
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
    _id: 7637bcf8-cf14-42dc-ad70-c66fcf1e6e77:1
    id: hackfest3charmed-vnf
    description: >-
      A VNF consisting of 2 VDUs connected to an internal VL, and one VDU
      with cloud-init
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
    kdu:
    - juju-bundle: stable/native-kdu
      name: native-kdu
    virtual-storage-desc:
      - id: mgmt-storage
        block-storage-data:
          size-of-storage: 10
      - id: data-storage
        block-storage-data:
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
        virtual-storage-desc: mgmt-storage
        int-cpd:
          - id: vnf-mgmt
            order: 1
            virtual-network-interface-requirement:
              - name: mgmtVM-eth0
                virtual-interface:
                  type: VIRTIO
          - id: mgmtVM-internal
            int-virtual-link-desc: internal
            order: 2
            virtual-network-interface-requirement:
              - name: mgmtVM-eth1
                virtual-interface:
                  type: VIRTIO
      - id: dataVM
        name: dataVM
        sw-image-desc: hackfest3-mgmt
        virtual-compute-desc: data-compute
        virtual-storage-desc: data-storage
        int-cpd:
          - id: dataVM-internal
            int-virtual-link-desc: internal
            order: 1
            virtual-network-interface-requirement:
              - name: dataVM-eth1
                virtual-interface:
                  type: VIRTIO
          - id: vnf-data
            order: 2
            virtual-network-interface-requirement:
              - name: dataVM-eth0
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
      A VNF consisting of 2 VDUs connected to an internal VL, and one VDU
      with cloud-init
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
        block-storage-data:
          size-of-storage: 10
      - id: data-storage
        block-storage-data:
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
        virtual-storage-desc: mgmt-storage
        int-cpd:
          - id: vnf-mgmt
            order: 1
            virtual-network-interface-requirement:
              - name: mgmtVM-eth0
                virtual-interface:
                  type: VIRTIO
          - id: mgmtVM-internal
            int-virtual-link-desc: internal
            order: 2
            virtual-network-interface-requirement:
              - name: mgmtVM-eth1
                virtual-interface:
                  type: VIRTIO
      - id: dataVM
        name: dataVM
        sw-image-desc: hackfest3-mgmt
        virtual-compute-desc: data-compute
        virtual-storage-desc: data-storage
        int-cpd:
          - id: dataVM-internal
            int-virtual-link-desc: internal
            order: 1
            virtual-network-interface-requirement:
              - name: dataVM-eth1
                virtual-interface:
                  type: VIRTIO
          - id: vnf-data
            order: 2
            virtual-network-interface-requirement:
              - name: dataVM-eth0
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
              relation:
                - entities:
                  - endpoint: interface
                    id: mgmtVM
                  - endpoint: interface
                    id: dataVM
                  name: relation
            - id: mgmtVM
              execution-environment-list:
              - id: simple-ee
                juju:
                  charm: simple_mgmtVM
                  proxy: false
                external-connection-point-ref: mgmt
            - id: dataVM
              execution-environment-list:
              - id: simple-ee
                juju:
                  charm: simple_dataVM
                  proxy: false
                external-connection-point-ref: mgmt

-   _admin:
        created: 1575031727.5383403
        modified: 1575031727.5383403
        onboardingState: ONBOARDED
        operationalState: ENABLED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        storage:
            descriptor: multikdu_knf/multikdu_vnfd.yaml
            folder: 7ab0d10d-8ce2-4c68-aef6-cc5a437a9c62
            fs: local
            path: /app/storage/
            pkg-dir: multikdu_knf
            zipfile: multikdu_knf.tar.gz
        usageState: NOT_IN_USE
        userDefinedData: {}
    _id: 7ab0d10d-8ce2-4c68-aef6-cc5a437a9c62
    connection-point:
    -   name: mgmt
    description: KNF with two KDU using helm-charts
    id: multikdu_knf
    df:
      - id: "default_df"
    k8s-cluster:
        nets:
        -   external-connection-point-ref: mgmt
            id: mgmtnet
    kdu:
    -   helm-chart: stable/openldap:1.2.1
        name: ldap
    -   helm-chart: stable/mongodb
        name: mongo
    mgmt-interface:
        cp: mgmt
    name: multikdu_knf
    short-name: multikdu_knf
    vendor: Telefonica
    version: '1.0'

-   _admin:
      created: 1575031727.5383403
      modified: 1575031727.5383403
      onboardingState: ONBOARDED
      operationalState: ENABLED
      projects_read:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
      projects_write:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
      storage:
        descriptor: native-kdu_knf/native-kdu_vnfd.yaml
        folder: d96b1cdf-5ad6-49f7-bf65-907ada989293
        fs: local
        path: /app/storage/
        pkg-dir: native-kdu_knf
        zipfile: native-kdu_knf.tar.gz
      usageState: NOT_IN_USE
      userDefinedData: {}
    _id: d96b1cdf-5ad6-49f7-bf65-907ada989293
    connection-point:
    - name: mgmt
    description: KNF with two KDU using juju-bundle
    df:
    - id: native-kdu
      kdu-resource-profile:
        - id: scale-app
          kdu-name: native-kdu
          min-number-of-instances: 1
          resource-name: app
        - id: scale-app2
          kdu-name: native-kdu
          min-number-of-instances: 1
          max-number-of-instances: 10
          resource-name: app2
      scaling-aspect:
      - id: kdu_scaling_group
        name: kdu_scaling_group
        max-scale-level: 10
        aspect-delta-details:
          deltas:
          - id: native-kdu-delta
            kdu-resource-delta:
            - id: scale-app
              number-of-instances: 1
      - id: kdu_scaling_group_2
        name: kdu_scaling_group_2
        max-scale-level: 10
        aspect-delta-details:
          deltas:
          - id: native-kdu-delta
            kdu-resource-delta:
            - id: scale-app
              number-of-instances: 1
            - id: scale-app2
              number-of-instances: 2
      lcm-operations-configuration:
        operate-vnf-op-config:
          day1-2:
          - id: native-kdu
            initial-config-primitive:
            - name: changecontent
              parameter:
              - data-type: STRING
                name: application-name
                value: nginx
              - data-type: STRING
                name: customtitle
                value: Initial Config Primitive
              seq: '1'
    id: native-kdu_knf
    k8s-cluster:
      nets:
      - external-connection-point-ref: mgmt
        id: mgmtnet
    kdu:
    - juju-bundle: stable/native-kdu
      name: native-kdu
    mgmt-interface:
      cp: mgmt
    name: native-kdu_knf
    short-name: native-kdu_knf
    vendor: Ulak Haberlesme A.S.
    version: '1.0'
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
        -   ip-address: 192.168.54.2
            mac-address: fa:16:3e:6e:7e:78
            name: mgmtVM-eth1
            vnf-vld-id: internal
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
        ns-image-id: 0
        ns-flavor-id: 0
        affinity-or-anti-affinity-group-id : []
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
        ns-image-id: 0
        ns-flavor-id: 0
        affinity-or-anti-affinity-group-id : []
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
        created: 1566823354.3668208
        modified: 1566823354.3668208
        nsState: NOT_INSTANTIATED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 6421c7c9-d865-4fb4-9a13-d4275d243e01
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
    id: 6421c7c9-d865-4fb4-9a13-d4275d243e01
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
        -   ip-address: 192.168.54.2
            mac-address: fa:16:3e:6e:7e:78
            name: mgmtVM-eth1
            vnf-vld-id: internal
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
        ns-image-id: 0
        ns-flavor-id: 0
        affinity-or-anti-affinity-group-id : []
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
        ns-image-id: 0
        ns-flavor-id: 0
        affinity-or-anti-affinity-group-id : []
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
        ns-image-id: 0
        ns-flavor-id: 0
        affinity-or-anti-affinity-group-id : []
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
        ns-image-id: 0
        ns-flavor-id: 0
        affinity-or-anti-affinity-group-id : []
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
        created: 1575034637.009597
        modified: 1575034637.009597
        nsState: NOT_INSTANTIATED
        projects_read:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
        projects_write:
        - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 5ac34899-a23a-4b3c-918a-cd77acadbea6
    additionalParamsForVnf: null
    connection-point:
    -   connection-point-id: null
        id: null
        name: mgmt
    created-time: 1575034636.9990137
    id: 5ac34899-a23a-4b3c-918a-cd77acadbea6
    ip-address: null
    k8s-cluster:
        nets:
        -   external-connection-point-ref: mgmt
            id: mgmtnet
            ns-vld-id: mgmtnet
            vim_net: internal
    kdur:
    -   ip-address: null
        k8s-cluster:
            id: e7169dab-f71a-4f1f-b82b-432605e8c4b3
        kdu-name: ldap
        helm-chart: stable/openldap:1.2.1
    -   ip-address: null
        k8s-cluster:
            id: e7169dab-f71a-4f1f-b82b-432605e8c4b3
        kdu-name: mongo
        helm-chart: stable/mongodb
    member-vnf-index-ref: multikdu
    nsr-id-ref: 0bcb701c-ee4d-41ab-8ee6-f4156f7f114d
    vdur: []
    vim-account-id: 74337dcb-ef54-41e7-bd2d-8c0d7fcd326f
    vnfd-id: 7ab0d10d-8ce2-4c68-aef6-cc5a437a9c62
    vnfd-ref: multikdu_knf

-   _admin:
      created: 1575034637.009597
      modified: 1575034637.009597
      nsState: NOT_INSTANTIATED
      projects_read:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
      projects_write:
      - 25b5aebf-3da1-49ed-99de-1d2b4a86d6e4
    _id: 5ac34899-a23a-4b3c-918a-cd77acadbea6
    additionalParamsForVnf: null
    connection-point:
    - connection-point-id: null
      id: null
      name: mgmt
    created-time: 1575034636.9990137
    id: 5ac34899-a23a-4b3c-918a-cd77acadbea6
    ip-address: null
    k8s-cluster:
      nets:
      - external-connection-point-ref: mgmt
        id: mgmtnet
        ns-vld-id: mgmtnet
        vim_net: internal
    kdur:
    - ip-address: null
      juju-bundle: app-bundle
      k8s-cluster:
        id: e7169dab-f71a-4f1f-b82b-432605e8c4b3
      kdu-name: native-kdu
    member-vnf-index-ref: native-kdu
    nsr-id-ref: c54b14cb-69a8-45bc-b011-d6bea187dc0a
    vdur: []
    vim-account-id: 74337dcb-ef54-41e7-bd2d-8c0d7fcd326f
    vnfd-id: d96b1cdf-5ad6-49f7-bf65-907ada989293
    vnfd-ref: native-kdu_knf

-   _id: a6df8aa0-1271-4dfc-85a5-e0484fea303f
    id: a6df8aa0-1271-4dfc-85a5-e0484fea303f
    nsr-id-ref: 52f0b3ac-1574-481f-a48f-528fc02912f7
    member-vnf-index-ref: '1'
    additionalParamsForVnf:
    created-time: 1652105830.965044
    vnfd-ref: ha_proxy_charm-vnf
    vnfd-id: 8b42078a-9d42-4def-8b5d-7dd0f041d078
    vim-account-id: dff4014e-bb5e-441a-a28d-6dd5d86c7175
    vca-id:
    vdur:
    - _id: 392e010d-3a39-4516-acc0-76993c19691f
      alt-image-ids:
      - '1'
      - '2'
      - '3'
      cloud-init: 8b42078a-9d42-4def-8b5d-7dd0f041d078:file:cloud-config.txt
      count-index: 0
      id: 392e010d-3a39-4516-acc0-76993c19691f
      internal-connection-point:
      - connection-point-id: mgmtVM-eth0-int
        id: mgmtVM-eth0-int
        name: mgmtVM-eth0-int
      - connection-point-id: dataVM-xe0-int
        id: dataVM-xe0-int
        name: dataVM-xe0-int
      ip-address: 10.45.28.134
      ns-flavor-id: '0'
      ns-image-id: '0'
      ssh-access-required: true
      vdu-id-ref: mgmtVM
      vdu-name: mgmtVM
      vim_info:
        vim:05357241-1a01-416f-9e02-af20f65f51cd:
          vim_id: 1f8c18e3-b3aa-484c-a211-e88d6654f24a
          vim_status: ACTIVE
          vim_name: test_ns_ch-1-mgmtVM-0
      status: ACTIVE
      vim-id: 1f8c18e3-b3aa-484c-a211-e88d6654f24a
      name: test_ns_ch-1-mgmtVM-0
      vim_details:
      vim_id: 1f8c18e3-b3aa-484c-a211-e88d6654f24a
      vim_status: DONE
      vim_message:
    ip-address: 10.45.28.134
    _admin:
      created: 1652105830.9652078
      modified: 1652105830.9652078
      projects_read:
      - e38990e1-6724-4292-ab6f-2ecc109f9af4
      projects_write:
      - e38990e1-6724-4292-ab6f-2ecc109f9af4
      nsState: INSTANTIATED
    vdu:
      status: DONE
      vim-id: 1f8c18e3-b3aa-484c-a211-e88d6654f24a
"""

db_nslcmops_scale_text = """
---
-   _admin:
      created: 1565250912.2643092
      modified: 1570026174.83263
      projects_read:
      - d3581c99-31e3-45f9-b45c-49a290faedbc
      current_operation: '5'
      deployed:
        RO: d9aea288-b9b1-11e9-b19e-02420aff0006
        RO-account: d9bb2f1c-b9b1-11e9-b19e-02420aff0006
      detailed-status: Done
      modified: 1565250912.2643092
      operationalState: ENABLED
      operations:
      - member_vnf_index: '1'
        primitive: touch
        primitive_params: /home/ubuntu/last-touch-1
        operationState: COMPLETED
        detailed-status: Done
      - member_vnf_index: '1'
        primitive: touch
        primitive_params: /home/ubuntu/last-touch-2
        operationState: COMPLETED
        detailed-status: Done
      - member_vnf_index: '2'
        primitive: touch
        primitive_params: /home/ubuntu/last-touch-3
        operationState: COMPLETED
        detailed-status: Done
      projects_read:
      - b2d2ce4b-a1a0-4c01-847e-048632c43b40
      projects_write:
      - b2d2ce4b-a1a0-4c01-847e-048632c43b40
      worker: c4055a07655b
      deploy:
        RO: ACTION-1570026232.061742
    _id: 053967e8-7c1c-400f-ae82-3d45b291374b
    lcmOperationType: scale
    nsInstanceId: 90d9ebb7-2b5a-4b7c-bc34-a51fd7ef7b7b
    statusEnteredTime: 1570026243.09784
    startTime: 1570026174.8326
    operationParams:
      lcmOperationType: scale
      nsInstanceId: 90d9ebb7-2b5a-4b7c-bc34-a51fd7ef7b7b
      scaleVnfData:
        scaleByStepData:
          member-vnf-index: '1'
          scaling-group-descriptor: scale_scaling_group
        scaleVnfType: SCALE_IN
      scaleType: SCALE_VNF
    isAutomaticInvocation: false
    isCancelPending: false
    id: 053967e8-7c1c-400f-ae82-3d45b291374b
    links:
      nsInstance: "/osm/nslcm/v1/ns_instances/90d9ebb7-2b5a-4b7c-bc34-a51fd7ef7b7b"
      self: "/osm/nslcm/v1/ns_lcm_op_occs/053967e8-7c1c-400f-ae82-3d45b291374b"
    operationState: COMPLETED
    detailed-status: done
"""

ro_update_action_text = """
action_id: e62fc036-6e6f-4a6f-885e-bc12e2fbe75d
details: progress 1/1
nsr_id: 31dbfa80-80a8-4f2a-a557-626904df3402
status: DONE
tasks:
- action: DELETE
  action_id: e62fc036-6e6f-4a6f-885e-bc12e2fbe75d
  item: vdu
  nsr_id: 31dbfa80-80a8-4f2a-a557-626904df3402
  status: FINISHED
  target_record: vnfrs:5bbe7015-ae98-4e09-9316-76f3bf218353:vdur.0.vim_info.vim:2a3dc443-415b-4865-8420-f804b993c5a3
  target_record_id: vnfrs:5bbe7015-ae98-4e09-9316-76f3bf218353:vdur.e03e2281-c70e-44ef-ac3b-052b81efd31d
  task_id: e62fc036-6e6f-4a6f-885e-bc12e2fbe75d:0
"""

test_ids = {
    # contains the ids of ns and operations of every test
    "TEST-A": {
        "ns": "f48163a6-c807-47bc-9682-f72caef5af85",
        "instantiate": "a639fac7-e0bb-4225-8ecb-c1f8efcc125e",
        "terminate": "a639fac7-e0bb-4225-ffff-c1f8efcc125e",
        "update": "6bd4362f-da74-4bd8-a825-fd00e610c644",
    },
    "TEST-KDU": {
        "ns": "0bcb701c-ee4d-41ab-8ee6-f4156f7f114d",
        "instantiate": "cf3aa178-7640-4174-b921-2330e6f2aad6",
        "terminate": None,
    },
    "TEST-NATIVE-KDU": {
        "ns": "c54b14cb-69a8-45bc-b011-d6bea187dc0a",
        "instantiate": "52770491-a765-40ce-97a1-c6e200bba7b3",
        "terminate": None,
    },
    "TEST-NATIVE-KDU-2": {
        "ns": "c54b14cb-69a8-45bc-b011-d6bea187dc0a",
        "instantiate": "4013bbd2-b151-40ee-bcef-7e24ce5432f6",
        "terminate": None,
    },
    "TEST-UPDATE": {
        "ns": "f48163a6-c807-47bc-9682-f72caef5af85",
        "vnf": "88d90b0c-faff-4b9f-bccd-017f33985984",
        "removeVnf": "a639fac7-e0bb-4225-8ecb-c1f8efcc125f",
    },
    "TEST-OP-VNF": {
        "ns": "f48163a6-c807-47bc-9682-f72caef5af85",
        "nslcmops": "1bd4b60a-e15d-49e5-b75e-2b3224f15dda",
        "nslcmops1": "6eace44b-2ef4-4de5-b15f-63f2e8898bfb",
        "vnfrs": "a6df8aa0-1271-4dfc-85a5-e0484fea303f",
    },
    "TEST-V-SCALE": {
        "ns": "f48163a6-c807-47bc-9682-f72caef5af85",
        "instantiate-1": "8b838aa8-53a3-4955-80bd-fbba6a7957ed",
        "instantiate": "a21af1d4-7f1a-4f7b-b666-222315113a62",
    },
}
