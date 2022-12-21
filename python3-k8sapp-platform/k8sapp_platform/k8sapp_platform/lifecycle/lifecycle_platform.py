#
# Copyright (c) 2021 Wind River Systems, Inc.
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
from sysinv.helm import lifecycle_base as base
from sysinv.helm import lifecycle_utils as lifecycle_utils

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
                    hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return self.pre_auto_apply_check(conductor_obj)

        # Rbd
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_RBD:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return lifecycle_utils.create_rbd_provisioner_secrets(app_op, app, hook_info)
            elif hook_info.operation == constants.APP_REMOVE_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_POST:
                return lifecycle_utils.delete_rbd_provisioner_secrets(app_op, app, hook_info)

        # Resources
        elif hook_info.lifecycle_type == constants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
                    hook_info.relative_timing == constants.APP_LIFECYCLE_TIMING_PRE:
                return lifecycle_utils.create_local_registry_secrets(app_op, app, hook_info)
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
