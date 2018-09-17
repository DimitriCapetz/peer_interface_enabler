# peer_interface_enabler
This is a quick fix for tracking interface state and enabling interfaces across a pair of switches.

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
