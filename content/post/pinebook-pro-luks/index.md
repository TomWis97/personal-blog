---
title: Pinebook Pro, Manjaro with BTRFS on LUKS on NVME
description: Running an overly complicated set-up on a underpowered laptop.
image: cover.jpg
slug: pinebook-pro-luks
date: 2025-05-20 16:32:12+0100
categories:
    - IT projects
tags:
    - Linux
    - Pinebook
weight: 1
---

So, I have this Pinebook Pro. Although a bit underpowered, still a nice and light laptop with good battery life. As it's an ideal candidate for a travel device, I wanted the disk to be encrypted.
However, this didn't turn out to be as easy as I was hoping. As it was quite a struggle with debugging over UART and a lot of cursing, I ended up writing this post.

I have standardised on Manjaro (with i3) with LUKS and Btrfs for my machines, so I also wanted this for the Pinebook Pro. I equipped my Pinebook Pro with an NVME SSD.

## Steps
To implement this you'd have to do this:
* Flash Tow-boot to SPI (maybe optional, I don't even know anymore).
* Create an SD card with a fresh Manjaro installation.
* Create partitions, LUKS, Btrfs volumes.
* Mount a fresh Manjaro image and the partitions created in the previous step.
* Change some configurations.
* (Bonus: UART on the Pinebook Pro.)

## Resulting set-up
This guide will result in the following boot sequence:
* The Pinebook Pro's CPU will read the Tow-Boot bootloader from SPI storage.
* Tow-Boot will load the initial boot ramdisk (`/boot`) from the first partition of the eMMC storage.
* Linux will boot and prompt for the disk encryption password.
* The LUKS volume is opened and `/`, `/home` (and `/.snapshots`) Btfs volumes will be mounted.
* Manjaro boots up as usual.

## Flashing Tow-boot on the Pinebook Pro
As I wanted to boot from NVME (which the Pinebook Pro does not support out of the box), I needed to flash Tow-Boot.

However, it turned out that I couldn't get that to work. Tow-boot read the boot partition just fine, but after loading the initial image the NVME drive would't show up. A missing module? Maybe. I don't care as I ended up placing `/boot` on the eMMC storage.

Installing Tow-Boot is quite simple, just follow [the documentation](https://tow-boot.org/devices/pine64-pinebookPro.html). You can download the Pinebook Pro version of Tow-Boot from [here](https://github.com/Tow-Boot/Tow-Boot/releases). Just make sure you grab the version for the Pinebook. `dd` it to a blank SD card and turn the Pinebook on. This should show a prompt where you can install it to the SPI storage.

Turn off the Pinebook, remove the SD card and reboot. This should show some sign of life from Tow-Boot.

## Create an SD card with Manjaro
Go to the [Manjaro ARM download page](https://manjaro.org/products/download/arm) and grab the *Generic* image with your preferred desktop environment. Unpack it and `dd` it to an SD card. (Something like `unxz Manjaro.img.xz; dd if=Manjaro.img of=/dev/yoursdcard bs=1M conv=fsync status=progress`.) Shove that SD in the Pinebook and boot from it. (Tow-Boot lets you easily select the boot device, which is cool.)

## Create partitions and stuff
As described earlier, I'm going to create the following partition layout:
```
Storage              FS             Mountpoint
eMMC (mmcblk2)
`- mmcblk2p1         FAT32          /boot
NVME (nvme0n1)
`- nvme0n1p1         LUKS container
   `- cryptroot      BTRFS          -
      |- @           BTRFS subvol   /
      |- @home       BTRFS subvol   /home
      `- @.snapshots BTRFS subvol   /.snapshots
```

Please check if you have the same device names before copy/pasting these commands.

### Create /boot
1. Wipe the eMMC storage.
`# wipefs -a /dev/mmcblk2p1`
2. Create a partition:
```
# gdisk /dev/mmcblk2
o (create new GPT partition table)
n (create new partition)
(Partition number 1, default start, end "+4G", type "ef00")
w (write partition table)
```
3. Create a filesystem:
`# mkfs.fat -F32 /dev/mmcblk2p1`

### Create LUKS and btrfs
4. Wipe the NVME SSD:
`# wipefs -a /dev/nvme0n1`
5. Create a partition for the LUKS container.
```
# gdisk /dev/nvme0n1
o (create new GPT partition table)
n (create new partition)
(Defaults for number, start and end. Type should be 8309.)
w (write partition table)
```
6. Create a LUKS container:
`# cryptsetup luksFormat --type=luks2 /dev/nvme0n1p1`
7. Mount the LUKS container:
`# cryptsetup open /dev/nvme0n1p1 cryptroot`
8. Now the opened LUKS volume is available at /dev/mapper/cryptroot. Create the BTRFS partition:
`# mkfs.btrfs /dev/mapper/cryptroot`
9. Temporarily mount this Btrfs volume so we can create the subvolumes and unmount it again.
```
# mkdir /mnt/tmp
# mount /dev/mapper/cryptroot /mnt/tmp
# btrfs subvolume create /mnt/tmp/@
<# btrfs subvolume create /mnt/tmp/@home
# btrfs subvolume create /mnt/tmp/@snapshots
# unmount /mnt/tmp
```

## Mount, mount, mount!
1. Mount the volumes of your to-be Manjaro installation.
```
# mkdir /mnt/manjaro
# mount -o subvol=@ /dev/mapper/cryptroot /mnt/manjaro
# mkdir /mnt/manjaro/{home,boot}
# mount -o subvol=@home /dev/mapper/cryptroot /mnt/manjaro/home
# mount /dev/mapper/mmcblk2p1 /mnt/manjaro/boot
```
2. From the Pinebook Pro, download the Manjaro pre-installed image. (Yes, again.) We are going to mount this image and use it as a source for a new installation.
3. `unxz` the image and mount it. With losetup we can directly interact with a disk image (`-P` for discovering all partitions, `-r` for read-only and `-f` for auto detecting the available loop device).
```
# mkdir -p /mnt/src/{boot,root}
# losetup -Prf Manjaro_something_generic.img
# mount -o ro /dev/loop0p1 /mnt/src/boot
# mount -o ro /dev/loop0p2 /mnt/src/root
```
4. Install rsync as it's probably not pre-installed. If this fails, you probably need to run `pacman -Syu` first.
```
# pacman-mirrors
# pacman -Sy rsync
```
5. Copy files from the fresh image into your new filesystems:
```
# rsync -aAXv /mnt/src/root /mnt/manjaro/
# rsync -aAXv /mnt/src/boot /mnt/manjaro/boot/
```

## A lot of configuration
Since the Manjaro installation we just copied isn't used to be encrypted and now has a different partition table, there's some configuration which needs to be done.

### Gather disk UUIDs
In the following few steps, we're going to refer to volumes through UUIDs which we need to gather first. Please note these somewhere, we're going to refer to these IDs as follows:
| Device                  | Name              |
|-------------------------|-------------------|
| /dev/mmcblk2 (eMMC)     | BOOT\_UUID        |
| /dev/nvme0n1p1          | LUKS\_UUID        |
| /dev/mapper/cryptroot   | BTRFS\_UUID       |

Per volume use the following command `blkid <device>` and note the value for `UUID=`. In the following steps, replace the relevant references. (I.e. change `UUID=<LUKS_UUID>` to `UUID=5ac35e05-0064-4a48-a896-56020298f90c`.)

### Configure crypttab
Crypttab is used to unlock the luks volumes on boot. Add the following line to `/mnt/manjaro/etc/crypttab`:
```
cryptroot      UUID=<LUKS_UUID>                             none                    luks
```

### Configure fstab
We have a lot of new partitions, so we need to update fstab. *Remove the two existing lines* (as those UUIDs don't exist anymore) and add the following lines to `/mnt/manjaro/etc/fstab`:
```
UUID=<BTRFS_UUID>      /            btrfs   subvol=@                                  0   0
UUID=<BTRFS_UUID>      /home        btrfs   subvol=@home                              0   0
UUID=<BTRFS_UUID>      /.snapshots  btrfs   subvol=@snapshots                         0   0
UUID=<BOOT_UUID>       /boot        vfat    defaults,noexec,umask=0077,nodev,showexec 0   0
```

### Confgure extlinux
Extlinux needs to instruct the Linux kernel to use the newly encrypted volume. This is done by editing `/mnt/manjaro/boot/extlinux/extlinux.conf`. Replace the `APPEND` line with the following one:
```
APPEND initrd=/initramfs-linux.img cryptdevice=UUID=<LUKS_UUID>:cryptroot root=UUID=<BTRFS_UUID> rootflags=subvol=@ rw rootwait audit=0 splash plymouth.ignore-serial-consoles console=ttyS2,1500000 loglevel=7 console=tty1 video=eDP-1:1920x1080@60
```
A short explaination of the options we added:
- `cryptdevice=UUID=5ac35e05-0064-4a48-a896-56020298f90c:cryptroot`: Instruct the kernel we have a LUKS device which should be named `cryptroot`.
- `root=UUID=84cf30ed-62dc-43b1-8882-fb0d3a88309e`: Refer to the BTRFS filsystem within the LUKS volume.
- `rootflags=subvol=@`: Instruct the kernel to use the correct subvolume for root.
- `rootwait`: Wait until the partition is unlocked.
- `plymouth.ignore-serial-consoles`: For UART debugging (so, optional).
- `console=ttyS2,1500000`: For UART debugging (so, optional).
- `loglevel=7`: For debugging (so, optional).
- `console=tty1`: Make sure TTY1 can be used to entering the password.
- `video=eDP-1:1920x1080@60`: Initialize display (might not be required, idk).

### Options for mkinitcpio.conf
The mkinitcpio creates the initial ramdisk the system uses to boot. We need to instruct it to build in the correct modules and hooks for encryption.
Within the file `/mnt/manjaro/etc/mkinitcpio.conf`, make sure the following lines are present like this:
```
MODULES=(panfrost rockchipdrm drm_kms_helper hantro_vpu analogix_dp rockchip_rga panel_simple arc_uart cw2015_battery i2c-hid iscsi_boot_sysfs jsm pwm_bl uhid)
HOOKS=(base udev autodetect modconf kms keyboard keymap consolefont block encrypt filesystems fsck)
COMPRESSION="cat"
```

We now need to run `mkinitcpio`. But in order to be able to do that, we need to mount some more stuff. Then chroot into your new installation and run `mkinitcpio -P`:
```
# for i in proc sys dev run; do mount --bind /$i /mnt/manjaro/$i; done
# chroot /mnt/manjaro
# mkinitcpio -P
```

## Done!
This should be all. Shutdown the Pinebook Pro, *remove the SD card* and turn the laptop on again. Tow-boot should look at the eMMC device, find the boot partition, load Linux and prompt you for the encryption password.

## Bonus: Pinebook Pro UART debugging
When you don't get any display (which I encountered), it can be very helpful to see the serial console output. The Pinebook Pro provides a serial interface through the headphone jack.

I had a PL-2303HX powered USB to Serial adapter laying around which I used. I ran to the local Action store for a 3,5mm cable. I referred to [the official documentation](https://wiki.pine64.org/wiki/Pinebook_Pro#Using_the_serial_console_UART) for the pinout. Please keep in mind that this is as seen from the Pinebook. So you need to connect the RX from the Pinebook Pro to the TX on the serial adapter.

Make sure that the Extlinux configuration has instructions for logging to the serial port (see above).

Also open up the Pinebook Pro and set the switch for the 3,5mm jack to UART instead of audio. Connect the 3,5mm to the Pinebook Pro and the USB adapter to another computer. On the other device, run something like picocom: `picocom /dev/ttyUSB0 -b 1500000`. As soon as the Linux kernel starts booting, you should see the output on your other computer.
