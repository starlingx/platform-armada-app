#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

# Helm: Supported charts:
# These values match the names in the chart package's Chart.yaml
from sysinv.helm import common

HELM_CHART_RBD_PROVISIONER = 'rbd-provisioner'
HELM_CHART_CEPH_POOLS_AUDIT = 'ceph-pools-audit'
HELM_CHART_HELM_TOOLKIT = 'helm-toolkit'
HELM_CHART_CEPH_FS_PROVISIONER = 'cephfs-provisioner'
HELM_NS_CEPH_FS_PROVISIONER = common.HELM_NS_KUBE_SYSTEM

HELM_CEPH_FS_PROVISIONER_CLAIM_ROOT = '/pvc-volumes'
HELM_CHART_CEPH_FS_PROVISIONER_NAME = 'ceph.com/cephfs'
K8S_CEPHFS_PROVISIONER_ADMIN_SECRET_NAME = 'ceph-secret-admin'
K8S_CEPHFS_PROVISIONER_ADMIN_SECRET_NAMESPACE = 'kube-system'
K8S_CEPHFS_PROVISIONER_USER_NAME = 'admin'

K8S_CEPHFS_PROVISIONER_DEFAULT_NAMESPACE = 'kube-system'
K8S_CEPHFS_PROVISIONER_RBAC_CONFIG_NAME = 'cephfs-provisioner-keyring'

# CephFS Provisioner backend
K8S_CEPHFS_PROV_STORAGECLASS_NAME = 'cephfs_storageclass_name'             # Customer
K8S_CEPHFS_PROV_STOR_CLASS_NAME = 'cephfs'

# Ceph FS constants for pools and fs
CEPHFS_DATA_POOL_KUBE_NAME = 'kube-cephfs-data'
CEPHFS_METADATA_POOL_KUBE_NAME = 'kube-cephfs-metadata'
CEPHFS_FS_KUBE_NAME = 'kube-cephfs'
