# Setting Up a Ubuntu Server From Scratch

These are generic setup instructions for getting a new Ubuntu 22.04 server from clean state to production-ready.

After logging in as the default "ubuntu" user, we should set a password so that we can use the aws serial
console if we ever need to

```console
ubuntu@localhost:~$ sudo passwd ubuntu
```

For intrusion prevention, we will install the fail2ban package

```console
ubuntu@localhost:~$ sudo apt-get update
ubuntu@localhost:~$ sudo apt-get install fail2ban
```

If an IP ever gets banned by mistake, the command to unban it is:

```console
ubuntu@localhost:~$ sudo fail2ban-client unban m.y.i.p
```

for security sake, security patches should be installed automatically. We need to configure the
unattended-upgrades package by editing the config

```console
ubuntu@localhost:~$ sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
```

in `Allowed-Origins` we want to make sure that "security" related lines are uncommented. The following settings
should also be enabled/configured:

```text
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Automatic-Reboot-Time "07:00";
```

The automatic upgrades are still not actually enabled, to do that we have to edit another file:

```console
ubuntu@localhost:~$ sudo nano /etc/apt/apt.conf.d/10periodic
```

and set the following settings:

```text
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
```

even now the automatic upgrades are not entirely set up. The whole thing will come to a hault and the system
will stop upgrading if dpkg ever wants to prompt with a question of if it should replace a config file you
modified with the default config file in the upgraded package. To prevent this, we need to just preemptively
answer it's question now

```console
ubuntu@localhost:~$ sudo nano /etc/apt/apt.conf.d/local
```

This file does not exist by default, but we will populate it with one of the following:

So the question dpkg would be asking is:

```text
Configuration file `/path/to/something.conf'
 ==> Modified (by you or by a script) since installation.
 ==> Package distributor has shipped an updated version.
   What would you like to do about it ?  Your options are:
    Y or I  : install the package maintainer's version
    N or O  : keep your currently-installed version
      D     : show the differences between the versions
      Z     : start a shell to examine the situation
```

We would normally answer answer "N" so this is the conf we want:

```text
# keep old configs on upgrade, move new versions to <file>.dpkg-dist
Dpkg::Options {
   "--force-confdef";
   "--force-confold";
}
```

You can confirm that the `/etc/apt/apt.conf.d/local` conf is taking effect with:

```console
ubuntu@localhost:~$ apt-config dump | grep "DPkg::Options"
```

You can now test the automatic upgrades by running:

```console
ubuntu@localhost:~$ sudo unattended-upgrades --dry-run
```

There should be no errors

You can see the next time the system will DOWNLOAD updates with:

```console
ubuntu@localhost:~$ systemctl list-timers apt-daily --all
```

You can edit the DOWNLOAD schedule with:

```console
ubuntu@localhost:~$ sudo systemctl --full edit apt-daily.timer
ubuntu@localhost:~$ sudo systemctl restart apt-daily.timer
ubuntu@localhost:~$ sudo systemctl status apt-daily.timer
```

You can see the next time the system will INSTALL updates with:

```console
ubuntu@localhost:~$ systemctl list-timers apt-daily-upgrade --all
```

You can edit the INSTALL schedule with:

```console
ubuntu@localhost:~$ sudo systemctl --full edit apt-daily-upgrade.timer
ubuntu@localhost:~$ sudo systemctl restart apt-daily-upgrade.timer
ubuntu@localhost:~$ sudo systemctl status apt-daily-upgrade.timer
```

amazon-ssm-agent is a tool that comes preinstalled that may be using resources for no good reason. If not using
it, then uninstall it with:

```console
ubuntu@localhost:~$ sudo snap remove amazon-ssm-agent
```

The next thing to do to squeeze out all the performance we can from an aws instance is to compress the memory.
This is only a good idea if your application is memory-constrained and not something that you would want to do
if you were running a cpu-constrained app. But my workloads are always memory-constrained

```console
ubuntu@localhost:~$ sudo apt-get install zram-config linux-modules-extra-aws
```

Ubuntu 22.04 comes with zswap installed but not enabled. We want to make sure it is not enabled, because it will
conflict with zram and hurt performance. Confirm zswap is disabled like so:

```console
ubuntu@localhost:~$ grep -R . /sys/module/zswap/parameters
```

It should say "/sys/module/zswap/parameters/enabled:N"

now we need to reboot so the new compression will be used

```console
ubuntu@localhost:~$ sudo reboot
```

Next we should make a swap file.

```console
ubuntu@localhost:~$ sudo fallocate -l 2G /swapfile
ubuntu@localhost:~$ sudo chmod 600 /swapfile
ubuntu@localhost:~$ sudo mkswap /swapfile
ubuntu@localhost:~$ sudo swapon /swapfile
ubuntu@localhost:~$ echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

digitalocean recommends that we should tweak the swap for better performance like so:

```console
ubuntu@localhost:~$ sudo sysctl vm.swappiness=10
ubuntu@localhost:~$ sudo sysctl vm.vfs_cache_pressure=50
ubuntu@localhost:~$ echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
ubuntu@localhost:~$ echo 'vm.vfs_cache_pressure=50' | sudo tee -a /etc/sysctl.conf
```

we can check that the swap (and memory compression) is working with:

```console
ubuntu@localhost:~$ swapon -s
```

Since this is a VM, there is a risk of the enprophy pool drying up, which can cause webpages not to load if this
is a webserver which needs to generate keys for example. So to prevent that, we need to install haveged

```console
ubuntu@localhost:~$ sudo apt-get install haveged
```

add ubuntu to www-data group (this will require logoff to take effect)

```console
ubuntu@localhost:~$ sudo usermod -a -G www-data ubuntu
```

## In the future, if we run out of disk space, the following can be used to expand the filesystem

(after expanding the disk in the aws console)

First, find the disk and partition of / using lsblk

```console
ubuntu@localhost:~$ sudo lsblk
```

Assuming the disk is /dev/nvme0n1, we first need to expand the GPT disk:

```console
ubuntu@localhost:~$ sudo sgdisk -e /dev/nvme0n1
```

partprobe allows the system to learn of the changes

```console
ubuntu@localhost:~$ sudo partprobe
```

We will use growpart to expand the partition, but if the partition is full, then growpart can't work because it
won't be able to write to /tmp. To work around that, we can make /tmp a ramdrive for a moment. Here we assume
the partition we want to grow is partition 1 (/dev/nvme0n1p1) adjust accordingly

```console
ubuntu@localhost:~$ sudo mount -o size=10M,rw,nodev,nosuid -t tmpfs tmpfs /tmp
ubuntu@localhost:~$ sudo growpart /dev/nvme0n1 1
ubuntu@localhost:~$ sudo umount /tmp
```

The last step is to expand the filesystem:

```console
ubuntu@localhost:~$ sudo resize2fs /dev/nvme0n1p1
```

Now you should see that you have plenty of free space

```console
ubuntu@localhost:~$ df -h
```
