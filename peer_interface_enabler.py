#!/usr/bin/env python3
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#  - Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#  - Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#  - Neither the name of Arista Networks nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#
#    Version 1.0 9/17/2018
#    Written by: 
#       Dimitri Capetz, Arista Networks
#
#    Revision history:
#       1.0 - Initial version tested on EOS 4.20.7M 
#       1.1 - Updated for Python3 on EOS 4.31.2F

"""
   DESCRIPTION
     The Peer Interface Enabler tool is used to enable an interface on 
     a peer switch or module when a local interface status changes. This is done by 
     modifying trunk allowed vlan lists to ensure only one is forwarding at L2. This is to 
     accomadate attached devices which to not adhere to standard protocols and need 
     active / standby to be managed by the network switch.
   INSTALLATION
     In order to install this script:
       - Copy the script to /mnt/flash
       - Enable the Command API interface:
            management api http-commands
              no shutdown
       - Change username and  password variables at the top of the script
         to the ones appropriate for your installation. 
   USAGE
      - To begin, candidate interfaces should be preconfigured in active / standby 
        setup, like below.  One is allowing all vlans, the other allows none.

        ACTIVE INTERFACE

        interface Ethernet1
           switchport trunk allowed vlan 2,502,503,606
           switchport mode trunk

        STANDBY INTERFACE

        interface Ethernet1
           switchport trunk allowed vlan none
           switchport mode trunk

      - Script should be configured to trigger with a pair of Event Handlers.
      - One is used for downlink detection, the other for dead peer detection.
      - The trigger action should be on the operStatus of the interface
        you are tracking.
      - The script uses passed arguments as indicated below.
      - Delay can be tweaked per environment needs.
      - Format vlan list in numerical order and individually, ie 2,502,503,606
      - Do not combine vlans in trunk list as a range
      
           event-handler Downlink_Detect
             trigger on-intf <downlink> operstatus
             action bash python3 /mnt/flash/peer_interface_enabler.py -s <downlink> -v <vlan_list>
             delay 1
           !
           event-handler Dead_Peer_Detect
             trigger on-intf <mlag_Peer-link_port-channel> operstatus
             action bash python3 /mnt/flash/peer_interface_enabler.py -s <downlink> -v <vlan_list>
             delay 1
        
        EXAMPLE

           event-handler Downlink_Detect
             trigger on-intf Ethernet1 operstatus
             action bash python3 /mnt/flash/peer_interface_enabler.py -s Ethernet1 -v 2,502,503,606
             delay 1
           !
           event-handler Dead_Peer_Detect
             trigger on-intf Port-Channel2000 operstatus
             action bash python3 /mnt/flash/peer_interface_enabler.py -s Ethernet1 -v 2,502,503,606
             delay 1
        
   COMPATIBILITY
      This has been tested with EOS 4.20.x using eAPI
   LIMITATIONS
      Strict logic is used to determine the backup port to be configured. If the
      environment does not adhere to this logic, the script will need to be 
      adjusted.  Please note that failover time can be affected by STP convergeance.
      If there are no L2 loops, STP can be disabled on vlans to speed failover time.
"""

import argparse
from jsonrpclib import Server
import signal
import sys
import syslog
import time

# Set to allow unverified cert for eAPI call
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context

# ----------------------------------------------------------------
# Configuration section
# ----------------------------------------------------------------
username = 'admin'
password = 'password'
# ----------------------------------------------------------------

# Pull in interface pair and vlans to configure file from command line argument
parser = argparse.ArgumentParser(description='Remove Vlans from down interface and apply to peer')
required_arg = parser.add_argument_group('Required Arguments')
required_arg.add_argument('-s', '--switchport', dest='switchport', required=True,
                          help='Switchport to apply configuration to', type=str)
required_arg.add_argument('-v', '--vlans', dest='vlans', required=True, help='Vlans to allow on enabled port', type=str)
args = parser.parse_args()
switchport = args.switchport
vlans = args.vlans

# Define URL for local eAPI connection. Uses local loopback
local_url_string = "https://{}:{}@{}/command-api".format(username, password, "127.0.0.1")
local_switch_req = Server(local_url_string)

# Open syslog for log creation
syslog.openlog('PeerInterfaceEnabler', 0, syslog.LOG_LOCAL4)

# Setup timeout function and signal
def handler(signum, frame):
    syslog.syslog("%%PeerInt-6-LOG: Timed out waiting for peer eAPI.")
    raise Exception("timeout")


signal.signal(signal.SIGALRM, handler)
signal.alarm(5)


def peer_setup():
    """ Sets up peer JSON-RPC instance based on MLAG Peer IP
        Returns:
            switch_req (instance): JSON-RPC instance for eAPI call to Peer
    """
    # Pull MLAG Peer IP for peer switch eAPI connection if fixed device.
    mlag_status = local_switch_req.runCmds(1, ["show mlag"])
    peer_switch = mlag_status[0]["peerAddress"]
    peer_url_string = "https://{}:{}@{}/command-api".format(username, password, peer_switch)
    switch_req = Server(peer_url_string)
    return switch_req


def config_main_port(backup_port, peer_switch_req):
    """ Configures main port to be active and removes config from backup
        Args:
            backup_port (str): Port to remove config from
            peer_switch_req (instance): eAPI instance of backup switch (self on modular)
    """
    local_switch_req.runCmds(1, ["enable", "configure", "interface " + switchport, 
                                 "switchport trunk allowed vlan " + vlans, "end"])
    peer_switch_req.runCmds(1, ["enable", "configure", "interface " + backup_port, 
                                "switchport trunk allowed vlan none", "end"])


def config_backup_port(backup_port, peer_switch_req):
    """ Configures backup port to be active and removes config from main
        Args:
            backup_port (str): Port to add config to
            peer_switch_req (instance): eAPI instance of backup switch (self on modular)
    """
    local_switch_req.runCmds(1, ["enable", "configure", "interface " + switchport, 
                                 "switchport trunk allowed vlan none", "end"])
    peer_switch_req.runCmds(1, ["enable", "configure", "interface " + backup_port, 
                                "switchport trunk allowed vlan " + vlans, "end"])

def enable_backup_port(main_port, model):
    """ Checks interface status and moves config to backup interface if necessary
        Args:
            main_port (str): Active port to validate
            model (str): model of device being configured
    """
    # Determine if device is modular or fixed
    if (model.startswith("DCS-750")) or (model.startswith("DCS-730")):
        # Current logic assumes downstream device is connected to same port on adjacent slot.
        port_list = main_port.split("/")
        port_slot = int(port_list[0][-1])
        if port_slot % 2 == 0:
            backup_slot = port_slot - 1
        else:
            backup_slot = port_slot + 1
        backup_port = "Ethernet" + str(backup_slot) + "/" + port_list[1]
        backup_switch_req = local_switch_req
    else:
        # If device is fixed (not modular), setup peer eAPI instance and backup_port
        # Assume device is connected to the same port on peer switch
        backup_port = main_port
        backup_switch_req = peer_setup()
    # Grab current port status to ensure it is down
    main_int_status = local_switch_req.runCmds(1, ["show interfaces " + main_port + " status"])
    main_link_status = main_int_status[0]["interfaceStatuses"][main_port]["linkStatus"]
    # If port is up, check again in two seconds.  If it remains up, take no action.
    # This will trigger on interface up changes, so this will prevent any config changes
    # as interface comes up from being down.
    if main_link_status == "connected":
        syslog.syslog("%%PeerInt-6-LOG: Main port " + main_port + " is up. Waiting to re-check")
        time.sleep(2)
        new_int_status = local_switch_req.runCmds(1, ["show interfaces " + main_port + " status"])
        new_link_status = new_int_status[0]["interfaceStatuses"][main_port]["linkStatus"]
        if new_link_status == "connected":
            # If primary port is connected, double check to ensure backup is configured.
            syslog.syslog("%%PeerInt-6-LOG: Main port " + main_port + " is still up")
            syslog.syslog("%%PeerInt-6-LOG: Verifying backup port " + backup_port + " is active")
            try:
                backup_int_status = backup_switch_req.runCmds(1, ["show interfaces " + backup_port + " status"])
                backup_link_status = backup_int_status[0]["interfaceStatuses"][backup_port]["linkStatus"]
            except:
                syslog.syslog("%%PeerInt-6-LOG: Peer eAPI not reachable")
                syslog.syslog("%%PeerInt-6-LOG: Assuming peer is dead and configuring local interface")
                local_switch_req.runCmds(1, ["enable", "configure", "interface " + switchport, 
                                             "switchport trunk allowed vlan " + vlans, "end"])
                raise Exception("peer dead")
            if backup_link_status == "connected":
                # If backup port is up as well, verify backup port has the proper vlans configured and trunked.
                backup_trunk_status = backup_switch_req.runCmds(1, ["show interfaces " + backup_port + " trunk"])
                backup_vlan_list = backup_trunk_status[0]["trunks"][backup_port]["allowedVlans"]["vlanIds"]
                backup_vlan_list.sort()
                # Split supplied vlan list from arg and convert to int and compile in list for comparison.
                main_vlan_list = vlans.split(",")
                main_vlan_list = [int(vlan) for vlan in main_vlan_list]
                main_vlan_list.sort()
                if main_vlan_list == backup_vlan_list:
                    syslog.syslog(
                        "%%PeerInt-6-LOG: Backup port " + backup_port + " is active.  Exiting script")
                    sys.exit()
                else:
                    # If vlan list doesn't match between ports, remove config from backup and add to main.
                    syslog.syslog("%%PeerInt-6-LOG: Backup port " + backup_port + " is up but misconfigured")
                    syslog.syslog("%%PeerInt-6-LOG: Configuring main port " + main_port)
                    config_main_port(backup_port, backup_switch_req)
                    
            else:
                # If main port status is up and backup port is down, ensure configuration is in place on main port.
                syslog.syslog("%%PeerInt-6-LOG: Backup port " + backup_port + " is down")
                syslog.syslog("%%PeerInt-6-LOG: Configuring main port " + main_port)
                config_main_port(backup_port, backup_switch_req)

        else:
            # If port is NOW down, remove all vlans from trunk and add vlans to backup interface.
            syslog.syslog("%%PeerInt-6-LOG: Main port " + main_port + " is down")
            syslog.syslog("%%PeerInt-6-LOG: Removing Vlans and adding them to backup port " + backup_port)
            config_backup_port(backup_port, backup_switch_req)
    else:
        # If port is down, remove all vlans from trunk and add vlans to backup interface.
        syslog.syslog("%%PeerInt-6-LOG: Main port " + main_port + " is down")
        syslog.syslog("%%PeerInt-6-LOG: Removing Vlans and adding them to backup port " + backup_port)
        config_backup_port(backup_port, backup_switch_req)

def main():
    # Determine model of device for chassis / fixed classification
    try:
        device_info = local_switch_req.runCmds(1, ["show version"])
        device_model = device_info[0]["modelName"]
    except:
        syslog.syslog("%%PeerInt-6-LOG: Unable to connect to local eAPI. No changes made")
        sys.exit()
    try:
        enable_backup_port(switchport, device_model)
    except Exception as code:
        code = str(code)
        if code == "peer dead":
            syslog.syslog("%%PeerInt-6-LOG: Main port " + switchport + " configured because peer was dead")
        else:
            syslog.syslog("%%PeerInt-6-LOG: No changes made")
            sys.exit()


if __name__ == '__main__':
    main()