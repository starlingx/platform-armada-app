#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

[global]
	# For version 0.55 and beyond, you must explicitly enable
	# or disable authentication with "auth" entries in [global].
	auth_cluster_required = none
	auth_service_required = none
	auth_client_required = none

{{ $defaults := .Values.classdefaults}}

{{ $monitors := $defaults.monitors }}{{ range $index, $element := $monitors}}
[mon.{{- $index }}]
mon_addr = {{ $element }}
{{- end }}
