import sys
import os
import subprocess
import socket
import shlex
import json
from consolemenu import *
from consolemenu.items import *
import shutil
import requests
import click

# executes the given command, but does not display output.
def run(command: str, rshell: bool=False):
	proc=subprocess.run(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=rshell)
	if proc.returncode!=0: # assume failure
		print ("The following command failed when executed:")
		print(command)
		if click.confirm("Would you like to view the processes output?"):
			print(proc.stdout.decode())
			print(proc.stderr.decode())
		if not click.confirm("Would you like to continue the installation process?"):
			sys.exit(0)

# Does same thing as run() but returns output
def execute(command: str, rshell: bool=False)->tuple:
	proc=subprocess.run(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=rshell)
	if proc.returncode!=0: # assume failure
		print ("The following command failed when executed:")
		print(command)
		if click.confirm("Would you like to view the processes output?"):
			print(proc.stdout.decode())
			print(proc.stderr.decode())
		if not click.confirm("Would you like to continue the installation process?"):
			sys.exit(0)
	else:
		return (proc.stdout.decode(), proc.stderr.decode())

os.remove("/etc/resolv.conf")
shutil.copy2("/etc/resolv.conf.new", "/etc/resolv.conf")
# Step 1 - determine that we are connected to the internet
try:
	socket.gethostbyname("google.com")
except Exception:
	print ("You are not connected to the internet. Please connect to the internet first to continue.")
	sys.exit(1)

print ("Refreshing GPG keyring")
run("pacman-key --refresh")
print ("Selecting closest 20 mirrors")
loc=requests.get("http://ipinfo.io/json").json()["country"]
shutil.copy("/etc/pacman.d/mirrorlist", "/etc/pacman.d/mirrorlist.old")
mirrorlist=execute(f"reflector -c {loc} -p https -f 20 ")
if len(mirrorlist[1])>0:
	print (f"Warning: mirror list couldn't be refreshed; output was:\n{mirrorlist[1]}")
else:
	with open("/etc/pacman.d/mirrorlist", "w") as f:
		f.write(mirrorlist[0])

# Step 2 - determine what disk is our "main disk".
diskjson=json.loads(execute("lsblk -dJO")[0])
disks=[]
for blockdevice in diskjson["blockdevices"]:
	disks.append(f"""{blockdevice["name"].upper()}: {blockdevice["path"]}, {blockdevice["size"]}""")

menu=SelectionMenu(disks, title="Select install disk")
menu.show(False)

disk=diskjson["blockdevices"][menu.selected_item.index]["path"]

if os.path.exists("/sys/firmware/efi") or os.path.exists("/sys/firmware/efi/efivars") or os.path.exists("/sys/firmware/efi/vars"):
	print ("Creating UEFI partition table")
	run(f"parted -s {disk} -- mklabel gpt")
	run(f"parted -s {disk} -- mkpart primary fat32 0% 1g")
	run(f"parted -s {disk} -- mkpart primary ext4 1g 100%")
	run(f"parted -s {disk} -- set 1 boot on")
else:
	print ("Creating BIOS partition table")
	run(f"parted -s {disk} -- mklabel msdos")
	run(f"parted -s {disk} -- mkpart primary ext4 0% 1g")
	run(f"parted -s {disk} -- mkpart primary ext4 1g 100%")
	run(f"parted -s {disk} -- set 1 boot on")

print ("Creating file systems")
if os.path.exists("/sys/firmware/efi") or os.path.exists("/sys/firmware/efi/efivars") or os.path.exists("/sys/firmware/efi/vars"):
	run(f"mkfs.fat -F32 {disk}1")
	run(f"mkfs.ext4 {disk}2")
else:
	run(f"mkfs.ext4 {disk}1")
	run(f"mkfs.ext4 {disk}2")

print ("Mounting disks")
run("mount /dev/sda2 /mnt")
os.mkdir("/mnt/boot", mode=755)
run("mount /dev/sda1 /mnt/boot")

print ("Installing the base system")
if os.path.exists("/sys/firmware/efi") or os.path.exists("/sys/firmware/efi/efivars") or os.path.exists("/sys/firmware/efi/vars"):
	run("pacstrap /mnt base base-devel alsa-utils grub efibootmgr python python-pip wireless_tools wpa_supplicant dialog wpa_actiond")
else:
	run("pacstrap /mnt base base-devel alsa-utils grub python python-pip wpa_supplicant wpa_actiond dialog wireless_tools")

print ("Generating fstab")
run("genfstab -U /mnt >> /mnt/etc/fstab")

shutil.copy("installer-stage2.py", "/mnt")
shutil.copy("yay-9.1.0-1-x86_64.pkg.tar.xz", "/mnt")
shutil.copy("fenrir-1.9.5-1-any.pkg.tar.xz", "/mnt")
shutil.copy("/etc/fenrirscreenreader/settings/settings.conf", "/mnt")
subprocess.run(shlex.split(f"arch-chroot /mnt /usr/bin/python /installer-stage2.py {disk}"))
os.remove("/mnt/installer-stage2.py")
if click.confirm("Would you like to reboot now?"):
	run("umount /mnt/boot /mnt")
	run("reboot")
else:
	run("umount /mnt/boot /mnt")
	run("mount /dev/sda2 /mnt")
	run("mount /dev/sda1 /mnt/boot")
	print ("All file systems have been remounted and are ready for customization. When your ready, type 'reboot' to boot into your new system.")