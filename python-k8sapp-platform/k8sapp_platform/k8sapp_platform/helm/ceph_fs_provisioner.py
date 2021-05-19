#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_platform.common import constants as app_constants

from sysinv.common import constants
from sysinv.common import exception

from sysinv.helm import base


class K8CephFSProvisioner(object):
    """ Utility methods for getting the k8 overrides for internal ceph
    from a corresponding storage backend.
    """

    @staticmethod
    def get_storage_class_name(bk):
        """ Get the name of the storage class for an rbd provisioner
        :param bk: Ceph storage backend object
        :returns: name of the rbd provisioner
        """
        if bk['capabilities'].get(app_constants.K8S_CEPHFS_PROV_STORAGECLASS_NAME):
            name = bk['capabilities'][app_constants.K8S_CEPHFS_PROV_STORAGECLASS_NAME]
        elif bk.name == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
            name = app_constants.K8S_CEPHFS_PROV_STOR_CLASS_NAME
        else:
            name = bk.name + '-' + app_constants.K8S_CEPHFS_PROV_STOR_CLASS_NAME

        return str(name)

    @staticmethod
    def get_data_pool(bk):
        """ Get the name of the ceph pool for an rbd provisioner
        This naming convention is valid only for internal backends
        :param bk: Ceph storage backend object
        :returns: name of the rbd provisioner
        """
        if bk['name'] == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
            return app_constants.CEPHFS_DATA_POOL_KUBE_NAME
        else:
            return str(app_constants.CEPHFS_DATA_POOL_KUBE_NAME + '-' + bk['name'])

    @staticmethod
    def get_metadata_pool(bk):
        """ Get the name of the ceph pool for an rbd provisioner
        This naming convention is valid only for internal backends
        :param bk: Ceph storage backend object
        :returns: name of the rbd provisioner
        """
        if bk['name'] == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
            return app_constants.CEPHFS_METADATA_POOL_KUBE_NAME
        else:
            return str(app_constants.CEPHFS_METADATA_POOL_KUBE_NAME + '-' + bk['name'])

    @staticmethod
    def get_fs(bk):
        """ Get the name of the ceph pool for an rbd provisioner
        This naming convention is valid only for internal backends
        :param bk: Ceph storage backend object
        :returns: name of the rbd provisioner
        """
        if bk['name'] == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
            return app_constants.CEPHFS_FS_KUBE_NAME
        else:
            return str(app_constants.CEPHFS_FS_KUBE_NAME + '-' + bk['name'])

    @staticmethod
    def get_user_id(bk):
        """ Get the non admin user name for an cephfs provisioner secret
        :param bk: Ceph storage backend object
        :returns: name of the cephfs provisioner
        """
        if bk['name'] == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
            name = K8CephFSProvisioner.get_data_pool(bk)
        else:
            name = K8CephFSProvisioner.get_data_pool(bk)

        prefix = 'ceph-pool'
        return str(prefix + '-' + name)

    @staticmethod
    def get_user_secret_name(bk):
        """ Get the name for the non admin secret key of a pool
        :param bk: Ceph storage backend object
        :returns: name of k8 secret
        """
        if bk['name'] == constants.SB_DEFAULT_NAMES[constants.SB_TYPE_CEPH]:
            name = K8CephFSProvisioner.get_data_pool(bk)
        else:
            name = K8CephFSProvisioner.get_data_pool(bk)

        base_name = 'ceph-pool'
        return str(base_name + '-' + name)


class CephFSProvisionerHelm(base.BaseHelm):
    """Class to encapsulate helm operations for the cephfs-provisioner chart"""

    CHART = app_constants.HELM_CHART_CEPH_FS_PROVISIONER
    SUPPORTED_NAMESPACES = base.BaseHelm.SUPPORTED_NAMESPACES + \
        [app_constants.HELM_NS_CEPH_FS_PROVISIONER]
    SUPPORTED_APP_NAMESPACES = {
        constants.HELM_APP_PLATFORM:
            base.BaseHelm.SUPPORTED_NAMESPACES + [app_constants.HELM_NS_CEPH_FS_PROVISIONER],
    }

    SERVICE_NAME = app_constants.HELM_CHART_CEPH_FS_PROVISIONER
    SERVICE_PORT_MON = 6789

    def execute_manifest_updates(self, operator):
        # On application load this chart is enabled. Only disable if specified
        # by the user
        if not self._is_enabled(operator.APP, self.CHART,
                                app_constants.HELM_NS_CEPH_FS_PROVISIONER):
            operator.chart_group_chart_delete(
                operator.CHART_GROUPS_LUT[self.CHART],
                operator.CHARTS_LUT[self.CHART])

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
            "adminId": app_constants.K8S_CEPHFS_PROVISIONER_USER_NAME,
            "adminSecretName": app_constants.K8S_CEPHFS_PROVISIONER_ADMIN_SECRET_NAME
        }

        # Get tier info.
        tiers = self.dbapi.storage_tier_get_list()

        classes = []
        for bk in ceph_bks:
            # Get the ruleset for the new kube-cephfs pools.
            tier = next((t for t in tiers if t.forbackendid == bk.id), None)
            if not tier:
                raise Exception("No tier present for backend %s" % bk.name)

            rule_name = "{0}{1}{2}".format(
                tier.name,
                constants.CEPH_CRUSH_TIER_SUFFIX,
                "-ruleset").replace('-', '_')

            cls = {
                "name": K8CephFSProvisioner.get_storage_class_name(bk),
                "data_pool_name": K8CephFSProvisioner.get_data_pool(bk),
                "metadata_pool_name": K8CephFSProvisioner.get_metadata_pool(bk),
                "fs_name": K8CephFSProvisioner.get_fs(bk),
                "replication": int(bk.capabilities.get("replication")),
                "crush_rule_name": rule_name,
                "chunk_size": 64,
                "userId": K8CephFSProvisioner.get_user_id(bk),
                "userSecretName": K8CephFSProvisioner.get_user_secret_name(bk),
                "claim_root": app_constants.HELM_CEPH_FS_PROVISIONER_CLAIM_ROOT,
                "additionalNamespaces": ['default', 'kube-public']
            }

            classes.append(cls)

        global_settings = {
            "replicas": self._num_replicas_for_platform_app(),
        }

        overrides = {
            app_constants.HELM_NS_CEPH_FS_PROVISIONER: {
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
