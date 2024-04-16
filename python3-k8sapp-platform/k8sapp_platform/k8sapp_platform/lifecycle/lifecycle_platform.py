#
# Copyright (c) 2021-2024 Wind River Systems, Inc.
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

from oslo_log import log as logging
from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import kubernetes
from sysinv.common import utils as cutils
from sysinv.db import api as dbapi
from sysinv.helm import lifecycle_base as base
from sysinv.helm import lifecycle_utils as lifecycle_utils
from k8sapp_platform.common import constants as app_constants

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
        if hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK:
            if hook_info.mode == constants.APP_LIFECYCLE_MODE_AUTO and \
                    ((hook_info.operation == constants.APP_APPLY_OP and
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE) or
                    hook_info.mode == constants.APP_EVALUATE_REAPPLY_OP):
                return self.pre_auto_apply_check(conductor_obj)

        # Rbd
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_RBD:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return lifecycle_utils.create_rbd_provisioner_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                return lifecycle_utils.delete_rbd_provisioner_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_RECOVER_OP:
                return self.delete_csi_drivers(app)

        # Resources
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return self.pre_apply(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                return lifecycle_utils.delete_local_registry_secrets(app_op, app, hook_info)

        # Use the default behaviour for other hooks
        super(PlatformAppLifecycleOperator, self).app_lifecycle_actions(context, conductor_obj, app_op, app, hook_info)

    def pre_auto_apply_check(self, conductor_obj):
        """ Semantic check for auto-apply

        Check:
            - ceph access
            - ceph health
            - crushmap applied
            - replica count is non-zero so that manifest apply will not timeout

        :param conductor_obj: conductor object

        """
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
                "Monitor access error")
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

    def pre_apply(self, app_op, app, hook_info):
        """Pre Apply actions

        Creates the local registry secret and rename user overrides from
        'classes' to 'storageClasses' in the rbd and cephfs charts if
        necessary.

        :param app_op: AppOperator object
        :param app: AppOperator.Application object
        :param hook_info: LifecycleHookInfo object

        """
        lifecycle_utils.create_local_registry_secrets(app_op, app, hook_info)

        # TODO: The code below is for stx.8.0 -> stx.9.0 updates.
        # It may be removed in the stx.10.0 release cycle
        dbapi_instance = dbapi.get_instance()
        # get most recently created inactive app
        inactive_db_apps = dbapi_instance.kube_app_get_inactive(
            app.name, limit=1, sort_key='created_at', sort_dir='desc')

        if not inactive_db_apps:
            # user overrides will not be updated because there is no
            # inactive platform-integ-apps entry in the database
            return

        from_db_app = inactive_db_apps[0]
        to_db_app = dbapi_instance.kube_app_get(app.name)

        charts = [
            app_constants.FLUXCD_HELMRELEASE_CEPH_FS_PROVISIONER,
            app_constants.FLUXCD_HELMRELEASE_RBD_PROVISIONER,
        ]

        # update of user overrides due to changing 'classes' to 'storageClasses'
        # to improve understanding. The namespace of both charts are the same
        for chart in charts:
            user_overrides = self._get_helm_user_overrides(
                dbapi_instance,
                from_db_app,
                chart,
                app_constants.K8S_CEPHFS_PROVISIONER_DEFAULT_NAMESPACE)

            if 'classes:' in user_overrides:
                user_overrides = user_overrides.replace("classes:", "storageClasses:")
                self._update_helm_user_overrides(
                        dbapi_instance,
                        to_db_app,
                        chart,
                        app_constants.K8S_CEPHFS_PROVISIONER_DEFAULT_NAMESPACE,
                        user_overrides,
                )
                LOG.debug("User overrides of 'classes' updated to 'storageClasses'"
                          " in {} chart from {}".format(chart, app.name))

    def delete_csi_drivers(self, app):
        """ Delete CSI drivers

        This function is invoked when a recovery occurs,
        deleting the drivers created during the update.

        :param app: AppOperator.Application object

        """
        drivers = ["cephfs.csi.ceph.com", "rbd.csi.ceph.com"]
        for driver in drivers:
            cmd = ["kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF, "delete", "csidriver", driver]
            stdout, stderr = cutils.trycmd(*cmd)
            LOG.debug("{} app: cmd={} stdout={} stderr={}".format(app.name, cmd, stdout, stderr))

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
