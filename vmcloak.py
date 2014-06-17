#!/usr/bin/env python
# Copyright (C) 2010-2014 Cuckoo Sandbox Developers.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import argparse
from ConfigParser import ConfigParser
import logging
import os.path
import random
import socket
import string
import subprocess
import sys
import tempfile
import time


logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


CONFIG = dict(
    bios=[
    ],
    system=[
    ],
    board=[
    ],
    chassis=[
    ],
    harddisk=[
    ],
)


def random_string(minimum, maximum=None):
    if maximum is None:
        maximum = minimum

    count = random.randint(minimum, maximum)
    return ''.join(random.choice(string.ascii_letters) for x in xrange(count))


def random_mac():
    """Generates a random MAC address."""
    values = [random.randint(0, 15) for _ in xrange(12)]

    # At least for VirtualBox there's a limitation for the second character,
    # as outlined in the following thread. Thus we handle this.
    # https://forums.virtualbox.org/viewtopic.php?p=85316
    values[1] = int(random.choice('02468ace'), 16)

    return '%x%x:%x%x:%x%x:%x%x:%x%x:%x%x' % tuple(values)


def random_serial(length=None):
    if length is None:
        length = random.randint(8, 20)

    return ''.join(random.choice(string.uppercase + string.digits)
                   for _ in xrange(length))


class VM(object):
    FIELDS = {}

    def __init__(self, name, basedir):
        self.name = name
        self.basedir = basedir

    def create_vm(self):
        """Create a new Virtual Machine."""
        raise

    def delete_vm(self):
        """Delete an existing Virtual Machine and its associated files."""
        raise

    def ramsize(self, ramsize):
        """Modify the amount of RAM available for this Virtual Machine."""
        raise

    def os_type(self, os, sp):
        """Set the OS type to the OS and the Service Pack."""
        raise

    def create_hd(self, fsize):
        """Create a harddisk."""
        raise

    def attach_iso(self, iso):
        """Attach a ISO file as DVDRom."""
        raise

    def set_field(self, key, value):
        """Set a specific field of a Virtual Machine."""
        raise

    def modify_mac(self, mac=None):
        """Modify the MAC address of a Virtual Machine."""
        raise

    def hostonly(self, index=0):
        """Configure a Hostonly adapter for the Virtual Machine."""
        raise

    def hwvirt(self, enable=True):
        """Enable or disable the usage of Hardware Virtualization."""
        raise

    def start_vm(self):
        """Start the associated Virtual Machine."""
        raise

    def snapshot(self, label):
        """Take a snapshot of the associated Virtual Machine."""
        raise

    def stopvm(self):
        """Stop the associated Virtual Machine."""
        raise

    def list_settings(self):
        """List all settings of a Virtual Machine."""
        raise

    def init_vm(self):
        """Initialize fields as specified by `FIELDS`."""
        def _init_vm(path, fields):
            for key, value in fields.items():
                key = path + '/' + key
                if isinstance(value, dict):
                    _init_vm(key, value)
                else:
                    if isinstance(value, tuple):
                        k, v = value
                        if not CONFIG[k]:
                            value = 'To be filled by O.E.M.'
                        else:
                            if k not in config:
                                config[k] = random.choice(CONFIG[k])

                            value = config[k][v]

                            # Some values are dynamically generated.
                            if callable(value):
                                value = value()

                    print '[+] Setting %r to %r' % (key, value)
                    ret = self.set_field(key, value)
                    if ret:
                        print ret

        config = {}
        _init_vm('', self.FIELDS)


class VirtualBox(VM):
    FIELDS = {
        'VBoxInternal/Devices/pcbios/0/Config': dict(

            # http://blog.prowling.nu/2012/08/modifying-virtualbox-settings-for.html
            DmiBIOSVendor=('bios', 'vendor'),
            DmiBIOSVersion=('bios', 'version'),
            DmiBIOSReleaseDate=('bios', 'release_date'),
            # DmiBIOSReleaseMajor=
            # DmiBIOSReleaseMinor=
            # DmiBIOSFirmwareMajor=
            # DmiBIOSFirmwareMinor=

            DmiSystemVendor=('system', 'vendor'),
            DmiSystemProduct=('system', 'product'),
            DmiSystemVersion=('system', 'version'),
            DmiSystemSerial=('system', 'serial'),
            DmiSystemSKU=('system', 'sku'),
            DmiSystemFamily=('system', 'family'),
            DmiSystemUuid=('system', 'uuid'),

            # http://blog.prowling.nu/2012/10/modifying-virtualbox-settings-for.html
            DmiBoardVendor=('board', 'vendor'),
            DmiBoardProduct=('board', 'product'),
            DmiBoardVersion=('board', 'version'),
            DmiBoardSerial=('board', 'serial'),
            DmiBoardAssetTag=('board', 'asset'),
            DmiBoardLocInChass=('board', 'location'),

            DmiChassisVendor=('chassis', 'vendor'),
            DmiChassisVersion=('chassis', 'version'),
            DmiChassisSerial=('chassis', 'serial'),
            DmiChassisAssetTag=('chassis', 'asset'),
        ),
        'VBoxInternal/Devices/piix3ide/0/Config': {
            'Port0': dict(

                # http://downloads.cuckoosandbox.org/slides/blackhat.pdf, Page 82
                # https://forums.virtualbox.org/viewtopic.php?f=1&t=48718
                # ATAPIProductId='',
                # ATAPIRevision='',
                # ATAPIVendorId='',
            ),
            'PrimaryMaster': dict(

                # http://blog.prowling.nu/2012/08/modifying-virtualbox-settings-for.html
                SerialNumber=('harddisk', 'serial'),
                FirmwareRevision=('harddisk', 'revision'),
                ModelNumber=('harddisk', 'model'),
            ),
        },
    }

    def __init__(self, *args, **kwargs):
        VM.__init__(self, *args, **kwargs)

        self.conf_path = os.path.join(CUCKOO_ROOT, 'conf', 'virtualbox.conf')

        try:
            self.vboxmanage = Config(self.conf_path).virtualbox.path
        except:
            log.error('Unable to locate VBoxManage path, please '
                      'configure conf/virtualbox.conf properly.')
            exit(1)

        if not os.path.isfile(self.vboxmanage):
            log.error('The configured VBoxManage path does not exist, '
                      'please configure conf/virtualbox.conf properly.')
            exit(1)

    def _call(self, *args, **kwargs):
        cmd = [self.vboxmanage] + list(args)

        for k, v in kwargs.items():
            if v is None or v is True:
                cmd += ['--' + k]
            else:
                cmd += ['--' + k, str(v)]

        try:
            ret = subprocess.check_output(cmd)
        except Exception as e:
            print '[-] Error running command:', e
            exit(1)

        return ret.strip()

    def _hd_path(self):
        return os.path.join(self.basedir, self.name, '%s.vdi' % self.name)

    def create_vm(self):
        return self._call('createvm', name=self.name,
                          basefolder=self.basedir, register=True)

    def delete_vm(self):
        self._call('unregistervm', self.name, delete=True)

    def ramsize(self, ramsize):
        return self._call('modifyvm', self.name, memory=ramsize)

    def os_type(self, os, sp):
        operating_systems = {
            'xp': 'WindowsXP',
        }
        return self._call('modifyvm', self.name, ostype=operating_systems[os])

    def create_hd(self, fsize):
        ctlname = 'IDE Controller'
        self._call('createhd', filename=self._hd_path(), size=fsize)
        self._call('storagectl', self.name, name=ctlname, add='ide')
        self._call('storageattach', self.name, storagectl=ctlname,
                   type='hdd', device=0, port=0, medium=self._hd_path())

    def attach_iso(self, iso):
        ctlname = 'IDE Controller'
        self._call('storageattach', self.name, storagectl=ctlname,
                   type='dvddrive', port=1, device=0, medium=iso)

    def set_field(self, key, value):
        return self._call('setextradata', self.name, key, value)

    def modify_mac(self, macaddr=None):
        if macaddr is None:
            macaddr = random_mac()

        # VBoxManage prefers MAC addresses without colons.
        vbox_mac = macaddr.replace(':', '')

        self._call('modifyvm', self.name, macaddress1=vbox_mac)
        return macaddr

    def hostonly(self, index=0):
        if os.name == 'posix':
            adapter = 'vboxnet0'
        else:
            adapter = 'VirtualBox Host-Only Ethernet Adapter'

        self._call('modifyvm', self.name,
                   nic1='hostonly',
                   nictype1='Am79C973',
                   nicpromisc1='allow-all',
                   hostonlyadapter1=adapter)

    def hwvirt(self, enable=True):
        """Enable or disable the usage of Hardware Virtualization."""
        self._call('modifyvm', self.name, hwvirtex='on' if enable else 'off')

    def start_vm(self):
        return self._call('startvm', self.name)

    def snapshot(self, label, description=''):
        return self._call('snapshot', self.name, 'take', label,
                          description=description, live=True)

    def stopvm(self):
        return self._call('controlvm', self.name, 'poweroff')

    def list_settings(self):
        return self._call('getextradata', self.name, 'enumerate')


def configure_winnt_sif(path, args):
    values = {
        'PRODUCTKEY': args.serial_key,
        'COMPUTERNAME': random_string(8, 16),
        'FULLNAME': '%s %s' % (random_string(4, 8), random_string(4, 10)),
        'ORGANIZATION': '',
        'WORKGROUP': random_string(4, 8),
    }

    buf = open(path, 'rb').read()
    for key, value in values.items():
        buf = buf.replace('@%s@' % key, value)
    return buf


class Configuration(object):
    def __init__(self):
        self.conf = {}

    def _process_value(self, value):
        if isinstance(value, str) and value.startswith('~'):
            return os.getenv('HOME') + value[1:]
        if value in ('true', 'True', 'on', 'yes', 'enable'):
            return True
        if value in ('false', 'False', 'off', 'no', 'disable'):
            return False
        return value

    def from_args(self, args):
        for key, value in args._get_kwargs():
            if key not in self.conf or value:
                self.conf[key] = self._process_value(value)

    def from_file(self, path):
        p = ConfigParser()
        p.read(path)
        for key in p.options('vmcloak'):
            self.conf[key.replace('-', '_')] = \
                self._process_value(p.get('vmcloak', key))

    def from_defaults(self, defaults):
        for key, value in defaults.items():
            if self.conf[key] is None:
                self.conf[key] = value

    def __getattr__(self, key):
        return self.conf[key]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('vmname', type=str, help='Name of the Virtual Machine.')
    parser.add_argument('--cuckoo', type=str, help='Directory where Cuckoo is located.')
    parser.add_argument('--basedir', type=str, help='Base directory for the virtual machine and its associated files.')
    parser.add_argument('--vm', type=str, help='Virtual Machine Software (VirtualBox.)')
    parser.add_argument('--list', action='store_true', help='List the cloaked settings for a VM.')
    parser.add_argument('--delete', action='store_true', help='Completely delete a Virtual Machine and its associated files.')
    parser.add_argument('--ramsize', type=int, help='Available virtual memory (in MB) for this virtual machine.')
    parser.add_argument('--resolution', type=str, help='Virtual Machine resolution.')
    parser.add_argument('--hdsize', type=int, help='Maximum size (in MB) of the dynamically allocated harddisk.')
    parser.add_argument('--iso', type=str, help='ISO Windows installer.')
    parser.add_argument('--host-ip', type=str, help='Static IP address to bind to on the Host.')
    parser.add_argument('--guest-ip', type=str, help='Static IP address to use on the Guest.')
    parser.add_argument('--guest-ip-gateway', type=str, help='Static IP address gateway to use on the Guest.')
    parser.add_argument('--hwvirt', action='store_true', default=None, help='Explicitly enable Hardware Virtualization.')
    parser.add_argument('--no-hwvirt', action='store_false', default=None, dest='hwvirt', help='Explicitly disable Hardware Virtualization.')
    parser.add_argument('--serial-key', type=str, help='Windows Serial Key.')
    parser.add_argument('-s', '--settings', type=str, help='Configuration file with various settings.')

    defaults = dict(
        vm='virtualbox',
        ramsize=1024,
        resolution='1024x768',
        hdsize=256*1024,
        host_ip='192.168.56.1',
        guest_ip='192.168.56.101',
        guest_ip_gateway='192.168.0.1',
    )

    args = parser.parse_args()
    s = Configuration()

    if args.settings:
        s.from_file(args.settings)

    s.from_args(args)
    s.from_defaults(defaults)

    if not s.cuckoo:
        print '[-] Please provide your Cuckoo root directory.'
        exit(1)

    if not s.basedir:
        print '[-] Please provide the base directory for the VM.'
        exit(1)

    sys.path.append(s.cuckoo)
    from lib.cuckoo.common.config import Config
    from lib.cuckoo.common.constants import CUCKOO_ROOT

    if s.vm == 'virtualbox':
        m = VirtualBox(s.vmname, s.basedir)
    else:
        print '[-] Only VirtualBox is supported as of now'
        exit(1)

    if s.list:
        print m.list_settings()
        exit(0)

    if s.delete:
        print '[x] Unregistering and deleting the VM and its associated files'
        m.delete_vm()
        exit(0)

    if not s.iso:
        print '[-] Please specify a Windows Installer ISO image'
        exit(1)

    print '[x] Using %s as Host IP' % s.host_ip
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((s.host_ip, 0))
    sock.listen(1)
    _, port = sock.getsockname()

    print '[x] Configuring WINNT.SIF'
    buf = configure_winnt_sif('winnt.sif', s)
    if not buf:
        print '[-] Error configuring WINNT.SIF'
        exit(1)

    # Write the WINNT.SIF file.
    _, winntsif = tempfile.mkstemp(suffix='.sif')
    open(winntsif, 'wb').write(buf)

    print '[x] Using static IP address %s on the Guest' % s.guest_ip
    settings_bat = dict(
        HOSTONLYIP=s.guest_ip,
        HOSTONLYGATEWAY=s.guest_ip_gateway,
    )

    settings_py = dict(
        HOST_IP=s.host_ip,
        HOST_PORT=port,
        RESOLUTION=s.resolution,
    )

    # Write the configuration values for bootstrap.bat.
    with open(os.path.join('bootstrap', 'settings.bat'), 'wb') as f:
        for key, value in settings_bat.items():
            print>>f, 'set %s=%s' % (key, value)

    # Write the configuration values for bootstrap.py.
    with open(os.path.join('bootstrap', 'settings.py'), 'wb') as f:
        for key, value in settings_py.items():
            print>>f, '%s = %r' % (key, value)

    # The directory doesn't exist yet, probably.
    if not os.path.exists(os.path.join(s.basedir, s.vmname)):
        os.mkdir(os.path.join(s.basedir, s.vmname))

    iso_path = os.path.join(s.basedir, s.vmname, 'image.iso')

    # Create the ISO file.
    print '[x] Creating ISO file.'
    try:
        subprocess.check_call(['./utils/buildiso.sh',
                               s.iso, winntsif, iso_path])
    except OSError as e:
        print '[-] Is ./utils/buildiso.sh executable?'
        print e
        exit(1)
    except subprocess.CalledProcessError as e:
        print '[-] Error creating ISO file.'
        print e
        exit(1)

    print '[x] Creating VM'
    print m.create_vm()

    m.ramsize(s.ramsize)
    m.os_type(os='xp', sp=3)

    print '[x] Creating Harddisk'
    m.create_hd(s.hdsize)

    print '[x] Temporarily attaching DVD-Rom unit for the ISO installer'
    m.attach_iso(iso_path)

    print '[x] Randomizing Hardware'
    m.init_vm()

    print '[x] Randomizing the MAC address:',
    print m.modify_mac()

    print '[x] Initially configuring Hostonly network'
    m.hostonly()

    if s.hwvirt is not None:
        if s.hwvirt:
            print '[x] Enabling Hardware Virtualization'
        else:
            print '[x] Disabling Hardware Virtualization'
        m.hwvirt(s.hwvirt)

    print '[!] Starting the Virtual Machine to install Windows'
    print m.start_vm()

    print '[x] Waiting for the Virtual Machine to connect back'
    print '[!] This may take up to 30 minutes'
    t = time.time()

    guest, _ = sock.accept()
    print '[x] It took %d seconds to install Windows!' % (time.time() - t)

    print '[x] Setting the resolution to %s' % s.resolution
    if ord(guest.recv(1)):
        print '[+] Resolution was set successfully'
    else:
        print '[-] Error setting the resolution'

    # Give the system a little bit of time to fully initialize.
    time.sleep(10)

    print '[x] Taking a snapshot of the current state'
    print m.snapshot('vmcloak', 'Snapshot created by VM Cloak.')

    print '[x] Powering off the virtual machine'
    print m.stopvm()
