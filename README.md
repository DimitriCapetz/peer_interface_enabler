# peer_interface_enabler
The Peer Interface Enabler tool is used to enable an interface on a peer switch or module when a local interface status changes.  This is to accomadate attached devices which to not adhere to standard protocols and need active / standby to be managed by the network switch.

# Installation

In order to install this script:
- Copy the script to /mnt/flash

- Enable the Command API interface:
```
management api http-commands
   no shutdown
```

- Change username and password variables at the top of the script to the ones appropriate for your installation.
         
# Usage
- Script should be configured to trigger with a pair of Event Handlers.

- One is used for downlink detection, the other for dead peer detection.

- The trigger action should be on the operStatus of the interface you are tracking.

- The script uses passed arguments as indicated below.

- Delay can be tweaked per environment needs.

- Format vlan list in numerical order and individually, ie 2,502,503,606

- Do not combine vlans in trunk list as a range
```
event-handler Downlink_Detect
   trigger on-intf <downlink> operstatus
   action bash python /mnt/flash/peer_interface_enabler.py -s <downlink> -v <vlan_list>
   delay 1

event-handler Dead_Peer_Detect
   trigger on-intf <mlag_peer-link_port-channel> operstatus
   action bash python /mnt/flash/peer_interface_enabler.py -s <downlink> -v <vlan_list>
   delay 1
```

# Compatibility

This has been tested with EOS 4.20.x using eAPI

# Limitations

Strict logic is used to determine the backup port to be configured. If the environment does not adhere to this logic, the script will need to be adjusted.  Please note that failover time can be affected by STP convergeance.  If there are no L2 loops, STP can be disabled on vlans to speed failover time.
