#
# Copyright (c) 2024 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log
from sysinv.common import kubernetes

import subprocess

LOG = log.getLogger(__name__)


def get_ceph_fsid():
    process = subprocess.Popen(['timeout', '30', 'ceph', 'fsid'],
        stdout=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return stdout.strip()


def check_snapshot_support(chart):
    # This method checks if the necessary resources for the csi-snapshotter are present to create the
    # container inside each provisioner pod
    crds = [
        'volumesnapshotclasses.snapshot.storage.k8s.io',
        'volumesnapshots.snapshot.storage.k8s.io',
        'volumesnapshotcontents.snapshot.storage.k8s.io'
    ]
    for crd in crds:
        # Use subprocess to check if the CRDs exist
        crd_result = subprocess.run(["kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF,
                                        "get", "crd", crd], check=False)
        # Check the CRD command status
        if crd_result.returncode == 0:
            LOG.debug("The CRD '{}' exists".format(crd))
        else:
            LOG.debug("The CRD '{}' does not exist. As a result, the csi-snapshotter container inside the {}"
                      " pod will be disabled".format(crd, chart))
            return False

    # Use subprocess to check the pod's health and its image version
    running_pod = subprocess.run(
        ["kubectl", "--kubeconfig", kubernetes.KUBERNETES_ADMIN_CONF, "get", "pods", "-A", "--selector",
        "app=volume-snapshot-controller", "-o=jsonpath='{.items[0].spec.containers[0].image}'"],
        check=False, stdout=subprocess.PIPE, text=True
    )

    kube = kubernetes.KubeOperator()
    k8s_version = kube.kube_get_kubernetes_version()

    # Use subprocess to get the correct version of snapshot-controller image according to the k8s version
    path = '/usr/share/ansible/stx-ansible/playbooks/roles/common/load-images-information/vars/k8s-' + \
            k8s_version + '/system-images.yml'
    command = "grep 'snapshot_controller_img:' " + path + " | cut -d ':' -f2,3"
    snapshot_version = subprocess.run(command, check=False, shell=True, stdout=subprocess.PIPE, text=True)

    # Check if the image version of the running pod is the same as the expected for the K8s version
    if running_pod.returncode == 0 and snapshot_version.stdout.strip() in running_pod.stdout:
        LOG.debug("A running snapshot-controller pod with the correct snapshot-controller image exists.")
        return True
    else:
        LOG.debug("No running snapshot-controller pod with the correct snapshot-controller image. "
                  "As a result, the csi-snapshotter container inside the {} pod will be "
                  "disabled".format(chart))
        return False
