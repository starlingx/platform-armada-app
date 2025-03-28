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


class CephFSProvisionerHelm(base.FluxCDBaseHelm):
    """Class to encapsulate helm operations for the cephfs-provisioner chart"""

    CHART = app_constants.HELM_CHART_CEPH_FS_PROVISIONER
    HELM_RELEASE = app_constants.FLUXCD_HELMRELEASE_CEPH_FS_PROVISIONER
    SUPPORTED_NAMESPACES = base.BaseHelm.SUPPORTED_NAMESPACES + \
        [app_constants.HELM_NS_CEPH_FS_PROVISIONER]
    SUPPORTED_APP_NAMESPACES = {
        constants.HELM_APP_PLATFORM:
            base.BaseHelm.SUPPORTED_NAMESPACES + [app_constants.HELM_NS_CEPH_FS_PROVISIONER],
    }

    SERVICE_NAME = app_constants.HELM_CHART_CEPH_FS_PROVISIONER
    SERVICE_PORT_MON = 6789

    def execute_kustomize_updates(self, operator):
        # On application load this chart is enabled. Only disable if specified
        # by the user
        if not self._is_enabled(operator.APP, self.CHART,
                                app_constants.HELM_NS_CEPH_FS_PROVISIONER):
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
            "adminId": app_constants.K8S_CEPHFS_PROVISIONER_USER_NAME,
            "adminSecretName": app_constants.K8S_CEPHFS_PROVISIONER_ADMIN_SECRET_NAME
        }

        is_simplex = utils.is_aio_simplex_system(self.dbapi)
        snapshot_support = cutils.check_snapshot_support(app_constants.HELM_CHART_CEPH_FS_PROVISIONER)
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

            user_secret_name = K8CephFSProvisioner.get_user_secret_name(bk)

            storage_class = {
                "clusterID": cluster_id,
                "name": K8CephFSProvisioner.get_storage_class_name(bk),
                "fs_name": K8CephFSProvisioner.get_fs(bk),
                "kernelMountOptions": "recover_session=clean",
                "data_pool_name": K8CephFSProvisioner.get_data_pool(bk),
                "metadata_pool_name": K8CephFSProvisioner.get_metadata_pool(bk),
                "volumeNamePrefix": app_constants.HELM_CEPH_FS_PROVISIONER_VOLUME_NAME_PREFIX,
                "provisionerSecret": user_secret_name,
                "controllerExpandSecret": user_secret_name,
                "nodeStageSecret": user_secret_name,
                "userId": K8CephFSProvisioner.get_user_id(bk),
                "userSecretName": user_secret_name or class_defaults["adminSecretName"],
                "chunk_size": 64,
                "replication": int(bk.capabilities.get("replication")),
                "min_replication": int(bk.capabilities.get("min_replication")),
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

        monitors = self._get_formatted_ceph_monitor_ips(
                name_filter=_skip_ceph_mon_2)

        csi_config = [{
            "clusterID": cluster_id,
            "monitors": [monitor for monitor in monitors],
            "cephFS": {
                "subvolumeGroup": "csi"
            }
        }]

        overrides = {
            app_constants.HELM_NS_CEPH_FS_PROVISIONER: {
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
