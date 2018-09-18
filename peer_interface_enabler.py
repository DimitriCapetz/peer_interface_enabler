
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
     a peer switch when a local interface status changes.  This is to 
     accomadate attached devices which to not adhere to standard protocols.

   INSTALLATION
     In order to install this script:
       - Copy the script to /mnt/flash
       - Enable the Command API interface:

            management api http-commands
              no shutdown

       - Change username, password, peer_switch and switchport
         variables at the top of the script to the ones appropriate 
         for your installation. The peer switch IP should be reachable
         in the default VRF.
         
   USAGE

      - Script should be configured to trigger with an Event Handler.
      - The trigger action should be on the operStatus of the interface
        you are tracking.
      
           event-handler <name>
             trigger on-intf <interface> operstatus
             action bash python /mnt/flash/peer_interface_enabler.py -s <interface> -v <vlan_list>

        
   COMPATIBILITY
      This has been tested with EOS 4.20.x using eAPI

   LIMITATIONS
      None known
"""

import argparse
from jsonrpclib import Server
import sys
import syslog
import time

#----------------------------------------------------------------
# Configuration section
#----------------------------------------------------------------
peer_switch = '10.255.255.254'
username = 'admin'
password = 'password'
#----------------------------------------------------------------

# Pull in Interface pair to configure file from command line argument
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
  # Pull MLAG Peer IP for peer switch eAPI connection if fixed device.
  mlag_status = local_switch_req.runCmds( 1, ["show mlag"] )
  peer_switch = mlag_status[0]["peerAddress"]
  peer_url_string = "https://{}:{}@{}/command-api".format(username,password,peer_switch)
  peer_switch_req = Server( peer_url_string )

def enable_peer():
  current_status = local_switch_req.runCmds( 1, ["show interfaces " + switchport + " status"] )
  status = current_status[0]["interfaceStatuses"][switchport]["linkStatus"]
  if status == "connected":
    syslog.syslog( switchport + " is currently up.  Waiting to check again..." )
    time.sleep(2)
    updated_status = local_switch_req.runCmds( 1, ["show interfaces " + switchport + " status"] )
    new_status = updated_status[0]["interfaceStatuses"][switchport]["linkStatus"]
    if new_status == "connected":
      syslog.syslog( switchport + " is still connected.  Exiting script." )
      sys.exit()
  else:
    syslog.syslog( switchport + " is not connected.  Removing Vlans from local interface and adding them to remote." )
    disable_local_int = local_switch_req.runCmds( 1, ["enable", "configure", "interface " + switchport, "switchport trunk allowed vlan none", "end"] )
    enable_peer_int = peer_switch_req.runCmds( 1, ["enable", "configure", "interface " + switchport, "switchport trunk allowed vlan " + vlans, "end"] )

def main():
  # Determine mode of device
  device_info = local_switch_req.runCmds( 1, ["show version"] )
  device_model = device_info[0]["modelName"]
  # If device is fixed, determine peer IP.
  if device_model.startswith('DCS-7280'):
    peer_setup()
  try:
    enable_peer()
  except:
    sys.exit()

if __name__ == '__main__':
    main()