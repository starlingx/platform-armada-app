#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

#! /bin/bash
set -x

{{ $classes := .Values.classes}}

touch /etc/ceph/ceph.client.admin.keyring

# Check if ceph is accessible
echo "===================================="
ceph -s
if [ $? -ne 0 ]; then
  echo "Error: Ceph cluster is not accessible, check Pod logs for details."
  exit 1
fi

set -ex
KEYRING=$(ceph auth get-or-create client.${USER_ID} mon "allow r" osd "allow rwx pool=${DATA_POOL_NAME}" | sed -n 's/^[[:blank:]]*key[[:blank:]]\+=[[:blank:]]\(.*\)/\1/p')
# Set up pool key in Ceph format
CEPH_USER_KEYRING=/etc/ceph/ceph.client.${USER_ID}.keyring
echo $KEYRING >$CEPH_USER_KEYRING
set +ex

if [ -n "${CEPH_USER_SECRET}" ]; then
  kubectl get secret -n ${NAMESPACE} ${CEPH_USER_SECRET} 2>/dev/null
  if [ $? -ne 0 ]; then
    echo "Create ${CEPH_USER_SECRET} secret"
    kubectl create secret generic -n ${NAMESPACE} ${CEPH_USER_SECRET} --type="kubernetes.io/cephfs" --from-literal=key=$KEYRING
    if [ $? -ne 0 ]; then
      echo"Error creating secret ${CEPH_USER_SECRET} in ${NAMESPACE}, exit"
      exit 1
    fi
  else
    echo "Secret ${CEPH_USER_SECRET} already exists"
  fi

  # Support creating namespaces and Ceph user secrets for additional
  # namespaces other than that which the provisioner is installed. This
  # allows the provisioner to set up and provide PVs for multiple
  # applications across many namespaces.
  if [ -n "${ADDITIONAL_NAMESPACES}" ]; then
    for ns in $(
      IFS=,
      echo ${ADDITIONAL_NAMESPACES}
    ); do
      kubectl get namespace $ns 2>/dev/null
      if [ $? -ne 0 ]; then
        kubectl create namespace $ns
        if [ $? -ne 0 ]; then
          echo "Error creating namespace $ns, exit"
          continue
        fi
      fi

      kubectl get secret -n $ns ${CEPH_USER_SECRET} 2>/dev/null
      if [ $? -ne 0 ]; then
        echo "Creating secret ${CEPH_USER_SECRET} for namespace $ns"
        kubectl create secret generic -n $ns ${CEPH_USER_SECRET} --type="kubernetes.io/cephfs" --from-literal=key=$KEYRING
        if [ $? -ne 0 ]; then
          echo "Error creating secret ${CEPH_USER_SECRET} in $ns, exit"
        fi
      else
        echo "Secret ${CEPH_USER_SECRET} for namespace $ns already exists"
      fi
    done
  fi
fi

ceph osd pool stats ${DATA_POOL_NAME} || ceph osd pool create ${DATA_POOL_NAME} ${CHUNK_SIZE}
ceph osd pool application enable ${DATA_POOL_NAME} cephfs
ceph osd pool set ${DATA_POOL_NAME} size ${POOL_REPLICATION}
ceph osd pool set ${DATA_POOL_NAME} crush_rule ${POOL_CRUSH_RULE_NAME}

ceph osd pool stats ${METADATA_POOL_NAME} || ceph osd pool create ${METADATA_POOL_NAME} ${CHUNK_SIZE}
ceph osd pool application enable ${METADATA_POOL_NAME} cephfs
ceph osd pool set ${METADATA_POOL_NAME} size ${POOL_REPLICATION}
ceph osd pool set ${METADATA_POOL_NAME} crush_rule ${POOL_CRUSH_RULE_NAME}

ceph fs ls | grep ${FS_NAME} || ceph fs new ${FS_NAME} ${METADATA_POOL_NAME} ${DATA_POOL_NAME}

ceph -s
