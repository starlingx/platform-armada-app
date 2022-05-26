# Application tunables (maps to metadata)
%global app_name platform-integ-apps
%global helm_repo stx-platform

# Install location
%global app_folder /usr/local/share/applications/helm

# Build variables
%global helm_folder /usr/lib/helm
%global toolkit_version 0.2.19

Summary: StarlingX K8S FluxCD application: Platform Integration
Name: stx-platform-helm
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: unknown

Source0: %{name}-%{version}.tar.gz

BuildArch: noarch

BuildRequires: helm
BuildRequires: openstack-helm-infra
BuildRequires: chartmuseum
BuildRequires: python-k8sapp-platform
BuildRequires: python-k8sapp-platform-wheels

%description
The StarlingX K8S FluxCD application for platform integration

%package armada
Summary: The StarlingX K8S Armada application for platform integration
Group: base
License: Apache-2.0

%description armada
The StarlingX K8S Armada application for platform integration

%prep
%setup

%build
# Stage helm-toolkit in the local repo
cp %{helm_folder}/helm-toolkit-%{toolkit_version}.tgz helm-charts/

# Host a server for the charts.
chartmuseum --debug --port=8879 --context-path='/charts' --storage="local" --storage-local-rootdir="./helm-charts" &
sleep 2
helm repo add local http://localhost:8879/charts

# Make the charts. These produce a tgz file
cd helm-charts
make rbd-provisioner
make ceph-pools-audit
make cephfs-provisioner
# TODO (rchurch): remove
make node-feature-discovery
cd -

# Terminate helm server (the last backgrounded task)
kill %1

# Create a chart tarball compliant with sysinv kube-app.py
%define app_staging %{_builddir}/staging
%define app_tarball_armada %{app_name}-armada-%{version}-%{tis_patch_ver}.tgz
%define app_tarball_fluxcd %{app_name}-%{version}-%{tis_patch_ver}.tgz
%define armada_app_path %{_builddir}/%{app_tarball_armada}
%define fluxcd_app_path %{_builddir}/%{app_tarball_fluxcd}

# Setup staging
mkdir -p %{app_staging}
cp files/metadata.yaml %{app_staging}
cp manifests/manifest.yaml %{app_staging}
mkdir -p %{app_staging}/charts
cp helm-charts/*.tgz %{app_staging}/charts
cd %{app_staging}

# Populate metadata
sed -i 's/@APP_NAME@/%{app_name}/g' %{app_staging}/metadata.yaml
sed -i 's/@APP_VERSION@/%{version}-%{tis_patch_ver}/g' %{app_staging}/metadata.yaml
sed -i 's/@HELM_REPO@/%{helm_repo}/g' %{app_staging}/metadata.yaml

# Copy the plugins: installed in the buildroot
mkdir -p %{app_staging}/plugins
cp /plugins/%{app_name}/*.whl %{app_staging}/plugins

# calculate checksum
find . -type f ! -name '*.md5' -print0 | xargs -0 md5sum > checksum.md5

# package armada app
tar -zcf %armada_app_path -C %{app_staging}/ .

# switch back to source root
cd -

# Prepare app_staging for fluxcd package
rm -f %{app_staging}/manifest.yaml

cp -R fluxcd-manifests %{app_staging}/

# calculate checksum of all files in app_staging
cd %{app_staging}
find . -type f ! -name '*.md5' -print0 | xargs -0 md5sum > checksum.md5
# package fluxcd app
tar -zcf %fluxcd_app_path -C %{app_staging}/ .

# switch back to source root
cd -

# Cleanup staging
rm -fr %{app_staging}

%install
install -d -m 755 %{buildroot}/%{app_folder}
install -p -D -m 755 %armada_app_path %{buildroot}/%{app_folder}
install -p -D -m 755 %fluxcd_app_path %{buildroot}/%{app_folder}
install -d -m 755 ${RPM_BUILD_ROOT}/opt/extracharts
# TODO (rchurch): remove
install -p -D -m 755 helm-charts/node-feature-discovery-*.tgz ${RPM_BUILD_ROOT}/opt/extracharts

%files armada
%defattr(-,root,root,-)
%{app_folder}/%{app_tarball_armada}
/opt/extracharts/*

%files
%defattr(-,root,root,-)
%{app_folder}/%{app_tarball_fluxcd}
