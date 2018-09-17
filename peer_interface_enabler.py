
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

       - Change username, password, peer_switch and device_interface
         variables at the top of the script to the ones appropriate 
         for your installation. The peer switch IP should be reachable
         in the default VRF.
         
   USAGE

      - Script should be configured to trigger with an Event Handler.
      - The trigger action should be on the operStatus of the interface
        you are tracking.
      
           event-handler <name>
             trigger on-intf <interface> operstatus
             action bash python /mnt/flash/peer_interface_enabler.py

        
   COMPATIBILITY
      This has been tested with EOS 4.20.x using eAPI

   LIMITATIONS
      None known
"""

from jsonrpclib import Server
import sys
import syslog
import time

#----------------------------------------------------------------
# Configuration section
#----------------------------------------------------------------
local_switch = '127.0.0.1'
peer_switch = '10.255.255.254'
username = 'admin'
password = 'password'
device_interface = "Ethernet47"
vlan_list = "2,502-503,606"
#----------------------------------------------------------------

local_url_string = "https://{}:{}@{}/command-api".format(username,password,local_switch)
local_switch_req = Server( local_url_string )
peer_url_string = "https://{}:{}@{}/command-api".format(username,password,peer_switch)
peer_switch_req = Server( peer_url_string )

# Open syslog for log creation
syslog.openlog( 'Peer Interface Enabler', 0, syslog.LOG_LOCAL4 )

# Tune delay to allow for link stabalization
syslog.syslog( "Waiting for link stabalization...")

def enable_peer():
  current_status = local_switch_req.runCmds( 1, ["show interfaces " + device_interface + " status"] )
  status = current_status[0]["interfaceStatuses"][device_interface]["linkStatus"]
  if status == "connected":
    syslog.syslog( device_interface + " is currently up.  Waiting to check again..." )
    time.sleep(2)
    updated_status = local_switch_req.runCmds( 1, ["show interfaces " + device_interface + " status"] )
    new_status = updated_status[0]["interfaceStatuses"][device_interface]["linkStatus"]
    if new_status == "connected":
      syslog.syslog( device_interface + " is still connected.  Exiting script." )
      sys.exit()
  else:
    syslog.syslog( device_interface + " is not connected.  Disabling local interface and enabling remote." )
    disable_local_int = local_switch_req.runCmds( 1, ["enable", "configure", "interface " + device_interface, "switchport trunk allowed vlan none", "end"] )
    enable_peer_int = peer_switch_req.runCmds( 1, ["enable", "configure", "interface " + device_interface, "switchport trunk allowed vlan " + vlan_list, "end"] )

def main():
  try:
    enable_peer()
  except:
    sys.exit()

if __name__ == '__main__':
    main()