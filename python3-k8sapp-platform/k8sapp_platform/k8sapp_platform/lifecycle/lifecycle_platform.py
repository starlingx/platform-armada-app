#
# Copyright (c) 2021-2025 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory App lifecycle operator."""
# Temporary disable pylint for lifecycle hooks until Ic83fbd25d23ae34889cb288330ec448f920bda39 merges
# This will be reverted in a future commit
# pylint: disable=no-member
# pylint: disable=no-name-in-module
import os
import subprocess
from pathlib import Path

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import kubernetes
from sysinv.common import utils as cutils
from sysinv.helm import lifecycle_base as base
from sysinv.helm import lifecycle_utils as lifecycle_utils
from sysinv.helm.lifecycle_constants import LifecycleConstants

LOG = logging.getLogger(__name__)


class PlatformAppLifecycleOperator(base.AppLifecycleOperator):
    def app_lifecycle_actions(self, context, conductor_obj, app_op, app, hook_info):
        """ Perform lifecycle actions for an operation

        :param context: request context
        :param conductor_obj: conductor object
        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        # Semantic checks
        if hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK:
            # The kube_app logic does not send the hook_info.relative_timing value
            # when this is an APP_EVALUATE_REAPLY_OP operation.
            # Therefore, check the hook_info.operation first and validate if the
            # relative_timing is provided. If it is not, run the pre-apply checks.
            if hook_info.operation in [constants.APP_APPLY_OP,
                                       constants.APP_EVALUATE_REAPPLY_OP]:
                if "relative_timing" not in hook_info or \
                        hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                    return self.pre_apply_check(app_op, conductor_obj)

        # Rbd
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_RBD:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return lifecycle_utils.create_rbd_provisioner_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                return lifecycle_utils.delete_rbd_provisioner_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_RECOVER_OP:
                return self.delete_csi_drivers(app)

        # Resources
        elif hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self.pre_apply(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_POST:
                return lifecycle_utils.delete_local_registry_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_UPDATE_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self.pre_update(app)
            elif hook_info.operation == constants.APP_DOWNGRADE_OP and \
                    hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self.pre_downgrade(app, hook_info)

        # Use the default behaviour for other hooks
        super(PlatformAppLifecycleOperator, self).app_lifecycle_actions(context, conductor_obj, app_op, app, hook_info)

    def pre_apply_check(self, app_op, conductor_obj):
        """ Semantic check for apply

        Check:
            - ceph backend configured
            - ceph access
            - ceph health
            - crushmap applied
            - replica count is non-zero so that manifest apply will not timeout
            - ceph cli is responsive as it will be used by the application during the apply

        :param conductor_obj: conductor object

        """
        dbapi = app_op._dbapi
        storage_backend_list = dbapi.storage_backend_get_list_by_type(constants.SB_TYPE_CEPH)

        if not storage_backend_list:
            raise exception.LifecycleSemanticCheckException(
                "Ceph storage backend not configured")

        crushmap_flag_file = os.path.join(constants.SYSINV_CONFIG_PATH,
                                          constants.CEPH_CRUSH_MAP_APPLIED)

        if not os.path.isfile(crushmap_flag_file):
            raise exception.LifecycleSemanticCheckException(
                "Crush map not applied")
        if conductor_obj is None:
            raise exception.LifecycleSemanticCheckException(
                "Conductor object is None")
        # conductor_obj._ceph (CephOperator) may not be initialized
        # at this point, as it depends on ceph and system conditions
        # to start the thread that initializes it
        if conductor_obj._ceph is None:
            raise exception.LifecycleSemanticCheckException(
                "CephOperator is not initialized yet")
        if not conductor_obj._ceph.have_ceph_monitor_access():
            raise exception.LifecycleSemanticCheckException(
                "Ceph monitor is unreacheable")
        if not conductor_obj._ceph.ceph_status_ok():
            raise exception.LifecycleSemanticCheckException(
                "Ceph status is not HEALTH_OK")
        if conductor_obj.dbapi.count_hosts_matching_criteria(
                personality=constants.CONTROLLER,
                administrative=constants.ADMIN_UNLOCKED,
                operational=constants.OPERATIONAL_ENABLED,
                availability=[constants.AVAILABILITY_AVAILABLE,
                              constants.AVAILABILITY_DEGRADED],
                vim_progress_status=constants.VIM_SERVICES_ENABLED) < 1:
            raise exception.LifecycleSemanticCheckException(
                "Not enough hosts in desired state")

        # Check if ceph cli is responsive.
        ceph_fsid_cmd = ["timeout", "10", "ceph", "fsid"]
        result = subprocess.run(ceph_fsid_cmd, check=False)
        if (result.returncode != 0):
            raise exception.LifecycleSemanticCheckException(
                "Ceph CLI is not responsive")

    def pre_apply(self, app_op, app, hook_info):
        """Pre Apply actions

        This function creates the local registry secret.

        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        lifecycle_utils.create_local_registry_secrets(app_op, app, hook_info)

    def pre_downgrade(self, app, hook_info):
        """ Pre downgrade actions

        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object
        """
        self.truncate_helm_overrides(app, hook_info)
        self.delete_cephfs_driver(app)

    def pre_update(self, app):
        """ Pre update actions

        :param app: AppOperator.Application object

        """
        self.delete_cephfs_driver(app)

    def truncate_helm_overrides(self, app, hook_info):
        """ Truncate helm overrides

        This function forces a reapply of the app after 'software deploy activate-rollback',
        clearing the contents of the N-1 release overrides, so that kube_app can identify
        changes in the overrides.

        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object
        """
        from_app_version = hook_info.extra.get("from_app_version")
        to_app_version = hook_info.extra.get("to_app_version")

        from_release = from_app_version.split("-")[0]
        to_release = to_app_version.split("-")[0]

        if from_release != to_release:
            overrides_path = Path(os.path.join(constants.PLATFORM_PATH,
                                               "helm",
                                               to_release,
                                               app.name,
                                               to_app_version))
            if os.path.isdir(overrides_path):
                for override_path in overrides_path.glob("*.yaml"):
                    override_path.write_text("")

    def delete_cephfs_driver(self, app):
        """ Delete CephFS CSI driver

        This is to address a breaking change when downgrading from cephcsi v3.15.0
        which added the csi-attacher to cephfs and the attachRequired field
        changed from false to true on the csi driver.

        Since this field is immutable, we need to delete the driver and allow
        helm to recreate it.

        :param app: AppOperator.Application object

        """
        driver_name = "cephfs.csi.ceph.com"
        self.delete_csi_driver(app, driver_name)

    def delete_csi_driver(self, app, driver_name):
        """ Delete a specific CSI driver

        :param app: AppOperator.Application object
        :param driver_name: name of the CSI driver to delete

        """
        cmd = ["kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF, "delete", "csidriver", driver_name]
        cutils.trycmd(*cmd)

    def delete_csi_drivers(self, app):
        """ Delete CSI drivers

        This function is invoked when a recovery occurs,
        deleting the drivers created during the update.

        :param app: AppOperator.Application object

        """
        drivers = ["cephfs.csi.ceph.com", "rbd.csi.ceph.com"]
        for driver in drivers:
            self.delete_csi_driver(app, driver)

    def _get_helm_user_overrides(self, dbapi_instance, app, chart, namespace):
        try:
            return dbapi_instance.helm_override_get(
                app_id=app.id,
                name=chart,
                namespace=namespace,
            ).user_overrides or ""
        except exception.HelmOverrideNotFound:
            # Override for this chart not found, nothing to be done
            return ""

    def _update_helm_user_overrides(self, dbapi_instance, app, chart, namespace, overrides):
        values = {'user_overrides': overrides}
        dbapi_instance.helm_override_update(
            app_id=app.id, name=chart, namespace=namespace, values=values)
