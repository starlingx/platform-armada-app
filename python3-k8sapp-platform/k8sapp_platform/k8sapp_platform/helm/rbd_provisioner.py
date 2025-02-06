#
# Copyright (c) 2020-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_platform.common import constants as app_constants
from k8sapp_platform.common import utils as cutils

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import utils
from sysinv.common.storage_backend_conf import K8RbdProvisioner

from sysinv.helm import base
from sysinv.helm import common


class RbdProvisionerHelm(base.FluxCDBaseHelm):
    """Class to encapsulate helm operations for the rbd-provisioner chart"""

    CHART = app_constants.HELM_CHART_RBD_PROVISIONER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_RBD_PROVISIONER
    SUPPORTED_NAMESPACES = base.BaseHelm.SUPPORTED_NAMESPACES + \
        [common.HELM_NS_RBD_PROVISIONER]
    SUPPORTED_APP_NAMESPACES = {
        constants.HELM_APP_PLATFORM:
            base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_RBD_PROVISIONER],
    }

    SERVICE_NAME = app_constants.HELM_CHART_RBD_PROVISIONER
    SERVICE_PORT_MON = 6789

    def execute_manifest_updates(self, operator):
        # On application load this chart is enabled. Only disable if specified
        # by the user
        if not self._is_enabled(operator.APP, self.CHART,
                                common.HELM_NS_RBD_PROVISIONER):
            operator.chart_group_chart_delete(
                operator.CHART_GROUPS_LUT[self.CHART],
                operator.CHARTS_LUT[self.CHART])

    def execute_kustomize_updates(self, operator):
        # On application load this chart is enabled. Only disable if specified
        # by the user
        if not self._is_enabled(operator.APP, self.CHART,
                                common.HELM_NS_RBD_PROVISIONER):
            operator.helm_release_resource_delete(self.HELM_RELEASE)

    def get_overrides(self, namespace=None):

        backends = self.dbapi.storage_backend_get_list()
        ceph_bks = [bk for bk in backends if bk.backend == constants.SB_TYPE_CEPH]

        if not ceph_bks:
            return {}  # ceph is not configured

        def _skip_ceph_mon_2(name):
            return name != constants.CEPH_MON_2

        class_defaults = {
            "monitors": self._get_formatted_ceph_monitor_ips(
                name_filter=_skip_ceph_mon_2),
            "adminId": constants.K8S_RBD_PROV_USER_NAME,
            "adminSecretName": constants.K8S_RBD_PROV_ADMIN_SECRET_NAME,
            "storageClass": constants.K8S_RBD_PROV_STOR_CLASS_NAME
        }

        is_simplex = utils.is_aio_simplex_system(self.dbapi)
        snapshot_support = cutils.check_snapshot_support(app_constants.HELM_CHART_RBD_PROVISIONER)
        # Get tier info.
        tiers = self.dbapi.storage_tier_get_list()
        cluster_id = cutils.get_ceph_fsid()
        if not cluster_id:
            raise Exception("Could not identify Ceph cluster fsid. Try again when ceph cli is responsive.")
        storage_classes = []

        for bk in ceph_bks:
            # Search tier for backend.
            tier = next((t for t in tiers if t.forbackendid == bk.id), None)
            if not tier:
                raise Exception("No tier present for backend %s" % bk.name)

            rule_name = "{0}{1}{2}".format(
                tier.name,
                constants.CEPH_CRUSH_TIER_SUFFIX,
                "-ruleset").replace('-', '_')

            user_secret_name = K8RbdProvisioner.get_user_secret_name(bk)

            storage_class = {
                "clusterID": cluster_id,
                "name": K8RbdProvisioner.get_storage_class_name(bk),
                "pool_name": K8RbdProvisioner.get_pool(bk),
                "provisionerSecret": user_secret_name or class_defaults["adminSecretName"],
                "controllerExpandSecret": user_secret_name or class_defaults["adminSecretName"],
                "nodeStageSecret": user_secret_name or class_defaults["adminSecretName"],
                "userId": K8RbdProvisioner.get_user_id(bk),
                "userSecretName": user_secret_name,
                "chunk_size": 64,
                "replication": int(bk.capabilities.get("replication")),
                "crush_rule_name": rule_name,
                "additionalNamespaces": ['default', 'kube-public']
            }

            storage_classes.append(storage_class)

        snapshot_class = {
            "clusterID": cluster_id,
            "provisionerSecret": user_secret_name or class_defaults["adminSecretName"]
        }

        provisioner = {
            "replicaCount": self._num_replicas_for_platform_app(),
            "snapshotter": {
                "enabled": snapshot_support
            },
            "leaderElection": {
                "enabled": not is_simplex
            }
        }

        csi_config = [{
            "clusterID": cluster_id,
            "monitors": [monitor for monitor in class_defaults["monitors"]]
        }]

        overrides = {
            common.HELM_NS_RBD_PROVISIONER: {
                "storageClasses": storage_classes,
                "snapshotClass": snapshot_class,
                "provisioner": provisioner,
                "csiConfig": csi_config,
                "classdefaults": class_defaults
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
