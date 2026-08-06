# AlmaLinux 9 unattended install for condor01.
# This profile wipes the target disk and installs only the base OS. HTCondor
# roles are applied later with Ansible.

text
skipx
eula --agreed
reboot

lang en_US.UTF-8
keyboard us
timezone Europe/Kyiv --utc

network --bootproto=dhcp --device=link --activate --hostname=condor01.internal

rootpw --lock
user --name=npdadmin --groups=wheel --shell=/bin/bash

firewall --enabled --service=ssh
selinux --enforcing
services --enabled=sshd,chronyd,NetworkManager

url --url=http://10.10.80.10/alma-cache/almalinux/9/BaseOS/x86_64/os
repo --name=AppStream --baseurl=http://10.10.80.10/alma-cache/almalinux/9/AppStream/x86_64/os

zerombr
clearpart --all --initlabel
autopart --type=lvm
bootloader --location=mbr

%packages --excludedocs --excludeWeakdeps
@^minimal-environment
chrony
curl
dnf-plugins-core
openssh-server
python3
rsync
sudo
vim-minimal
wget
%end

%post --log=/root/npd-postinstall.log
set -eux

mkdir -p /home/npdadmin/.ssh
cat > /home/npdadmin/.ssh/authorized_keys <<'EOF'
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDf7y0qcaGhfdha0Dz9mSMLNvPteO7JZ4nuk2Q1ZX9oa87PKv0oKZjz8b9/x0I1SffbkCfOncZMSUOHZ8omfj7ryIIa46qMFhhxcwvNVEbxiAqC71UyfXLzlmFW42TDF/fhLVlB1MNpLXhPznkGj5uwnNy9jYr0F9HfD86N02AEdsQbJ7IUFiezx2kr8xagmgFnrJ2Tv+b+mYwkxlcutNip4r43e+5I3avMhqtlDG3/bgtxj5k/HKVfMNRctf8MtCwXBRfiI0xP7mF4xahsXj8RxHMvjKNg9q4AagDbOJBmzSn5WxNsQhI+oaSB+V9pQ0qoYG3mPUvH5yJNQTSmpRcQewqtEAyjEMZRjLgHR3Ps+ywHsUP6M+BReQj1KLyUvQUd+KJB2zHB44Hn4YmfZJxR7yvCMjo6lLvMvUT3D9QaOmJ3Lztjd9s0LtENKTpRLT8X4dWud6EWM/hV62s9nYFPhDd9YF0eSOJTtFVLMH5SG+dxxOLOpebjWwTrhuv2cEHr+bafnS4Ou+GYzC98ncF44IOAC2TfdTexVCILKZF+8jMKERR5wmnI0ExjmSSCyDFy5o/NagQhDl0pPTN8V3IAL/XkVdna8+wea10B0UTJRvg3Uw8uBVCb4UaZ0bXwidlbRlghTfVKZ8R0hdj1aY5zJsR7VdBinV+nEkjgJotbfQ== root@pve01
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINNadSzjCps//MuPpXnIxsEL7Rnd5SLagcM4hAnuNsJ1 vinni@pve01-admin
EOF
chmod 700 /home/npdadmin/.ssh
chmod 600 /home/npdadmin/.ssh/authorized_keys
chown -R npdadmin:npdadmin /home/npdadmin/.ssh

cat > /etc/sudoers.d/90-npdadmin <<'EOF'
npdadmin ALL=(ALL) NOPASSWD: ALL
EOF
chmod 440 /etc/sudoers.d/90-npdadmin

mkdir -p /scratch
chmod 1777 /scratch

curl -fsS http://10.10.80.10/scripts/condor01-firstboot.sh -o /usr/local/sbin/condor01-firstboot.sh
curl -fsS http://10.10.80.10/scripts/npd-condor01-firstboot.service -o /etc/systemd/system/npd-condor01-firstboot.service
chmod 755 /usr/local/sbin/condor01-firstboot.sh
systemctl enable npd-condor01-firstboot.service

systemctl enable sshd chronyd NetworkManager
%end
