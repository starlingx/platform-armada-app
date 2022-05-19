#
# Copyright (c) 2020-2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_platform.common import constants as app_constants

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common.storage_backend_conf import K8RbdProvisioner

from sysinv.helm import base
from sysinv.helm import common


class RbdProvisionerHelm(base.BaseHelm):
    """Class to encapsulate helm operations for the rbd-provisioner chart"""

    CHART = app_constants.HELM_CHART_RBD_PROVISIONER
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
            operator.helm_release_resource_delete(self.CHART)

    def get_overrides(self, namespace=None):

        backends = self.dbapi.storage_backend_get_list()
        ceph_bks = [bk for bk in backends if bk.backend == constants.SB_TYPE_CEPH]

        if not ceph_bks:
            return {}  # ceph is not configured

        def _skip_ceph_mon_2(name):
            return name != constants.CEPH_MON_2

        classdefaults = {
            "monitors": self._get_formatted_ceph_monitor_ips(
                name_filter=_skip_ceph_mon_2),
            "adminId": constants.K8S_RBD_PROV_USER_NAME,
            "adminSecretName": constants.K8S_RBD_PROV_ADMIN_SECRET_NAME
        }

        # Get tier info.
        tiers = self.dbapi.storage_tier_get_list()

        classes = []
        for bk in ceph_bks:
            # Get the ruleset for the new kube-rbd pool.
            tier = next((t for t in tiers if t.forbackendid == bk.id), None)
            if not tier:
                raise Exception("No tier present for backend %s" % bk.name)

            rule_name = "{0}{1}{2}".format(
                tier.name,
                constants.CEPH_CRUSH_TIER_SUFFIX,
                "-ruleset").replace('-', '_')

            cls = {
                "name": K8RbdProvisioner.get_storage_class_name(bk),
                "pool_name": K8RbdProvisioner.get_pool(bk),
                "replication": int(bk.capabilities.get("replication")),
                "crush_rule_name": rule_name,
                "chunk_size": 64,
                "userId": K8RbdProvisioner.get_user_id(bk),
                "userSecretName": K8RbdProvisioner.get_user_secret_name(bk),
                "additionalNamespaces": ['default', 'kube-public'],
            }
            classes.append(cls)

        global_settings = {
            "replicas": self._num_replicas_for_platform_app(),
            "defaultStorageClass": constants.K8S_RBD_PROV_STOR_CLASS_NAME
        }

        overrides = {
            common.HELM_NS_RBD_PROVISIONER: {
                "classdefaults": classdefaults,
                "classes": classes,
                "global": global_settings
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
