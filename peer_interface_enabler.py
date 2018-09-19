#!/usr/bin/env python
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

"""
   DESCRIPTION
     The Peer Interface Enabler tool is used to enable an interface on 
     a peer switch or module when a local interface status changes.  This is to 
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

      - Script should be configured to trigger with an Event Handler.
      - The trigger action should be on the operStatus of the interface
        you are tracking.
      - The script uses passed arguments as indicated below.
      - Delay can be tweaked per environment needs.
      - Format vlan list in numerical order and individually, ie 2,502,503,606
      - Do not combine vlans in trunk list as a range
      
           event-handler <name>
             trigger on-intf <interface> operstatus
             action bash python /mnt/flash/peer_interface_enabler.py -s <interface> -v <vlan_list>
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
import sys
import syslog
import time

#----------------------------------------------------------------
# Credential Configuration section
#----------------------------------------------------------------
username = 'admin'
password = 'password'
#----------------------------------------------------------------

# Pull in interface pair and vlans to configure file from command line argument
parser = argparse.ArgumentParser(description='Remove Vlans from down interface and apply to peer')
required_arg = parser.add_argument_group('Required Arguments')
required_arg.add_argument('-s', '--switchport', dest='switchport', required=True, help='Switchport to apply configuration to', type=str)
required_arg.add_argument('-v', '--vlans', dest='vlans', required=True, help='Vlans to allow on enabled port', type=str)
args = parser.parse_args()
switchport = args.switchport
vlans = args.vlans

# Define URL for local eAPI connection. Uses local loopback
local_url_string = "https://{}:{}@{}/command-api".format(username,password,"127.0.0.1")
local_switch_req = Server( local_url_string )

# Open syslog for log creation
syslog.openlog( 'Peer Interface Enabler', 0, syslog.LOG_LOCAL4 )

def peer_setup():
  """ Sets up peer JSON-RPC instance based on MLAG Peer IP

      Args:
          none
      
      Returns:
          switch_req (instance): JSON-RPC instance for eAPI call to Peer

  """
  # Pull MLAG Peer IP for peer switch eAPI connection if fixed device.
  mlag_status = local_switch_req.runCmds( 1, ["show mlag"] )
  peer_switch = mlag_status[0]["peerAddress"]
  peer_url_string = "https://{}:{}@{}/command-api".format(username,password,peer_switch)
  switch_req = Server( peer_url_string )
  return switch_req

def config_main_port(backup_port, peer_switch_req):
  """ Configures main port to be active and removes config from backup

      Args:
          backup_port (str): Port to remove config from
          peer_switch_req (instance): eAPI instance of backup switch (self on modular)

  """
  enable_main_int = local_switch_req.runCmds( 1, ["enable", "configure", "interface " + switchport, "switchport trunk allowed vlan " + vlans, "end"] )
  disable_backup_int = peer_switch_req.runCmds( 1, ["enable", "configure", "interface " + backup_port, "switchport trunk allowed vlan none", "end"] )

def config_backup_port(backup_port, peer_switch_req):
  """ Configures backup port to be active and removes config from main

      Args:
          backup_port (str): Port to add config to
          peer_switch_req (instance): eAPI instance of backup switch (self on modular)

  """
  disable_main_int = local_switch_req.runCmds( 1, ["enable", "configure", "interface " + switchport, "switchport trunk allowed vlan none", "end"] )
  enable_backup_int = peer_switch_req.runCmds( 1, ["enable", "configure", "interface " + backup_port, "switchport trunk allowed vlan " + vlans, "end"] )

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
  main_int_status = local_switch_req.runCmds( 1, ["show interfaces " + main_port + " status"] )
  main_link_status = main_int_status[0]["interfaceStatuses"][main_port]["linkStatus"]
  # If port is up, check again in two seconds.  If it remains up, take no action.
  # This will trigger on interface up changes, so this will prevent any config changes
  # as interface comes up from being down.
  if main_link_status == "connected":
    syslog.syslog( "Main port " + main_port + " is currently up.  Waiting to check again..." )
    time.sleep(2)
    new_int_status = local_switch_req.runCmds( 1, ["show interfaces " + main_port + " status"] )
    new_link_status = new_int_status[0]["interfaceStatuses"][main_port]["linkStatus"]
    if new_link_status == "connected":
      # If primary port is connected, double check to ensure backup is configured.
      syslog.syslog( "Main port " + main_port + " is still connected.  Verifying backup port " + backup_port + " is up and configured..." )
      backup_int_status = backup_switch_req.runCmds( 1, ["show interfaces " + backup_port + " status"])
      backup_link_status = backup_int_status[0]["interfaceStatuses"][backup_port]["linkStatus"]
      if backup_link_status == "connected":
        # If backup port is up as well, verify backup port has the proper vlans configured and trunked.
        backup_trunk_status = backup_switch_req.runCmds( 1, ["show interfaces " + backup_port + " trunk"] )
        backup_vlan_list = backup_trunk_status[0]["trunks"][backup_port]["allowedVlans"]["vlanIds"]
        backup_vlan_list.sort()
        # Split supplied vlan list from arg and convert to int and compile in list for comparison.
        main_vlan_list = vlans.split(",")
        main_vlan_list = [ int(vlan) for vlan in main_vlan_list ]
        main_vlan_list.sort()
        if main_vlan_list == backup_vlan_list:
          syslog.syslog( "Backup port " + backup_port + " is both up and configured with the proper vlans.  Exiting script...")
          sys.exit()
        else:
          # If vlan list doesn't match between ports, remove config from backup and add to main.
          syslog.syslog( "Backup port " + backup_port + " is up but configured with the incorrect vlans.  Assuming misconfig and configuring main port " + main_port )
          config_main_port(backup_port, backup_switch_req)
      else:
        # If main port status is up and backup port is down, ensure configuration is in place on main port.
        syslog.syslog( "Backup port " + backup_port + " is down.  Configuring vlans on main port " + main_port + " and removing all vlans from backup port " + backup_port )
        config_main_port(backup_port, backup_switch_req)
    else:
      # If port is NOW down, remove all vlans from trunk and add vlans to backup interface.
      syslog.syslog( "Main port " + main_port + " is not connected.  Removing Vlans from local interface and adding them to backup port " + backup_port )
      config_backup_port(backup_port, backup_switch_req)
  else:
    # If port is down, remove all vlans from trunk and add vlans to backup interface.
    syslog.syslog( "Main port " + main_port + " is not connected.  Removing Vlans from local interface and adding them to backup port " + backup_port )
    config_backup_port(backup_port, backup_switch_req)

def main():
  # Determine model of device for chassis / fixed classification
  device_info = local_switch_req.runCmds( 1, ["show version"] )
  device_model = device_info[0]["modelName"]
  try:
    enable_backup_port(switchport, device_model)
  except:
    syslog.syslog( "No changes made." )
    sys.exit()

if __name__ == '__main__':
    main()