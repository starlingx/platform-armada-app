#
# Copyright (c) 2022 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory Kustomization resource operator."""

from sysinv.common import constants
from sysinv.helm import kustomize_base as base


class PlatformFluxCDKustomizeOperator(base.FluxCDKustomizeOperator):

    APP = constants.HELM_APP_PLATFORM

    def platform_mode_kustomize_updates(self, dbapi, mode):
        """ Update the top-level kustomization resource list

        Make changes to the top-level kustomization resource list based on the
        platform mode

        :param dbapi: DB api object
        :param mode: mode to control when to update the resource list
        """
        pass
