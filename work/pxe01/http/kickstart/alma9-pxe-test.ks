# AlmaLinux 9 unattended install for PXE test VMID 120.
# This profile wipes all attached disks. Use only for the disposable test VM.

text
skipx
eula --agreed
reboot

lang en_US.UTF-8
keyboard us
timezone Europe/Kyiv --utc

network --bootproto=dhcp --device=link --activate --hostname=pxe-alma-test.internal

rootpw --lock
user --name=npdadmin --groups=wheel --shell=/bin/bash --lock

firewall --enabled --service=ssh
selinux --enforcing
services --enabled=sshd,chronyd,NetworkManager

url --url=http://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os
repo --name=AppStream --baseurl=http://repo.almalinux.org/almalinux/9/AppStream/x86_64/os

zerombr
clearpart --all --initlabel
autopart --type=lvm
bootloader --location=mbr --append="console=ttyS0,115200n8"

%packages
@^minimal-environment
chrony
curl
openssh-server
sudo
vim-minimal
wget
%end

%post --log=/root/npd-postinstall.log
set -eux

mkdir -p /home/npdadmin/.ssh
cat > /home/npdadmin/.ssh/authorized_keys <<'EOF'
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

systemctl enable sshd chronyd NetworkManager
%end
